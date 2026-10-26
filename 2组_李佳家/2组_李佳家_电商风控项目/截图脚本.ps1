# 电商风险控制系统 - 一键重跑 8 张测试截图
# 前置：Python 3.12 + Chrome；chrome_shot.ps1 位于同级 _工具 目录
# 用法：在 PowerShell 中执行 .\截图脚本.ps1

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DeliveryRoot = Split-Path -Parent $Root
$ShotTool = Join-Path $DeliveryRoot '_工具\chrome_shot.ps1'
$ShotDir = Join-Path $Root '测试截图'
$BaseUrl = 'http://127.0.0.1:8713'
$env:PYTHONIOENCODING = 'utf-8'

if (-not (Test-Path $ShotTool)) {
    Write-Host ('[错误] 未找到截图工具：' + $ShotTool) -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $ShotDir)) {
    New-Item -ItemType Directory -Force -Path $ShotDir | Out-Null
}

function Test-Service {
    try {
        $health = Invoke-RestMethod -Uri ($BaseUrl + '/api/health') -TimeoutSec 2
        return ($health.status -eq 'ok')
    } catch {
        return $false
    }
}

if (-not (Test-Service)) {
    Write-Host '[启动] 未检测到服务，正在后台启动 uvicorn ...' -ForegroundColor Yellow
    Start-Process -FilePath 'python' `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8713') `
        -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
    $ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Service) { $ready = $true; break }
    }
    if (-not $ready) {
        Write-Host '[错误] 服务启动超时，请手动执行 启动.ps1 检查错误。' -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host '[启动] 服务已就绪。' -ForegroundColor Green
}

$Pages = @(
    @{ Name = '01_风险检查_高风险结果.png'; Url = $BaseUrl + '/#/check?demo=1' },
    @{ Name = '02_规则管理_规则列表.png';   Url = $BaseUrl + '/#/rules' },
    @{ Name = '03_案件管理_案件列表.png';   Url = $BaseUrl + '/#/cases' },
    @{ Name = '04_案件详情_人工审核.png';   Url = $BaseUrl + '/#/cases?demo=1' },
    @{ Name = '05_黑名单管理.png';          Url = $BaseUrl + '/#/blacklist' },
    @{ Name = '06_用户画像.png';            Url = $BaseUrl + '/#/profile?demo=1' },
    @{ Name = '07_运营看板.png';            Url = $BaseUrl + '/#/dashboard' },
    @{ Name = '08_接口文档.png';            Url = $BaseUrl + '/docs' }
)

Write-Host ''
Write-Host '开始生成测试截图（每张等待 8 秒，确保 API 与图表渲染完成）...' -ForegroundColor Cyan
$results = @()
foreach ($page in $Pages) {
    $outFile = Join-Path $ShotDir $page.Name
    # Chrome 在部分机器会向 stderr 输出扩展注册表警告，PS 5.1 下需临时放宽错误策略
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $ShotTool -Url $page.Url -OutFile $outFile -Width 1440 -Height 1150 -WaitMs 8000 2>$null
    } finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if (-not (Test-Path $outFile)) {
        Write-Host ('[错误] 截图未生成：' + $page.Name) -ForegroundColor Red
        exit 1
    }
    $size = (Get-Item $outFile).Length
    $ok = $size -gt 40960
    $results += [pscustomobject]@{
        File = $page.Name
        SizeKB = [math]::Round($size / 1KB, 1)
        Pass = $ok
    }
    if (-not $ok) {
        Write-Host ('[警告] 文件偏小，请检查页面：' + $page.Name) -ForegroundColor Yellow
    }
    Start-Sleep -Milliseconds 600
}

Write-Host ''
Write-Host '================ 截图结果 ================' -ForegroundColor Cyan
$results | Format-Table -AutoSize
$failed = ($results | Where-Object { -not $_.Pass }).Count
if ($failed -gt 0) {
    Write-Host ('[失败] ' + $failed + ' 张截图小于 40KB，请检查。') -ForegroundColor Red
    exit 1
}
Write-Host ('[完成] 8 张截图已保存至：' + $ShotDir) -ForegroundColor Green
Write-Host '注意：01 会真实写入一条风险检查记录，建议在干净的演示库上重跑截图。' -ForegroundColor DarkGray
