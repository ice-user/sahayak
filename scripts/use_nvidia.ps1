# Point Sahayak at NVIDIA's API using the key already in another project's .env.
# The key is read into this PowerShell session only; it is not copied or printed.
#
# Usage (note the leading dot, so the variables stay in your session):
#   . .\scripts\use_nvidia.ps1
#   . .\scripts\use_nvidia.ps1 -Model "nvidia/nemotron-3-super-120b-a12b"
#   . .\scripts\use_nvidia.ps1 -EnvFile "C:\path\to\other\.env"
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\..\source-trail\backend\.env"),
    [string]$Model = ""
)

if (-not (Test-Path $EnvFile)) { Write-Error "Not found: $EnvFile"; return }

foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*(NVIDIA_API_KEY|NVIDIA_MODEL)\s*=\s*(.*)$') {
        $value = $matches[2].Trim().Trim("'").Trim('"')
        Set-Item -Path "env:$($matches[1])" -Value $value
    }
}
if (-not $env:NVIDIA_API_KEY) { Write-Error "No NVIDIA_API_KEY in $EnvFile"; return }

# Clear other providers' settings so NVIDIA is used
Remove-Item env:LLM_BASE_URL, env:LLM_API_KEY -ErrorAction SilentlyContinue
if ($Model) { $env:LLM_MODEL = $Model } else { Remove-Item env:LLM_MODEL -ErrorAction SilentlyContinue }

$chosen = if ($Model) { $Model } elseif ($env:NVIDIA_MODEL) { $env:NVIDIA_MODEL } else { "nvidia/nemotron-3-super-120b-a12b" }
Write-Host "NVIDIA key loaded (not shown). Model: $chosen"
Write-Host "Next: python -m sahayak.check_llm"
