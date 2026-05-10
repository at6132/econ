<#
.SYNOPSIS
  Starts the Realm solo dev stack: FastAPI (:8000) and Next.js (:3000), each in its own terminal window.

.NOTES
  Run from repo root:  .\start-dev.ps1
  Uses engine\.venv\Scripts\python.exe when present; otherwise `python` on PATH.
  If uvicorn is missing, runs once: pip install -e ".[dev]" from engine/.
  If web/node_modules is missing, runs npm install in web/.
#>

param()

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
if (-not $Root) {
    $Root = (Get-Location).Path
}

$Engine = Join-Path $Root "engine"
$Web = Join-Path $Root "web"

if (-not (Test-Path $Engine)) {
    Write-Error "Missing engine/ directory. Run this script from the repo root (same folder as start-dev.ps1). Expected: $Engine"
}

if (-not (Test-Path $Web)) {
    Write-Error "Missing web/ directory. Expected: $Web"
}

$pythonExe = Join-Path $Engine ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

& $pythonExe -c "import uvicorn" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Python dependencies in engine/ (pip install -e '.[dev]') ..."
    Push-Location $Engine
    & $pythonExe -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        exit $LASTEXITCODE
    }
    Pop-Location
}

if (-not (Test-Path (Join-Path $Web "node_modules"))) {
    Write-Host "Installing npm dependencies in web/ ..."
    Push-Location $Web
    npm install
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        exit $LASTEXITCODE
    }
    Pop-Location
}

$apiCmd = "Set-Location -LiteralPath '$Engine'; & `"$pythonExe`" -m uvicorn realm.api:app --reload --port 8000"
$webCmd = "Set-Location -LiteralPath '$Web'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $apiCmd
Start-Process powershell -ArgumentList "-NoExit", "-NoProfile", "-Command", $webCmd

Write-Host ""
Write-Host "Started two windows:"
Write-Host "  API  http://localhost:8000  (FastAPI + uvicorn)"
Write-Host "  Web  http://localhost:3000  (Next.js; proxies /api/engine to the API)"
Write-Host ""
