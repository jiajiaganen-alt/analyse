# 电商风险控制系统 - 一键启动
# 用法：右键“使用 PowerShell 运行”，或在 PowerShell 中执行 .\启动.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$env:PYTHONIOENCODING = 'utf-8'

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  RiskShield · 电商风险控制系统' -ForegroundColor White
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    Write-Host '[错误] 未找到 python，请先安装 Python 3.12 并加入 PATH。' -ForegroundColor Red
    exit 1
}

Write-Host ('[1/3] Python: ' + (& python --version)) -ForegroundColor Green
if (Test-Path (Join-Path $Root 'data\risk_control.db')) {
    Write-Host '[2/3] 已检测到数据库，沿用现有演示数据。' -ForegroundColor Green
} else {
    Write-Host '[2/3] 首次启动：将自动建库并灌入 30 个用户、60 笔订单、40 条评估、12 个案件。' -ForegroundColor Yellow
}
Write-Host '[3/3] 正在启动 FastAPI 服务（端口 8713）...' -ForegroundColor Green
Write-Host ''
Write-Host '  控制台地址: http://127.0.0.1:8713' -ForegroundColor Cyan
Write-Host '  接口文档:   http://127.0.0.1:8713/docs' -ForegroundColor Cyan
Write-Host '  健康检查:   http://127.0.0.1:8713/api/health' -ForegroundColor Cyan
Write-Host ''
Write-Host '  按 Ctrl+C 停止服务。' -ForegroundColor DarkGray
Write-Host ''

& python -m uvicorn app.main:app --host 127.0.0.1 --port 8713
