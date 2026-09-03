@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
.venv\Scripts\python.exe -m ruff check app.py paper_repro_app scripts tests --select F,B --ignore B007,B005 --output-format concise
if errorlevel 1 (
  echo.
  echo [Lint] 发现问题，请修复后重试。
  pause
)
