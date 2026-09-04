@echo off
REM 论文复现助手 · 手机局域网访问启动（0.0.0.0 + 访问口令门）
cd /d "%~dp0"
call "%~dp0start_app.bat" --expose lan
