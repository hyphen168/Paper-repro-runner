@echo off
chcp 65001 >nul
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PaperReproRemote.lnk"
if exist "%LNK%" (
    del "%LNK%"
    echo [OK] 已移除开机自启。
) else (
    echo [提示] 未找到自启项（可能未安装过）。
)
pause
