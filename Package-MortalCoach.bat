@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package-windows.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] Packaging failed.
  pause
  exit /b 1
)

echo.
echo MortalCoach installer is ready in the release folder.
pause
