@echo off
echo Starting FastAPI Backend...
start "CAPTP Backend" cmd /k "call ""%~dp0captp_env\Scripts\activate.bat"" && cd /d ""%~dp0backend"" && uvicorn main:app --reload --host 101.33.210.169 --port 6063"

echo Starting Vue Frontend...
start "CAPTP Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev -- --host 101.33.210.169 --port 6062"

echo All services started! Close this window when done.
pause
