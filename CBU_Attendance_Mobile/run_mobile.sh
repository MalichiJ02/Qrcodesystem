#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo
echo "=================================================="
echo "       CBU QR Attendance - Student Mobile"
echo "=================================================="
echo

if ! command -v flutter >/dev/null 2>&1; then
  echo "ERROR: Flutter is not installed or is not in PATH."
  exit 1
fi

echo "✓ Flutter found: $(flutter --version | head -n 1)"

# Generate platform files using the installed Flutter version. This keeps the
# project portable across teammates without shipping machine-specific Gradle files.
if [ ! -f "android/app/src/main/AndroidManifest.xml" ]; then
  echo "→ First mobile run detected. Creating Android platform files..."
  TMP_DIR="$(mktemp -d)"
  cp -R lib "$TMP_DIR/lib"
  cp pubspec.yaml "$TMP_DIR/pubspec.yaml"
  cp analysis_options.yaml "$TMP_DIR/analysis_options.yaml"

  flutter create \
    --platforms=android \
    --org zm.ac.cbu \
    --project-name cbu_attendance_mobile \
    .

  rm -rf lib
  cp -R "$TMP_DIR/lib" ./lib
  cp "$TMP_DIR/pubspec.yaml" ./pubspec.yaml
  cp "$TMP_DIR/analysis_options.yaml" ./analysis_options.yaml
  rm -rf "$TMP_DIR"
fi

# Camera permission and local HTTP fallback for development.
MANIFEST="android/app/src/main/AndroidManifest.xml"
python3 - "$MANIFEST" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
if 'android.permission.CAMERA' not in s:
    s=s.replace('<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
                '<manifest xmlns:android="http://schemas.android.com/apk/res/android">\n    <uses-permission android:name="android.permission.CAMERA" />\n    <uses-feature android:name="android.hardware.camera" android:required="false" />')
if 'android:usesCleartextTraffic=' not in s:
    s=s.replace('<application\n', '<application\n        android:usesCleartextTraffic="true"\n', 1)
p.write_text(s)
PY

echo "→ Getting Flutter packages..."
flutter pub get

echo
echo "Connected devices:"
flutter devices

echo
echo "Starting student app..."
echo "On the login screen, enter the server address printed by the backend run.sh."
echo
flutter run
