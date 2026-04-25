@echo off
setlocal
cd /d "%~dp0..\..\frontend"
npm run dev -- --host 0.0.0.0 --port 6062
