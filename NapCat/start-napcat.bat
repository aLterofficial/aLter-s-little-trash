@echo off
rem start-napcat.bat - launch QQ NT with the NapCat hook in an ISOLATED QQ profile,
rem                    with automatic quick login (no QR scan on every start).
rem
rem Why isolated: QQ derives its Electron user-data-dir from the Windows known-folder API
rem (NOT the %APPDATA% env var - that was tried and does not work). If your personal QQ is
rem running, both instances would share one profile and the 2nd instance crashes right after
rem QR login confirmation. NapCatWinBootMain forwards one extra argv to QQ.exe, so we spend
rem that single slot on --user-data-dir.
rem
rem Why the loader template: because that one slot is taken by --user-data-dir, NapCat would
rem otherwise receive "-q --user-data-dir=..." and mistake it for an account name, forcing a
rem QR scan on every start. loadNapCat.template.js injects the real "-q <account>" into
rem process.argv before napcat.mjs loads; see the comments in that file.
rem
rem ASCII-only on purpose: .bat/.ps1 without BOM get mis-decoded by Windows PowerShell.
chcp 65001 >nul

rem --- unattended login: account + password fallback (MD5 only, no plaintext) ---
set "NAPCAT_QUICK_ACCOUNT="<BOT_QQ>"<BOT_QQ>"
set "NAPCAT_QUICK_PASSWORD_MD5="<QQ_PASSWORD_MD5>"
cd /d "%~dp0"

set "NAP_PROFILE=D:\QQBot\QQProfile"
if not exist "%NAP_PROFILE%" mkdir "%NAP_PROFILE%"

set "NAPCAT_PATCH_PACKAGE=%cd%\qqnt.json"
set "NAPCAT_LOAD_PATH=%cd%\loadNapCat.js"
set "NAPCAT_INJECT_PATH=%cd%\NapCatWinBootHook.dll"
set "NAPCAT_LAUNCHER_PATH=%cd%\NapCatWinBootMain.exe"
set "NAPCAT_MAIN_PATH=%cd%\napcat.mjs"

rem --- regenerate the loader from the template (it carries the -q account injection) ---
if not exist "%cd%\loadNapCat.template.js" (
    echo [start-napcat] ERROR: loadNapCat.template.js missing
    exit /b 1
)
copy /y "%cd%\loadNapCat.template.js" "%NAPCAT_LOAD_PATH%" >nul

rem locate QQ.exe: prefer the registry uninstall string, fall back to the default dir
set "QQPath="
for /f "tokens=2*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QQ" /v "UninstallString" 2^>nul') do (
    for %%b in ("%%~b") do set "QQPath=%%~dpbQQ.exe"
)
if not defined QQPath set "QQPath=C:\Program Files\Tencent\QQNT\QQ.exe"
if not exist "%QQPath%" (
    echo [start-napcat] QQ.exe not found at "%QQPath%"
    exit /b 1
)

echo [start-napcat] QQ         = %QQPath%
echo [start-napcat] QQ profile = %NAP_PROFILE%  (isolated from your personal QQ)
echo [start-napcat] quick-login account injected by loadNapCat.js
echo [start-napcat] starting...

"%NAPCAT_LAUNCHER_PATH%" "%QQPath%" "%NAPCAT_INJECT_PATH%" --user-data-dir=%NAP_PROFILE%
echo [start-napcat] NapCatWinBootMain exited with code %ERRORLEVEL%
