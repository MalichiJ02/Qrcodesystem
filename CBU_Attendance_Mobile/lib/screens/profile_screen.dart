import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../services/session_store.dart';
import '../widgets/app_widgets.dart';

class ProfileScreen extends StatefulWidget {
  final ApiService api;
  final Future<void> Function() onLogout;

  const ProfileScreen({required this.api, required this.onLogout, super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  late Future<Map<String, dynamic>> _future;
  final _store = SessionStore();

  @override
  void initState() {
    super.initState();
    _future = widget.api.profile();
  }

  void _refresh() => setState(() => _future = widget.api.profile());

  Future<void> _changeServer() async {
    final controller = TextEditingController(text: await _store.getBaseUrl());
    if (!mounted) return;
    final value = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Server address'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(hintText: 'https://192.168.1.20:8000'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (value != null && value.isNotEmpty) {
      await _store.saveBaseUrl(value);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Server saved. Sign out and back in to reconnect.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return ErrorPanel(snapshot.error.toString(), onRetry: _refresh);
        }
        final user = snapshot.data!['user'] as Map<String, dynamic>;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const SizedBox(height: 8),
            CircleAvatar(
              radius: 42,
              child: Text(
                user['full_name'].toString().isEmpty
                    ? 'S'
                    : user['full_name'].toString()[0].toUpperCase(),
                style: Theme.of(context).textTheme.headlineMedium,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              user['full_name'].toString(),
              textAlign: TextAlign.center,
              style: Theme.of(context)
                  .textTheme
                  .headlineSmall
                  ?.copyWith(fontWeight: FontWeight.bold),
            ),
            Text(
              user['identifier'].toString(),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            Card(
              child: Column(
                children: [
                  ListTile(
                    leading: const Icon(Icons.verified_user_outlined),
                    title: const Text('Account type'),
                    subtitle: Text(user['role'].toString().toUpperCase()),
                  ),
                  const Divider(height: 1),
                  const ListTile(
                    leading: Icon(Icons.warning_amber_outlined),
                    title: Text('Low-attendance threshold'),
                    subtitle: Text('75%'),
                  ),
                  const Divider(height: 1),
                  ListTile(
                    leading: const Icon(Icons.dns_outlined),
                    title: const Text('Change server address'),
                    subtitle: const Text('Use when the backend laptop IP changes'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: _changeServer,
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            FilledButton.tonalIcon(
              onPressed: widget.onLogout,
              icon: const Icon(Icons.logout),
              label: const Text('Sign out'),
            ),
          ],
        );
      },
    );
  }
}
