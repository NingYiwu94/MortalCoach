$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$vendor = Join-Path $root "vendor"
$target = Join-Path $vendor "tensoul"

if (!(Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git is required."
}

if (!(Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required. Install it from https://nodejs.org/ first."
}

if (!(Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is required. It is usually installed with Node.js."
}

New-Item -ItemType Directory -Force $vendor | Out-Null

if (!(Test-Path $target)) {
    git clone https://github.com/Equim-chan/tensoul.git $target
}

Push-Location $target
try {
    npm install
    if (!(Test-Path "config.js")) {
        Copy-Item "config.example.js" "config.js"
    }
}
finally {
    Pop-Location
}

Write-Host "tensoul is ready at $target"
Write-Host "Next: copy config.example.json to config.json and fill access_token."
