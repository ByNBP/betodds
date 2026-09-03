@echo off
REM BetOdds - cevrimdisi kurulum. Cift tiklayarak calistirin.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0KURULUM-OFFLINE.ps1" %*
if errorlevel 1 pause
