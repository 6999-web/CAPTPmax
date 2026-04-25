@echo off
start "CAPTP Backend CPU" cmd /k "call "%~dp0run_backend_cpu.bat""
start "CAPTP Frontend" cmd /k "call "%~dp0run_frontend.bat""

