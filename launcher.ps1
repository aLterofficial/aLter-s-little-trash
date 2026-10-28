#Requires -Version 5.1
<#
    幻梦 QQ 机器人 —— 一键启动 / 停止 / 状态
    NapCat (QQ 协议) + 幻梦 (Python 框架)

    用法:
      launcher.ps1              启动（已在运行则只汇报状态，不会重复启动）
      launcher.ps1 -Stop        停止（不会动你的个人 QQ）
      launcher.ps1 -Status      仅查看状态

    设计要点（都是踩坑后加的）:
      * NapCat 用独立 QQ 数据目录 D:\QQBot\QQProfile，绝不碰你的个人 QQ。
      * 启动 NapCat 时写「带时间戳」的日志：固定文件名会被上一次残留进程锁住，
        导致 cmd 的重定向失败、批处理根本没执行（曾表现为「点了没反应」）。
      * 启动前清理「父进程已死」的孤儿 NapCat 进程，它们会锁文件并抢 profile。
      * 识别 NapCat 实例**只认命令行里有 QQProfile**，不用可执行路径判断
        （QQNT 与 qqnt 仅大小写不同，-like 不区分大小写，会误杀你的个人 QQ）。
#>
param(
    [switch]$Stop,
    [switch]$Status
)

$ErrorActionPreference = 'Continue'

# ── 路径 ─────────────────────────────────────────────
$Root      = 'D:\QQBot'
$NapDir    = Join-Path $Root 'NapCat'
$BotDir    = Join-Path $Root 'huanmeng'
$QqProfile = Join-Path $Root 'QQProfile'
$PyExe     = Join-Path $BotDir '.venv\Scripts\python.exe'
$NapBat    = Join-Path $NapDir 'start-napcat.bat'
$BotLog    = Join-Path $BotDir 'bot-console.log'
$WebUiJson = Join-Path $NapDir 'config\webui.json'

# ── 控制台 UTF-8 ─────────────────────────────────────
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    & chcp.com 65001 > $null 2>&1
} catch { }
$Host.UI.RawUI.WindowTitle = '幻梦 QQ 机器人'

# ── 输出 ─────────────────────────────────────────────
function Write-Title($text) {
    Write-Host ''
    Write-Host ('  ' + ('-' * 58)) -ForegroundColor DarkGray
    Write-Host ("  $text") -ForegroundColor Cyan
    Write-Host ('  ' + ('-' * 58)) -ForegroundColor DarkGray
}
function Write-Ok($t)    { Write-Host "  [OK]   $t" -ForegroundColor Green }
function Write-Bad($t)   { Write-Host "  [FAIL] $t" -ForegroundColor Red }
function Write-Warn2($t) { Write-Host "  [WARN] $t" -ForegroundColor Yellow }
function Write-Info($t)  { Write-Host "         $t" -ForegroundColor Gray }

