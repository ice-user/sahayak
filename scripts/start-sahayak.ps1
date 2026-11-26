# One-click local launcher for Sahayak (Windows PowerShell 5.1+).
#   Full app (backend + NVIDIA + frontend):  double-click "Start Sahayak.bat"
#   Frontend demo only (no backend/AI):      double-click "Start Demo.bat"
# Options: -Demo  -Model "nvidia/nemotron-3-super-120b-a12b"  -EnvFile "C:\path\to\.env"
param(
    [switch]$Demo,
    [string]$Model = "",
    [string]$EnvFile = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
function Say($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# ---------- Node / frontend ----------
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Node.js (npm) not found. Install Node 20+ from https://nodejs.org and run this again." }
if (-not (Test-Path "$root\web\node_modules")) {
    Say "Installing frontend packages (first run only, ~1-2 min)..."
    Push-Location "$root\web"; npm install; $code = $LASTEXITCODE; Pop-Location
    if ($code -ne 0) { Fail "npm install failed." }
}

if ($Demo) {
    Say "Starting the frontend in DEMO mode (simulated AI, real eligibility rules)..."
    $env:NEXT_PUBLIC_MOCK = "1"
    Remove-Item env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.ui.RawUI.WindowTitle='Sahayak frontend (demo)'; Set-Location '$root\web'; npm run dev"
} else {
    # ---------- Python / backend ----------
    $py = $null
    foreach ($c in @(@{exe = "py"; pre = @("-3")}, @{exe = "python"; pre = @()})) {
        if (-not (Get-Command $c.exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $ver = & $c.exe @($c.pre + @("-c", "import sys; print(sys.version_info[0]*100+sys.version_info[1])"))
            if ([int]$ver -ge 310) { $py = $c; break }
        } catch {}
    }
    if (-not $py) { Fail "Python 3.10+ not found. Install it from https://python.org (tick 'Add to PATH') and run this again." }

    $venvPy = "$root\.venv\Scripts\python.exe"
    if (-not (Test-Path $venvPy)) {
        Say "Creating Python environment (first run only)..."
        & $py.exe @($py.pre + @("-m", "venv", "$root\.venv"))
        if ($LASTEXITCODE -ne 0) { Fail "Could not create .venv" }
    }
    $stamp = "$root\.venv\.requirements-installed"
    if (-not (Test-Path $stamp) -or ((Get-Item "$root\requirements.txt").LastWriteTime -gt (Get-Item $stamp).LastWriteTime)) {
        Say "Installing Python packages (first run only, a few minutes)..."
        & $venvPy -m pip install --upgrade pip --quiet
        & $venvPy -m pip install -r "$root\requirements.txt"
        if ($LASTEXITCODE -ne 0) { Fail "pip install failed." }
        New-Item -ItemType File -Force $stamp | Out-Null
    }

    # ---------- NVIDIA key (read from your other project's .env; never printed) ----------
    if (-not $EnvFile) { $EnvFile = Join-Path (Split-Path -Parent $root) "source-trail\backend\.env" }
    if (-not $env:NVIDIA_API_KEY) {
        if (-not (Test-Path $EnvFile)) { Fail "No NVIDIA_API_KEY set and $EnvFile not found. Use -EnvFile or set `$env:NVIDIA_API_KEY." }
        foreach ($line in Get-Content $EnvFile) {
            if ($line -match '^\s*(NVIDIA_API_KEY|NVIDIA_MODEL)\s*=\s*(.*)$') {
                Set-Item -Path "env:$($matches[1])" -Value ($matches[2].Trim().Trim("'").Trim('"'))
            }
        }
    }
    if (-not $env:NVIDIA_API_KEY) { Fail "NVIDIA_API_KEY not found in $EnvFile" }
    Remove-Item env:LLM_BASE_URL, env:LLM_API_KEY -ErrorAction SilentlyContinue
    if ($Model) { $env:LLM_MODEL = $Model }

    # ---------- check the model supports tool calling; fall back if not ----------
    Say "Checking the NVIDIA model can call tools..."
    & $venvPy -m sahayak.check_llm
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Configured model didn't work for tool calling; trying nvidia/nemotron-3-super-120b-a12b" -ForegroundColor Yellow
        $env:LLM_MODEL = "nvidia/nemotron-3-super-120b-a12b"
        & $venvPy -m sahayak.check_llm
        if ($LASTEXITCODE -ne 0) { Fail "No working NVIDIA model for tool calling. See the messages above." }
    }

    Say "Starting the backend on http://localhost:8000 ..."
    $env:SAHAYAK_SEARCH = "bm25"
    $env:ALLOWED_ORIGINS = "http://localhost:3000"
    $env:RATE_LIMIT_PER_10MIN = "200"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.ui.RawUI.WindowTitle='Sahayak backend'; Set-Location '$root'; & '$venvPy' -m uvicorn server.main:app --port 8000"

    Say "Starting the frontend on http://localhost:3000 ..."
    $env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
    Remove-Item env:NEXT_PUBLIC_MOCK -ErrorAction SilentlyContinue
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.ui.RawUI.WindowTitle='Sahayak frontend'; Set-Location '$root\web'; npm run dev"
}

# ---------- open the browser when ready ----------
Say "Waiting for the app to come up..."
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://localhost:3000" | Out-Null; $ok = $true; break } catch {}
}
if ($ok) {
    Say "Ready! Opening http://localhost:3000"
    Start-Process "http://localhost:3000"
    Write-Host "Close the 'Sahayak backend' and 'Sahayak frontend' windows to stop." -ForegroundColor Green
} else {
    Write-Host "The frontend didn't respond yet. Check the 'Sahayak frontend' window, then open http://localhost:3000 yourself." -ForegroundColor Yellow
}
