$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host "YuQing Analysis Platform"
Write-Host "  Console : http://127.0.0.1:8714/#/console"
Write-Host "  API Doc : http://127.0.0.1:8714/docs"
Write-Host "  Press Ctrl+C to stop."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8714
