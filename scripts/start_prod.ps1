<#
  智膳 AI · 生产模式启动（单服务，Flask 托管前端构建产物）
  由 start_prod.bat 调用。默认监听 0.0.0.0:8000。
#>

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Fail([string]$Text, [string]$Hint) {
    Write-Host "`n[错误] $Text" -ForegroundColor Red
    if ($Hint) { Write-Host "       $Hint" -ForegroundColor Yellow }
    Read-Host "按回车键退出"
    exit 1
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host "   智膳 AI · 生产模式启动（waitress + 前端静态托管）" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

$venvPython = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) { Fail "未找到 Python 虚拟环境。" "请先运行 start.bat 完成首次安装。" }
if (Get-Command npm -ErrorAction SilentlyContinue) { $pkgManager = 'npm' }
elseif (Get-Command pnpm -ErrorAction SilentlyContinue) { $pkgManager = 'pnpm' }
else { Fail "未检测到 npm 或 pnpm。" "生产模式需要先构建前端，请安装 Node.js 18+。" }

Write-Host "`n[1/3] 构建前端 ..." -ForegroundColor Cyan
Push-Location (Join-Path $Root 'frontend')
if (-not (Test-Path 'node_modules')) { & $pkgManager install }
& $pkgManager run build
$buildCode = $LASTEXITCODE
Pop-Location
if ($buildCode -ne 0) { Fail "前端构建失败。" "请查看上方日志（常见原因：Node 版本过低、依赖未安装完整）。" }

Write-Host "`n[2/3] 初始化数据库（幂等）..." -ForegroundColor Cyan
& $venvPython (Join-Path $Root 'backend\init_db.py')
if ($LASTEXITCODE -ne 0) { Fail "数据库初始化失败。" "请查看上方错误信息。" }

Write-Host "`n[3/3] 启动 waitress ..." -ForegroundColor Cyan
$env:SERVE_FRONTEND = '1'
$env:APP_PORT = '8000'

$lanIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254*' } |
    Select-Object -First 1).IPAddress

Write-Host "============================================================" -ForegroundColor Green
Write-Host "   电脑访问： http://localhost:8000" -ForegroundColor White
Write-Host "   健康检查： http://localhost:8000/api/health" -ForegroundColor White
if ($lanIp) { Write-Host "   局域网：   http://$lanIp`:8000" -ForegroundColor White }
Write-Host "   按 Ctrl+C 停止服务" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Green

Push-Location (Join-Path $Root 'backend')
try {
    & (Join-Path $Root 'backend\.venv\Scripts\waitress-serve.exe') --listen=0.0.0.0:8000 --threads=8 --channel-timeout=300 wsgi:app
} catch {
    Fail "waitress 启动失败。" "请确认已安装：backend\.venv\Scripts\python.exe -m pip install waitress"
} finally {
    Pop-Location
}
Read-Host "`n服务已退出，按回车键关闭窗口"
