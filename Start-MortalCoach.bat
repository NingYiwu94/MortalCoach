@echo off
setlocal
pushd "%~dp0mortalcoach" || (
  echo Failed to enter MortalCoach app directory.
  exit /b 1
)

set "ELECTRON_RUN_AS_NODE="
if not defined ELECTRON_MIRROR set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"

if /I "%~1"=="doctor" goto doctor

if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
set "NODE_EXE=C:\Program Files\nodejs\node.exe"
set "NPM_EXE=C:\Program Files\nodejs\npm.cmd"
if not exist "%NODE_EXE%" set "NODE_EXE=node"
if not exist "%NPM_EXE%" set "NPM_EXE=npm"

if exist package.json (
  if not exist node_modules\electron\dist\electron.exe (
    echo Installing Electron dependencies. This may take a while on first launch...
    "%NPM_EXE%" install --no-audit --no-fund
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
echo MortalCoach desktop launch failed or Electron is unavailable.
echo Falling back to browser mode through Python.
echo Run "Start-MortalCoach.bat doctor" to check the local environment.
echo.
python "%CD%\launch.py"
goto end

:doctor
python "%CD%\scripts\doctor.py"
pause

:end
popd
endlocal