# 双击运行时等按键；输入被重定向时直接跳过，避免阻塞
function Wait-Key {
    try { if ([Console]::IsInputRedirected) { return } } catch { return }
    try { $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown') } catch { }
}

# ── 进程探测（关键：只认 QQProfile，绝不误伤个人 QQ） ──
function Get-NapCatProc {
    Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like '*QQProfile*' -and $_.CommandLine -notmatch '--type=' }
}
function Get-NapCatOrphan {
    # 父进程已不存在的 NapCat QQ 主进程：会锁住日志、抢 profile，必须先清掉
    Get-NapCatProc | Where-Object {
        -not (Get-Process -Id $_.ParentProcessId -ErrorAction SilentlyContinue)
    }
}
function Get-BotProc {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$BotDir*" }
}
function Test-PortListen([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}
function Test-LinkUp([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Established -ErrorAction SilentlyContinue)
}
function Get-WebUiUrl {
    $token = ''
    if (Test-Path $WebUiJson) {
        try { $token = (Get-Content $WebUiJson -Raw -Encoding UTF8 | ConvertFrom-Json).token } catch { }
    }
    if ($token) { "http://127.0.0.1:6099/webui?token=$token" } else { 'http://127.0.0.1:6099/webui' }
}
function Get-LatestNapLog {
    Get-ChildItem (Join-Path $NapDir 'napcat-*.log') -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}

# ── 状态 ─────────────────────────────────────────────
function Show-Status {
    $nap    = @(Get-NapCatProc)
    $bot    = @(Get-BotProc)
    $listen = Test-PortListen 8099
    $link   = Test-LinkUp 8099

    Write-Title '运行状态'
    if ($nap.Count -gt 0) { Write-Ok  "NapCat       运行中 (PID $($nap.ProcessId -join ','))" }
    else                  { Write-Bad 'NapCat       未运行' }

    if ($listen) { Write-Ok  'OneBot 8099  已监听' }
    else         { Write-Bad 'OneBot 8099  未监听（QQ 未登录，或 NapCat 未启动）' }

    if ($link)                { Write-Ok  '幻梦         已连接 NapCat' }
    elseif ($bot.Count -gt 0) { Write-Warn2 '幻梦         进程在，但未连上 NapCat' }
    else                      { Write-Bad '幻梦         未运行' }

    $mine = @(Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" -ErrorAction SilentlyContinue |
              Where-Object { $_.CommandLine -and $_.CommandLine -notmatch 'QQProfile' -and $_.CommandLine -notmatch '--type=' })
    if ($mine.Count -gt 0) { Write-Info "你的个人 QQ 正常（PID $($mine.ProcessId -join ',')），未受影响" }

    Write-Host ''
    Write-Info "NapCat 登录页 : $(Get-WebUiUrl)"
    $log = Get-LatestNapLog
    if ($log) { Write-Info "NapCat 日志   : $log" }
    Write-Info "幻梦日志      : $BotLog"
    Write-Info "Web 日志台    : http://127.0.0.1:58888"
}

# ── 等待 ─────────────────────────────────────────────
function Wait-ForPort {
    param([int]$Port, [int]$TimeoutSec, [string]$Label)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $lastNote = 0
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        if (Test-PortListen $Port) { return $true }
        $e = [int]$sw.Elapsed.TotalSeconds
        if ($e -gt 0 -and $e % 10 -eq 0 -and $e -ne $lastNote) {
            $lastNote = $e
            Write-Host ''
            Write-Info "$Label 已等待 ${e}s / ${TimeoutSec}s ..."
            Write-Host '         ' -NoNewline
        } else {
            Write-Host '.' -NoNewline -ForegroundColor DarkGray
        }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

# ── 停止 ─────────────────────────────────────────────
function Stop-Stack {
    Write-Title '停止服务'
    $n = 0
    foreach ($p in @(Get-BotProc)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Info "已停止幻梦 (PID $($p.ProcessId))"; $n++
    }
    if ($n -eq 0) { Write-Info '幻梦本来就没在运行' }

    $n = 0
    foreach ($p in @(Get-NapCatProc)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Info "已停止 NapCat (PID $($p.ProcessId))"; $n++
    }
    foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name='NapCatWinBootMain.exe'" -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; $n++
    }
    if ($n -eq 0) { Write-Info 'NapCat 本来就没在运行' }

    Start-Sleep -Seconds 5
    Write-Host ''
    if (Test-PortListen 8099) { Write-Warn2 '端口 8099 仍在监听，稍等几秒' } else { Write-Ok '端口已释放' }
    Write-Ok '已停止。你的个人 QQ 未受影响。'
}

# ── 启动 ─────────────────────────────────────────────
function Start-Stack {
    Write-Title '启动服务'

    if (-not (Test-Path $PyExe))  { Write-Bad "找不到 Python: $PyExe"; return }
    if (-not (Test-Path $NapBat)) { Write-Bad "找不到 NapCat 启动脚本: $NapBat"; return }

    # --- 清理孤儿 NapCat 进程（会锁日志、抢 profile） ---
    $orphans = @(Get-NapCatOrphan)
    if ($orphans.Count -gt 0) {
        Write-Warn2 "清理 $($orphans.Count) 个残留的 NapCat 进程（父进程已退出）"
        foreach ($o in $orphans) {
            Stop-Process -Id $o.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Info "已清理 PID $($o.ProcessId)"
        }
        Start-Sleep -Seconds 4
    }

    # --- NapCat ---
    $nap = @(Get-NapCatProc)
    if ($nap.Count -gt 0) {
        Write-Ok "NapCat 已在运行 (PID $($nap.ProcessId -join ',')），跳过启动"
    } else {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $log   = Join-Path $NapDir "napcat-$stamp.log"
        Write-Info '正在启动 NapCat（独立 QQ 数据目录）…'
        Write-Info "本次日志: $log"

        # 用单个字符串传参 + 双引号包裹：数组形式会让 cmd 的重定向解析失败、静默不执行
        $cmdLine = "/c `"`"$NapBat`" > `"$log`" 2>&1`""
        Start-Process -FilePath 'cmd.exe' -ArgumentList $cmdLine `
            -WorkingDirectory $NapDir -WindowStyle Hidden

        Write-Host '      等待 OneBot 8099 ' -NoNewline -ForegroundColor Gray
        if (-not (Wait-ForPort -Port 8099 -TimeoutSec 45 -Label 'OneBot 8099')) {
            Write-Host ''
            Write-Warn2 'QQ 尚未登录 —— 正在打开 NapCat 登录页'
            Write-Info '请用「机器人小号」的手机 QQ 扫码（不是你的主号）'
            Write-Info (Get-WebUiUrl)
            Start-Process (Get-WebUiUrl) | Out-Null
            Write-Host '      等待扫码登录 ' -NoNewline -ForegroundColor Gray
            Write-Info ''
            Write-Info '（NapCat 每约 2 分钟自动换一张二维码，请在浏览器里用最新那张扫）'
            if (-not (Wait-ForPort -Port 8099 -TimeoutSec 900 -Label '扫码登录')) {
                Write-Host ''
                Write-Bad '仍未登录，已超时（等了 15 分钟）。扫码成功后重新运行本程序即可。'
                Write-Info "排查请看日志: $log"
                return
            }
        }
        Write-Host ''
        Write-Ok 'NapCat 就绪，8099 已监听'
    }

    # --- 幻梦 ---
    $bot = @(Get-BotProc)
    if ($bot.Count -gt 0) {
        Write-Ok "幻梦已在运行 (PID $($bot.ProcessId -join ',')），跳过启动"
    } else {
        Write-Info '正在启动幻梦框架…'
        # -X utf8 = Python UTF-8 模式。幻梦日志含 emoji，而 stdout 重定向到文件时
        # 默认用系统 locale(GBK)，编不出 emoji 会抛 UnicodeEncodeError，在日志里刷出
        # 大段「假堆栈」（功能正常，纯噪声）。加此参数后 stdout 与日志文件均为 UTF-8。
        $botCmd = "/c `"`"$PyExe`" -X utf8 main.py > `"$BotLog`" 2>&1`""
        Start-Process -FilePath 'cmd.exe' -ArgumentList $botCmd `
            -WorkingDirectory $BotDir -WindowStyle Hidden

        Write-Host '      等待幻梦连接 NapCat ' -NoNewline -ForegroundColor Gray
        $sw = [Diagnostics.Stopwatch]::StartNew()
        $linked = $false
        while ($sw.Elapsed.TotalSeconds -lt 45) {
            if (Test-LinkUp 8099) { $linked = $true; break }
            Write-Host '.' -NoNewline -ForegroundColor DarkGray
            Start-Sleep -Milliseconds 800
        }
        Write-Host ''
        if ($linked) { Write-Ok '幻梦已连接 NapCat' }
        else         { Write-Warn2 '幻梦启动较慢或连接失败，请查看日志' }
    }

    Show-Status
    Write-Host ''
    Write-Host '  机器人在群里被 @ 时就会回复。' -ForegroundColor White
}

# ── 入口 ─────────────────────────────────────────────
Clear-Host
Write-Host ''
Write-Host '   +------------------------------------------------------+' -ForegroundColor DarkMagenta
Write-Host '   |         幻梦 QQ 机器人  ·  NapCat + DeepSeek         |' -ForegroundColor Magenta
Write-Host '   +------------------------------------------------------+' -ForegroundColor DarkMagenta

if ($Status) {
    Show-Status
    Write-Host ''
    Write-Host '  按任意键关闭…' -ForegroundColor DarkGray
    Wait-Key
}
elseif ($Stop) {
    Stop-Stack
    Write-Host ''
    Write-Host '  按任意键关闭…' -ForegroundColor DarkGray
    Wait-Key
}
else {
    Start-Stack
    Write-Host ''
    Write-Host '  按任意键关闭本窗口（服务继续在后台运行）。' -ForegroundColor DarkGray
    Wait-Key
}
