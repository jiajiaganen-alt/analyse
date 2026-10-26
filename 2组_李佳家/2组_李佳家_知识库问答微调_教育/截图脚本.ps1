# -*- mode: powershell -*-
# 一键重新生成实验报告并截图（Windows PowerShell 5.1 可用）
$ErrorActionPreference = 'Continue'
Set-Location $PSScriptRoot

Write-Host '[1/2] 生成实验报告...'
python scripts/make_report.py

$chrome = @(
    'C:\Program Files\Google\Chrome\Application\chrome.exe',
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw '未找到 Chrome 或 Edge' }

$shotDir = Join-Path $PSScriptRoot '测试截图'
if (-not (Test-Path $shotDir)) { New-Item -ItemType Directory -Path $shotDir | Out-Null }

$rootUrl = 'file:///' + (($PSScriptRoot -replace '\\', '/'))
$shots = @(
    @{ File = '01_实验总览.png';            Page = 'index.html';      Height = 1200 },
    @{ File = '02_数据集构建.png';          Page = 'dataset.html';    Height = 1730 },
    @{ File = '03_训练过程与损失曲线.png';   Page = 'training.html';   Height = 1700 },
    @{ File = '04_评测指标对比.png';        Page = 'evaluation.html'; Height = 1880 },
    @{ File = '05_样例对比_基线与微调.png';  Page = 'samples.html';    Height = 1650 }
)

Write-Host '[2/2] 截图中...'
foreach ($shot in $shots) {
    $out = Join-Path $shotDir $shot.File
    if (Test-Path $out) { Remove-Item $out -Force }
    $profile = Join-Path $env:TEMP ('ft-shot-' + [guid]::NewGuid().ToString('N'))
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    & $chrome --headless=new --disable-gpu --hide-scrollbars --no-first-run `
        --force-device-scale-factor=1 --window-size="1440,$($shot.Height)" `
        --virtual-time-budget=3000 --user-data-dir="$profile" --screenshot="$out" `
        "$rootUrl/report/$($shot.Page)" 2>$null | Out-Null
    $ErrorActionPreference = $previous
    for ($i = 0; $i -lt 30 -and -not (Test-Path $out); $i++) { Start-Sleep -Milliseconds 200 }
    Remove-Item $profile -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path $out)) { throw "截图失败：$($shot.File)" }
    Write-Host ("[OK] {0}" -f $shot.File)
}
Write-Host '完成，截图位于 测试截图/'
