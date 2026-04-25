@echo off
setlocal
set "PROJECT_ROOT=%~dp0..\.."
set "BACKEND_ROOT=%~dp0.."

if not exist "%PROJECT_ROOT%\captp_env\Scripts\activate.bat" (
  echo [ERROR] Python env not found: %PROJECT_ROOT%\captp_env
  exit /b 1
)

call "%PROJECT_ROOT%\captp_env\Scripts\activate.bat"
cd /d "%BACKEND_ROOT%"
set CAPTP_RUNTIME_PROFILE=cpu
uvicorn main:app --reload --host 0.0.0.0 --port 6063
