# CBU QR Attendance - Combined Web + Mobile Build

This package contains:

- `CBU_QR_Attendance_Web/` - existing FastAPI web application for Admin and Lecturer, now with student mobile JSON API endpoints.
- `CBU_Attendance_Mobile/` - Flutter Android student application.
- `QRcode data/` - prepared CSV import data included in the supplied project.

## Run backend

```bash
cd CBU_QR_Attendance_Web
./run.sh
```

Keep the backend terminal open and note the network URL it prints.

## Run Android student app

In another terminal:

```bash
cd CBU_Attendance_Mobile
./run_mobile.sh
```

Enter the backend network URL on the student login screen.

## Mobile API added to FastAPI

- `GET /api/health`
- `POST /api/student/login`
- `GET /api/student/profile`
- `GET /api/student/dashboard`
- `GET /api/student/courses`
- `GET /api/student/attendance`
- `POST /api/student/checkin`
- `POST /api/student/logout`

The existing web routes and database remain intact.
