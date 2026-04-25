@echo off
setlocal
if not exist "%~dp0captp_env\Scripts\activate.bat" (
  echo [ERROR] Python env not found: %~dp0captp_env
  exit /b 1
)
call "%~dp0captp_env\Scripts\activate.bat"
cd /d "%~dp0backend"
set CAPTP_RUNTIME_PROFILE=cpu
uvicorn main:app --reload --host 101.33.210.169 --port 6063

