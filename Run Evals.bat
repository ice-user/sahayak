@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-evals.ps1" %*
pause
