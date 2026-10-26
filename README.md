# QQ 机器人部署说明（NapCat + 幻梦 + 中转站 API）

部署日期：2026-09-30
部署根目录：`D:\QQBot`

> **新对话请先读 [`SESSION-LOG.md`](SESSION-LOG.md)** —— 那是按时间线整理的会话交接日志，
> 含当前状态快照、已完成工作、未完成待办、常用命令与故障速查。
> 本文（README）讲的是**部署原理与踩坑详版**，适合需要深挖某个机制时查阅。

---

## 1. 服务拓扑

```
手机QQ(小号 <BOT_QQ>)
        │ 扫码登录
        ▼
┌───────────────────────────────┐
│ NapCat 4.18.28 (QQ 协议适配)   │  注入 QQ NT 9.9.27-45758
│ D:\QQBot\NapCat                │  独立 profile: D:\QQBot\QQProfile
│ ─ OneBot v11 正向 WS           │
│ ─ WebUI  127.0.0.1:6099        │
└───────────────┬───────────────┘
                │ ws://127.0.0.1:8099/
                ▼
┌───────────────────────────────┐
│ 幻梦 v2.3.69 (Python 3.11)     │
│ D:\QQBot\huanmeng              │
│ ─ 判断/回复/摘要 → 中转站 API   │
│ ─ SQLite+FTS5 聊天记录检索      │
└───────────────┬───────────────┘
                ▼
        router.shengsuanyun.com/api/v1
        model: deepseek/deepseek-v4.1-flash
```

---

## 2. 目录与关键文件

| 路径 | 说明 |
|---|---|
| `D:\QQBot\NapCat\` | NapCat 程序本体 |
| `D:\QQBot\NapCat\start-napcat.bat` | **启动 NapCat（含独立 profile 参数，勿删参数）** |
| `D:\QQBot\NapCat\loadNapCat.template.js` | **引导脚本模板：注入 `-q <账号>` 实现免扫码自动登录（勿删）** |
| `D:\QQBot\NapCat\config\onebot11_<BOT_QQ>.json` | OneBot v11 服务端配置（WS 端口 8099） |
| `D:\QQBot\NapCat\config\webui.json` | WebUI token（当前 `<NAPCAT_WEBUI_TOKEN>`） |
| `D:\QQBot\QQProfile\` | **NapCat 专用的 QQ 用户数据目录（登录态在这里）** |
| `D:\QQBot\huanmeng\` | 幻梦框架 |
| `D:\QQBot\huanmeng\config\.env` | **API 密钥（中转站 Key 在这里）** |
| `D:\QQBot\huanmeng\config\bot_config.toml` | 模型名 / QQ 号 / 人格 |
| `D:\QQBot\huanmeng\config\adapter_config.toml` | WS 地址 / 群白名单 / 私聊白名单 |
| `D:\QQBot\huanmeng\config\roles.toml` | 主人 QQ（admin） |
| `D:\QQBot\huanmeng\relay_test.py` | **接口自检脚本（换 API 后先跑它）** |
| `D:\QQBot\launcher.ps1` | **一键启动器（启动/停止/状态，带健康检查）** |
| `D:\QQBot\bot.ico` | 启动器图标（由 `tools\make_icon.py` 生成） |
| `D:\QQBot\tools\pget.ps1` | 并发分片下载器（应对 GitHub 单连接限速） |
| `D:\QQBot\start-all.bat` | 简易启动（launcher 的旧版替代，保留备用） |
| `D:\QQBot\stop-all.ps1` | 简易停止（不会动你的个人 QQ） |

---

## 3. 日常操作

### 3.1 推荐：桌面快捷方式

安装时已在桌面生成三个快捷方式（图标为猫脸 `bot.ico`）：

| 快捷方式 | 等效命令 | 作用 |
|---|---|---|
| **启动QQ机器人** | `launcher.ps1` | 启动；已在运行则只汇报状态，**不会重复启动** |
| **停止QQ机器人** | `launcher.ps1 -Stop` | 停止（只杀 NapCat 实例，不动你的个人 QQ） |
| **QQ机器人状态** | `launcher.ps1 -Status` | 只看状态，不改变任何东西 |

启动器的行为：

1. 前置检查 Python 与 NapCat 脚本是否存在
2. NapCat 未运行 → 启动并**轮询等待 8099 端口**（最多 60 秒）
3. 若 60 秒内没起来（说明 QQ 未登录）→ **自动打开 WebUI 登录页**并再等 150 秒
4. 幻梦未运行 → 启动并等待与 NapCat 建立连接
5. 打印状态汇总（含日志路径与 Web 日志台地址），按键退出，**服务继续在后台运行**

日志：NapCat `NapCat\napcat-console.log`、幻梦 `huanmeng\bot-console.log`，
或打开 Web 日志台 <http://127.0.0.1:58888>。

### 3.2 命令行

```powershell
# 启动 / 停止 / 查看状态
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1 -Stop
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1 -Status

