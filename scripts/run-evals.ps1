# Runs every Sahayak eval against NVIDIA and saves the output to evals\results\.
# Double-click "Run Evals.bat" (in the project folder). Takes roughly 20-40 minutes.
param(
    [string]$Models = "",              # comma-separated; default: your configured model + two Llama models
    [string]$GuardModel = "nvidia/nemotron-3-nano-30b-a3b",
    [int]$Repeat = 2,
    [string]$EnvFile = ""
)
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
$py = "$root\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "No .venv found. Run 'Start Sahayak.bat' once first (it installs everything)." -ForegroundColor Red; exit 1 }

# NVIDIA key from your other project's .env (never printed)
if (-not $EnvFile) { $EnvFile = Join-Path (Split-Path -Parent $root) "source-trail\backend\.env" }
if (-not $env:NVIDIA_API_KEY) {
    foreach ($line in Get-Content $EnvFile) {
        if ($line -match '^\s*(NVIDIA_API_KEY|NVIDIA_MODEL)\s*=\s*(.*)$') {
            Set-Item -Path "env:$($matches[1])" -Value ($matches[2].Trim().Trim("'").Trim('"'))
        }
    }
}
if (-not $env:NVIDIA_API_KEY) { Write-Host "NVIDIA_API_KEY not found in $EnvFile" -ForegroundColor Red; exit 1 }
Remove-Item env:LLM_BASE_URL, env:LLM_API_KEY, env:LLM_MODEL -ErrorAction SilentlyContinue

if (-not $Models) {
    $list = @()
    if ($env:NVIDIA_MODEL) { $list += $env:NVIDIA_MODEL }
    $list += "nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-nano-30b-a3b"   # Llama 3.x returned HTTP 410 for this key in our first run
    $Models = ($list | Select-Object -Unique) -join ","
}
$out = "$root\evals\results"
New-Item -ItemType Directory -Force $out | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = "$out\all-evals-$stamp.txt"

function Step($title, [string[]]$pyArgs) {
    $line = "`n========== $title ==========`n> python $($pyArgs -join ' ')"
    Write-Host $line -ForegroundColor Cyan
    Add-Content -Path $log -Value $line -Encoding UTF8
    $t0 = Get-Date
    # Add-Content keeps the log UTF-8 (Tee-Object -Append writes UTF-16 on Windows PowerShell 5.1)
    & $py @pyArgs 2>&1 | ForEach-Object { $s = "$_"; Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }
    $secs = [int]((Get-Date) - $t0).TotalSeconds
    Add-Content -Path $log -Value "(exit $LASTEXITCODE, ${secs}s)" -Encoding UTF8
}

Add-Content -Path $log -Value "Sahayak eval run $stamp | models: $Models | guard model: $GuardModel" -Encoding UTF8

# Which models can actually call tools?
foreach ($m in $Models.Split(",")) { Step "check_llm $m" @("-m", "sahayak.check_llm", "--model", $m) }

# 1. Latency + quality across models
Step "bench_latency" @("-m", "evals.bench_latency", "--models", $Models, "--repeat", "$Repeat")

# 2. Full agent eval on each model (saves answers for reading)
foreach ($m in $Models.Split(",")) { Step "run_agent_evals $m" @("-m", "evals.run_agent_evals", "--model", $m) }

# 3. Off-topic guard, full stack
$env:TOPIC_GUARD_MODEL = $GuardModel
Step "run_topic_eval (full)" @("-m", "evals.run_topic_eval", "--layer", "full", "--list-misses")

# 4. Search quality (downloads a ~220 MB embedding model the first time)
Step "run_retrieval_eval" @("-m", "evals.run_retrieval_eval")

Write-Host "`nDone. Everything is in $log (and the JSON files next to it)." -ForegroundColor Green
Write-Host "Tell Claude 'evals done' so it can read the results." -ForegroundColor Green
