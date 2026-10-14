$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe') -or -not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
        throw 'Run .\scripts\setup.ps1 first.'
    }
    Write-Host 'Triage Desk: http://127.0.0.1:8000 — press Ctrl+C to stop.'
    & '.\.venv\Scripts\python.exe' -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1
} finally { Pop-Location }