# NapCat 登录页（二维码过期时在这里刷新）
http://127.0.0.1:6099/webui?token=<NAPCAT_WEBUI_TOKEN>

# 只重启幻梦（改完配置后）
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*D:\QQBot\huanmeng*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
cd D:\QQBot\huanmeng; .venv\Scripts\python.exe main.py

# 换 API / 换模型后先自检
cd D:\QQBot\huanmeng; .venv\Scripts\python.exe relay_test.py
```

> ⚠️ **`launcher.ps1` 必须保存为 UTF-8 with BOM**。Windows PowerShell 5.1 读取无 BOM 的
> `.ps1` 会按 ANSI 解码，脚本里的中文会导致解析失败。用编辑器改动后若出现乱码报错，
> 用这条命令补 BOM：
> ```powershell
> $p='D:\QQBot\launcher.ps1'
> $t=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)
> [IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($true)))
> ```


**注意**：改 `.env` 里的 Key 必须**重启进程**，`/~reload` 无效——因为 `load_dotenv`
不会覆盖进程里已存在的环境变量。

---

## 4. 配置要点

### 4.1 WS 地址（与常见教程不同）

幻梦的连接地址由 `adapter_config.toml` 的 `[napcat_server]` 段决定，源码里硬拼成
`ws://{host}:{port}/`，**没有 `/onebot/v11/ws` 这段路径**：

```toml
[napcat_server]
host = "127.0.0.1"
port = 8099

[chat]
group_list = [<GROUP_1>]          # 群白名单，不在名单的群一律忽略
private_whitelist = [<OWNER_QQ>]  # 私聊白名单
```

⚠️ 仓库自带的 `example.adapter_config.toml` 写的是 `[napcat] ws_url = "..."`，
**代码根本不读那个段**，照抄模板会静默失效（只是恰好默认端口 8099 蒙对）。

### 4.2 模型与中转站

```toml
[model.replyer_1]
name = "deepseek/deepseek-v4.1-flash"   # 必须与中转站 /v1/models 完全一致
provider = "RELAY"                       # 对应 .env 的 RELAY_KEY / RELAY_URL
maxtoken = 1000
```

```ini
# config/.env
RELAY_KEY=<API_KEY>
RELAY_URL=https://router.shengsuanyun.com/api/v1
```

**`base_url` 由框架原样传给 OpenAI SDK（`services/llm.py:994`），不会自动补 `/v1`**，
必须与中转站文档完全一致。

---

## 5. 部署时踩过的坑（重要）

### 5.1 两个 QQ 实例抢同一个 profile → 登录后必崩

**现象**：扫码确认后 6 秒，日志出现 `[UtilityProcess] Worker进程退出`，NapCat 重载并
退回二维码界面，`passkey.json` 始终是 `{}`。

**原因**：QQ 的用户数据目录来自 Windows 已知文件夹 API，**不是** `%APPDATA%` 环境变量。
所以个人 QQ 和 NapCat 的 QQ 会共用 `C:\Users\<用户>\AppData\Roaming\QQ`，
两个 Electron 实例并发写同一 profile，登录握手写会话状态时崩溃。

**解法**：通过 NapCat 引导器给 QQ 追加 `--user-data-dir` 参数
（`NapCatWinBootMain.exe` 会把多余 argv 转发给 QQ.exe），使 NapCat 使用
`D:\QQBot\QQProfile`。已固化在 `start-napcat.bat` 里。

验证隔离是否生效：

