# stop-all.ps1 - stop the bot stack.
# Stops the HuanMeng bot process and ONLY the NapCat QQ instance.
# The personal QQ instance is identified by its own profile path and is never touched.
# ASCII-only on purpose (BOM-less script files get mis-decoded by Windows PowerShell).

$ErrorActionPreference = 'Continue'
$NapProfile = 'D:\QQBot\QQProfile'
$BotDir     = 'D:\QQBot\huanmeng'

Write-Host '=== Stopping HuanMeng bot ==='
$botCount = 0
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -like "*$BotDir*") {
        Write-Host ("  killing python.exe PID {0}" -f $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $botCount++
    }
}
if ($botCount -eq 0) { Write-Host '  no running bot process found' }

Write-Host ''
Write-Host '=== Stopping NapCat QQ instance (isolated profile) ==='
# only main QQ processes carry the --user-data-dir switch pointing at our profile
$napCount = 0
Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
    if ($_.CommandLine -and $_.CommandLine -like "*$NapProfile*" -and $_.CommandLine -notmatch '--type=') {
        Write-Host ("  killing QQ.exe PID {0}" -f $_.ProcessId)
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        $napCount++
    }
}
if ($napCount -eq 0) { Write-Host '  no NapCat QQ instance found' }

Start-Sleep -Seconds 3
Write-Host ''
Write-Host '=== Remaining state ==='
$qq = @(Get-Process QQ -ErrorAction SilentlyContinue)
Write-Host ("  QQ processes still alive: {0}  (your personal QQ is expected to remain)" -f $qq.Count)
foreach ($p in 8099, 6099) {
    $l = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    if ($l) { Write-Host ("  port {0}: still listening" -f $p) } else { Write-Host ("  port {0}: released" -f $p) }
}
Write-Host ''
Write-Host 'Done.'
