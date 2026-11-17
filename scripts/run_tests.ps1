<#
  智膳 AI · 一键运行全部自动化测试
  由 run_tests.bat 调用。
  说明：会先检查服务是否在运行；接口冒烟测试需要后端已启动。
#>

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $env:PYTHONIOENCODING = 'utf-8'
} catch { }

$venvPython = Join-Path $Root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "[错误] 未找到 backend\.venv，请先运行 start.bat。" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

$results = @()

function Run-Step([string]$Name, [scriptblock]$Action) {
    Write-Host "`n============================================================" -ForegroundColor Cyan
    Write-Host "  $Name" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    & $Action
    $code = $LASTEXITCODE
    $script:results += [pscustomobject]@{ Name = $Name; Code = $code }
    if ($code -eq 0) { Write-Host "  -> 通过" -ForegroundColor Green }
    else { Write-Host "  -> 失败（退出码 $code）" -ForegroundColor Red }
}

# 1) 后端测试
Run-Step "1/4 后端 pytest（102 项）" {
    Push-Location (Join-Path $Root 'backend')
    & $venvPython -m pytest -q
    $global:pytestCode = $LASTEXITCODE
    Pop-Location
    $global:LASTEXITCODE = $global:pytestCode
}

# 2) 前端类型检查
Run-Step "2/4 前端类型检查（vue-tsc）" {
    Push-Location (Join-Path $Root 'frontend')
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        & npm run type-check
    } elseif (Get-Command pnpm -ErrorAction SilentlyContinue) {
        & pnpm run type-check
    } else {
        Write-Host "  未找到 npm/pnpm，跳过前端类型检查" -ForegroundColor Yellow
        $global:LASTEXITCODE = 1
    }
    $global:tscCode = $LASTEXITCODE
    Pop-Location
    $global:LASTEXITCODE = $global:tscCode
}

# 3) 前端生产构建
Run-Step "3/4 前端生产构建（vite build）" {
    Push-Location (Join-Path $Root 'frontend')
    if (Get-Command npm -ErrorAction SilentlyContinue) { & npm run build }
    elseif (Get-Command pnpm -ErrorAction SilentlyContinue) { & pnpm run build }
    else { $global:LASTEXITCODE = 1 }
    $global:buildCode = $LASTEXITCODE
    Pop-Location
    $global:LASTEXITCODE = $global:buildCode
}

# 4) 接口冒烟（需要后端已启动）
Run-Step "4/4 接口冒烟测试（需后端已启动）" {
    $baseUrl = 'http://127.0.0.1:5000'
    if (-not (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue)) {
        if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) {
            $baseUrl = 'http://127.0.0.1:8000'
        } else {
            Write-Host "  未检测到运行中的后端（5000/8000），跳过接口冒烟测试。" -ForegroundColor Yellow
            Write-Host "  请先运行 start.bat 或 start_prod.bat。" -ForegroundColor Yellow
            $global:LASTEXITCODE = 2
            return
        }
    }
    & $venvPython (Join-Path $Root 'scripts\api_smoke_test.py') --base-url $baseUrl
    $global:LASTEXITCODE = $LASTEXITCODE
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "  测试汇总" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
foreach ($item in $results) {
    $mark = if ($item.Code -eq 0) { "[通过]" } elseif ($item.Code -eq 2) { "[跳过]" } else { "[失败]" }
    $color = if ($item.Code -eq 0) { 'Green' } elseif ($item.Code -eq 2) { 'Yellow' } else { 'Red' }
    Write-Host ("  {0} {1}" -f $mark, $item.Name) -ForegroundColor $color
}
$failed = ($results | Where-Object { $_.Code -ne 0 -and $_.Code -ne 2 }).Count
if ($failed -eq 0) { Write-Host "`n  全部通过（跳过的项请手动确认）" -ForegroundColor Green }
else { Write-Host "`n  $failed 项失败，请查看上方日志" -ForegroundColor Red }

Write-Host "`n提示：响应式检查请单独运行 scripts\responsive_check.py（需要前后端已启动）。" -ForegroundColor DarkGray
Read-Host "`n按回车键退出"
if ($failed -eq 0) { exit 0 } else { exit 1 }
