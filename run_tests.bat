@echo off
rem 智膳 AI - run all tests (see scripts\run_tests.ps1 for details)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_tests.ps1"
if errorlevel 1 pause
