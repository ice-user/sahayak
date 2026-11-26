@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-sahayak.ps1" %*
pause
