@echo off
setlocal
pushd "%~dp0" || (
  echo Failed to enter MortalCoach directory.
  exit /b 1
)

echo.
echo ========================================
echo MortalCoach installer
echo ========================================
echo.
echo This script will check/install:
echo - Python 3.12
echo - Node.js LTS
echo - MortalCoach desktop dependencies
echo - Desktop shortcut
echo.

where winget >nul 2>nul
if errorlevel 1 (
  echo [ERROR] winget was not found on this Windows system.
  echo Please install Python 3.10+ and Node.js 20+ manually, then run Start-MortalCoach.bat.
  echo.
  pause
  exit /b 1
)

call :ensure_python
if errorlevel 1 goto failed
call :ensure_node
if errorlevel 1 goto failed
call :electron
if errorlevel 1 goto failed
call :create_shortcut
if errorlevel 1 goto failed

echo.
echo ========================================
echo MortalCoach is ready.
echo ========================================
echo.
echo You can now start MortalCoach from the desktop shortcut,
echo or double-click Start-MortalCoach.bat in this folder.
echo.
pause
popd
endlocal
exit /b 0

:failed
echo.
echo [ERROR] MortalCoach installation did not finish.
echo Please check the messages above, then run Install-MortalCoach.bat again.
echo.
pause
popd
endlocal
exit /b 1

:ensure_python
where python >nul 2>nul
if not errorlevel 1 (
  echo [OK] Python found.
  exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
  echo [OK] Python found.
  exit /b 0
)
if exist "C:\Program Files\Python312\python.exe" (
  echo [OK] Python found.
  exit /b 0
)
echo [INSTALL] Python 3.12
winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 1
exit /b 0

:ensure_node
where node >nul 2>nul
if not errorlevel 1 (
  echo [OK] Node.js found.
  exit /b 0
)
if exist "C:\Program Files\nodejs\node.exe" (
  echo [OK] Node.js found.
  exit /b 0
)
echo [INSTALL] Node.js LTS
winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 1
exit /b 0

:electron
echo.
echo [SETUP] Installing MortalCoach desktop dependencies...
pushd "%~dp0mortalcoach"
if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
if not defined ELECTRON_MIRROR set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"
set "NPM_EXE=C:\Program Files\nodejs\npm.cmd"
set "NODE_EXE=C:\Program Files\nodejs\node.exe"
if not exist "%NPM_EXE%" set "NPM_EXE=npm"
if not exist "%NODE_EXE%" set "NODE_EXE=node"
call "%NPM_EXE%" install --no-audit --no-fund
if errorlevel 1 (
  echo [ERROR] npm install failed.
  popd
  exit /b 1
)
if not exist node_modules\electron\dist\electron.exe (
  if exist node_modules\electron\install.js (
    echo [SETUP] Downloading Electron runtime...
    "%NODE_EXE%" node_modules\electron\install.js
  )
)
if not exist node_modules\electron\dist\electron.exe (
  echo [ERROR] Electron runtime was not installed.
  popd
  exit /b 1
)
popd
exit /b 0

:create_shortcut
echo.
echo [SETUP] Creating desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desktop=[Environment]::GetFolderPath('Desktop'); $shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'MortalCoach.lnk')); $shortcut.TargetPath=(Join-Path '%~dp0' 'Start-MortalCoach.bat'); $shortcut.WorkingDirectory='%~dp0'; $shortcut.IconLocation='%SystemRoot%\System32\shell32.dll,44'; $shortcut.Save()"
if errorlevel 1 (
  echo [WARN] Failed to create desktop shortcut. You can still run Start-MortalCoach.bat manually.
) else (
  echo [OK] Desktop shortcut created.
)
exit /b 0
