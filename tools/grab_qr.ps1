# grab_qr.ps1 - force a fresh NapCat login QR code and publish it as D:\QQBot\qrcode.jpg
# ASCII-only on purpose (BOM-less .ps1 files get mis-decoded by Windows PowerShell).
$ErrorActionPreference = 'Continue'

$NapDir = 'D:\QQBot\NapCat'
$Qr     = Join-Path $NapDir 'cache\qrcode.png'
$Out    = 'D:\QQBot\qrcode.jpg'

$nap = @(Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" -ErrorAction SilentlyContinue |
         Where-Object { $_.CommandLine -and $_.CommandLine -like '*QQProfile*' -and $_.CommandLine -notmatch '--type=' })
$listen = [bool](Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue)

$age = 9999
if (Test-Path $Qr) { $age = ((Get-Date) - (Get-Item $Qr).LastWriteTime).TotalSeconds }

$napTxt = 'not running'
if ($nap.Count -gt 0) { $napTxt = 'PID ' + ($nap.ProcessId -join ',') }
$lisTxt = 'not listening'
if ($listen) { $lisTxt = 'listening' }

Write-Host ('now        : ' + (Get-Date -Format 'HH:mm:ss'))
Write-Host ('NapCat     : ' + $napTxt)
Write-Host ('port 8099  : ' + $lisTxt)
Write-Host ('QR age     : ' + [math]::Round($age, 0) + ' s')

if ($listen) {
    Write-Host ''
    Write-Host 'RESULT: 8099 already listening - no QR needed.'
    exit 0
}

# determine baseline: if we restart NapCat, wait for the file to change from this point
$baseline = Get-Date '2000-01-01'
if (Test-Path $Qr) { $baseline = (Get-Item $Qr).LastWriteTime }

if ($age -gt 100) {
    Write-Host ''
    Write-Host 'QR is stale and NapCat stopped rotating - restarting NapCat to force a new code...'
    Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*QQProfile*' } |
        ForEach-Object {
            Write-Host ('  killing QQ PID ' + $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Get-CimInstance Win32_Process -Filter "Name='NapCatWinBootMain.exe'" -ErrorAction SilentlyContinue |
        ForEach-Object {
            Write-Host ('  killing NapCatWinBootMain PID ' + $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Seconds 7
    if (Test-Path $Qr) { $baseline = (Get-Item $Qr).LastWriteTime }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $log   = Join-Path $NapDir ('napcat-' + $stamp + '.log')
    $inner = '"' + (Join-Path $NapDir 'start-napcat.bat') + '" > "' + $log + '" 2>&1'
    $args  = '/c "' + $inner + '"'
    Write-Host ('  launching NapCat, log: ' + $log)
    Start-Process -FilePath 'cmd.exe' -ArgumentList $args -WorkingDirectory $NapDir -WindowStyle Hidden
} else {
    Write-Host ''
    Write-Host 'Existing QR is still fresh - capturing it directly.'
}

Write-Host ''
Write-Host 'waiting for a fresh QR file...'
$got = $false
for ($i = 0; $i -lt 55; $i++) {
    Start-Sleep -Seconds 2
    if (Get-NetTCPConnection -LocalPort 8099 -State Listen -ErrorAction SilentlyContinue) {
        Write-Host ''
        Write-Host 'FLASH: 8099 is now listening - someone scanned successfully.'
        exit 0
    }
    if ((Test-Path $Qr) -and ((Get-Item $Qr).LastWriteTime -gt $baseline)) { $got = $true; break }
    Write-Host '.' -NoNewline -ForegroundColor DarkGray
}
Write-Host ''

if ($got) {
    Copy-Item $Qr $Out -Force
    $f = Get-Item $Out
    $a = ((Get-Date) - $f.LastWriteTime).TotalSeconds
    Write-Host ('RESULT: fresh QR -> ' + $Out)
    Write-Host ('  generated : ' + $f.LastWriteTime.ToString('HH:mm:ss'))
    Write-Host ('  now       : ' + (Get-Date -Format 'HH:mm:ss'))
    Write-Host ('  age       : ' + [math]::Round($a, 0) + ' s')
    Write-Host ('  remaining : about ' + [math]::Round(123 - $a, 0) + ' s')
} else {
    Write-Host 'RESULT: failed to obtain a fresh QR - check the newest log under ' + $NapDir
}
