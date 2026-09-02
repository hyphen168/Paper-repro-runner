@echo off
setlocal
cd /d "%~dp0.."
python scripts/start_release.py
if errorlevel 1 (
    echo.
    echo [Release] Startup failed. Please check Python installation and dependency setup.
    pause
)
