# Implementation Notes

## Agreed operating rules
1. Users sign in using student/staff number and password.
2. Administrators create all student and lecturer accounts.
3. Administrators manually create courses, assign lecturers and enroll students.
4. Lecturers choose the attendance-session duration.
5. Students below 75% attendance are flagged as low attendance.
6. Student web clients support camera QR scanning and manual token fallback.
7. Course reports can be viewed in the browser and downloaded as CSV or PDF.

## Attendance workflow
Lecturer login -> assigned course -> create time-limited attendance session -> display QR -> authenticated student scans -> server validates token/session/time/enrollment/duplicate -> attendance saved -> student confirmation -> lecturer sees record -> close/expire session -> report.

## Database tables
users, courses, enrollments, attendance_sessions, attendance_records, audit_log.

## Deliberate scope boundaries
No biometrics, no CBU SIS integration, no claim that QR alone proves physical presence, no GPS requirement in the current web prototype.
