# prepare_github_publish.ps1
#
# 把 D:\QQBot 里「可以公开的部分」整理到 _publish_github\，并自动脱敏，
# 供你 git init / push 到 GitHub 留档。
#
# 设计原则：
#   1. **白名单**（只复制明确允许的东西），不是黑名单 —— 漏一个敏感文件代价太大。
#   2. 复制过程中**逐个文本文件脱敏**，并做正则兜底（任何 sk- 密钥、QQ 密码 MD5 都替换掉）。
#   3. 结束前**自检输出目录**：如果还能扫到敏感模式，直接报红并列出，绝不留隐患。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File D:\QQBot\tools\prepare_github_publish.ps1
#   加 -Keep 可以保留上次的输出目录（默认会清空重建）
#
param(
    [string]$Out = "D:\QQBot\_publish_github",
    [switch]$Keep
)

$ErrorActionPreference = 'Stop'
$Src = "D:\QQBot"
$Hm  = Join-Path $Src "huanmeng"

function Info($m) { Write-Host "  $m" }
function Ok($m)   { Write-Host "  [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }

# ── 1. 准备输出目录 ──────────────────────────────────────────
if ((Test-Path $Out) -and (-not $Keep)) {
    Remove-Item $Out -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Info "输出目录: $Out"

# ── 2. 脱敏规则 ──────────────────────────────────────────────
# 字面替换：**长的放前面**（否则 <BOT_QQ> 会被 <BOT_QQ> 先吃掉半边）
$Literal = [ordered]@{
    '<NAPCAT_WEBUI_TOKEN>' = '<NAPCAT_WEBUI_TOKEN>'
    '<BOT_QQ>'  = '<BOT_QQ>'
    '<BOT_QQ>'   = '<BOT_QQ>'
    '<OWNER_QQ>'   = '<OWNER_QQ>'
    '<MOM_QQ>'   = '<MOM_QQ>'
    '<FRIEND_QQ_1>'   = '<FRIEND_QQ_1>'
    '<FRIEND_QQ_2>'   = '<FRIEND_QQ_2>'
    '<GROUP_1>'    = '<GROUP_1>'
    '<GROUP_2>'   = '<GROUP_2>'
    '<GROUP_3>'   = '<GROUP_3>'
    '<GROUP_4>'   = '<GROUP_4>'
    '<GROUP_5>'    = '<GROUP_5>'
    '<GROUP_6>'    = '<GROUP_6>'
    '<GROUP_7>'    = '<GROUP_7>'
}

# 正则兜底：任何形式的 API key / 密码哈希 / 明文密码赋值
$RegexRules = @(
    @{ p = 'sk-[A-Za-z0-9_\-]{16,}';                       r = '<API_KEY>' }
    @{ p = '(?i)(NAPCAT_QUICK_PASSWORD_MD5\s*=\s*)"?[^\r\n"]*"?'; r = '$1"<QQ_PASSWORD_MD5>"' }
    @{ p = '(?i)(NAPCAT_QUICK_ACCOUNT\s*=\s*)"?[0-9]*"?';  r = '$1"<BOT_QQ>"' }
    @{ p = "(?i)(DEEPSEEK_KEY|RELAY_KEY|ZHIPU_KEY|AGNES_KEY|AGNES_API_KEY)\s*=\s*\S+"; r = '$1=<API_KEY>' }
    @{ p = "(?i)const ACCOUNT = '<BOT_QQ>']*'";                   r = "const ACCOUNT = '<BOT_QQ>'" }
)

function Invoke-Redact([string]$text) {
    foreach ($k in $Literal.Keys) { $text = $text.Replace($k, $Literal[$k]) }
    foreach ($rule in $RegexRules) { $text = [regex]::Replace($text, $rule.p, $rule.r) }
    return $text
}

# 只对这些扩展名做文本脱敏（二进制直接跳过）
$TextExt = @('.md', '.py', '.toml', '.json', '.txt', '.ps1', '.bat', '.js', '.html',
             '.css', '.yml', '.yaml', '.mermaid', '.env', '.example', '.cfg', '.ini')

$copied = 0; $redacted = 0

function Copy-One($srcPath, $dstPath) {
    $dir = Split-Path $dstPath -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $ext = [IO.Path]::GetExtension($srcPath).ToLower()
    if ($TextExt -contains $ext -or $ext -eq '') {
        $orig = Get-Content -LiteralPath $srcPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($null -ne $orig) {
            $new = Invoke-Redact $orig
            if ($new -ne $orig) { $script:redacted++ }
            # 用 UTF8 无 BOM 写回
            [IO.File]::WriteAllText($dstPath, $new, (New-Object Text.UTF8Encoding $false))
            return
        }
    }
    Copy-Item -LiteralPath $srcPath -Destination $dstPath -Force
}

# ── 3. 复制顶层可公开文件 ────────────────────────────────────
Info "`n[1/5] 顶层文件与脚本"
$TopFiles = @('README.md', 'SESSION-LOG.md', 'launcher.ps1', 'start-all.bat',
              'stop-all.ps1', 'bot.ico')
foreach ($f in $TopFiles) {
    $p = Join-Path $Src $f
    if (Test-Path $p) { Copy-One $p (Join-Path $Out $f); Ok $f }
    else { Warn "缺少 $f" }
}

# ── 在顶层 README 追加「来源与许可」声明 ────────────────────
# 发布别人的 MIT 项目时，保留版权声明之外，还应明确说明"这是部署留档 / 修改版"，
# 避免被误认为原创。
$readmeOut = Join-Path $Out 'README.md'
if (Test-Path $readmeOut) {
    $attrib = @"

---

## 来源与许可

本仓库是**部署留档**，核心框架并非本仓库作者原创：

- **HuanMeng · 幻梦** 来自开源项目
  [Trusler258/huanmeng-qqbot](https://github.com/Trusler258/huanmeng-qqbot)，
  采用 **MIT License**，版权归 **Trusler** 所有（见 ``huanmeng/LICENSE``）。
- 本仓库主要记录该框架**本地部署期间的配置调整、问题修复与排查文档**
  （见 ``SESSION-LOG.md``），不主张对上游框架的著作权。
- 再分发 / 二次使用请**保留 ``huanmeng/LICENSE``** 与其中的版权声明。

> 文档中的 QQ 号、群号、WebUI 令牌、密码哈希等**均已替换为占位符**
> （如 ``<BOT_QQ>`` / ``<OWNER_QQ>`` / ``<GROUP_1>`` / ``<NAPCAT_WEBUI_TOKEN>``），
> 请勿据此推断真实账号或凭据。
"@
    [IO.File]::AppendAllText($readmeOut, $attrib, (New-Object Text.UTF8Encoding $false))
    Ok "README.md 已追加来源与许可声明"
}

if (Test-Path (Join-Path $Src 'tools')) {
    Get-ChildItem (Join-Path $Src 'tools') -File -Recurse | ForEach-Object {
        Copy-One $_.FullName (Join-Path $Out ("tools\" + $_.Name))
    }
    Ok ("tools\ (" + (Get-ChildItem (Join-Path $Src 'tools') -File -Recurse).Count + " 个文件)")
}

# ── 4. 复制 huanmeng 源码（排除运行时）──────────────────────
Info "`n[2/5] huanmeng 源码"
$SkipDirs  = @('.venv', 'data', '__pycache__', '.git', 'node_modules', 'logs', '.pytest_cache')
$SkipFiles = @('adapter_config.toml', 'bot_config.toml', 'roles.toml', '.env',
               'game_web_secret', 'huanmeng.db', 'test_search_result.txt')
$hmCount = 0
Get-ChildItem $Hm -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring($Hm.Length + 1)
    $parts = $rel -split '\\'
    $skip = $false
    foreach ($d in $parts) {
        if ($SkipDirs -contains $d) { $skip = $true; break }
        if ($d -like '_backup-*')   { $skip = $true; break }
    }
    if (-not $skip) {
        if ($SkipFiles -contains $_.Name) { $skip = $true }
        if ($_.Name -like '.last-*') { $skip = $true }   # 备份指针文件，无意义
        if ($_.Extension -in @('.log', '.db', '.pyc')) { $skip = $true }
    }
    if (-not $skip) {
        Copy-One $_.FullName (Join-Path $Out ("huanmeng\" + $rel))
        $script:hmCount++
    }
}
Ok "huanmeng\ ($hmCount 个文件)"

# ── 5. 复制 data 里「属于源码/提示词」的部分 ─────────────────
Info "`n[3/5] data 中的提示词与模板（白名单）"
$DataAllow = @(
    'skills', 'templates',
    'self_knowledge.md', 'assistant_kb.md', 'update_log.md',
    'architecture.mermaid', 'data_stores.mermaid',
    'features.json',
    'faces\README.md', 'faces\_descriptions.json'
)
foreach ($item in $DataAllow) {
    $p = Join-Path (Join-Path $Hm 'data') $item
    if (-not (Test-Path $p)) { Warn "缺少 data\$item"; continue }
    if (Test-Path $p -PathType Container) {
        Get-ChildItem $p -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring((Join-Path $Hm 'data').Length + 1)
            Copy-One $_.FullName (Join-Path $Out ("huanmeng\data\" + $rel))
        }
        Ok "data\$item\"
    } else {
        Copy-One $p (Join-Path $Out ("huanmeng\data\" + $item))
        Ok "data\$item"
    }
}

# ── 6. 复制 NapCat 的部署脚本（不含二进制与配置）────────────
Info "`n[4/5] NapCat 部署脚本"
$NapCatFiles = @('start-napcat.bat', 'loadNapCat.template.js', 'KillQQ.bat',
                 'quickLoginExample.bat')
foreach ($f in $NapCatFiles) {
    $p = Join-Path (Join-Path $Src 'NapCat') $f
    if (Test-Path $p) { Copy-One $p (Join-Path $Out ("NapCat\" + $f)); Ok "NapCat\$f" }
    else { Warn "缺少 NapCat\$f" }
}

# ── 7. 写 .gitignore ─────────────────────────────────────────
Info "`n[5/5] 生成 .gitignore"
$gitignore = @'
# ── 运行时与数据（绝不入仓）──
.venv/
__pycache__/
*.pyc
data/*.json
data/*.db
data/*.jsonl
data/*.txt
data/*.png
data/memory_*.md
data/notes/
data/msglog/
data/stm/
data/img_temp/
data/agnes_output/
data/inspection/
data/stats*/
data/faces/*.png
data/faces/*.jpg
data/faces/*.gif
data/faces/*.webp

# ── 配置（只保留 example.* 模板）──
huanmeng/config/.env
huanmeng/config/adapter_config.toml
huanmeng/config/bot_config.toml
huanmeng/config/roles.toml
huanmeng/config/persona_data.json

# ── 备份与日志 ──
_backup-*/
*.log
*.bak
*.last-*

# ── 账号数据 ──
QQProfile/
QQProfile.bak-*/
_downloads/
qrcode.*
api key.txt

# ── NapCat 运行时 ──
NapCat/config/
NapCat/node_modules/
NapCat/*.exe
NapCat/*.dll
NapCat/**/*.log

# ── 系统 ──
Thumbs.db
desktop.ini
.DS_Store
'@
[IO.File]::WriteAllText((Join-Path $Out '.gitignore'), $gitignore, (New-Object Text.UTF8Encoding $false))
Ok ".gitignore"

# ── 8. 自检：输出目录里还有没有敏感内容 ─────────────────────
Info "`n════ 自检：扫描输出目录里残留的敏感内容 ════"
$problems = @()
$files = Get-ChildItem $Out -Recurse -File
foreach ($f in $files) {
    if ($TextExt -notcontains $f.Extension.ToLower()) { continue }
    $txt = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($null -eq $txt) { continue }
    foreach ($k in $Literal.Keys) {
        if ($txt.Contains($k)) { $problems += "$($f.FullName) 含 $k" }
    }
    # ★ 用 -cmatch（**区分大小写**），不要用 -match。
    #   踩过的坑：-match 默认不区分大小写，百度搜索结果 URL 里那种
    #   "...PsK-IA-b5HmY0A71TAPW5H00..." 的随机跟踪参数会被误判成 sk- 开头的 key，
    #   于是一份干净的文件也报红。真实的 DeepSeek key 是**小写** sk- + 长串字母数字。
    if ($txt -cmatch '(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}') { $problems += "$($f.FullName) 含 sk- 密钥" }
    if ($txt -match 'NAPCAT_QUICK_PASSWORD_MD5\s*=\s*"?[0-9a-fA-F]{16,}') { $problems += "$($f.FullName) 含密码 MD5" }
}

$totalMB = [math]::Round(((Get-ChildItem $Out -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host ""
Info ("文件总数: " + $files.Count + " | 体积: " + $totalMB + " MB | 脱敏过的文件: " + $redacted)
Write-Host ""
if ($problems.Count -eq 0) {
    Ok "自检通过：未发现残留的 QQ 号 / 令牌 / 密钥 / 密码哈希"
    $pushed = $Out.Replace('\', '/')
    Info "下一步："
    Info "  cd $Out"
    Info "  git init -b main"
    Info "  git add ."
    Info "  git commit -m 'archive: 幻梦部署留档（已脱敏）'"
    Info "  git remote add origin <你的仓库 URL>"
    Info "  git push -u origin main"
} else {
    Write-Host "  [FAIL] 自检发现 $($problems.Count) 处残留，**不要推送**：" -ForegroundColor Red
    $problems | Select-Object -First 30 | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
}
