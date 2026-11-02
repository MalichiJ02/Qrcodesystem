#!/usr/bin/env bash

set -e

# ------------------------------------------------------------
# CBU QR Attendance System Launcher
# ------------------------------------------------------------

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PORT=8000
VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"

echo
echo "=================================================="
echo "       CBU QR Attendance System"
echo "=================================================="
echo

# ------------------------------------------------------------
# 1. Check Python
# ------------------------------------------------------------

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: Python 3 is not installed."
    echo "Install Python 3 and try again."
    exit 1
fi

echo "✓ Python found: $(python3 --version)"

# ------------------------------------------------------------
# 2. Create virtual environment only when needed
# ------------------------------------------------------------

if [ ! -d "$VENV_DIR" ]; then
    echo "→ First run detected."
    echo "→ Creating Python virtual environment..."

    python3 -m venv "$VENV_DIR"

    echo "✓ Virtual environment created."
else
    echo "✓ Virtual environment found."
fi

source "$VENV_DIR/bin/activate"

# ------------------------------------------------------------
# 3. Install/update dependencies only when necessary
# ------------------------------------------------------------

HASH_FILE="$VENV_DIR/.requirements.sha256"

if command -v sha256sum >/dev/null 2>&1; then
    CURRENT_HASH="$(sha256sum "$REQUIREMENTS" | awk '{print $1}')"
else
    CURRENT_HASH=""
fi

NEED_INSTALL=0

if ! python -c "import fastapi, uvicorn, jinja2, multipart, qrcode, reportlab" \
    >/dev/null 2>&1; then
    NEED_INSTALL=1
fi

if [ -n "$CURRENT_HASH" ]; then
    if [ ! -f "$HASH_FILE" ] || [ "$(cat "$HASH_FILE")" != "$CURRENT_HASH" ]; then
        NEED_INSTALL=1
    fi
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
    echo "→ Installing project dependencies..."
    python -m pip install --upgrade pip
    python -m pip install -r "$REQUIREMENTS"

    if [ -n "$CURRENT_HASH" ]; then
        echo "$CURRENT_HASH" > "$HASH_FILE"
    fi

    echo "✓ Dependencies installed."
else
    echo "✓ Dependencies ready."
fi

# ------------------------------------------------------------
# 4. Check database
# ------------------------------------------------------------

mkdir -p data

if [ -f "data/attendance.db" ]; then
    echo "✓ Database found."
else
    echo "→ Database not found."
    echo "→ The application will initialise it on startup."
fi

# ------------------------------------------------------------
# 5. Detect LAN IP
# ------------------------------------------------------------

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"

if [ -z "$LAN_IP" ]; then
    LAN_IP="127.0.0.1"
fi

echo "✓ Network address: $LAN_IP"

# ------------------------------------------------------------
# 6. Check whether port is already occupied
# ------------------------------------------------------------

if command -v ss >/dev/null 2>&1 && ss -ltn | awk '{print $4}' | grep -Eq ":${PORT}$"; then
    echo
    echo "=================================================="
    echo " Application appears to already be running."
    echo "=================================================="
    echo
    echo "Laptop:"
    echo "  https://localhost:${PORT}"
    echo
    echo "Other devices on the same network:"
    echo "  https://${LAN_IP}:${PORT}"
    echo
    echo "If those addresses do not work, another program may"
    echo "be using port ${PORT}."
    echo
    exit 0
fi

# ------------------------------------------------------------
# 7. Find HTTPS certificate for current IP
# ------------------------------------------------------------

SSL_CERT=""
SSL_KEY=""

# Prefer certificate matching current LAN IP.
for CERT in certs/"${LAN_IP}"*.pem; do
    [ -e "$CERT" ] || continue

    if [[ "$CERT" != *"-key.pem" ]]; then
        POSSIBLE_KEY="${CERT%.pem}-key.pem"

        if [ -f "$POSSIBLE_KEY" ]; then
            SSL_CERT="$CERT"
            SSL_KEY="$POSSIBLE_KEY"
            break
        fi
    fi
done

# ------------------------------------------------------------
# 8. Start application
# ------------------------------------------------------------

echo
echo "=================================================="

if [ -n "$SSL_CERT" ] && [ -n "$SSL_KEY" ]; then

    echo " HTTPS certificate found."
    echo "=================================================="
    echo
    echo "Laptop:"
    echo "  https://localhost:${PORT}"
    echo
    echo "Phone / other device:"
    echo "  https://${LAN_IP}:${PORT}"
    echo
    echo "Keep this terminal open while using the system."
    echo "Press Ctrl+C to stop."
    echo
    echo "=================================================="
    echo

    exec python -m uvicorn app:app \
        --host 0.0.0.0 \
        --port "$PORT" \
        --ssl-keyfile "$SSL_KEY" \
        --ssl-certfile "$SSL_CERT"

else

    echo " No HTTPS certificate found for $LAN_IP"
    echo "=================================================="
    echo
    echo "Starting in HTTP development mode."
    echo
    echo "Laptop:"
    echo "  http://localhost:${PORT}"
    echo
    echo "Other devices:"
    echo "  http://${LAN_IP}:${PORT}"
    echo
    echo "NOTE:"
    echo "QR camera scanning on phones may require HTTPS."
    echo
    echo "Keep this terminal open while using the system."
    echo "Press Ctrl+C to stop."
    echo
    echo "=================================================="
    echo

    exec python -m uvicorn app:app \
        --host 0.0.0.0 \
        --port "$PORT"
fi
