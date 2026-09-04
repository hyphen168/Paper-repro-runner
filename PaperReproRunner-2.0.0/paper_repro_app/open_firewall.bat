@echo off
REM 放行 8505 端口入站（手机局域网访问用；需以管理员运行）
netsh advfirewall firewall add rule name="Paper Repro LAN 8505" dir=in action=allow protocol=TCP localport=8505 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [OK] 防火墙已放行 8505 端口。
) else (
    echo [提示] 自动放行失败，请手动操作：
    echo    Windows 安全中心 - 防火墙和网络保护 - 允许应用通过防火墙
    echo    添加本目录 .venv\Scripts\python.exe 或选择「专用网络」允许。
)
pause
