$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$AppDir = Join-Path $RepoRoot "mortalcoach"
$BuildDir = Join-Path $RepoRoot "build"
$BackendDist = Join-Path $BuildDir "backend"
$PyWork = Join-Path $BuildDir "pyinstaller-work"
$ReleaseDir = Join-Path $RepoRoot "release"

Write-Host "========================================"
Write-Host "MortalCoach Windows package"
Write-Host "========================================"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python was not found. Install Python 3.10+ before packaging."
}
$NpmCmd = Get-Command npm -ErrorAction SilentlyContinue
$CommonNodeDir = "C:\Program Files\nodejs"
if (-not $NpmCmd -and (Test-Path (Join-Path $CommonNodeDir "npm.cmd"))) {
  $env:Path = "$CommonNodeDir;$env:Path"
  $NpmCmd = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $NpmCmd) {
  throw "npm was not found. Install Node.js 20+ before packaging."
}

New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Remove-Item -Recurse -Force $BackendDist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $PyWork -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "[1/4] Installing Python packaging tool..."
python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "[2/4] Building bundled Python backend..."
$StaticDir = Join-Path $AppDir "static"
$KillerGuiDir = Join-Path $RepoRoot "killer_mortal_gui"
Push-Location $AppDir
try {
  python -m PyInstaller `
    --noconfirm `
    --clean `
    --name MortalCoachBackend `
    --distpath $BackendDist `
    --workpath $PyWork `
    --specpath $BuildDir `
    --add-data "$StaticDir;static" `
    --add-data "$KillerGuiDir;killer_mortal_gui" `
    app.py
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
}
finally {
  Pop-Location
}

$BackendExe = Join-Path $BackendDist "MortalCoachBackend\MortalCoachBackend.exe"
if (-not (Test-Path $BackendExe)) {
  throw "Backend build did not create $BackendExe"
}

Write-Host ""
Write-Host "[3/4] Installing Electron packaging dependencies..."
Push-Location $AppDir
try {
  if (-not $env:ELECTRON_MIRROR) {
    $env:ELECTRON_MIRROR = "https://npmmirror.com/mirrors/electron/"
  }
  npm install --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "[4/4] Building Windows installer..."
Push-Location $AppDir
try {
  npm run dist:win
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed with exit code $LASTEXITCODE" }
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Done. Installer files:"
Get-ChildItem $ReleaseDir -Filter "MortalCoach-Setup-*.exe" | ForEach-Object {
  Write-Host " - $($_.FullName)"
}
