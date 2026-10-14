$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
    Push-Location -LiteralPath 'frontend'
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
    Write-Host 'Setup complete. Set ADMIN_PASSWORD and OPENROUTER_API_KEY in .env, then run .\scripts\start.ps1.'
} finally { Pop-Location }
