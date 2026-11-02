import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/session_store.dart';

class LoginScreen extends StatefulWidget {
  final VoidCallback onLoggedIn;

  const LoginScreen({required this.onLoggedIn, super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _studentIdController = TextEditingController();
  final _passwordController = TextEditingController();
  final _serverController = TextEditingController();
  final _store = SessionStore();

  bool _loading = false;
  bool _obscure = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadServerAddress();
  }

  Future<void> _loadServerAddress() async {
    _serverController.text = await _store.getBaseUrl();
    if (mounted) setState(() {});
  }

  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });

    final server = _serverController.text.trim();
    ApiService? api;
    try {
      api = ApiService(baseUrl: server);
      final result = await api.login(
        _studentIdController.text.trim(),
        _passwordController.text,
      );
      final user = result['user'] as Map<String, dynamic>;
      await _store.saveSession(
        token: result['token'].toString(),
        baseUrl: api.baseUrl,
        name: user['full_name'].toString(),
        identifier: user['identifier'].toString(),
      );
      widget.onLoggedIn();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(() => _error =
          'Could not reach the attendance server. Check the server address and Wi-Fi connection.');
    } finally {
      api?.close();
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _studentIdController.dispose();
    _passwordController.dispose();
    _serverController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Icon(Icons.qr_code_scanner, size: 72),
                    const SizedBox(height: 16),
                    Text(
                      'CBU QR Attendance',
                      textAlign: TextAlign.center,
                      style: Theme.of(context)
                          .textTheme
                          .headlineMedium
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Student mobile application',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 32),
                    TextFormField(
                      controller: _studentIdController,
                      textInputAction: TextInputAction.next,
                      decoration: const InputDecoration(
                        labelText: 'Student ID',
                        prefixIcon: Icon(Icons.badge_outlined),
                      ),
                      validator: (value) => value == null || value.trim().isEmpty
                          ? 'Enter your Student ID'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _passwordController,
                      obscureText: _obscure,
                      onFieldSubmitted: (_) => _login(),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        prefixIcon: const Icon(Icons.lock_outline),
                        suffixIcon: IconButton(
                          onPressed: () => setState(() => _obscure = !_obscure),
                          icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                        ),
                      ),
                      validator: (value) => value == null || value.isEmpty
                          ? 'Enter your password'
                          : null,
                    ),
                    const SizedBox(height: 16),
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('Server connection'),
                      subtitle: const Text('Use the address shown by run.sh'),
                      children: [
                        TextFormField(
                          controller: _serverController,
                          keyboardType: TextInputType.url,
                          decoration: const InputDecoration(
                            labelText: 'Server address',
                            hintText: 'https://192.168.1.20:8000',
                            prefixIcon: Icon(Icons.dns_outlined),
                          ),
                          validator: (value) => value == null || value.trim().isEmpty
                              ? 'Enter the server address'
                              : null,
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'Your phone and the laptop running the backend must be on the same network for local use.',
                        ),
                      ],
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 12),
                      Material(
                        color: Theme.of(context).colorScheme.errorContainer,
                        borderRadius: BorderRadius.circular(12),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Text(
                            _error!,
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.onErrorContainer,
                            ),
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 20),
                    FilledButton.icon(
                      onPressed: _loading ? null : _login,
                      icon: _loading
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.login),
                      label: Text(_loading ? 'Signing in...' : 'Sign in'),
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Use the Student ID provided by the administrator. This app is for student accounts only.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
