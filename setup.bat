@echo off
setlocal
cd /d "%~dp0"
echo Preparing AirPresent environment...
where py >nul 2>nul
if errorlevel 1 (
    python -m venv .venv
) else (
    py -3.12 -m venv .venv
)
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" main.py --download-model
if errorlevel 1 goto failed
echo Setup complete. Double-click run.bat to start.
pause
exit /b 0
:failed
echo Setup failed. Check Python 3.12, network access and the error above.
pause
exit /b 1
