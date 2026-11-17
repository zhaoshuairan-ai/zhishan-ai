@echo off
rem 智膳 AI - stop local services (see scripts\stop.ps1 for details)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
if errorlevel 1 pause
