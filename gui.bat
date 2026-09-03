@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (echo Execute setup.bat primeiro.& pause & exit /b 1)
start "" .venv\Scripts\pythonw.exe gui.py
endlocal

