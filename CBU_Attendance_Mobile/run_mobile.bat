@echo off
setlocal
cd /d "%~dp0"

echo.
echo ==================================================
echo        CBU QR Attendance - Student Mobile
echo ==================================================
echo.

where flutter >nul 2>&1
if errorlevel 1 (
  echo ERROR: Flutter is not installed or is not in PATH.
  pause
  exit /b 1
)

if not exist "android\app\src\main\AndroidManifest.xml" (
  echo First mobile run detected. Creating Android platform files...
  set "TMPMOB=%TEMP%\cbu_attendance_mobile_backup"
  if exist "%TMPMOB%" rmdir /s /q "%TMPMOB%"
  mkdir "%TMPMOB%"
  xcopy /e /i /q "lib" "%TMPMOB%\lib" >nul
  copy /y "pubspec.yaml" "%TMPMOB%\pubspec.yaml" >nul
  copy /y "analysis_options.yaml" "%TMPMOB%\analysis_options.yaml" >nul

  flutter create --platforms=android --org zm.ac.cbu --project-name cbu_attendance_mobile .
  if errorlevel 1 goto :error

  if exist "lib" rmdir /s /q "lib"
  xcopy /e /i /q "%TMPMOB%\lib" "lib" >nul
  copy /y "%TMPMOB%\pubspec.yaml" "pubspec.yaml" >nul
  copy /y "%TMPMOB%\analysis_options.yaml" "analysis_options.yaml" >nul
  rmdir /s /q "%TMPMOB%"
)

powershell -NoProfile -Command "$p='android/app/src/main/AndroidManifest.xml'; $s=Get-Content $p -Raw; if($s -notmatch 'android.permission.CAMERA'){ $s=$s -replace '<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">','<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">`r`n    <uses-permission android:name=\"android.permission.CAMERA\" />`r`n    <uses-feature android:name=\"android.hardware.camera\" android:required=\"false\" />' }; if($s -notmatch 'android:usesCleartextTraffic='){ $s=$s -replace '<application','<application android:usesCleartextTraffic=\"true\"' }; Set-Content $p $s"

flutter pub get
if errorlevel 1 goto :error

flutter devices
echo.
echo Starting student app...
echo Enter the backend server address on the app login screen.
echo.
flutter run
goto :end

:error
echo.
echo Mobile setup failed.
pause
exit /b 1

:end
pause
endlocal
