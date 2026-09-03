@echo off
REM BetOdds - cift tiklayarak calistirin.
REM PowerShell'in imzasiz betik kisitini bu oturum icin atlar.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0KURULUM.ps1" %*
if errorlevel 1 pause
