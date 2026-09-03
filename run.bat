@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (echo Execute setup.bat primeiro.& exit /b 1)
.venv\Scripts\python.exe main.py %*
endlocal

