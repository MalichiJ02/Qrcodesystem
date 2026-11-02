@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title CBU QR Attendance System

echo.
echo ==================================================
echo        CBU QR Attendance System
echo ==================================================
echo.

REM --------------------------------------------------
REM Check Python
REM --------------------------------------------------

where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Install Python 3 and select:
    echo "Add Python to PATH"
    echo during installation.
    echo.
    pause
    exit /b 1
)

echo [OK] Python found
python --version

REM --------------------------------------------------
REM Create virtual environment if missing
REM --------------------------------------------------

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [SETUP] First run detected.
    echo [SETUP] Creating virtual environment...

    python -m venv .venv

    if errorlevel 1 (
        echo ERROR: Could not create virtual environment.
        pause
        exit /b 1
    )

    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment found.
)

call ".venv\Scripts\activate.bat"

REM --------------------------------------------------
REM Install dependencies when needed
REM --------------------------------------------------

".venv\Scripts\python.exe" -c "import fastapi,uvicorn,jinja2,multipart,qrcode,reportlab" >nul 2>&1

if errorlevel 1 (
    echo.
    echo [SETUP] Installing dependencies...

    ".venv\Scripts\python.exe" -m pip install -r requirements.txt

    if errorlevel 1 (
        echo.
        echo ERROR: Dependency installation failed.
        pause
        exit /b 1
    )

    echo [OK] Dependencies installed.
) else (
    echo [OK] Dependencies ready.
)

REM --------------------------------------------------
REM Database
REM --------------------------------------------------

if exist "data\attendance.db" (
    echo [OK] Database found.
) else (
    echo [INFO] Database not found.
    echo [INFO] Application will initialise it.
)

REM --------------------------------------------------
REM Detect local IPv4 address
REM --------------------------------------------------

set "LAN_IP="

for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /C:"IPv4 Address"') do (
    if not defined LAN_IP (
        set "LAN_IP=%%A"
        set "LAN_IP=!LAN_IP: =!"
    )
)

if not defined LAN_IP (
    set "LAN_IP=127.0.0.1"
)

echo [OK] Network address: !LAN_IP!

REM --------------------------------------------------
REM Check port 8000
REM --------------------------------------------------

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1

if not errorlevel 1 (
    echo.
    echo ==================================================
    echo  Port 8000 is already in use
    echo ==================================================
    echo.
    echo The application may already be running.
    echo.
    echo Laptop:
    echo   http://localhost:8000
    echo.
    echo Phone / other device:
    echo   http://!LAN_IP!:8000
    echo.
    echo If those addresses do not work, another program
    echo may be using port 8000.
    echo.
    pause
    exit /b 0
)

REM --------------------------------------------------
REM Look for HTTPS certificate matching current IP
REM --------------------------------------------------

set "SSL_CERT="
set "SSL_KEY="

for %%F in ("certs\!LAN_IP!*.pem") do (
    echo %%~nxF | findstr /I /C:"-key.pem" >nul

    if errorlevel 1 (
        if exist "%%~fF" (
            if exist "%%~dpnF-key.pem" (
                if not defined SSL_CERT (
                    set "SSL_CERT=%%~fF"
                    set "SSL_KEY=%%~dpnF-key.pem"
                )
            )
        )
    )
)

REM --------------------------------------------------
REM Start server
REM --------------------------------------------------

echo.
echo ==================================================

if defined SSL_CERT (

    echo  HTTPS MODE
    echo ==================================================
    echo.
    echo OPEN ON THIS WINDOWS LAPTOP:
    echo.
    echo   https://!LAN_IP!:8000
    echo.
    echo OPEN ON PHONE / OTHER DEVICE:
    echo.
    echo   https://!LAN_IP!:8000
    echo.
    echo Both devices must be on the same network.
    echo.
    echo Keep this window open while using the system.
    echo Press Ctrl+C to stop the server.
    echo.
    echo ==================================================
    echo.

    ".venv\Scripts\python.exe" -m uvicorn app:app ^
        --host 0.0.0.0 ^
        --port 8000 ^
        --ssl-keyfile "!SSL_KEY!" ^
        --ssl-certfile "!SSL_CERT!"

) else (

    echo  HTTP DEVELOPMENT MODE
    echo ==================================================
    echo.
    echo No HTTPS certificate was found for:
    echo   !LAN_IP!
    echo.
    echo OPEN ON THIS WINDOWS LAPTOP:
    echo.
    echo   http://localhost:8000
    echo.
    echo OPEN ON PHONE / OTHER DEVICE:
    echo.
    echo   http://!LAN_IP!:8000
    echo.
    echo NOTE:
    echo Phone camera QR scanning may require HTTPS.
    echo.
    echo Keep this window open while using the system.
    echo Press Ctrl+C to stop the server.
    echo.
    echo ==================================================
    echo.

    ".venv\Scripts\python.exe" -m uvicorn app:app ^
        --host 0.0.0.0 ^
        --port 8000
)

echo.
echo Server stopped.
pause

endlocal
