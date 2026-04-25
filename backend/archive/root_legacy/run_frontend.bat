@echo off
setlocal
cd /d "%~dp0frontend"
npm run dev -- --host 101.33.210.169 --port 6062

