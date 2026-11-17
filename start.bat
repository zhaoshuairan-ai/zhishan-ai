@echo off
setlocal EnableExtensions
chcp 65001 >nul

rem Zhishan AI - one click start
rem Paths may contain Chinese characters and spaces.

cd /d "%~dp0"
if errorlevel 1 (
    echo.
    echo [ERROR] Cannot enter project directory:
    echo         %~dp0
    echo.
    pause
    exit /b 1
)

set "PS_ARGS="
if /I "%~1"=="--reset" set "PS_ARGS=-Reset"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %PS_ARGS%
set "APP_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%APP_EXIT_CODE%"=="0" (
    echo [ERROR] Startup script failed. Exit code: %APP_EXIT_CODE%
    echo Review the messages above or logs\backend.err.log.
) else (
    echo Startup script completed.
)

echo.
echo Press any key to close this window...
pause >nul
endlocal & exit /b %APP_EXIT_CODE%
