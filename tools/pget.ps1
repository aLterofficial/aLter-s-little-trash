# pget.ps1 - Parallel chunked downloader for networks that throttle per-connection.
# Splits the file into N ranges, fetches them with concurrent curl processes,
# verifies each chunk's byte count, retries failures, then merges in order.
# ASCII-only on purpose: .ps1 files without BOM get mis-decoded by Windows PowerShell.
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [int]$Threads = 16,
    [int]$Retries = 8
)

$ErrorActionPreference = 'Continue'
Write-Host ("PowerShell {0}" -f $PSVersionTable.PSVersion)

$dir = Join-Path $env:TEMP ("pget_" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $dir | Out-Null

Write-Host "[1/3] Probing file size..."
$hdr = & curl.exe -s -I -L --max-time 30 $Url 2>&1 | Out-String
$m = [regex]::Match($hdr, '(?im)^content-length:\s*(\d+)')
if (-not $m.Success) { throw "Cannot read content-length; aborting chunked download." }
$total = [int64]$m.Groups[1].Value
Write-Host ("      total {0} bytes ({1:N2} MB), splitting into {2} chunks" -f $total, ($total / 1MB), $Threads)

$chunk = [math]::Ceiling($total / $Threads)
$jobs = @()
for ($i = 0; $i -lt $Threads; $i++) {
    $from = [int64]$i * $chunk
    if ($from -ge $total) { break }
    $to = [math]::Min($from + $chunk - 1, $total - 1)
    $expect = $to - $from + 1
    $out = Join-Path $dir ("c{0:D3}.part" -f $i)
    $jobs += Start-Job -ScriptBlock {
        param($url, $from, $to, $expect, $out, $retries)
        for ($try = 1; $try -le $retries; $try++) {
            if (Test-Path $out) { Remove-Item $out -Force -ErrorAction SilentlyContinue }
            & curl.exe -s -L --max-time 900 -r "$from-$to" -o $out $url 2>$null | Out-Null
            if ((Test-Path $out) -and (Get-Item $out).Length -eq $expect) {
                return "OK   $from-$to ($expect bytes, attempt $try)"
            }
            Start-Sleep -Seconds 2
        }
        $got = if (Test-Path $out) { (Get-Item $out).Length } else { 0 }
        return "FAIL $from-$to got $got expected $expect"
    } -ArgumentList $Url, $from, $to, $expect, $out, $Retries
}

Write-Host ("[2/3] Downloading {0} chunks concurrently..." -f $jobs.Count)
$sw = [Diagnostics.Stopwatch]::StartNew()
$jobs | Wait-Job | Out-Null
$results = $jobs | Receive-Job
$jobs | Remove-Job -Force -ErrorAction SilentlyContinue
$sw.Stop()
$results | ForEach-Object { Write-Host "      $_" }

$failed = @($results | Where-Object { $_ -like 'FAIL*' })
if ($failed.Count -gt 0) {
    Write-Host ("      {0} chunk(s) failed; leaving temp dir for retry: {1}" -f $failed.Count, $dir)
    exit 1
}
Write-Host ("      done in {0:N1}s, aggregate {1:N0} KB/s" -f $sw.Elapsed.TotalSeconds, ($total / $sw.Elapsed.TotalSeconds / 1KB))

Write-Host "[3/3] Merging chunks..."
if (Test-Path $OutFile) { Remove-Item $OutFile -Force }
$outStream = [System.IO.File]::Create($OutFile)
try {
    Get-ChildItem $dir -Filter 'c*.part' | Sort-Object Name | ForEach-Object {
        $fs = [System.IO.File]::OpenRead($_.FullName)
        try { $fs.CopyTo($outStream) } finally { $fs.Dispose() }
    }
} finally { $outStream.Dispose() }

$finalSize = (Get-Item $OutFile).Length
Write-Host ("      merged: {0} bytes ({1:N2} MB)" -f $finalSize, ($finalSize / 1MB))

$ok = $true
if ($finalSize -ne $total) { Write-Host "      MISMATCH: expected $total"; $ok = $false }
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($OutFile)
    $entryCount = $zip.Entries.Count
    $zip.Dispose()
    Write-Host "      ZIP structure valid, $entryCount entries"
} catch {
    Write-Host "      ZIP CORRUPT: $($_.Exception.Message)"
    $ok = $false
}

Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
if ($ok) { Write-Host "`nSUCCESS: $OutFile" } else { Write-Host "`nFAILED validation"; exit 1 }
