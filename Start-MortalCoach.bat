@echo off
setlocal
cd /d "%~dp0mortalcoach"

set ELECTRON_RUN_AS_NODE=

if /I "%~1"=="doctor" goto doctor

if exist "C:\Program Files\nodejs\node.exe" set "PATH=C:\Program Files\nodejs;%PATH%"
set "NODE_EXE=C:\Program Files\nodejs\node.exe"
set "NPM_EXE=C:\Program Files\nodejs\npm.cmd"
if not exist "%NODE_EXE%" set "NODE_EXE=node"
if not exist "%NPM_EXE%" set "NPM_EXE=npm"

if exist package.json (
  if not exist node_modules\electron\dist\electron.exe (
    "%NPM_EXE%" install
    if errorlevel 1 goto fallback
  )
  if exist node_modules\electron\dist\electron.exe (
    "%NODE_EXE%" node_modules\electron\cli.js .
  ) else (
    "%NPM_EXE%" start
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
python launch.py
goto end

:doctor
python scripts\doctor.py
pause

:end
endlocal
