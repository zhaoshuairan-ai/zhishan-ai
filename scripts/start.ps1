<#
  智膳 AI · 全场景健康膳食管家
  一键启动（生产静态托管模式）

  说明：
  - 本脚本兼容中文目录、空格目录；
  - 所有路径变量均通过 Join-Path 构造，并在调用时使用引号；
  - 前端由后端 8000 端口直接托管，不依赖 Vite；
  - 由 start.bat 调用，脚本本身不额外等待按键。
#>

param(
    [switch]$Reset
)

$ErrorActionPreference = 'Stop'

# 使用 .NET 解析绝对路径，避免中文/空格被截断
$Root = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$BackendDir = Join-Path -Path $Root -ChildPath 'backend'
$FrontendDir = Join-Path -Path $Root -ChildPath 'frontend'
$FrontendDist = Join-Path -Path $FrontendDir -ChildPath 'dist'
$FrontendIndex = Join-Path -Path $FrontendDist -ChildPath 'index.html'
$VenvDir = Join-Path -Path $BackendDir -ChildPath '.venv'
$VenvPython = Join-Path -Path $VenvDir -ChildPath 'Scripts\python.exe'
$LogDir = Join-Path -Path $Root -ChildPath 'logs'
$EnvFile = Join-Path -Path $Root -ChildPath '.env'
$EnvExample = Join-Path -Path $Root -ChildPath '.env.example'
$DbPath = Join-Path -Path $Root -ChildPath 'data\food_safety.db'

Set-Location -LiteralPath $Root

# 统一控制台编码，避免中文乱码
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = 'utf-8'
} catch { }

function Write-Step([string]$Text) {
    Write-Host "`n$Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "  [OK] $Text" -ForegroundColor Green
}

function Write-Warn([string]$Text) {
    Write-Host "  [注意] $Text" -ForegroundColor Yellow
}

function Fail([string]$Text, [string]$Hint) {
    Write-Host "`n[错误] $Text" -ForegroundColor Red
    if ($Hint) {
        Write-Host "       $Hint" -ForegroundColor Yellow
    }
    exit 1
}

function Get-ProjectPython {
    # 优先 project venv；不存在时再找系统 Python
    if (Test-Path -LiteralPath $VenvPython) {
        return $VenvPython
    }

    $pythonCmd = Get-Command 'python' -ErrorAction SilentlyContinue
    if ($pythonCmd -and $pythonCmd.Source) {
        return $pythonCmd.Source
    }

    $pyCmd = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($pyCmd -and $pyCmd.Source) {
        return $pyCmd.Source
    }

    return $null
}

Clear-Host
Write-Host "============================================================" -ForegroundColor Green
Write-Host "   智膳 AI · 全场景健康膳食管家" -ForegroundColor Green
Write-Host "   多模态识别 · 健康画像 · 智能配餐 Agent" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Green
Write-Host "   项目目录：$Root" -ForegroundColor DarkGray

# ---------- 1. 环境检查 ----------
Write-Step "[1/6] 检查 Python 运行环境 ..."

$PythonExe = Get-ProjectPython
if (-not $PythonExe) {
    Fail "未检测到 Python。" "请安装 Python 3.11/3.12，并勾选 Add Python to PATH。"
}

$PythonVersion = & $PythonExe -c "import sys; print('.'.join(map(str, sys.version_info[:2])))" 2>$null
if (-not $PythonVersion) {
    Fail "无法运行 Python。" "请确认 Python 已正确安装并加入 PATH。"
}

$VersionParts = $PythonVersion.Split('.')
if ([int]$VersionParts[0] -lt 3 -or ([int]$VersionParts[0] -eq 3 -and [int]$VersionParts[1] -lt 11)) {
    Fail "Python 版本过低（当前 $PythonVersion，需要 3.11 及以上）。" "请升级 Python 后重试。"
}
Write-Ok "Python $PythonVersion"
Write-Ok "Python 路径：$PythonExe"

# ---------- 2. 虚拟环境 ----------
Write-Step "[2/6] 准备 Python 虚拟环境 ..."

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "  首次运行，正在创建 backend\.venv（约 10-30 秒）..."
    & $PythonExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) {
        Fail "虚拟环境创建失败。" "请确认 Python 安装完整（包含 venv 模块）。"
    }
}
Write-Ok "虚拟环境就绪：$VenvDir"

# ---------- 3. 环境变量 ----------
Write-Step "[3/6] 检查 .env 配置 ..."

