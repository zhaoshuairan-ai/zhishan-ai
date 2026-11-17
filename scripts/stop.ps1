<#
  智膳 AI · 停止本地服务
  由 stop.bat 调用。
#>

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "============================================================" -ForegroundColor Green
Write-Host "   智膳 AI · 停止本地服务" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

$ports = @(5000, 5173, 4173, 8000)
$stopped = 0
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        try {
            $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
            Write-Host "  结束进程 PID $($conn.OwningProcess)（$($proc.ProcessName)，端口 $port）" -ForegroundColor Yellow
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction Stop
            $stopped++
        } catch {
            Write-Host "  无法结束 PID $($conn.OwningProcess)，请手动在任务管理器结束。" -ForegroundColor Red
        }
    }
}

foreach ($title in @('智膳-后端', '智膳-前端')) {
    Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "*$title*" } | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        $stopped++
    }
}

if ($stopped -eq 0) {
    Write-Host "  没有发现运行中的服务（端口 5000 / 5173 / 4173 / 8000 均空闲）。" -ForegroundColor DarkGray
} else {
    Write-Host "`n  已停止 $stopped 个进程。" -ForegroundColor Green
}
Write-Host "  数据已保存在 data\ 与 uploads\ 目录，不会丢失。" -ForegroundColor DarkGray
Read-Host "`n按回车键退出"
