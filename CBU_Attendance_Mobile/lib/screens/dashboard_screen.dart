import 'package:flutter/material.dart';

import '../services/api_service.dart';
import '../utils/formatters.dart';
import '../widgets/app_widgets.dart';

class DashboardScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback onScanRequested;

  const DashboardScreen({required this.api, required this.onScanRequested, super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = widget.api.dashboard();
  }

  void _refresh() => setState(() => _future = widget.api.dashboard());

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

        final data = snapshot.data!;
        final user = data['user'] as Map<String, dynamic>;
        final summary = data['summary'] as Map<String, dynamic>;
        final courses = (data['courses'] as List).cast<Map<String, dynamic>>();
        final recent =
            (data['recent_attendance'] as List).cast<Map<String, dynamic>>();
        final overall = (summary['overall_percentage'] as num).toDouble();

        return RefreshIndicator(
          onRefresh: () async {
            _refresh();
            await _future;
          },
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Welcome, ${user['full_name']}',
                style: Theme.of(context)
                    .textTheme
                    .headlineSmall
                    ?.copyWith(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Text('Student ID: ${user['identifier']}'),
              const SizedBox(height: 20),
              FilledButton.icon(
                onPressed: widget.onScanRequested,
                icon: const Icon(Icons.qr_code_scanner),
                label: const Text('Scan attendance QR'),
              ),
              const SizedBox(height: 20),
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                childAspectRatio: 1.55,
                crossAxisSpacing: 10,
                mainAxisSpacing: 10,
                children: [
                  StatCard(
                    label: 'Overall attendance',
                    value: '${overall.toStringAsFixed(1)}%',
                    icon: Icons.percent,
                    warning: summary['eligible_sessions'] != 0 && overall < 75,
                  ),
                  StatCard(
                    label: 'Courses',
                    value: '${summary['courses']}',
                    icon: Icons.menu_book_outlined,
                  ),
                  StatCard(
                    label: 'Sessions attended',
                    value: '${summary['attended']}',
                    icon: Icons.check_circle_outline,
                  ),
                  StatCard(
                    label: 'Below 75%',
                    value: '${summary['low_courses']}',
                    icon: Icons.warning_amber_rounded,
                    warning: (summary['low_courses'] as num) > 0,
                  ),
                ],
              ),
              const SizedBox(height: 24),
              const SectionTitle('My courses',
                  subtitle: 'Attendance uses only closed or expired sessions.'),
              if (courses.isEmpty)
                const Card(
                    child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('You are not enrolled in any course yet.'),
                ))
              else
                ...courses.take(4).map((course) => _CourseSummary(course: course)),
              const SizedBox(height: 24),
              const SectionTitle('Recent attendance'),
              if (recent.isEmpty)
                const Card(
                    child: Padding(
                  padding: EdgeInsets.all(16),
                  child: Text('No attendance records yet.'),
                ))
              else
                ...recent.take(5).map(
                      (row) => Card(
                        child: ListTile(
                          leading: const CircleAvatar(child: Icon(Icons.check)),
                          title: Text('${row['code']} · ${row['name']}'),
                          subtitle: Text(formatDateTime(row['recorded_at'])),
                          trailing: Text(row['method'].toString().toUpperCase()),
                        ),
                      ),
                    ),
            ],
          ),
        );
      },
    );
  }
}

class _CourseSummary extends StatelessWidget {
  final Map<String, dynamic> course;

  const _CourseSummary({required this.course});

  @override
  Widget build(BuildContext context) {
    final pct = (course['percentage'] as num).toDouble();
    final low = course['low_attendance'] == true;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '${course['code']} · ${course['name']}',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.bold),
                  ),
                ),
                Chip(
                  avatar: Icon(low ? Icons.warning_amber : Icons.check_circle,
                      size: 18),
                  label: Text(low ? 'Below 75%' : 'On track'),
                ),
              ],
            ),
            if (course['lecturer_name'].toString().isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('Lecturer: ${course['lecturer_name']}'),
              ),
            const SizedBox(height: 12),
            LinearProgressIndicator(value: (pct / 100).clamp(0.0, 1.0).toDouble()),
            const SizedBox(height: 8),
            Text(
                '${pct.toStringAsFixed(1)}% · ${course['attended']} of ${course['total_sessions']} eligible sessions'),
          ],
        ),
      ),
    );
  }
}
