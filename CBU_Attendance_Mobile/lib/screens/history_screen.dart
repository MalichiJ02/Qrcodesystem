import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_widgets.dart';

class HistoryScreen extends StatefulWidget {
  final ApiService api;

  const HistoryScreen({required this.api, super.key});

  @override
  State<HistoryScreen> createState() => _HistoryScreenState();
}

class _HistoryScreenState extends State<HistoryScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.attendance(limit: 200);
  }

  void _refresh() => setState(() => _future = widget.api.attendance(limit: 200));

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
        final rows =
            (snapshot.data!['attendance'] as List).cast<Map<String, dynamic>>();
        if (rows.isEmpty) {
          return const Center(child: Text('No attendance history yet.'));
        }
        return RefreshIndicator(
          onRefresh: () async {
            _refresh();
            await _future;
          },
          child: ListView.separated(
            padding: const EdgeInsets.all(16),
            itemCount: rows.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (context, index) {
              final r = rows[index];
              return Card(
                child: ListTile(
                  leading: const CircleAvatar(child: Icon(Icons.done_all)),
                  title: Text('${r['code']} · ${r['name']}'),
                  subtitle: Text(
                    '${formatDateTime(r['recorded_at'])}\nMethod: ${r['method']}',
                  ),
                  isThreeLine: true,
                  trailing: Chip(label: Text(r['status'].toString().toUpperCase())),
                ),
              );
            },
          ),
        );
      },
    );
  }
}
