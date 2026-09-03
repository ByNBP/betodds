@echo off
REM Kurulum bittikten sonra sunucuyu tekrar baslatir (yerel mod).
cd /d "%~dp0"
if not exist "runtime\python\python.exe" (
  echo Once KURULUM-OFFLINE.bat calistirin.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0KURULUM-OFFLINE.ps1" -Native %*
if errorlevel 1 pause