```powershell
Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" |
  Where-Object { $_.CommandLine -notmatch '--type=' } |
  ForEach-Object { "$($_.ProcessId)  $($_.CommandLine)" }
```

> ⚠️ 试过但**无效**的方案：覆盖 `APPDATA` 环境变量（QQ 不读它）。

**副作用**：多余 arg 会让 NapCat 同时发一个 `-q` 快速登录请求，找不到记录就自动回退
二维码登录，属正常噪音。

### 5.2 思考模式吃掉 token 预算

`deepseek-v4.1-flash` **默认开启思考模式**，推理 `reasoning_content` 与正文共享
`max_tokens`。实测 `max_tokens=20` 时全部被推理占用，`content` 返回空字符串。

幻梦对此已有适配（`services/llm.py`）：

- 短判断调用显式传 `thinking=disabled`（`llm.py:1163`，默认 `False`）
- FC 循环正确回传 `reasoning_content`（`llm.py:1847`），规避 DeepSeek 要求的 400

**但这依赖中转站透传 `extra_body.thinking` 参数**——`relay_test.py` 的
「思考开关透传」一项就是验证这个。

### 5.3 GitHub 下载被按连接限速

本机 `github.com` 单连接仅 6~26 KB/s，28 MB 的 NapCat 包要 1 小时以上。
但**限速是按连接的**：16 线程分片聚合到 152 KB/s（实测 16.3 倍增益）。

用 `D:\QQBot\tools\pget.ps1`（并发分片下载器，带字节校验+重试）：

```powershell
& D:\QQBot\tools\pget.ps1 -Url '<url>' -OutFile '<path>' -Threads 16
```

### 5.4 依赖清单缺项

`requirements.txt` 没写但实际需要的包：

| 包 | 用途 | 缺失后果 |
|---|---|---|
| `sqlalchemy[asyncio]` | ORM | 数据库降级 |
| `greenlet` | SQLAlchemy asyncio 必需 | `数据库初始化失败` |
| `aiosqlite` | 异步 SQLite 驱动 | `No module named 'aiosqlite'` |
| `pillow` / `numpy` | 卡片渲染（懒加载） | `/~help` 等卡片指令异常 |

`playwright`（2026-10-01 更正，此前本节写的是"未安装但不影响"，**那是错的**）：
`/~help` 确实已迁到 Pillow、不需要 playwright；但 **weather / box / changelog 三类卡片
仍然依赖 playwright + 一个 Chromium 内核浏览器**。缺了它们不是报错那么简单 ——
`weather` 指令会「查到了却什么都不发」（静默失败），详见 `SESSION-LOG.md` §4.7.20。

已装且已验证可用：

```powershell
.venv\Scripts\python.exe -m pip install playwright
```

**不需要**再跑 `playwright install chromium`（省 ~150MB）：本机已有 Chrome，
`changelog.py:_find_chromium_executable()` 会自动复用它；
只有本机既无 Chrome 也无 Edge 时才需要下载自带的 chromium。

### 5.5 脚本编码

Windows PowerShell 是 **5.1**，读取无 BOM 的 `.ps1`/`.bat` 时会按 ANSI 解码，
**脚本里的中文会导致解析失败**。本目录所有脚本一律纯 ASCII。

### 5.6 中转站写死的两处官方地址

| 位置 | 地址 | 影响 |
|---|---|---|
| `modules/commands.py:488` | `api.deepseek.com/user/balance` | `/~balance` 失效 |
| `modules/web_search.py:484` | `api.deepseek.com/responses`（服务端 `web_search` 工具） | 该搜索路径失效 |

其余搜索后端（ddgs / 百度 / Bing）不受影响。

---

## 6. 故障排查速查

