@echo off
start "CAPTP Backend GPU" cmd /k "call "%~dp0run_backend_gpu.bat""
start "CAPTP Frontend" cmd /k "call "%~dp0run_frontend.bat""

