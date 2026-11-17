@echo off
rem 智膳 AI - production mode: build frontend then serve with waitress
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_prod.ps1"
if errorlevel 1 pause
