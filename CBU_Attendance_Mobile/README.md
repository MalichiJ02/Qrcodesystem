# CBU QR Attendance - Student Mobile App

Flutter Android client for the existing CBU QR Attendance FastAPI backend.

## Included student features

- Student ID + password login
- Configurable backend server address
- Student dashboard
- Overall attendance percentage
- 75% low-attendance warnings
- Enrolled courses and lecturer names
- Per-course attendance percentage
- QR camera scanning
- Existing QR URL/token extraction
- Server-side validation of active/expired/closed sessions
- Duplicate attendance prevention
- Enrolment validation
- Manual token fallback
- Full attendance history
- Profile
- Logout

The app does **not** create a second attendance database. All data is stored in the existing FastAPI/SQLite backend.

## Fedora/Linux: fastest start

1. Start the backend first from `../CBU_QR_Attendance_Web`:

   ```bash
   ./run.sh
   ```

2. Note the phone/server address printed by the backend, for example:

   ```text
   https://172.19.15.179:8000
   ```

3. Connect the Android phone by USB and enable USB debugging, or use an Android emulator.

4. In this mobile folder run:

   ```bash
   ./run_mobile.sh
   ```

5. On the mobile login screen enter:
   - Student ID
   - Student password
   - Backend server address from `run.sh`

For the imported demonstration accounts the temporary password is `Test1234` unless changed by the administrator.

## Windows

Install Flutter + Android Studio first, then double-click:

```text
run_mobile.bat
```

## Build an APK

After Android platform setup:

```bash
flutter pub get
flutter build apk --release
```

APK output:

```text
build/app/outputs/flutter-apk/app-release.apk
```

## Local HTTPS note

The API client accepts the locally generated development certificate so the student app can communicate with the laptop during the academic prototype/demo. Do not keep permissive certificate validation for a public production deployment. Use a trusted TLS certificate in production.

## Architecture

```text
Admin Browser ───────┐
Lecturer Browser ────┼── FastAPI ── SQLite
Student Flutter App ─┘
```

Admin and Lecturer remain web-based. Students use this mobile app.
