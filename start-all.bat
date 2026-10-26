@echo off
rem start-all.bat - start NapCat (isolated QQ profile) then the HuanMeng bot.
rem ASCII-only on purpose (BOM-less .bat files get mis-decoded by Windows PowerShell).
chcp 65001 >nul
setlocal

echo ============================================================
echo  Starting QQ bot stack
echo ============================================================

echo [1/2] Starting NapCat (QQ profile: D:\QQBot\QQProfile)...
start "NapCat" cmd /c "cd /d D:\QQBot\NapCat && start-napcat.bat > napcat-console.log 2>&1"

echo       waiting 25s for QQ login / OneBot WebSocket on 127.0.0.1:8099 ...
timeout /t 25 /nobreak >nul

echo [2/2] Starting HuanMeng bot...
start "HuanMeng" cmd /c "cd /d D:\QQBot\huanmeng && .venv\Scripts\python.exe main.py > bot-console.log 2>&1"

echo.
echo  Done.
echo    NapCat WebUI : http://127.0.0.1:6099/webui?token=<NAPCAT_WEBUI_TOKEN>
echo    OneBot WS    : ws://127.0.0.1:8099/
echo    Bot logs     : D:\QQBot\huanmeng\bot-console.log
echo    NapCat logs  : D:\QQBot\NapCat\napcat-console.log
echo.
echo  To stop everything, run stop-all.ps1
endlocal
