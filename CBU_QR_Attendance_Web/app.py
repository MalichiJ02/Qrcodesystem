from __future__ import annotations
import base64, csv, hashlib, hmac, io, os, secrets, sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import qrcode
from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "data" / "attendance.db"
APP_SECRET = os.getenv("APP_SECRET", "dev-change-this-secret")
LOW_THRESHOLD = 75.0


class StudentLoginPayload(BaseModel):
    identifier: str
    password: str


class StudentCheckinPayload(BaseModel):
    token: str

app = FastAPI(title="CBU QR Attendance")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()

def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return base64.b64encode(salt + dk).decode()

def verify_password(password: str, stored: str) -> bool:
    raw = base64.b64decode(stored)
    salt, expected = raw[:16], raw[16:]
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return hmac.compare_digest(actual, expected)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          identifier TEXT UNIQUE NOT NULL,
          full_name TEXT NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL CHECK(role IN ('student','lecturer','admin')),
          active INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS courses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          code TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          lecturer_id INTEGER,
          created_at TEXT NOT NULL,
          FOREIGN KEY(lecturer_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS enrollments(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          student_id INTEGER NOT NULL,
          course_id INTEGER NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          UNIQUE(student_id, course_id),
          FOREIGN KEY(student_id) REFERENCES users(id),
          FOREIGN KEY(course_id) REFERENCES courses(id)
        );
        CREATE TABLE IF NOT EXISTS attendance_sessions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          course_id INTEGER NOT NULL,
          lecturer_id INTEGER NOT NULL,
          started_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          closed_at TEXT,
          token_hash TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active',
          created_at TEXT NOT NULL,
          FOREIGN KEY(course_id) REFERENCES courses(id),
          FOREIGN KEY(lecturer_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS attendance_records(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER NOT NULL,
          student_id INTEGER NOT NULL,
          recorded_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'present',
          method TEXT NOT NULL DEFAULT 'qr',
          corrected_by INTEGER,
          correction_reason TEXT,
          UNIQUE(session_id, student_id),
          FOREIGN KEY(session_id) REFERENCES attendance_sessions(id),
          FOREIGN KEY(student_id) REFERENCES users(id),
          FOREIGN KEY(corrected_by) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS audit_log(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          actor_user_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          entity_type TEXT NOT NULL,
          entity_id INTEGER,
          reason TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY(actor_user_id) REFERENCES users(id)
        );
        """)
        if c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"] == 0:
            t = iso(now_utc())
            users = [
                ("ADM001","System Administrator",hash_password("Admin123!"),"admin",t),
                ("STF001","Dr. Demo Lecturer",hash_password("Lecturer123!"),"lecturer",t),
                ("20260001","Demo Student One",hash_password("Student123!"),"student",t),
                ("20260002","Demo Student Two",hash_password("Student123!"),"student",t),
            ]
            c.executemany("INSERT INTO users(identifier,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)", users)
            lec = c.execute("SELECT id FROM users WHERE identifier='STF001'").fetchone()[0]
            s1 = c.execute("SELECT id FROM users WHERE identifier='20260001'").fetchone()[0]
            s2 = c.execute("SELECT id FROM users WHERE identifier='20260002'").fetchone()[0]
            c.execute("INSERT INTO courses(code,name,lecturer_id,created_at) VALUES(?,?,?,?)",("CS301","Systems and Project Management",lec,t))
            course = c.execute("SELECT id FROM courses WHERE code='CS301'").fetchone()[0]
            c.executemany("INSERT INTO enrollments(student_id,course_id) VALUES(?,?)",[(s1,course),(s2,course)])

init_db()


def sign_session(uid: int) -> str:
    payload = f"{uid}:{int(datetime.now().timestamp())}"
    sig = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}:{sig}".encode()).decode()

def read_session(token: str) -> Optional[int]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        uid, ts, sig = raw.split(":",2)
        payload = f"{uid}:{ts}"
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected): return None
        if datetime.now().timestamp() - int(ts) > 60*60*12: return None
        return int(uid)
    except Exception:
        return None

def current_user(request: Request):
    tok = request.cookies.get("attendance_session")
    uid = read_session(tok) if tok else None
    if not uid: return None
    with db() as c:
        return c.execute("SELECT id,identifier,full_name,role,active FROM users WHERE id=? AND active=1",(uid,)).fetchone()

def require_user(request: Request, roles=None):
    u = current_user(request)
    if not u: raise HTTPException(status_code=401)
    if roles and u["role"] not in roles: raise HTTPException(status_code=403)
    return u

def current_api_user(request: Request):
    auth = request.headers.get("Authorization", "").strip()
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    uid = read_session(token) if token else None
    if not uid:
        return None
    with db() as c:
        return c.execute(
            "SELECT id,identifier,full_name,role,active FROM users WHERE id=? AND active=1",
            (uid,),
        ).fetchone()


def require_api_student(request: Request):
    u = current_api_user(request)
    if not u:
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    if u["role"] != "student":
        raise HTTPException(status_code=403, detail="Student account required.")
    return u

def redirect_login():
    return RedirectResponse("/login", status_code=303)

def add_audit(c, actor, action, entity_type, entity_id=None, reason=None):
    c.execute("INSERT INTO audit_log(actor_user_id,action,entity_type,entity_id,reason,created_at) VALUES(?,?,?,?,?,?)",
              (actor,action,entity_type,entity_id,reason,iso(now_utc())))

def expire_sessions(c):
    n = iso(now_utc())
    c.execute("UPDATE attendance_sessions SET status='expired' WHERE status='active' AND expires_at < ?",(n,))


def render(request, name, **ctx):
    ctx.update({
        "request": request,
        "user": current_user(request),
        "low_threshold": LOW_THRESHOLD
    })

    return templates.TemplateResponse(
        request=request,
        name=name,
        context=ctx
    )

@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    u = current_user(request)
    if not u: return RedirectResponse("/login",303)
    return RedirectResponse(f"/{u['role']}",303)

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str=""):
    return render(request,"login.html",error=error)

@app.post("/login")
def login(request: Request, identifier: str=Form(...), password: str=Form(...)):
    with db() as c:
        u = c.execute(
            "SELECT * FROM users WHERE identifier=? AND active=1",
            (identifier.strip(),)
        ).fetchone()

    ajax_login = request.headers.get("X-Login-Request") == "fetch"

    if not u or not verify_password(password, u["password_hash"]):
        if ajax_login:
            return JSONResponse(
                {"success": False, "message": "Invalid ID or password"},
                status_code=401
            )
        return RedirectResponse("/login?error=Invalid+ID+or+password", 303)

    # The web portal is reserved for lecturers and administrators.
    # Student accounts are retained for authentication through the mobile app.
    if u["role"] == "student":
        if ajax_login:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Students must use the mobile attendance app."
                },
                status_code=403
            )
        return RedirectResponse(
            "/login?error=Students+must+use+the+mobile+attendance+app",
            303
        )

    if ajax_login:
        r = JSONResponse({
            "success": True,
            "message": "Login successful",
            "redirect": f"/{u['role']}"
        })
    else:
        r = RedirectResponse(f"/{u['role']}", 303)

    r.set_cookie(
        "attendance_session",
        sign_session(u["id"]),
        httponly=True,
        samesite="lax",
        max_age=43200
    )
    return r

@app.post("/logout")
def logout():
    r=RedirectResponse("/login",303); r.delete_cookie("attendance_session"); return r

@app.get("/student", response_class=HTMLResponse)
def student_dashboard(request: Request):
    try: u=require_user(request,["student"])
    except HTTPException: return redirect_login()
    with db() as c:
        expire_sessions(c)
        courses=c.execute("""SELECT c.*,
          (SELECT COUNT(*) FROM attendance_sessions s WHERE s.course_id=c.id AND s.status IN ('closed','expired')) total_sessions,
          (SELECT COUNT(*) FROM attendance_records ar JOIN attendance_sessions s2 ON s2.id=ar.session_id WHERE ar.student_id=? AND s2.course_id=c.id AND s2.status IN ('closed','expired')) attended
          FROM courses c JOIN enrollments e ON e.course_id=c.id WHERE e.student_id=? AND e.status='active' ORDER BY c.code""",(u['id'],u['id'])).fetchall()
        history=c.execute("""SELECT ar.recorded_at,ar.method,ar.status,c.code,c.name,s.started_at
          FROM attendance_records ar JOIN attendance_sessions s ON s.id=ar.session_id JOIN courses c ON c.id=s.course_id
          WHERE ar.student_id=? ORDER BY ar.recorded_at DESC LIMIT 50""",(u['id'],)).fetchall()
    return render(request,"student.html",courses=courses,history=history)

@app.get("/student/checkin", response_class=HTMLResponse)
def checkin_page(request: Request, token: str=""):
    try: require_user(request,["student"])
    except HTTPException:
        nexturl = "/student/checkin?token="+token
        return RedirectResponse("/login?error=Please+login+before+recording+attendance",303)
    return render(request,"checkin.html",token=token,message="",success=False)

@app.post("/student/checkin", response_class=HTMLResponse)
def checkin(request: Request, token: str=Form(...)):
    try: u=require_user(request,["student"])
    except HTTPException: return redirect_login()
    message=""; success=False
    with db() as c:
        expire_sessions(c)
        s=c.execute("SELECT s.*,c.code,c.name FROM attendance_sessions s JOIN courses c ON c.id=s.course_id WHERE s.token_hash=?",(token_hash(token.strip()),)).fetchone()
        if not s: message="Invalid QR code or attendance token."
        elif s["status"]!="active": message="This attendance session is no longer active."
        elif parse_dt(s["expires_at"]) < now_utc(): message="This QR code has expired."
        elif not c.execute("SELECT 1 FROM enrollments WHERE student_id=? AND course_id=? AND status='active'",(u['id'],s['course_id'])).fetchone(): message="You are not enrolled in this course."
        elif c.execute("SELECT 1 FROM attendance_records WHERE session_id=? AND student_id=?",(s['id'],u['id'])).fetchone(): message="Your attendance has already been recorded for this session."
        else:
            c.execute("INSERT INTO attendance_records(session_id,student_id,recorded_at,status,method) VALUES(?,?,?,?,?)",(s['id'],u['id'],iso(now_utc()),'present','qr'))
            message=f"Attendance recorded for {s['code']} - {s['name']}."; success=True
    return render(request,"checkin.html",token="",message=message,success=success)

@app.get("/lecturer", response_class=HTMLResponse)
def lecturer_dashboard(request: Request):
    try: u=require_user(request,["lecturer"])
    except HTTPException: return redirect_login()
    with db() as c:
        expire_sessions(c)
        courses=c.execute("""SELECT c.*, (SELECT COUNT(*) FROM enrollments e WHERE e.course_id=c.id AND e.status='active') enrolled
          FROM courses c WHERE c.lecturer_id=? ORDER BY c.code""",(u['id'],)).fetchall()
        sessions=c.execute("""SELECT s.*,c.code,c.name,(SELECT COUNT(*) FROM attendance_records ar WHERE ar.session_id=s.id) present
          FROM attendance_sessions s JOIN courses c ON c.id=s.course_id WHERE s.lecturer_id=? ORDER BY s.id DESC LIMIT 20""",(u['id'],)).fetchall()
    return render(request,"lecturer.html",courses=courses,sessions=sessions)

@app.post("/lecturer/session/create")
def create_session(request: Request, course_id: int=Form(...), duration: int=Form(...)):
    try:u=require_user(request,["lecturer"])
    except HTTPException:return redirect_login()
    duration=max(1,min(duration,180))
    token=secrets.token_urlsafe(24); start=now_utc(); exp=start+timedelta(minutes=duration)
    with db() as c:
        course=c.execute("SELECT * FROM courses WHERE id=? AND lecturer_id=?",(course_id,u['id'])).fetchone()
        if not course: raise HTTPException(403)
        c.execute("INSERT INTO attendance_sessions(course_id,lecturer_id,started_at,expires_at,token_hash,status,created_at) VALUES(?,?,?,?,?,?,?)",
                  (course_id,u['id'],iso(start),iso(exp),token_hash(token),'active',iso(start)))
        sid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
        add_audit(c,u['id'],'CREATE_SESSION','attendance_session',sid,f'{duration} minutes')
    return RedirectResponse(f"/lecturer/session/{sid}?token={token}",303)

@app.get("/lecturer/session/{sid}", response_class=HTMLResponse)
def session_view(request: Request,sid:int,token:str=""):
    try:u=require_user(request,["lecturer"])
    except HTTPException:return redirect_login()
    with db() as c:
        expire_sessions(c)
        s=c.execute("SELECT s.*,c.code,c.name FROM attendance_sessions s JOIN courses c ON c.id=s.course_id WHERE s.id=? AND s.lecturer_id=?",(sid,u['id'])).fetchone()
        if not s: raise HTTPException(404)
        records=c.execute("""SELECT ar.*,u.identifier,u.full_name FROM attendance_records ar JOIN users u ON u.id=ar.student_id WHERE ar.session_id=? ORDER BY ar.recorded_at""",(sid,)).fetchall()
        students=c.execute("""SELECT u.id,u.identifier,u.full_name FROM enrollments e JOIN users u ON u.id=e.student_id WHERE e.course_id=? AND e.status='active' ORDER BY u.full_name""",(s['course_id'],)).fetchall()
    qr_data=""
    if token and s['status']=='active':
        url=str(request.base_url).rstrip('/')+f"/student/checkin?token={token}"
        img=qrcode.make(url); b=io.BytesIO(); img.save(b,format='PNG'); qr_data=base64.b64encode(b.getvalue()).decode()
    return render(request,"session.html",s=s,records=records,students=students,token=token,qr_data=qr_data)

@app.post("/lecturer/session/{sid}/close")
def close_session(request: Request,sid:int):
    try:u=require_user(request,["lecturer"])
    except HTTPException:return redirect_login()
    with db() as c:
        row=c.execute("SELECT id FROM attendance_sessions WHERE id=? AND lecturer_id=?",(sid,u['id'])).fetchone()
        if not row: raise HTTPException(404)
        c.execute("UPDATE attendance_sessions SET status='closed',closed_at=? WHERE id=?",(iso(now_utc()),sid))
        add_audit(c,u['id'],'CLOSE_SESSION','attendance_session',sid)
    return RedirectResponse(f"/lecturer/session/{sid}",303)

@app.post("/lecturer/session/{sid}/manual")
def manual_attendance(request: Request,sid:int,student_id:int=Form(...),reason:str=Form(...)):
    try:u=require_user(request,["lecturer"])
    except HTTPException:return redirect_login()
    if not reason.strip(): return RedirectResponse(f"/lecturer/session/{sid}?error=Reason+required",303)
    with db() as c:
        s=c.execute("SELECT * FROM attendance_sessions WHERE id=? AND lecturer_id=?",(sid,u['id'])).fetchone()
        if not s: raise HTTPException(404)
        if not c.execute("SELECT 1 FROM enrollments WHERE student_id=? AND course_id=? AND status='active'",(student_id,s['course_id'])).fetchone(): raise HTTPException(400)
        existing=c.execute("SELECT id FROM attendance_records WHERE session_id=? AND student_id=?",(sid,student_id)).fetchone()
        if existing:
            c.execute("UPDATE attendance_records SET status='present',method='manual',corrected_by=?,correction_reason=?,recorded_at=? WHERE id=?",
                      (u['id'],reason.strip(),iso(now_utc()),existing['id']))
            rid=existing['id']; action='CORRECT_ATTENDANCE'
        else:
            c.execute("INSERT INTO attendance_records(session_id,student_id,recorded_at,status,method,corrected_by,correction_reason) VALUES(?,?,?,?,?,?,?)",
                      (sid,student_id,iso(now_utc()),'present','manual',u['id'],reason.strip()))
            rid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; action='MANUAL_ATTENDANCE'
        add_audit(c,u['id'],action,'attendance_record',rid,reason.strip())
    return RedirectResponse(f"/lecturer/session/{sid}",303)


def report_rows(c,course_id:int):
    students=c.execute("""SELECT u.id,u.identifier,u.full_name FROM enrollments e JOIN users u ON u.id=e.student_id WHERE e.course_id=? AND e.status='active' ORDER BY u.full_name""",(course_id,)).fetchall()
    total=c.execute("SELECT COUNT(*) n FROM attendance_sessions WHERE course_id=? AND status IN ('closed','expired')",(course_id,)).fetchone()['n']
    out=[]
    for st in students:
        attended=c.execute("""SELECT COUNT(*) n FROM attendance_records ar JOIN attendance_sessions s ON s.id=ar.session_id
            WHERE ar.student_id=? AND s.course_id=? AND s.status IN ('closed','expired') AND ar.status='present'""",(st['id'],course_id)).fetchone()['n']
        pct=round(attended/total*100,1) if total else 0.0
        out.append({"identifier":st['identifier'],"full_name":st['full_name'],"attended":attended,"total":total,"percentage":pct,"low":pct<LOW_THRESHOLD if total else False})
    return out

@app.get("/lecturer/course/{course_id}/report", response_class=HTMLResponse)
def course_report(request:Request,course_id:int):
    try:u=require_user(request,["lecturer","admin"])
    except HTTPException:return redirect_login()
    with db() as c:
        course=c.execute("SELECT * FROM courses WHERE id=?",(course_id,)).fetchone()
        if not course: raise HTTPException(404)
        if u['role']=='lecturer' and course['lecturer_id']!=u['id']: raise HTTPException(403)
        rows=report_rows(c,course_id)
    return render(request,"report.html",course=course,rows=rows)

@app.get("/lecturer/course/{course_id}/report.csv")
def report_csv(request:Request,course_id:int):
    try:u=require_user(request,["lecturer","admin"])
    except HTTPException:return redirect_login()
    with db() as c:
        course=c.execute("SELECT * FROM courses WHERE id=?",(course_id,)).fetchone()
        if not course: raise HTTPException(404)
        if u['role']=='lecturer' and course['lecturer_id']!=u['id']: raise HTTPException(403)
        rows=report_rows(c,course_id)
    sio=io.StringIO(); w=csv.writer(sio); w.writerow(["Student Number","Student Name","Present","Eligible Sessions","Percentage","Low Attendance"])
    for r in rows:w.writerow([r['identifier'],r['full_name'],r['attended'],r['total'],r['percentage'],"Yes" if r['low'] else "No"])
    return Response(sio.getvalue(),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={course['code']}_attendance.csv"})

@app.get("/lecturer/course/{course_id}/report.pdf")
def report_pdf(request:Request,course_id:int):
    try:u=require_user(request,["lecturer","admin"])
    except HTTPException:return redirect_login()
    with db() as c:
        course=c.execute("SELECT * FROM courses WHERE id=?",(course_id,)).fetchone()
        if not course: raise HTTPException(404)
        if u['role']=='lecturer' and course['lecturer_id']!=u['id']: raise HTTPException(403)
        rows=report_rows(c,course_id)
    b=io.BytesIO(); doc=SimpleDocTemplate(b,pagesize=A4); styles=getSampleStyleSheet(); story=[Paragraph(f"Attendance Report: {course['code']} - {course['name']}",styles['Title']),Spacer(1,12)]
    data=[["Student No.","Name","Present","Sessions","%","Low"]]+[[r['identifier'],r['full_name'],r['attended'],r['total'],f"{r['percentage']}%","Yes" if r['low'] else "No"] for r in rows]
    tbl=Table(data,repeatRows=1,colWidths=[70,170,55,55,45,45]); tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#0B5FFF')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.5,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(tbl); doc.build(story); b.seek(0)
    return StreamingResponse(b,media_type="application/pdf",headers={"Content-Disposition":f"attachment; filename={course['code']}_attendance.pdf"})

def admin_url(message: str = "", error: str = "") -> str:
    params = {}
    if message: params["message"] = message
    if error: params["error"] = error
    return "/admin" + (f"?{urlencode(params)}" if params else "")

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request:Request, message:str="", error:str=""):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    with db() as c:
        users=c.execute("SELECT id,identifier,full_name,role,active FROM users ORDER BY role,full_name").fetchall()
        courses=c.execute("""SELECT c.*,u.full_name lecturer_name,u.identifier lecturer_identifier,
          (SELECT COUNT(*) FROM enrollments e WHERE e.course_id=c.id AND e.status='active') enrolled
          FROM courses c LEFT JOIN users u ON u.id=c.lecturer_id ORDER BY c.code""").fetchall()
        audit=c.execute("""SELECT a.*,u.identifier,u.full_name FROM audit_log a JOIN users u ON u.id=a.actor_user_id ORDER BY a.id DESC LIMIT 50""").fetchall()
        lecturers=c.execute("SELECT id,identifier,full_name FROM users WHERE role='lecturer' AND active=1 ORDER BY full_name").fetchall()
        students=c.execute("SELECT id,identifier,full_name FROM users WHERE role='student' AND active=1 ORDER BY full_name").fetchall()
        enrollments=c.execute("""SELECT e.id,e.student_id,e.course_id,e.status,s.identifier student_identifier,s.full_name student_name,c.code course_code,c.name course_name
          FROM enrollments e JOIN users s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id ORDER BY c.code,s.full_name""").fetchall()
    stats = {
        "students": sum(1 for x in users if x["role"] == "student" and x["active"]),
        "lecturers": sum(1 for x in users if x["role"] == "lecturer" and x["active"]),
        "courses": len(courses),
        "enrollments": sum(1 for x in enrollments if x["status"] == "active"),
    }

    return render(
        request,
        "admin.html",
        users=users,
        courses=courses,
        audit=audit,
        lecturers=lecturers,
        students=students,
        enrollments=enrollments,
        stats=stats,
        message=message,
        error=error
    )


@app.post("/admin/import/students")
async def admin_import_students(
    request: Request,
    csv_file: UploadFile = File(...)
):
    try:
        u = require_user(request, ["admin"])
    except HTTPException:
        return redirect_login()

    if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
        return RedirectResponse(
            admin_url(error="Please upload a CSV file."),
            303
        )

    try:
        raw = await csv_file.read()
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except (UnicodeDecodeError, csv.Error):
        return RedirectResponse(
            admin_url(error="The student CSV file could not be read."),
            303
        )

    required = {"student_number", "full_name", "password"}

    if not reader.fieldnames or not required.issubset(
        {x.strip() for x in reader.fieldnames if x}
    ):
        return RedirectResponse(
            admin_url(
                error="Student CSV must contain: student_number, full_name, password."
            ),
            303
        )

    created = 0
    skipped = 0
    errors = []

    with db() as c:
        for row_number, row in enumerate(reader, start=2):
            identifier = (row.get("student_number") or "").strip().upper()
            full_name = (row.get("full_name") or "").strip()
            password = (row.get("password") or "").strip()

            if not identifier and not full_name and not password:
                continue

            if not identifier or not full_name:
                errors.append(f"Row {row_number}: missing student number or full name.")
                continue

            if len(password) < 8:
                errors.append(
                    f"Row {row_number} ({identifier}): password must contain at least 8 characters."
                )
                continue

            existing = c.execute(
                "SELECT id FROM users WHERE identifier=?",
                (identifier,)
            ).fetchone()

            if existing:
                skipped += 1
                continue

            try:
                c.execute(
                    """INSERT INTO users
                       (identifier,full_name,password_hash,role,created_at)
                       VALUES(?,?,?,?,?)""",
                    (
                        identifier,
                        full_name,
                        hash_password(password),
                        "student",
                        iso(now_utc())
                    )
                )

                uid = c.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]

                add_audit(
                    c,
                    u["id"],
                    "IMPORT_STUDENT",
                    "user",
                    uid,
                    f"{identifier} - {full_name}"
                )

                created += 1

            except sqlite3.IntegrityError:
                skipped += 1

    if errors:
        preview = "; ".join(errors[:3])
        if len(errors) > 3:
            preview += f"; plus {len(errors) - 3} more error(s)"

        return RedirectResponse(
            admin_url(
                message=f"Imported {created} student(s); skipped {skipped}.",
                error=preview
            ),
            303
        )

    return RedirectResponse(
        admin_url(
            message=f"Student import complete: {created} created, {skipped} duplicate(s) skipped."
        ),
        303
    )


@app.post("/admin/import/lecturers")
async def admin_import_lecturers(
    request: Request,
    csv_file: UploadFile = File(...)
):
    try:
        u = require_user(request, ["admin"])
    except HTTPException:
        return redirect_login()

    if not csv_file.filename or not csv_file.filename.lower().endswith(".csv"):
        return RedirectResponse(
            admin_url(error="Please upload a CSV file."),
            303
        )

    try:
        raw = await csv_file.read()
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
    except (UnicodeDecodeError, csv.Error):
        return RedirectResponse(
            admin_url(error="The lecturer CSV file could not be read."),
            303
        )

    required = {"staff_number", "full_name", "password"}

    if not reader.fieldnames or not required.issubset(
        {x.strip() for x in reader.fieldnames if x}
    ):
        return RedirectResponse(
            admin_url(
                error="Lecturer CSV must contain: staff_number, full_name, password."
            ),
            303
        )

    created = 0
    skipped = 0
    errors = []

    with db() as c:
        for row_number, row in enumerate(reader, start=2):
            identifier = (row.get("staff_number") or "").strip().upper()
            full_name = (row.get("full_name") or "").strip()
            password = (row.get("password") or "").strip()

            if not identifier and not full_name and not password:
                continue

            if not identifier or not full_name:
                errors.append(
                    f"Row {row_number}: missing staff number or full name."
                )
                continue

            if len(password) < 8:
                errors.append(
                    f"Row {row_number} ({identifier}): password must contain at least 8 characters."
                )
                continue

            existing = c.execute(
                "SELECT id FROM users WHERE identifier=?",
                (identifier,)
            ).fetchone()

            if existing:
                skipped += 1
                continue

            try:
                c.execute(
                    """INSERT INTO users
                       (identifier,full_name,password_hash,role,created_at)
                       VALUES(?,?,?,?,?)""",
                    (
                        identifier,
                        full_name,
                        hash_password(password),
                        "lecturer",
                        iso(now_utc())
                    )
                )

                uid = c.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]

                add_audit(
                    c,
                    u["id"],
                    "IMPORT_LECTURER",
                    "user",
                    uid,
                    f"{identifier} - {full_name}"
                )

                created += 1

            except sqlite3.IntegrityError:
                skipped += 1

    if errors:
        preview = "; ".join(errors[:3])
        if len(errors) > 3:
            preview += f"; plus {len(errors) - 3} more error(s)"

        return RedirectResponse(
            admin_url(
                message=f"Imported {created} lecturer(s); skipped {skipped}.",
                error=preview
            ),
            303
        )

    return RedirectResponse(
        admin_url(
            message=f"Lecturer import complete: {created} created, {skipped} duplicate(s) skipped."
        ),
        303
    )


@app.post("/admin/user/create")
def admin_create_user(request:Request,identifier:str=Form(...),full_name:str=Form(...),role:str=Form(...),password:str=Form(...)):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    identifier=identifier.strip().upper(); full_name=full_name.strip(); role=role.strip().lower()
    if not identifier or not full_name: return RedirectResponse(admin_url(error="Student/staff number and full name are required."),303)
    if role not in {'student','lecturer','admin'}: return RedirectResponse(admin_url(error="Invalid account role."),303)
    if len(password)<8: return RedirectResponse(admin_url(error="Password must contain at least 8 characters."),303)
    try:
        with db() as c:
            c.execute("INSERT INTO users(identifier,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",(identifier,full_name,hash_password(password),role,iso(now_utc())))
            uid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; add_audit(c,u['id'],'CREATE_USER','user',uid,role)
    except sqlite3.IntegrityError:
        return RedirectResponse(admin_url(error=f"An account with ID {identifier} already exists."),303)
    return RedirectResponse(admin_url(message=f"Account {identifier} created successfully."),303)

@app.post("/admin/user/{user_id}/edit")
def admin_edit_user(request:Request,user_id:int,identifier:str=Form(...),full_name:str=Form(...)):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    identifier=identifier.strip().upper(); full_name=full_name.strip()
    if not identifier or not full_name: return RedirectResponse(admin_url(error="Student/staff number and full name are required."),303)
    try:
        with db() as c:
            target=c.execute("SELECT id,identifier,full_name FROM users WHERE id=?",(user_id,)).fetchone()
            if not target: return RedirectResponse(admin_url(error="User account not found."),303)
            c.execute("UPDATE users SET identifier=?,full_name=? WHERE id=?",(identifier,full_name,user_id))
            add_audit(c,u['id'],'EDIT_USER','user',user_id,f"{target['identifier']} -> {identifier}; {target['full_name']} -> {full_name}")
    except sqlite3.IntegrityError:
        return RedirectResponse(admin_url(error=f"Another account already uses ID {identifier}."),303)
    return RedirectResponse(admin_url(message=f"Account {identifier} updated successfully."),303)

@app.post("/admin/user/{user_id}/toggle")
def admin_toggle_user(request:Request,user_id:int):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    if user_id==u['id']: return RedirectResponse(admin_url(error="You cannot disable your own administrator account."),303)
    with db() as c:
        target=c.execute("SELECT id,identifier,active FROM users WHERE id=?",(user_id,)).fetchone()
        if not target: return RedirectResponse(admin_url(error="User account not found."),303)
        active=0 if target['active'] else 1
        c.execute("UPDATE users SET active=? WHERE id=?",(active,user_id)); add_audit(c,u['id'],'ACTIVATE_USER' if active else 'DEACTIVATE_USER','user',user_id)
    return RedirectResponse(admin_url(message=f"{target['identifier']} has been {'activated' if active else 'deactivated'}."),303)

@app.post("/admin/user/{user_id}/reset-password")
def admin_reset_password(request:Request,user_id:int,password:str=Form(...)):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    if len(password)<8: return RedirectResponse(admin_url(error="The new password must contain at least 8 characters."),303)
    with db() as c:
        target=c.execute("SELECT id,identifier FROM users WHERE id=?",(user_id,)).fetchone()
        if not target: return RedirectResponse(admin_url(error="User account not found."),303)
        c.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(password),user_id)); add_audit(c,u['id'],'RESET_PASSWORD','user',user_id)
    return RedirectResponse(admin_url(message=f"Password reset for {target['identifier']}."),303)

@app.post("/admin/user/{user_id}/delete")
def admin_delete_user(request:Request,user_id:int):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    if user_id==u['id']: return RedirectResponse(admin_url(error="You cannot delete your own administrator account."),303)
    with db() as c:
        target=c.execute("SELECT id,identifier,full_name,role FROM users WHERE id=?",(user_id,)).fetchone()
        if not target: return RedirectResponse(admin_url(error="User account not found."),303)
        checks=[("course assignment","SELECT COUNT(*) n FROM courses WHERE lecturer_id=?"),("course enrolment","SELECT COUNT(*) n FROM enrollments WHERE student_id=?"),("attendance session","SELECT COUNT(*) n FROM attendance_sessions WHERE lecturer_id=?"),("attendance record","SELECT COUNT(*) n FROM attendance_records WHERE student_id=?"),("attendance correction","SELECT COUNT(*) n FROM attendance_records WHERE corrected_by=?"),("audit record","SELECT COUNT(*) n FROM audit_log WHERE actor_user_id=?")]
        used=[label for label,sql in checks if c.execute(sql,(user_id,)).fetchone()['n']]
        if used: return RedirectResponse(admin_url(error=f"{target['identifier']} cannot be permanently deleted because the account has academic/history records ({', '.join(used)}). Deactivate it instead."),303)
        add_audit(c,u['id'],'DELETE_UNUSED_USER','user',None,f"{target['identifier']} - {target['full_name']} ({target['role']})")
        c.execute("DELETE FROM users WHERE id=?",(user_id,))
    return RedirectResponse(admin_url(message=f"Unused account {target['identifier']} permanently deleted."),303)

@app.post("/admin/course/create")
def admin_create_course(request:Request,code:str=Form(...),name:str=Form(...),lecturer_id:int=Form(...)):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    code=code.strip().upper(); name=name.strip()
    if not code or not name: return RedirectResponse(admin_url(error="Course code and course name are required."),303)
    try:
        with db() as c:
            if not c.execute("SELECT id FROM users WHERE id=? AND role='lecturer' AND active=1",(lecturer_id,)).fetchone(): return RedirectResponse(admin_url(error="Select an active lecturer."),303)
            c.execute("INSERT INTO courses(code,name,lecturer_id,created_at) VALUES(?,?,?,?)",(code,name,lecturer_id,iso(now_utc())))
            cid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; add_audit(c,u['id'],'CREATE_COURSE','course',cid)
    except sqlite3.IntegrityError: return RedirectResponse(admin_url(error=f"A course with code {code} already exists."),303)
    return RedirectResponse(admin_url(message=f"Course {code} created successfully."),303)

@app.post("/admin/course/{course_id}/edit")
def admin_edit_course(request:Request,course_id:int,code:str=Form(...),name:str=Form(...),lecturer_id:int=Form(...)):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    code=code.strip().upper(); name=name.strip()
    if not code or not name: return RedirectResponse(admin_url(error="Course code and course name are required."),303)
    try:
        with db() as c:
            course=c.execute("SELECT * FROM courses WHERE id=?",(course_id,)).fetchone()
            if not course: return RedirectResponse(admin_url(error="Course not found."),303)
            if not c.execute("SELECT id FROM users WHERE id=? AND role='lecturer' AND active=1",(lecturer_id,)).fetchone(): return RedirectResponse(admin_url(error="Select an active lecturer."),303)
            c.execute("UPDATE courses SET code=?,name=?,lecturer_id=? WHERE id=?",(code,name,lecturer_id,course_id)); add_audit(c,u['id'],'EDIT_COURSE','course',course_id,f"{course['code']} -> {code}")
    except sqlite3.IntegrityError: return RedirectResponse(admin_url(error=f"Another course already uses code {code}."),303)
    return RedirectResponse(admin_url(message=f"Course {code} updated successfully."),303)

@app.post("/admin/enroll")
def admin_enroll(request:Request,student_id:int=Form(...),course_id:int=Form(...)):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    with db() as c:
        student=c.execute("SELECT id,identifier FROM users WHERE id=? AND role='student' AND active=1",(student_id,)).fetchone(); course=c.execute("SELECT id,code FROM courses WHERE id=?",(course_id,)).fetchone()
        if not student: return RedirectResponse(admin_url(error="Select an active student."),303)
        if not course: return RedirectResponse(admin_url(error="Course not found."),303)
        existing=c.execute("SELECT id,status FROM enrollments WHERE student_id=? AND course_id=?",(student_id,course_id)).fetchone()
        if existing and existing['status']=='active': return RedirectResponse(admin_url(error=f"{student['identifier']} is already enrolled in {course['code']}."),303)
        if existing:
            c.execute("UPDATE enrollments SET status='active' WHERE id=?",(existing['id'],)); eid=existing['id']; action='REENROLL_STUDENT'
        else:
            c.execute("INSERT INTO enrollments(student_id,course_id,status) VALUES(?,?,'active')",(student_id,course_id)); eid=c.execute("SELECT last_insert_rowid()").fetchone()[0]; action='ENROLL_STUDENT'
        add_audit(c,u['id'],action,'enrollment',eid)
    return RedirectResponse(admin_url(message=f"{student['identifier']} enrolled in {course['code']}."),303)

@app.post("/admin/enrollment/{enrollment_id}/remove")
def admin_remove_enrollment(request:Request,enrollment_id:int):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    with db() as c:
        e=c.execute("""SELECT e.id,e.status,s.identifier student_identifier,c.code course_code FROM enrollments e JOIN users s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id WHERE e.id=?""",(enrollment_id,)).fetchone()
        if not e: return RedirectResponse(admin_url(error="Enrolment not found."),303)
        if e['status']!='active': return RedirectResponse(admin_url(error="This enrolment is already inactive."),303)
        c.execute("UPDATE enrollments SET status='inactive' WHERE id=?",(enrollment_id,)); add_audit(c,u['id'],'REMOVE_ENROLLMENT','enrollment',enrollment_id,f"{e['student_identifier']} from {e['course_code']}")
    return RedirectResponse(admin_url(message=f"{e['student_identifier']} removed from {e['course_code']}. Attendance history was preserved."),303)

@app.post("/admin/enrollment/{enrollment_id}/reactivate")
def admin_reactivate_enrollment(request:Request,enrollment_id:int):
    try: u=require_user(request,["admin"])
    except HTTPException: return redirect_login()
    with db() as c:
        e=c.execute("""SELECT e.id,e.status,s.identifier student_identifier,s.active student_active,c.code course_code FROM enrollments e JOIN users s ON s.id=e.student_id JOIN courses c ON c.id=e.course_id WHERE e.id=?""",(enrollment_id,)).fetchone()
        if not e: return RedirectResponse(admin_url(error="Enrolment not found."),303)
        if not e['student_active']: return RedirectResponse(admin_url(error="Activate the student account before restoring the enrolment."),303)
        if e['status']=='active': return RedirectResponse(admin_url(error="This enrolment is already active."),303)
        c.execute("UPDATE enrollments SET status='active' WHERE id=?",(enrollment_id,)); add_audit(c,u['id'],'REENROLL_STUDENT','enrollment',enrollment_id,f"{e['student_identifier']} in {e['course_code']}")
    return RedirectResponse(admin_url(message=f"{e['student_identifier']} restored to {e['course_code']}."),303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=int(os.getenv("PORT","8000")), reload=False)


# -----------------------------------------------------------------------------
# Student mobile API
# -----------------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    return {"success": True, "service": "CBU QR Attendance", "status": "online"}


@app.post("/api/student/login")
def api_student_login(payload: StudentLoginPayload):
    identifier = payload.identifier.strip()
    if not identifier or not payload.password:
        raise HTTPException(status_code=400, detail="Student ID and password are required.")

    with db() as c:
        u = c.execute(
            "SELECT * FROM users WHERE identifier=? AND active=1",
            (identifier,),
        ).fetchone()

    if not u or not verify_password(payload.password, u["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid Student ID or password.")
    if u["role"] != "student":
        raise HTTPException(status_code=403, detail="This mobile application is for student accounts only.")

    auth_token = sign_session(u["id"])
    return {
        "success": True,
        "message": "Login successful",
        "token": auth_token,
        "expires_in": 43200,
        "low_threshold": LOW_THRESHOLD,
        "user": {
            "id": u["id"],
            "identifier": u["identifier"],
            "full_name": u["full_name"],
            "role": u["role"],
        },
    }


def mobile_course_rows(c, student_id: int):
    rows = c.execute(
        """SELECT c.id,c.code,c.name,
          COALESCE(l.full_name,'') lecturer_name,
          (SELECT COUNT(*) FROM attendance_sessions s
             WHERE s.course_id=c.id AND s.status IN ('closed','expired')) total_sessions,
          (SELECT COUNT(*) FROM attendance_records ar
             JOIN attendance_sessions s2 ON s2.id=ar.session_id
             WHERE ar.student_id=? AND s2.course_id=c.id
               AND s2.status IN ('closed','expired') AND ar.status='present') attended
          FROM courses c
          JOIN enrollments e ON e.course_id=c.id
          LEFT JOIN users l ON l.id=c.lecturer_id
          WHERE e.student_id=? AND e.status='active'
          ORDER BY c.code""",
        (student_id, student_id),
    ).fetchall()

    out = []
    for row in rows:
        total = row["total_sessions"] or 0
        attended = row["attended"] or 0
        percentage = round(attended / total * 100, 1) if total else 0.0
        out.append({
            "id": row["id"],
            "code": row["code"],
            "name": row["name"],
            "lecturer_name": row["lecturer_name"],
            "attended": attended,
            "total_sessions": total,
            "percentage": percentage,
            "low_attendance": bool(total and percentage < LOW_THRESHOLD),
        })
    return out


def mobile_history_rows(c, student_id: int, limit: int = 100):
    rows = c.execute(
        """SELECT ar.id,ar.recorded_at,ar.method,ar.status,
                  c.id course_id,c.code,c.name,s.started_at
           FROM attendance_records ar
           JOIN attendance_sessions s ON s.id=ar.session_id
           JOIN courses c ON c.id=s.course_id
           WHERE ar.student_id=?
           ORDER BY ar.recorded_at DESC
           LIMIT ?""",
        (student_id, max(1, min(limit, 500))),
    ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/student/profile")
def api_student_profile(request: Request):
    u = require_api_student(request)
    return {
        "success": True,
        "user": {
            "id": u["id"],
            "identifier": u["identifier"],
            "full_name": u["full_name"],
            "role": u["role"],
        },
        "low_threshold": LOW_THRESHOLD,
    }


@app.get("/api/student/dashboard")
def api_student_dashboard(request: Request):
    u = require_api_student(request)
    with db() as c:
        expire_sessions(c)
        courses = mobile_course_rows(c, u["id"])
        history = mobile_history_rows(c, u["id"], 10)

    eligible = sum(x["total_sessions"] for x in courses)
    attended = sum(x["attended"] for x in courses)
    overall = round(attended / eligible * 100, 1) if eligible else 0.0
    low_courses = sum(1 for x in courses if x["low_attendance"])

    return {
        "success": True,
        "user": {"identifier": u["identifier"], "full_name": u["full_name"]},
        "summary": {
            "courses": len(courses),
            "attended": attended,
            "eligible_sessions": eligible,
            "overall_percentage": overall,
            "low_courses": low_courses,
            "low_threshold": LOW_THRESHOLD,
        },
        "courses": courses,
        "recent_attendance": history,
    }


@app.get("/api/student/courses")
def api_student_courses(request: Request):
    u = require_api_student(request)
    with db() as c:
        expire_sessions(c)
        courses = mobile_course_rows(c, u["id"])
    return {"success": True, "courses": courses, "low_threshold": LOW_THRESHOLD}


@app.get("/api/student/attendance")
def api_student_attendance(request: Request, limit: int = 100):
    u = require_api_student(request)
    with db() as c:
        expire_sessions(c)
        history = mobile_history_rows(c, u["id"], limit)
    return {"success": True, "attendance": history}


@app.post("/api/student/checkin")
def api_student_checkin(request: Request, payload: StudentCheckinPayload):
    u = require_api_student(request)
    token = payload.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Attendance token is required.")

    with db() as c:
        expire_sessions(c)
        s = c.execute(
            """SELECT s.*,c.code,c.name
               FROM attendance_sessions s
               JOIN courses c ON c.id=s.course_id
               WHERE s.token_hash=?""",
            (token_hash(token),),
        ).fetchone()

        if not s:
            raise HTTPException(status_code=400, detail="Invalid QR code or attendance token.")
        if s["status"] != "active":
            raise HTTPException(status_code=409, detail="This attendance session is no longer active.")
        if parse_dt(s["expires_at"]) < now_utc():
            raise HTTPException(status_code=409, detail="This QR code has expired.")
        if not c.execute(
            "SELECT 1 FROM enrollments WHERE student_id=? AND course_id=? AND status='active'",
            (u["id"], s["course_id"]),
        ).fetchone():
            raise HTTPException(status_code=403, detail="You are not enrolled in this course.")
        if c.execute(
            "SELECT 1 FROM attendance_records WHERE session_id=? AND student_id=?",
            (s["id"], u["id"]),
        ).fetchone():
            raise HTTPException(status_code=409, detail="Your attendance has already been recorded for this session.")

        recorded_at = iso(now_utc())
        c.execute(
            """INSERT INTO attendance_records
               (session_id,student_id,recorded_at,status,method)
               VALUES(?,?,?,?,?)""",
            (s["id"], u["id"], recorded_at, "present", "qr"),
        )

    return {
        "success": True,
        "message": f"Attendance recorded for {s['code']} - {s['name']}.",
        "attendance": {
            "session_id": s["id"],
            "course_id": s["course_id"],
            "course_code": s["code"],
            "course_name": s["name"],
            "recorded_at": recorded_at,
            "method": "qr",
            "status": "present",
        },
    }


@app.post("/api/student/logout")
def api_student_logout(request: Request):
    require_api_student(request)
    # Authentication tokens are short-lived signed tokens and are not stored server-side.
    # The mobile client removes its token on logout.
    return {"success": True, "message": "Logged out"}
