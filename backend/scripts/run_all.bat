@echo off
echo Starting FastAPI Backend...
start "CAPTP Backend" cmd /k "call ""%~dp0run_backend_cpu.bat"""

echo Starting Vue Frontend...
start "CAPTP Frontend" cmd /k "call ""%~dp0run_frontend.bat"""

echo All services started! Close this window when done.
pause
