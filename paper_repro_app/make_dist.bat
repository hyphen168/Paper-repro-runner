@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Paper Repro Runner - 打包分发

set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3"
if not defined PY_CMD (
    where python >nul 2>nul && set "PY_CMD=python"
)
if not defined PY_CMD (
    for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%P\python.exe" set "PY_CMD=%%P\python.exe"
    )
)
if not defined PY_CMD (
    echo 未检测到 Python，打包脚本需要 Python 3。
    pause
    exit /b 1
)

%PY_CMD% make_dist.py
if errorlevel 1 (
    echo.
    echo 打包失败，请检查上方错误信息。
    pause
)
pause
