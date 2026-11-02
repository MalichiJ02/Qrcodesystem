import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../widgets/app_widgets.dart';

class CoursesScreen extends StatefulWidget {
  final ApiService api;

  const CoursesScreen({required this.api, super.key});

  @override
  State<CoursesScreen> createState() => _CoursesScreenState();
}

class _CoursesScreenState extends State<CoursesScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.courses();
  }

  void _refresh() => setState(() => _future = widget.api.courses());

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
        final courses =
            (snapshot.data!['courses'] as List).cast<Map<String, dynamic>>();
        if (courses.isEmpty) {
          return const Center(child: Text('No active course enrolments.'));
        }
        return RefreshIndicator(
          onRefresh: () async {
            _refresh();
            await _future;
          },
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: courses.length,
            itemBuilder: (context, index) {
              final c = courses[index];
              final pct = (c['percentage'] as num).toDouble();
              final low = c['low_attendance'] == true;
              return Card(
                margin: const EdgeInsets.only(bottom: 12),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          CircleAvatar(child: Text(c['code'].toString().substring(0, 1))),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(c['code'].toString(),
                                    style: Theme.of(context).textTheme.titleMedium),
                                Text(c['name'].toString()),
                              ],
                            ),
                          ),
                          Text('${pct.toStringAsFixed(1)}%',
                              style: Theme.of(context)
                                  .textTheme
                                  .titleLarge
                                  ?.copyWith(fontWeight: FontWeight.bold)),
                        ],
                      ),
                      const SizedBox(height: 12),
                      LinearProgressIndicator(value: (pct / 100).clamp(0.0, 1.0).toDouble()),
                      const SizedBox(height: 8),
                      Text('${c['attended']} of ${c['total_sessions']} eligible sessions'),
                      if (c['lecturer_name'].toString().isNotEmpty)
                        Text('Lecturer: ${c['lecturer_name']}'),
                      const SizedBox(height: 8),
                      Chip(
                        avatar: Icon(low ? Icons.warning_amber : Icons.check_circle,
                            size: 18),
                        label: Text(low ? 'Below 75% threshold' : 'Attendance on track'),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }
}
