import 'package:flutter/material.dart';

import '../services/api_service.dart';
import 'courses_screen.dart';
import 'dashboard_screen.dart';
import 'history_screen.dart';
import 'profile_screen.dart';
import 'scan_screen.dart';

class HomeShell extends StatefulWidget {
  final ApiService api;
  final Future<void> Function() onLogout;

  const HomeShell({required this.api, required this.onLogout, super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  int _dataVersion = 0;

  void _goToScan() => setState(() => _index = 1);

  void _attendanceRecorded() {
    setState(() {
      _dataVersion++;
      _index = 0;
    });
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      DashboardScreen(
        key: ValueKey('dashboard-$_dataVersion'),
        api: widget.api,
        onScanRequested: _goToScan,
      ),
      ScanScreen(
        api: widget.api,
        onAttendanceRecorded: _attendanceRecorded,
      ),
      CoursesScreen(key: ValueKey('courses-$_dataVersion'), api: widget.api),
      HistoryScreen(key: ValueKey('history-$_dataVersion'), api: widget.api),
      ProfileScreen(api: widget.api, onLogout: widget.onLogout),
    ];
    const titles = ['Dashboard', 'Scan QR', 'My Courses', 'Attendance History', 'Profile'];

    return Scaffold(
      appBar: AppBar(
        title: Text(titles[_index]),
        centerTitle: false,
      ),
      body: IndexedStack(index: _index, children: pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (value) => setState(() => _index = value),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'Home'),
          NavigationDestination(icon: Icon(Icons.qr_code_scanner), label: 'Scan'),
          NavigationDestination(icon: Icon(Icons.menu_book_outlined), selectedIcon: Icon(Icons.menu_book), label: 'Courses'),
          NavigationDestination(icon: Icon(Icons.history), label: 'History'),
          NavigationDestination(icon: Icon(Icons.person_outline), selectedIcon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}
