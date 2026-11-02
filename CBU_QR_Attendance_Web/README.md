# CBU QR Attendance Web Prototype

A complete web-first prototype of the approved **Digital Class Attendance System Using QR Codes**.

## Main requirements implemented
- Student/staff-number + password login
- Administrator creates student and lecturer accounts
- Administrator manually creates courses
- Administrator assigns lecturers and enrolls students
- Lecturer chooses attendance-session duration
- Session-specific, time-limited QR codes
- Server-side validation of authentication, course enrollment, session status, expiry and duplicates
- Student browser QR scanning plus manual token fallback
- Student attendance history and percentages
- Lecturer live session view, manual attendance correction with reason, reports
- 75% low-attendance threshold
- CSV and PDF report downloads
- Administrator audit log
- Responsive dark navy + electric-blue UI

## Run
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```
Open: `http://127.0.0.1:8000`

For students on another device on the same Wi-Fi, run with the laptop LAN address and open `http://YOUR_LAPTOP_IP:8000` from the phone.

## Demo accounts
- Admin: `ADM001` / `Admin123!`
- Lecturer: `STF001` / `Lecturer123!`
- Student: `20260001` / `Student123!`
- Student 2: `20260002` / `Student123!`

## Prototype notes
This is a local academic prototype. Before real deployment: use HTTPS, a production database/server, stronger session management, secrets outside source code, backups, monitoring, and institutional identity integration.
