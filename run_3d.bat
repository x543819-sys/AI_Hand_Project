@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first to prepare the project environment.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m airpresent.viewer3d.server
if errorlevel 1 pause