| 现象 | 检查点 |
|---|---|
| 幻梦一直 `远程计算机拒绝网络连接` | NapCat 是否登录成功、8099 是否监听 |
| NapCat 二维码扫了就失败 | 看日志错误码：`ErrCode 10`=风控；`ErrCode 3`=过期；`Worker进程退出`=profile 冲突 |
| 机器人不回话 | 群是否在 `group_list`；`回复兴趣` 阈值（默认 8，越高越沉默）；中转站 `tools` 是否可用 |
| 机器人回空消息 | 中转站是否丢弃 `thinking` 参数（跑 `relay_test.py`） |
| 卡片指令报错 / 天气指令"查到了却不发消息" | `playwright` 缺失或 chromium 路径不对（详见 `SESSION-LOG.md` §4.7.20）。已修复：装了 playwright 并复用本机 Chrome，正常无需再动 |
| 双击启动器没反应 / 窗口卡住 | 看 `NapCat\napcat-*.log` 最新那个：若为空且 bat 未执行，是**日志被残留进程锁定**（启动器已自动清理孤儿进程）；跑 `launcher.ps1 -Status` 看状态 |
| 启动后日志出现 `当前账号已登录,无法重复登录` 且进程退出 | 隔离 profile 登录态损坏 → 重置 `D:\QQBot\QQProfile`（改名备份 + 新建空目录）后重新扫码一次 |

---

## 7. 实测验证结果（2026-09-30 21:33）

在群 `<GROUP_1>` 实测三条，全部通过：

| 测试 | 结果 | 耗时 |
|---|---|---|
| `@幻梦 你能自己说话吗` | 收到 2 句回复，好感度 +2，长期记忆写入 | 2.59s |
| `/~ping` | 返回用法说明（见下方注意） | 立即 |
| `/~help` | 输出图片卡片（`data/help_card.png`） | 1.7s |

`@` 触发的完整管道（日志实证）：

```
📩 消息接收 → @ 替换为机器人名 → 好感度注册 → 判断 should_reply=True (0.02s)
→ LLM 生成 JSON {"replies":[...],"fav":2,"mood":"好奇","action":"歪歪头"} (2.58s)
→ [FACE:好奇] 标记剥离 → 分批发送 2 条（句间 1.34s）→ 好感度更新 → 自动记忆压缩
```

运行期产物：

- `data/fav.json` —— 好感度 `{"g<GROUP_1>:<OWNER_QQ>": 52}`
- `data/memory_<GROUP_1>.md` —— 长期记忆（含关键词提取）
- `data/huanmeng.db` —— `memories` + `memories_fts` 已索引（FTS5 生效）

⚠️ **`/~ping` 的语义与社区文档不符**：幻梦 README 把它写成"在线检测/延迟测试"，
但代码里它是**查询域名/IP 的 ping 工具**（用法 `/~ping <域名或IP> [国家...] [img]`）。
想要"机器人活着吗"这类健康检查，用 `/~info`。

---

## 7.5 一键启动器：故障复盘与免扫码机制

### 三个导致「点了没反应 / 卡住」的 bug（已修复）

| # | Bug | 根因 | 修复 |
|---|---|---|---|
| 1 | 启动命令静默失败 | `Start-Process -ArgumentList '/c', "带引号+重定向的串"` 用**数组**传参，PowerShell 以空格拼接后 cmd 解析失败，**批处理根本没执行** | 改传**单个完整字符串**：`-ArgumentList "/c `"`"$bat`" > `"$log`" 2>&1`""` |
| 2 | 日志被锁 → 重定向失败 | 固定日志名被上一次的残留进程持有（孤儿 QQ 进程继承了句柄）→ cmd 打不开重定向文件 → 同样静默不执行 | 改用**带时间戳**的日志 `napcat-<yyyyMMdd-HHmmss>.log` |
| 3 | 孤儿进程抢 profile | 父进程已死的 NapCat QQ 进程仍占着 profile 与文件句柄 | 启动前自动清理（判据：含 `QQProfile` 且父进程不存在） |

判定「NapCat 是否在运行」的过滤条件**只认命令行里的 `QQProfile`**。
推而广之：**绝不能用可执行路径判断 NapCat 实例**——你的个人 QQ 是
`C:\Program Files\Tencent\QQNT\QQ.exe`，NapCat 用的是 `...\Tencent\qqnt\QQ.exe`，
仅大小写不同，而 PowerShell 的 `-like`/`-match` **不区分大小写**，会连你的个人 QQ 一起杀掉。
（这个错误我犯过一次，已修正。）

### 免扫码自动登录的实现

