@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Paper Repro Runner

rem ============================================================
rem  查找本机可用的 Python 解释器（PATH + 常见安装位置）
rem ============================================================
set "PY_CMD="

rem 1) py 启动器（官方安装包自带）
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 set "PY_CMD=py -3"

rem 2) python 在 PATH 中
if not defined PY_CMD (
    where python >nul 2>nul
    if %ERRORLEVEL% EQU 0 set "PY_CMD=python"
)

rem 3) 常见安装目录（不在 PATH 时也能找到）
if not defined PY_CMD (
    for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
        if exist "%%P\python.exe" set "PY_CMD=%%P\python.exe"
    )
)

if not defined PY_CMD goto :nopython

rem ============================================================
rem  启动引导（版本检查/虚拟环境/依赖安装都在 start_app.py 内完成）
rem ============================================================
%PY_CMD% start_app.py %*
if errorlevel 1 (
    echo.
    echo [Paper Repro] 启动失败，请将上方错误信息截图反馈给开发者。
    echo.
    pause
)
exit /b %ERRORLEVEL%

:nopython
echo.
echo ============================================================
echo  未检测到 Python 环境。
echo  本应用需要 Python 3.11 或更高版本（建议 3.12）。
echo.
echo  请任选一种方式安装：
echo    1. 官网下载:  https://www.python.org/downloads/
echo       （安装时务必勾选 "Add python.exe to PATH"）
echo    2. Win11 命令行:  winget install Python.Python.3.12
echo.
echo  安装完成后重新双击 start_app.bat 即可。
echo ============================================================
start "" "https://www.python.org/downloads/"
pause
exit /b 1
