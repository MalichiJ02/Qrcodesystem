import 'package:flutter/material.dart';

import 'screens/home_shell.dart';
import 'screens/login_screen.dart';
import 'services/api_service.dart';
import 'services/session_store.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AttendanceApp());
}

class AttendanceApp extends StatelessWidget {
  const AttendanceApp({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF0B5CAD),
      brightness: Brightness.light,
    );
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'CBU QR Attendance',
      theme: ThemeData(
        colorScheme: colorScheme,
        useMaterial3: true,
        scaffoldBackgroundColor: const Color(0xFFF5F7FA),
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
        ),
        cardTheme: const CardThemeData(
          elevation: 0,
          margin: EdgeInsets.zero,
        ),
        filledButtonTheme: FilledButtonThemeData(
          style: FilledButton.styleFrom(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 15),
          ),
        ),
      ),
      home: const _AppGate(),
    );
  }
}

class _AppGate extends StatefulWidget {
  const _AppGate();

  @override
  State<_AppGate> createState() => _AppGateState();
}

class _AppGateState extends State<_AppGate> {
  final _store = SessionStore();
  bool _loading = true;
  bool _loggedIn = false;
  ApiService? _api;

  @override
  void initState() {
    super.initState();
    _restoreSession();
  }

  Future<void> _restoreSession() async {
    final token = await _store.getToken();
    final baseUrl = await _store.getBaseUrl();
    if (token != null && token.isNotEmpty) {
      final api = ApiService(baseUrl: baseUrl, token: token);
      try {
        await api.profile();
        _api = api;
        _loggedIn = true;
      } catch (_) {
        api.close();
        await _store.clearSession();
      }
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _handleLoggedIn() async {
    _api?.close();
    final token = await _store.getToken();
    final baseUrl = await _store.getBaseUrl();
    if (token == null) return;
    setState(() {
      _api = ApiService(baseUrl: baseUrl, token: token);
      _loggedIn = true;
    });
  }

  Future<void> _logout() async {
    final api = _api;
    if (api != null) await api.logout();
    await _store.clearSession();
    api?.close();
    if (mounted) {
      setState(() {
        _api = null;
        _loggedIn = false;
      });
    }
  }

  @override
  void dispose() {
    _api?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (!_loggedIn || _api == null) {
      return LoginScreen(onLoggedIn: _handleLoggedIn);
    }
    return HomeShell(api: _api!, onLogout: _logout);
  }
}
