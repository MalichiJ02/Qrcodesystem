import 'package:intl/intl.dart';

String formatDateTime(dynamic value) {
  if (value == null) return '—';
  try {
    final date = DateTime.parse(value.toString()).toLocal();
    return DateFormat('dd MMM yyyy, HH:mm').format(date);
  } catch (_) {
    return value.toString();
  }
}

String extractAttendanceToken(String raw) {
  final text = raw.trim();
  if (text.isEmpty) return '';
  try {
    final uri = Uri.parse(text);
    final token = uri.queryParameters['token'];
    if (token != null && token.trim().isNotEmpty) return token.trim();
  } catch (_) {}
  return text;
}
