@echo off
REM 论文复现助手 · 公网远程访问启动（本机回环 + SSH 反向隧道）
REM 用法：1) 先在应用内完成 SSH 配置并注入公钥（免密）；2) 双击本脚本
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  步骤 1/2：启动应用（本机回环模式，供隧道转发）
echo ============================================================
start "Paper Repro App" cmd /c ""%~dp0start_app.bat" --expose tunnel"
echo.
echo  步骤 2/2：启动反向隧道（云机 127.0.0.1:18505 -^> 本机 8505）
echo  云机回环端口再用 AutoDL 控制台「自定义服务」映射为公网 URL。
echo ============================================================
"%~dp0.venv\Scripts\python.exe" "%~dp0tunnel_keepalive.py" --local-port 8505 --remote-port 18505
pause
