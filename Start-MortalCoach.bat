@echo off
setlocal
pushd "%~dp0mortalcoach" || (
  echo Failed to enter MortalCoach app directory.
  exit /b 1
)

set "ELECTRON_RUN_AS_NODE="
if not defined ELECTRON_MIRROR set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"

if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
set "NODE_EXE=C:\Program Files\nodejs\node.exe"
set "NPM_EXE=C:\Program Files\nodejs\npm.cmd"
if not exist "%NODE_EXE%" set "NODE_EXE=node"
if not exist "%NPM_EXE%" set "NPM_EXE=npm"

set "PYTHON_EXE=python"
where python >nul 2>nul
if errorlevel 1 (
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
  if exist "C:\Program Files\Python312\python.exe" set "PYTHON_EXE=C:\Program Files\Python312\python.exe"
  if exist "C:\Program Files\Python311\python.exe" set "PYTHON_EXE=C:\Program Files\Python311\python.exe"
)
set "MORTALCOACH_PYTHON=%PYTHON_EXE%"

if /I "%~1"=="doctor" goto doctor

if exist package.json (
  if not exist node_modules\electron\dist\electron.exe (
    echo Installing Electron dependencies. This may take a while on first launch...
    call "%NPM_EXE%" install --no-audit --no-fund
    if errorlevel 1 goto fallback
    if not exist node_modules\electron\dist\electron.exe (
      if exist node_modules\electron\install.js (
        "%NODE_EXE%" node_modules\electron\install.js
      )
    )
    if errorlevel 1 goto fallback
  )
  if exist node_modules\electron\dist\electron.exe (
    node_modules\electron\dist\electron.exe .
  ) else (
    goto fallback
  )
  if errorlevel 1 goto fallback
  goto end
)

:fallback
echo.
echo MortalCoach desktop launch failed.
echo Please run "Install-MortalCoach.bat" first, or run "Start-MortalCoach.bat doctor" to check the local environment.
echo.
pause
goto end

:doctor
"%PYTHON_EXE%" "%CD%\scripts\doctor.py"
pause

:end
popd
endlocal
