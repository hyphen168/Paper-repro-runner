@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PY_CMD=py -3
) else (
    set PY_CMD=python
)

%PY_CMD% start_app.py
exit /b %ERRORLEVEL%
