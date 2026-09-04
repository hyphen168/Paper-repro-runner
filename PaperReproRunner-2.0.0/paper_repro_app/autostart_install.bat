@echo off
REM 开机自启（手机随时直连）：把"最小化启动远程模式"快捷方式装入启动文件夹
chcp 65001 >nul
setlocal
set "SRC=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LNK=%STARTUP%\PaperReproRemote.lnk"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%LNK%');" ^
  "$s.TargetPath = 'cmd.exe';" ^
  "$s.Arguments = '/c cd /d \"%SRC%\" ^&^& start \"\" /min cmd /c \"%SRC%start_app.bat\" --expose lan --no-browser';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Paper Repro Runner 远程常驻';" ^
  "$s.Save()"

if exist "%LNK%" (
    echo [OK] 开机自启已安装（下次开机自动以局域网模式常驻，含访问口令保护）。
    echo      立即启动：请手动运行 start_app_remote.bat 或重启电脑。
) else (
    echo [失败] 快捷方式创建失败，请手动把 start_app_remote.bat 的快捷方式放入：
    echo       %STARTUP%
)
pause