NapCat 通过 `process.argv` 里的 `-q`/`--qq` 判断是否快速登录
（`napcat.mjs:82700`，取该标志**后面那个 token** 当账号）。
而 `NapCatWinBootMain.exe` 只会把**唯一一个额外参数**包装成 `-q <参数>` 转发给 QQ.exe，
那个位置必须留给 `--user-data-dir`（profile 隔离是硬需求）。于是 NapCat 把
`--user-data-dir=...` 当成了账号名，快速登录必然失败、每次都要扫码。

解法：`loadNapCat.template.js` 在 `napcat.mjs` 加载**之前**改写 `process.argv`，
把第一个 `-q` 后面的 token **覆盖**成真实账号（不是追加——`findIndex` 只认第一个）。
`start-napcat.bat` 每次启动都从模板复制出 `loadNapCat.js`。

**该模板有三个必须遵守的约束**（都实际踩过）：

1. **不能用 `require()`**。该执行上下文里 `require` 不可用；一旦使用，`napcat.mjs`
   根本不会被加载——表现为 NapCat 毫无日志、WebUI(6099) 不监听、**静默失败**。
   （官方发行版自带的 `loadNapCat.js` 正是 `require` 写法，故被替换。）
2. 路径必须**硬编码绝对路径**（正斜杠）。移动 `D:\QQBot\NapCat` 后需同步修改模板。
3. 必须**覆盖**而非追加 `-q` 的账号。

### 快速登录依赖「干净的登录态」

若隔离 profile 里残留了损坏的会话（多次强杀进程后容易出现），QQ 会返回
`当前账号(…)已登录,无法重复登录`，而且 **NapCat 不会回退到扫码，而是直接结束进程**。
处理办法：停掉所有 NapCat 进程 → 把 `D:\QQBot\QQProfile` 改名备份、新建空目录 →
重新扫码登录一次。之后重启即为免扫码。

实测对比（同一台机器，各次冷启动）：

| 日志 | 是否需扫码 | 快速登录 |
|---|---|---|
| `napcat-20260930-224632.log` | 需扫码（profile 刚重置，无记录） | 尝试过，回退扫码 |
| `napcat-20260930-224852.log` | **免扫码** | **成功（约 1 秒）** |

冷启动全流程实测：**13 秒**内完成「启动 NapCat → 自动登录 → 启动幻梦 → 连接成功」。

---

## 8. 已知待办

- [ ] `fastapi` + `uvicorn`：棋局在线对战 Web 服务（启动日志里唯一的 ERROR，与聊天无关）
- [ ] `data/faces` 表情素材库：仓库未附带（属"部分私有模块未包含"），
      缺失时 `[FACE:xxx]` 标记会被剥离但不配图，不影响文字回复
- [ ] 人格定制：改 `bot_config.toml` 的 `[personality]` 三段
- [ ] 调整 `回复兴趣`（当前 8）：调低到 5–6 会让机器人更主动插话。这一项在 `bot_config.toml` 里，
      改完 `/~reload` **有效**（但改 `data/skills/*.md` 则必须重启，见 `SESSION-LOG.md` §4.7.17）

---

## 9. 安全提示

- WebUI token（`<NAPCAT_WEBUI_TOKEN>`）等同登录权限，勿泄露；WebUI 已限定本机
- `config/.env` 含 API 密钥，勿提交到任何仓库
- NapCat 与幻梦均以当前用户身份运行，未提权
- 机器人使用第三方协议库，**存在账号被腾讯风控/封禁的可能**，务必使用小号

---

## 来源与许可

本仓库是**部署留档**，核心框架并非本仓库作者原创：

- **HuanMeng · 幻梦** 来自开源项目
  [Trusler258/huanmeng-qqbot](https://github.com/Trusler258/huanmeng-qqbot)，
  采用 **MIT License**，版权归 **Trusler** 所有（见 `huanmeng/LICENSE`）。
- 本仓库主要记录该框架**本地部署期间的配置调整、问题修复与排查文档**
  （见 `SESSION-LOG.md`），不主张对上游框架的著作权。
- 再分发 / 二次使用请**保留 `huanmeng/LICENSE`** 与其中的版权声明。

> 文档中的 QQ 号、群号、WebUI 令牌、密码哈希等**均已替换为占位符**
> （如 `<BOT_QQ>` / `<OWNER_QQ>` / `<GROUP_1>` / `<NAPCAT_WEBUI_TOKEN>`），
> 请勿据此推断真实账号或凭据。