if (-not (Test-Path -LiteralPath $EnvFile)) {
    if (-not (Test-Path -LiteralPath $EnvExample)) {
        Fail "未找到 .env.example。" "请恢复项目根目录下的 .env.example 后重试。"
    }
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Ok "已根据 .env.example 生成 .env"
} else {
    Write-Ok ".env 已存在"
}

# ---------- 4. 依赖 ----------
Write-Step "[4/6] 检查后端依赖 ..."

& $VenvPython -c "import flask, flask_cors, flask_sqlalchemy, pydantic" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  正在安装后端依赖（首次较慢，约 1-3 分钟）..."
    $Requirements = Join-Path -Path $BackendDir -ChildPath 'requirements.txt'
    & $VenvPython -m pip install -r $Requirements --disable-pip-version-check -q
    if ($LASTEXITCODE -ne 0) {
        Fail "后端依赖安装失败。" "请检查网络后重试：backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt"
    }
}
Write-Ok "后端依赖已就绪"

# ---------- 5. 数据库 ----------
Write-Step "[5/6] 初始化数据库与知识库 ..."

if ($Reset) {
    Write-Warn "已启用 --reset：正在清理旧数据库并重新生成演示数据 ..."

    foreach ($port in @(5000, 8000, 5173)) {
        $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($listeners) {
            $listeners | ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Start-Sleep -Milliseconds 800

    if (Test-Path -LiteralPath $DbPath) {
        Remove-Item -LiteralPath $DbPath -Force
        Write-Ok "旧数据库已删除"
    }
}

$InitScript = Join-Path -Path $BackendDir -ChildPath 'init_db.py'
& $VenvPython $InitScript
if ($LASTEXITCODE -ne 0) {
    Fail "数据库初始化失败。" "请查看上方错误信息，必要时备份后删除 data\food_safety.db 重试。"
}

# ---------- 6. 启动服务 ----------
Write-Step "[6/6] 启动服务 ..."

if (-not (Test-Path -LiteralPath $FrontendIndex)) {
    Fail "未找到前端构建产物：$FrontendIndex" "请先在 frontend 目录执行 npm run build，再运行 start.bat。"
}

$BackendPort = 8000
$existing = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Warn "端口 $BackendPort 已被占用，尝试结束旧进程..."
    $existing | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 800
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$BackendLog = Join-Path -Path $LogDir -ChildPath 'backend.log'
$BackendErr = Join-Path -Path $LogDir -ChildPath 'backend.err.log'
$EnvFileForBackend = $EnvFile

# 只修改子进程环境变量，不修改 .env 文件
$env:APP_PORT = "$BackendPort"
$env:SERVE_FRONTEND = '1'

$BackendProc = Start-Process -FilePath $VenvPython `
    -ArgumentList @('wsgi.py') `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput $BackendLog `
    -RedirectStandardError $BackendErr `
    -WindowStyle Hidden `
    -PassThru

Write-Host "  后端进程 PID：$($BackendProc.Id)"
Write-Host "  前端页面由后端 $BackendPort 端口静态托管"
Write-Host "  日志文件：$BackendLog"

Write-Host "  等待后端就绪 ..." -NoNewline
$Healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/health" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) {
            $Healthy = $true
            break
        }
    } catch { }
    Write-Host "." -NoNewline
}
Write-Host ""

$LanIp = (
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254*' -and
        $_.PrefixOrigin -ne 'WellKnown'
    } |
    Select-Object -First 1
).IPAddress

Write-Host "`n============================================================" -ForegroundColor Green
if ($Healthy) {
    Write-Host "   启动成功！" -ForegroundColor Green
} else {
    Write-Host "   服务未完全启动，请查看日志进行排查。" -ForegroundColor Yellow
    if (Test-Path -LiteralPath $BackendErr) {
        Write-Host "`n  ---- backend.err.log（最后 15 行）----" -ForegroundColor DarkGray
        Get-Content -LiteralPath $BackendErr -Tail 15 -ErrorAction SilentlyContinue |
            ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    }
}

Write-Host "============================================================" -ForegroundColor Green
Write-Host "   电脑访问：   http://localhost:$BackendPort" -ForegroundColor White
Write-Host "   后端接口：   http://127.0.0.1:$BackendPort/api/health" -ForegroundColor White
if ($LanIp) {
    Write-Host "   手机访问：   http://$LanIp`:$BackendPort   （手机与电脑需连同一个 Wi-Fi）" -ForegroundColor White
}
Write-Host "   演示账号：   demo / demo123456" -ForegroundColor White
Write-Host "   停止服务：   双击 stop.bat" -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor Green

if ($Healthy -and -not $env:NO_BROWSER) {
    Start-Process "http://localhost:$BackendPort"
}

if (-not $Healthy) {
    exit 1
}
exit 0
