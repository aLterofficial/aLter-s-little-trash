#Requires -Version 5.1
<#
    set_qq_password.ps1 - enable NapCat's password fallback for unattended cold start.

    What it does:
      1. reads the QQ password from a file (default D:\QQBot\_qqpw.txt) or prompts securely
      2. computes the 32-hex MD5 that NapCat expects (NAPCAT_QUICK_PASSWORD_MD5)
      3. writes NAPCAT_QUICK_ACCOUNT / NAPCAT_QUICK_PASSWORD_MD5 into start-napcat.bat
      4. deletes the password file so the plaintext does not linger on disk
      5. prints only a masked MD5 - never the password

    The plaintext password is never stored; only its MD5 (what NapCat's
    passwordLogin() consumes, see napcat.mjs:82149-82157).

    ASCII-only on purpose (BOM-less .ps1 files get mis-decoded by Windows PowerShell).

    Usage:
      powershell -ExecutionPolicy Bypass -File D:\QQBot\tools\set_qq_password.ps1
      powershell -ExecutionPolicy Bypass -File D:\QQBot\tools\set_qq_password.ps1 -Remove
#>
param(
    [string]$PasswordFile = 'D:\QQBot\_qqpw.txt',
    [string]$Account      = '',
    [string]$Bat          = 'D:\QQBot\NapCat\start-napcat.bat',
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'

if (-not $Account) { throw 'missing -Account: pass the bot QQ number, e.g. -Account 123456789' }

if (-not (Test-Path $Bat)) { throw "start-napcat.bat not found: $Bat" }

# ---- collect the MD5 -------------------------------------------------------
$md5hex = $null
if (-not $Remove) {
    $pw = $null
    if (Test-Path $PasswordFile) {
        $pw = (Get-Content $PasswordFile -Raw -Encoding UTF8).Trim()
        Write-Host ("[1/4] read password from {0} ({1} chars)" -f $PasswordFile, $pw.Length)
    } else {
        Write-Host "[1/4] no password file found, prompting (input is hidden, not echoed)"
        $sec = Read-Host -Prompt '      QQ password' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
        try   { $pw = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    if ([string]::IsNullOrEmpty($pw)) { throw "empty password, aborting" }

    $md5 = [Security.Cryptography.MD5]::Create()
    try   { $bytes = $md5.ComputeHash([Text.Encoding]::UTF8.GetBytes($pw)) }
    finally { $md5.Dispose() }
    $md5hex = ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''

    if ($md5hex -notmatch '^[a-f0-9]{32}$') { throw "MD5 computation failed" }
    Write-Host ("[2/4] computed MD5: {0}...{1} (32 hex, masked)" -f $md5hex.Substring(0,6), $md5hex.Substring(28))
} else {
    Write-Host "[1/4] -Remove: will strip password fallback from the launcher"
}

# ---- patch the bat --------------------------------------------------------
$lines = Get-Content $Bat -Encoding ASCII
$kept = $lines | Where-Object {
    $_ -notmatch '^\s*set\s+"?NAPCAT_QUICK_ACCOUNT=' -and
    $_ -notmatch '^\s*set\s+"?NAPCAT_QUICK_PASSWORD_MD5='
}

if (-not $Remove) {
    $anchor = -1
    for ($i = 0; $i -lt $kept.Count; $i++) {
        if ($kept[$i] -match '^chcp 65001') { $anchor = $i; break }
    }
    if ($anchor -lt 0) { throw "anchor line 'chcp 65001' not found in $Bat" }

    $inject = @(
        '',
        'rem --- unattended login: account + password fallback (MD5 only, no plaintext) ---',
        ('set "NAPCAT_QUICK_ACCOUNT={0}"' -f $Account),
        ('set "NAPCAT_QUICK_PASSWORD_MD5={0}"' -f $md5hex)
    )
    $out = @()
    $out += $kept[0..$anchor]
    $out += $inject
    $out += $kept[($anchor + 1)..($kept.Count - 1)]
    $kept = $out
    Write-Host "[3/4] injected NAPCAT_QUICK_ACCOUNT + NAPCAT_QUICK_PASSWORD_MD5 into the launcher"
} else {
    Write-Host "[3/4] removed password fallback lines from the launcher"
}

# keep the file plain ASCII + CRLF; write without BOM
$text = ($kept -join "`r`n") + "`r`n"
[IO.File]::WriteAllText($Bat, $text, (New-Object Text.ASCIIEncoding))
Write-Host "[4/4] wrote $Bat"

# ---- clean up the plaintext ----------------------------------------------
if (-not $Remove -and (Test-Path $PasswordFile)) {
    Remove-Item $PasswordFile -Force
    Write-Host ("      deleted plaintext password file: {0}" -f $PasswordFile)
}

Write-Host ''
Write-Host 'Done. Verify with:'
Write-Host ('  Select-String -Path "{0}" -Pattern "NAPCAT_QUICK_"' -f $Bat)
