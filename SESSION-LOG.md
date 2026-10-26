# 会话交接日志（SESSION-LOG）

> **给新对话的读者**：本文是这套 QQ 机器人系统在 `2026-09-30 ~ 10-01` 会话中搭建与排障的完整记录。
> 想快速上手，按这个顺序读：
> 1. 本文 §1 当前状态 → 2. §2 路径速查 → 3. §7 常用命令 → 4. `README.md`（部署原理与踩坑详版）
>
> 最后更新：**2026-10-04 22:55**（第二次交接：掉线恢复、图片识别/好感度/表情包三大根因修复、搜索彻底修好、weather 卡片三层缺陷修复、群白名单补全、绘图打通并加一键开关、动图多帧识别、**新增群聊共享记忆（全局笔记本层）**；另附换号清单与配置注释会被清空的备忘，见 §4.7）

---

## 1. 当前状态快照（2026-10-01 13:48）

> ⚠️ **交接教训**：上一版快照（13:37）写着"全部运行中"，而 **13:38:50 NapCat 就已经死了**
> ——无任何退出日志，属强杀或崩溃。幻梦随后空转重连 4 分钟（每 5 秒一次，刷爆日志）。
> **接手时一律实测，不要相信快照。**

| 项 | 状态 |
|---|---|
| NapCat QQ 实例 | ✅ 运行中（独立 profile，13:43 冷启动） |
| 幻梦框架 | ✅ 运行中，已连接 NapCat（13:48 重启，日志编码噪声已修） |
| OneBot 8099 | ✅ 监听中，且已建立连接 |
| NapCat WebUI 6099 | ✅ 监听中 |
| 实时二维码页 8899 | ⚪ 未运行（本次免扫码，未启动 `tools/qr_server.mjs`） |
| Web 日志台 58888 | ✅ 监听中 |
| 你的个人 QQ | ✅ 运行中，与机器人互不干扰 |
| 登录方式 | ✅ **免扫码快速登录成功**（13:43:56 `正在快速登录 <BOT_QQ>`），**冷启动全程约 11 秒** |
| 密码回退 | ⚠️ **仍未验证**——快速登录这次没失败，密码路径根本没被触发（见 §4.7.3） |

---

## 2. 路径与凭据速查

```
D:\QQBot\
├── NapCat\                          NapCat 4.18.28（QQ 协议适配层）
│   ├── start-napcat.bat             ★启动脚本（含 profile 隔离 + 密码回退环境变量）
│   ├── loadNapCat.template.js       ★引导模板（注入 -q 账号，实现免扫码）
│   ├── loadNapCat.js                由 bat 每次从模板复制生成
│   ├── qqnt.json                    NapCat 改过的 QQ package.json（main → loadNapCat.js）
│   ├── config\onebot11_<BOT_QQ>.json   OneBot v11 服务端（WS 8099）
│   ├── config\webui.json            WebUI token = <NAPCAT_WEBUI_TOKEN>
│   └── napcat-<时间戳>.log          每次冷启动一个日志（避免文件锁）
├── QQProfile\                       ★NapCat 专用 Electron 用户数据目录（**不是**登录态所在，见 §4.7.2）
├── QQProfile.bak-224627\            重置前的旧 profile（备份，可删）
├── huanmeng\                        幻梦 v2.3.69（Python 框架）
│   ├── config\.env                  RELAY_KEY / RELAY_URL（中转站）
│   ├── config\bot_config.toml       模型名 / QQ号 / 人格三段
│   ├── config\adapter_config.toml   WS地址 / 群白名单
│   ├── config\roles.toml            主人 QQ
│   ├── data\skills\*.md             ★分层提示词（00_core.md 含人格锁）
│   ├── relay_test.py                接口自检（换 API 后先跑）
│   └── .venv\                       Python 3.11 虚拟环境
├── launcher.ps1                     ★一键启动器（启动/停止/状态）
├── bot.ico                          快捷方式图标
└── tools\
    ├── pget.ps1                     并发分片下载器（破 GitHub 单连接限速）
    ├── qr_server.mjs                ★实时二维码页面（:8899）
    ├── grab_qr.ps1                  抓一张最新二维码到 qrcode.jpg
    ├── set_qq_password.ps1          配置密码回退（读文件→算MD5→写bat→删明文）
    └── make_icon.py                 生成 bot.ico
```

**关键标识**

| 项 | 值 |
|---|---|
| 机器人 QQ / 昵称 | `<BOT_QQ>` / 大肥鱼 |
| 主人（admin）QQ | `<OWNER_QQ>` |
| 群白名单 | `<GROUP_1>`、`<GROUP_2>`（★ 2026-10-01 补加，见 §4.7.21） |
| OneBot 地址 | `ws://127.0.0.1:8099/`（**无 `/onebot/v11/ws` 路径段**） |
| WebUI | `http://127.0.0.1:6099/webui?token=<NAPCAT_WEBUI_TOKEN>` |
| 实时二维码 | `http://127.0.0.1:8899/` |
| 中转站 | `https://router.shengsuanyun.com/api/v1` |
| 模型 | `deepseek/deepseek-v4.1-flash`（provider `RELAY`） |
| 桌面快捷方式 | 启动QQ机器人 / 停止QQ机器人 / QQ机器人状态 |

---

## 3. 架构

```
手机QQ(小号 <BOT_QQ>)
      │ 扫码或密码登录
      ▼
NapCat 4.18.28  ──注入──▶ QQ NT 9.9.27-45758
  D:\QQBot\NapCat         profile: D:\QQBot\QQProfile（与个人QQ隔离）
  OneBot v11 正向 WS :8099
  WebUI :6099
      │ ws://127.0.0.1:8099/
      ▼
幻梦 v2.3.69（Python 3.11）
  判断/回复/摘要 → router.shengsuanyun.com
  SQLite+FTS5 聊天记录检索
```

⚠️ **profile 隔离是硬需求**：QQ 从 Windows 已知文件夹 API 取数据目录（**不是** `%APPDATA%` 环境变量）。
两个 QQ 实例共用同一 profile 会导致"扫码确认后 worker 进程崩溃、会话写不进去"。

---

## 4. 本会话完成的工作

### 4.1 部署（9-30 晚）

1. **NapCat 4.18.28** 从 GitHub Release 下载——本机 github.com 单连接仅 6~26 KB/s，
   用自写的 16 线程分片下载器 `tools/pget.ps1` 聚合到 152 KB/s（16.3 倍增益）。
2. **幻梦 v2.3.69**（Python，`git` 不存在故用 zip + 代理下载）。
3. 依赖补齐：`requirements.txt` 漏了 `sqlalchemy` / `greenlet` / `aiosqlite` / `pillow` / `numpy`。
4. 配置三处**与官方模板不符**的地方（详见 README §4.1）：
   - WS 地址：框架硬拼 `ws://{host}:{port}/`，用 **8099**，不是 `.../onebot/v11/ws`
   - `adapter_config.toml` 必须用 `[napcat_server]` 段，仓库模板写的 `[napcat]` 代码不读
   - `deepseek-flash` 确实有效（DeepSeek-V4.1-Flash），且自带图像理解 → 省掉智谱视觉模型

### 4.2 接入中转站（9-30 晚）

- 中转站 `https://router.shengsuanyun.com/api/v1`，模型 `deepseek/deepseek-v4.1-flash`
- `relay_test.py` 全 7 项通过，含两个关键项：
  - **Function Calling 可用**（幻梦 76 条指令依赖它）
  - **`extra_body.thinking` 被透传**（幻梦对判断类短调用主动关思考，中转站若丢弃该参数会返回空）
- 已知失效功能：`/~balance`（源码写死官方余额接口）、`modules/web_search.py:484` 的官方 `/responses` 搜索路径

### 4.3 启动器（10-01 凌晨修好）

初版有三个 bug 导致"点了没反应"，全部修复（详见 README §7.5）：

| # | Bug | 修复 |
|---|---|---|
| 1 | `Start-Process -ArgumentList` 用**数组**传参 → cmd 解析失败、静默不执行 | 改传**单个完整字符串** |
| 2 | 固定日志名被残留进程锁定 → 重定向失败、同样静默不执行 | 改**带时间戳**的日志 |
| 3 | 孤儿进程抢 profile / 锁文件 | 启动前自动清理（判据：含 `QQProfile` 且父进程已死） |

**免扫码自动登录**：`loadNapCat.template.js` 在 `napcat.mjs` 加载前把 `process.argv` 中
第一个 `-q` 后面的 token **覆盖**成真实账号。三个约束（都踩过）：
① 不能用 `require()`（该上下文没有，会导致 napcat.mjs 完全不加载、静默死亡）；
② 路径必须硬编码绝对路径；③ 必须**覆盖**而非追加（NapCat 用 `findIndex` 只认第一个 `-q`）。

实测冷启动 **13 秒**完成「启动 NapCat → 自动登录 → 启动幻梦 → 连接成功」。

### 4.4 角色卡替换（10-01）

原角色"猫娘"来自 `data/skills/00_core.md` 的**人格锁**（不是 `bot_config.toml`）。
已整体替换为：

> **大肥鱼**｜主人专属女仆｜可爱软萌 + 傲娇｜称主人为「主人」，其余人一律「平民」且腹黑毒舌

改动 9 个文件、15 处精确替换 + 1 段重写；`bot的名字` 幻梦 → 大肥鱼。
**改人格必须同时改两处**：`data/skills/00_core.md` 的 persona_lock 和 `bot_config.toml [personality]`，
否则技能文件会把人格锁回去。**改完必须重启幻梦才生效** ——
`/~reload` **不会**重载 `data/skills/*.md`，详见 §4.7.17。

`/~persona` 是**仅私聊**的按用户覆盖层（`config/persona_data.json`），群聊改不了。

### 4.5 密码回退（10-01，无人值守）

**背景**：QQ 会周期性回收第三方客户端会话（10-01 早上就出现「你的用户身份已失效，请你重新登录」），
且风控会拦截扫码（`ErrCode 10`）。为此配上密码回退。

- NapCat 读 `NAPCAT_QUICK_ACCOUNT` + `NAPCAT_QUICK_PASSWORD_MD5`（32 位十六进制）
- 已写入 `start-napcat.bat`：账号 `<BOT_QQ>`，MD5 `dd9d92...0e04`（**明文已删除**）
- 工具：`tools/set_qq_password.ps1`（读 `_qqpw.txt` → 算 MD5 → 写 bat → 删明文；`-Remove` 可撤销）
- ⚠️ **尚未验证**：只影响下次冷启动。若腾讯返回 `140022008`（需验证码）或 `140022010`（需新设备扫码验证），
  仍须人工介入一次——这是腾讯侧风控，非配置问题

### 4.6 实时二维码页面（10-01）

扫码码每约 2 分钟轮换，聊天里转发图片每次浪费 30~60 秒导致频繁过期。
`tools/qr_server.mjs`（Node，无依赖，:8899）提供：
- `/` 自动刷新页面（每 3 秒跟随最新码，显示剩余有效期）
- `/qr.png` 当前二维码；`/status.json` 状态（含 8099 是否已监听）
- 兜底：`tools/grab_qr.ps1` 抓一张到 `qrcode.jpg`

### 4.7 第二次交接（10-01 13:43~10-14 14:16）：掉线恢复 + 全链路实测 + 三十五项纠偏/修复 + 一次 8099 停机事故

#### 4.7.1 日志里满屏的 `Traceback` 是假警报（已修）

**现象**：`huanmeng\bot-console.log` 反复出现——

```
UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f310'
  File "core\log_server.py", line 408, in start
```

**根因**：幻梦日志里有 emoji（🌐、⏳ 等），而 stdout 被 `cmd /c python main.py > 日志 2>&1`
重定向到文件时，Python 3.11 用**系统 locale 编码（GBK）**，编不出 emoji 就抛异常。
**功能完全正常**，只是丢掉那一条日志——但它把日志刷成 MB 级噪声，且极易被误判为崩溃。

**修复**：`launcher.ps1` 启动幻梦的命令加 `-X utf8`（Python UTF-8 模式）：

```powershell
$botCmd = "/c `"`"$PyExe`" -X utf8 main.py > `"$BotLog`" 2>&1`""
```

实测对照：不加 → `UnicodeEncodeError`；加 → 正常输出 `🌐 hello`。
重启后 `UnicodeEncodeError` 与 `Logging error` 计数均为 **0**，日志从 1.1 MB 降到 9 KB。

> ⚠️ 改 `launcher.ps1` 后**必须确认 BOM 还在**——编辑器/自动化工具常会悄悄去掉它。
> 验证：文件前 3 字节应为 `EF BB BF`。补 BOM 命令见 §7 末尾。

#### 4.7.2 `QQProfile` 里**没有**登录态

实测 `D:\QQBot\QQProfile` 递归只有 **1 个文件**：`Local State`（434 字节，9-30 22:46 创建）。

真正的账号数据在：

```
C:\Users\<用户>\Documents\Tencent Files\<BOT_QQ>\nt_qq\
    ├── nt_db\nt_msg.db          消息库
    ├── nt_db\profile_info.db    资料库
    └── nt_data\log\qq-log_*.log QQ 自身日志（**判断进程何时死亡就看它**）
```

→ `--user-data-dir` 隔离的只是 **Electron 用户数据层**；账号数据按 UIN 分目录，本来就不冲突。
隔离之所以有效，是挡掉了 Electron 层的 profile 争用。**"登录态在 QQProfile 里"属错误理解**，
它会影响"重置 QQProfile 就能重新扫码"这类操作的心理预期。

#### 4.7.3 密码回退**依然没验证到**（因为它压根没被触发）

本次冷启动日志是 **`正在快速登录 <BOT_QQ>`**，而**不是** `正在密码登录`——
**免扫码快速登录（token 型）直接成功，密码回退根本没轮到出场。**

另外查清了上一轮为何也没验证到：那次 NapCat 于 **10:59:26** 启动，而
`start-napcat.bat` 写入 `NAPCAT_QUICK_PASSWORD_MD5` 是在 **13:37:59**（文件 mtime）——
**那次启动根本没带上密码回退**。所以 10:59:36 报 `快速登录错误：登录态已失效` 之后，
只能连出 7 张二维码（11:01~11:13 全是 `ErrCode 3` 过期），最后靠 11:15:33 人工扫码。

**结论**：密码回退只在快速登录失败时才兜底，**无法通过"正常启动"验证**——
只能等腾讯真的回收会话，或人为制造失败条件。

#### 4.7.4 受限沙箱下 `launcher.ps1 -Status` 会给出假读数

在 DSH 的 workspace-write 沙箱下（无 WMI 权限）：

- `Get-CimInstance` 直接报 `拒绝访问` → `Show-Status` 里 NapCat/幻梦一律显示"未运行"
- `Get-NetTCPConnection` **不报错、静默返回空** → 所有端口一律显示"未监听"

即脚本会给出**整片假红灯**，而同一时刻 `netstat -ano` 显示 58888 明明在监听。
**受限环境下必须用 `netstat -ano` 交叉验证端口。**

#### 4.7.5 `launcher.ps1 -Stop` 是正确的（曾怀疑漏杀，实测否定）

幻梦真实 worker 的命令行是裸 `main.py`（由 venv 的 `python.exe` stub 转交给系统 Python
解释器），**不含 `huanmeng` 路径**，看着像是会漏杀。但实测：杀掉 venv stub（命令行含
`huanmeng` 的那个）后，worker 一并退出。**过滤条件工作正常，无需修改。**

#### 4.7.6 `relay_test.py` 有同一个编码 bug（跑法必须带 `-X utf8`）

`relay_test.py` 在最后打印结果时用了 `✓`（U+2713），**在普通 Windows 控制台会抛
`UnicodeEncodeError` 直接崩掉**——测试其实全跑完了，但结果一行都没打出来，**看起来像自检失败**。

正确跑法（10-01 13:52 实测 7 项全过）：

```powershell
cd D:\QQBot\huanmeng
& .\.venv\Scripts\python.exe -X utf8 relay_test.py
```

结果：基础对话 / Function Calling / **思考开关透传** / 多轮FC+思考 / JSON 输出 /
流式输出 / 模型列表 —— **全部 OK**，中转站 `deepseek/deepseek-v4.1-flash` 可用于幻梦。

#### 4.7.7 重启后全链路实测（10-01 13:51~13:53）

**指令链路**（私聊 `/~info`）：接收 → 渲染 → `send_private_msg` → API 成功，约 **0.3 秒**。

**LLM 链路**（私聊普通聊天）：完整走通，总耗时 **2.69 秒**——

```
📩 消息接收 → should_reply=True (0.02s) → 思考模式:关闭
→ LLM 生成 4 句 (2.69s) → 分批发送(句间 0.5~1.0s) → 自动记忆压缩 ✅
```

⚠️ **新发现：LLM 不按 JSON 输出时，好感度与心情会静默失效。** 本次日志：

```
LLM 输出非 JSON 但内容完整，已救回直接使用（97 字原始输出）
JSON回复解析: 4句 fav=+0 calls=0 mood=        ← fav / mood 全空
```

幻梦有"非 JSON 救回"兜底，**回复本身完全正常**，但 `fav`（好感度增量）与 `mood` 取不到值。
对照 §7 记录的理想路径应为 `{"replies":[...],"fav":2,"mood":"好奇","action":"歪歪头"}`。
→ 好感度增长、心情标签这两个功能**依赖模型老实输出 JSON**，一旦降级就**静默**不生效。
**若发现"好感度不涨"，先查日志有没有 `输出非 JSON` 字样。**

🔴 **补充实测（10-01 13:53 / 13:55 / 13:59 连续三条 LLM 回复）：3 次全部走了"非 JSON 救回"路径。**
也就是说当前配置下 `fav` 恒为 `+0`、`mood` 恒为空 —— **好感度与心情不是偶发失效，而是长期失效**。
优先级建议高于 `data/faces`（那条只是不配图，这条是功能实际不生效）。

#### 4.7.8 psutil 已装（**无需重启**）

`pip install psutil` → **7.2.2**（本机内存 31.3 GB）。

**不必重启幻梦**：`modules/commands.py:384` 与 `:406` 的 `import psutil` 在**函数体内**
（带 `try/except ImportError`），每次 `/~info` 调用时重新 import —— 因此
**下一条 `/~info` 就会生效**，`Memory/CPU/Disk/Uptime` 四项从 `unavailable` 变为真实值。

#### 4.7.9 图片识别根因修复（10-01 13:57，已 A/B 验证）

**现象**：机器人拿到的"图片描述"其实是**提示词回显**，例如
`我们需要回答用户。用户要求：请直接描写图片中的内容…`，且同一张图每次都返回同一段垃圾。

**根因链**（全在 `services/image_api.py`）：

| # | 问题 | 位置 |
|---|---|---|
| ① | 视觉调用**没关思考**（对比 `llm.py:1207` 的短判断调用——那里关了） | `:215` |
| ② | `max_tokens=120` 太小 → 思考吃掉全部预算 → `content` **返回空**（§5.2 同款问题） | `:217` |
| ③ | 触发"从推理链提取描述"兜底 → 把模型**复述提示词的独白**当成描述 | `:246-252` |
| ④ | `description = _cleaned[:200]` → 真描述被截掉 | `:252` |
| ⑤ | 垃圾被 **MD5 永久缓存** → 同图永远返回垃圾 | `:265` |

**证据**：缓存 21 条中 7 条污染，其 `desc` 长度恰为 **200**（= ④ 的截断值），
且全部以 `我们需要回答用户` 开头（= 模型在复述提示词）。

**修复**（两处）：

```python
max_tokens=300,                                    # 120 → 300
extra_body={"thinking": {"type": "disabled"}},     # ★ 新增，与 llm.py:1207 对齐
```

并清掉 7 条污染缓存（`Image_description_cache.txt` + `image_repo.jsonl`，21 → 14 条）。
改动前已备份到 `huanmeng\_backup-imagefix-<时间戳>\`（路径见 `huanmeng\.last-imagefix-backup`）。

**A/B 实测（同一张图，MD5 `01a439db9fa1…`）**：

| | 结果 |
|---|---|
| 修复前 | `图片识别缓存命中 → '我们需要回答用户。用户要求：请直接描写图片中的内容…'`（200 字，提示词回显） |
| 修复后 | `调用视觉模型识别图片` → `图片识别成功: 蓝发女仆装少女狂喜大笑，紧握"deepseek桌面端赠金+6.00元"卡片。情绪：极度兴奋、惊喜、满足、激动。伴星星爱心。`（**61 字**） |

修复后日志中**不再出现 `从推理链提取描述`** —— 这一条最关键，它证明
`thinking=disabled` 确实透传成功、`content` 不再为空。OCR 出卡片文字、情绪元素给满 4 点，质量正常。

> ⚠️ 剩余 14 条缓存**仍带推理独白前缀**（真描述还在，只是前面挂了句模型的自我叙述）。
> 要彻底刷新，把 `data\Image_description_cache.txt` 内容改成 `{}` 即可，图片再被发送时会自动重建。

#### 4.7.10 🔴 好感度/心情长期失效的**真正根因**（10-01 14:05，已修复并验证）

**症状**：每次回复日志都是 `LLM 输出非 JSON 但内容完整，已救回直接使用`，
接着 `fav=+0 calls=0 mood=` —— 好感度不涨、心情恒空（实测 3/3，是**长期**而非偶发）。

**排查过程（三步，前两步都被否定，第三步才命中）**：

| 步骤 | 假设 | 实测结论 |
|---|---|---|
| ① | 视觉调用没关思考那一类问题 | ✗ 与图片无关 |
| ② | `response_format` 缺失导致模型不吐 JSON | ✗ **直接打 API 实测**：带 tools、不带 `response_format`，模型照样返回完整 JSON（含 `fav:1`、`mood:"开心"`） |
| ③ | **提示词有问题** | ✗ dump 出真实 system 提示词：6186 字符，**含**「必须是合法 JSON」，**不含** `||` |

**真凶在上下文历史里**：`context_cache.json` 的私聊历史 **81 条中 33 条含 `||`**，
全是 bot 自己的旧回复，形如：

```
大肥鱼: 诶？大半夜的调 ESP32 呀 || 主人这是又在折腾什么小玩意儿呢～ || ...
```

**模型在模仿自己**——system 里再怎么强调 JSON，也压不过"我过去 33 次都是这么说的"这种示范。

**而 `||` 是 pipeline 亲手写进去的**：

```python
# core/pipeline.py:1133（修复前）
_context_reply = re.sub(..., '', " || ".join(sentences)).strip()
ctx.append_to_context(chat_id, f"{cfg.bot_name}: {_context_reply}")   # :1139
```

每轮回复都以 `句1 || 句2 || 句3` 写回历史 → 模型模仿 → 又输出 `||` → 再写回，
**自我强化、越陷越深**。而一旦走 `_salvage_plain_reply`，`:1544` 是：

```python
payload = {"replies": sentences, "fav": 0}   # fav 硬编码 0，mood 字段直接没有
```

→ 这就是 `fav` 恒 `+0`、`mood` 恒空的**唯一出口**。

**修复**（两处）：

1. **代码**：`core/pipeline.py:1139` 的上下文拼接改为自然标点
   ```python
   _context_reply = re.sub(..., '', "，".join(sentences)).strip()
   ```
   （`:1034` 的 `combined_reply = " || ".join(...)` **保留不动**——它只在
   `:1034→:1045→:1059` 之间内部往返、从不落盘，是进程内分隔符，安全。）

2. **数据**：清掉历史里已有的 `||`（递归替换为 `，`）：
   - `data\context_cache.json`：**164 处 / 77 个字符串** → 剩余 `||` 为 **0**
   - 三个会话分别 1 / 35 / 9 条；其余数据文件（msglog 等）本来就干净
   - ⚠️ **清理前必须先停幻梦**，否则内存里的上下文会在下次保存时覆盖清理结果

备份：`huanmeng\_backup-jsonfix-<时间戳>\`（`pipeline.py` + `context_cache.json`），
路径见 `huanmeng\.last-jsonfix-backup`。

**验证（真实 LLM 调用，机器人停机状态下用干净历史跑）**：

```
体检：历史 assistant 34 条，含 "||" 的 = 0
输出：{"replies":["主人好呀～在呢，随时听候差遣哦"],"fav":1,"mood":"开心","action":"歪头看你"}
解析：JSON回复解析: 1句 fav=+1 calls=0 mood=开心        ← 修复前恒为 fav=+0 / mood=空
```

> ⚠️ **修复后仍有残留**：2026-10-01 14:14 线上那轮又退化成了非 JSON。
> 已查明是「真实历史 + `thinking=False`（生产默认）」这个组合触发的模型抖动，
> 并**实测否决**了用 `response_format` 强制 JSON 的修法（会引入空返回，反而更糟）。
> 完整对照实验与结论见 **§4.7.13**。
> 🔴 **但最终结论以 §4.7.15 为准**：本节当时给出的"合规率 0/4 → 5/7"**统计有误**
> （混入了空历史/思考开启的成功案例）。按生产配置算，本节修复后**仍是 0/4 全失败**；
> 真正的根因是 `thinking=False`，已于 §4.7.15 修复。

#### 4.7.11 棋局 Web 服务已恢复（fastapi + uvicorn）

启动日志里唯一的 ERROR `No module named 'fastapi'` 是缺依赖。已装：

```
pip install fastapi uvicorn   →   fastapi 0.142.2 / uvicorn 0.54.0
```

服务实现在 `services/game_web.py`，**挂在 bot 进程自己的 asyncio loop 上**
（`uvicorn.Server` 当 task，不额外起进程），监听 **`127.0.0.1:59400`**
（可用环境变量 `GAME_WEB_PORT` 覆盖）。

实测启动日志已变为：

```
[14:06:02] INFO (game_web:start_server:706) 棋局 Web 服务已启动: http://127.0.0.1:59400（0 个房间，对外走隧道）
```

**启动日志里已无任何 ERROR。**

#### 4.7.12 `data/faces` 表情素材：目录已建好，素材需自行导入

**事实**：仓库确实未附带素材（原作者说明"部分私有模块未包含"）。
`face_lib._init()` 找不到目录时只打一条 `表情目录不存在` 警告，
`[FACE:xxx]` 标记会被正常剥离、**文字回复不受任何影响**（实测日志确认）。

**关键机制**（`modules/face_lib.py`）：**关键词来自文件名**，两种写法——

- 中文名：`开心_01.png` → 取文件名的 2~4 字汉字片段 → 命中「开心」
- 英文标签：`happy_026.png` → 经 `_TAG_CN` 表（`:37`）映射成中文词

**规范词共 48 个**（`_TAG_CN` 的元组首词，也正是提示词里给 LLM 的可用清单）：
开心、坏笑、得意、害羞、大哭、委屈、失落、生气、不满、慌张、大喊、惊讶、疑惑、无聊、
疲惫、不舍、道歉、祝贺、加油、拒绝、饿、闭眼、睡觉、困、打哈欠、发呆、打招呼、挥手、
眨眼、抱猫、抱玩偶、抱蛋糕、抱爱心、抱花、抱东西、端东西、吃东西、吃冰淇淋、喝饮料、
逗猫、敬礼、没问题、蹦跳、偷看、张望、站着、坐着、趴着

**已建**：`data\faces\README.md`（完整命名规则 + 48 词表 + 素材来源 + 生效方式）。

**素材来源（本机实测存在）**：QQ 表情缓存，文件名是数字、**必须重命名**才能被 face_lib 识别。

| 来源 | 路径 | 数量 |
|---|---|---|
| 机器人小号 <BOT_QQ> | `%USERPROFILE%\Documents\Tencent Files\<BOT_QQ>\nt_qq\nt_data\Emoji\` | 800 张（去重后 **707**） |
| 你的主号 <OWNER_QQ> | `%USERPROFILE%\Documents\Tencent Files\<OWNER_QQ>\nt_qq\nt_data\Emoji\` | 1308 张 |

**新增工具 `D:\QQBot\tools\import_faces.py`**：用视觉模型逐张识别情绪 → 从 48 个规范词里
选一个 → 复制成 `data/faces/<情绪词>_<编号>.png`。特性：

- **默认 dry-run**，加 `--apply` 才真写文件
- 自动**滤除 `Thumb/` 缩略图**并按内容 **MD5 去重**
- 复用 `[model.picture]` 配置（跟随 `bot_config.toml` 的 provider 切换）
- 调用时**带 `extra_body={"thinking":{"type":"disabled"}}`** —— 复用 §4.7.9 的修复，
  否则 `content` 为空、打标全废

试跑结果（dry-run 8 张）：**命中率 8/8**，样例 `惊讶 / 委屈 / 疑惑 / 慌张`，分布合理。

用法：

```powershell
cd D:\QQBot\huanmeng
.venv\Scripts\python.exe -X utf8 D:\QQBot\tools\import_faces.py --limit 40             # 预览
.venv\Scripts\python.exe -X utf8 D:\QQBot\tools\import_faces.py --limit 40 --apply     # 导入
```

导入后**重启幻梦**生效（⚠️ `/~reload` 不会重载技能，见 §4.7.17），日志出现 `表情库加载: N 关键词, M 文件`。
⚠️ 707 张 = 707 次视觉调用，**会消耗中转站额度**，建议先小批量试。

**已实际导入 40 张（10-01 14:09，试水）**：命中规范词 **40/40**，落盘 40 个文件 / 2.8 MB。
分布：委屈×9、害羞×6、惊讶×5、生气×5、不满×4、慌张×2、开心×2、坏笑×2、抱东西×2、
疑惑×1、打哈欠×1、打招呼×1。

**验证（`face_lib._init()` 实测）**：

```
表情库加载: 151 关键词, 40 文件
  开心   -> 开心_001.png      委屈   -> 委屈_005.png
  害羞   -> 害羞_002.png      生气   -> 生气_003.png
  坏笑   -> 坏笑_001.png      惊讶   -> 惊讶_004.png
  抱东西 -> 抱东西_002.png    打招呼 -> 打招呼_001.png
```

提示词里给 LLM 的词表也随之变成（**带画面描述**）：

```
不满(嘟嘴)/坏笑(抿嘴偷笑不怀好意)/委屈(瘪嘴要哭)/害羞(脸红捂脸)/开心(眯眼笑)/
惊讶(瞪圆眼)/慌张(手忙脚乱冒汗)/哈欠/招呼/东西/生气(鼓脸瞪眼)/疑惑(歪头冒问号)
```

> ⚠️ **注意上面括号里的描述是原作者那批素材的**（见 §6 `_TAG_DESC` 警告）。
> 换句话说：词表已经生效、图也确实能发了，但「词 ↔ 画面」的对应关系尚未按新素材校正，
> 可能出现在 LLM 看来"词不配图"的情况。要彻底解决得重写 `_TAG_DESC`。

> 📌 **`face_lib` 没有重载函数**（只有模块级 `_initialized`），
> 且 `_init()` 是**懒加载**（首次用到表情才扫描）。所以在幻梦运行中新增素材后，
> 光发 `/~reload` **不保证**能重建索引 —— 稳妥做法是**重启幻梦**。
> 重启后索引才会重建（机器人停机时该目录若还不存在，就更必须重启）。

#### 4.7.13 ⛔ 尝试用 `response_format` 强制 JSON —— **实测否决并已撤回**

**动机**：§4.7.10 的 `||` 修复解决的是"系统性"污染，但线上仍有残留——
2026-10-01 14:14 那轮回复依旧 `LLM 输出非 JSON 但内容完整，已救回直接使用` → `fav=+0 mood=`。

**逐步排除（8 次对照实验，全部可复现）**：

| # | 消息 | 历史 | 记忆 | thinking | 结果 |
|---|---|---|---|---|---|
| 1 | 图片描述 | 空 | 无 | None | ✅ JSON |
| 2 | 我喜欢你 | 空 | 无 | None | ✅ JSON |
| 3 | 我喜欢你 | 空 | 无 | **False** | ✅ JSON |
| 4 | 我喜欢你 | 空 | 无 | **True** | ✅ JSON |
| 5 | 我喜欢你 | 真实87条 | 无 | None | ✅ JSON |
| 6 | 图片描述 | 真实87条 | 无 | **False** | ❌ **非 JSON** |
| 7 | 图片描述 | 真实87条 | 完整记忆 | **False** | ❌ **非 JSON** |

→ 被否定的假设：玩梗模式注入（`needs=['play']`，因图片描述含"角色"被误触发）、
`thinking` 开关单独作用、真实历史单独作用。
**真正的组合是「真实历史 + `thinking=False`」** —— 而 `thinking=False` 正是
`pipeline.py:831` 的**默认值**（只有命中 "deep" 才开启思考）。所以这是系统性、非偶发的。

**尝试的修法**：在 `call_llm_with_tools` 加可选 `json_mode` 参数并在回复生成处传 True
（不动 `core/tools.py:631` 的搜索助手）。前置实测证明**可行**：

```
[A 仅 tools]                    finish=tool_calls  get_weather({"city":"上海"})
[B tools + response_format]     finish=tool_calls  get_weather({"city":"上海"})   ← 工具调用未受影响
```

**但实现后实测反而更糟，故撤回**：

```
[无记忆]  轮1 content=（空）  →  轮2 content=[FACE:害羞]        ← 空返回后退化成一个碎片
[带记忆]  轮1 空 → 轮2 空 → 最终 JSON 解析成功 fav=+5          ← 这个成功了
```

强制 `response_format` 触发了 **`llm.py:1508` 那段的原作者已经写明的问题**：
DeepSeek 官方文档承认 *"When using the JSON Output feature, the API may
occasionally return empty content."* 而空返回后的重试拿回的是 `[FACE:害羞]`
这种碎片 —— **比原来的散文回复更糟**（散文至少是通顺的话）。

> 🚫 **给后来者**：不要为了 fav/mood 再去给 FC 路径加 `response_format`。
> 原作者在 `_salvage_plain_reply` 的注释里已经解释过为什么放弃 json_mode。
> 除非先解决"JSON 模式偶发空返回"（例如空返回时改用单句小请求补 fav/mood），
> 否则这条路是负收益。改动已完整撤回，`llm.py` 与改动前逐字节一致
> （备份在 `huanmeng\_backup-jsonmode-<时间戳>\`，仅作事故记录，无需使用）。

**结论**：`||` 修复（§4.7.10）是这个问题**唯一有效**的修复。
修复后 JSON 合规率从 **0/4 变成 5/7**（真实调用实测），且回复不再带 `||`；
残留的"少数回复丢 fav/mood"属于模型在 `thinking=False` 下的固有抖动，
**可接受、且比引入空返回风险划算**。

> ⚠️ **中转站有 300 万 TPM 上限，实测会被打爆**：本轮 40 次视觉打标 + 8 次对照调用
> 连续跑，触发了
> `HTTP 429 rate_limit_exceeded: user TPM (limit=3000000, current=3240077)`，
> 并让幻梦的**熔断器跳闸**（`连续3次失败 → 冷却180s`，期间走规则兜底）。
> 表现是日志里出现 11 个 ERROR、且回复质量可能下降。
> **教训**：跑 `import_faces.py --apply`（或任何批量 LLM 测试）时不要同时做压测。
> 429 是瞬时的、冷却后自动复位（实测 14:14:55 复位，无需人工干预），
> **排查时看到 429 不要误判成配置错误**。

#### 4.7.14 表情「画面描述」改用实际图片生成（`_FACE_DESC` 的坑）

**问题**：`face_lib.py:258` 的 `_FACE_DESC` 是一张「48 个情绪词 → 一句话画面简述」表，
会跟着词表一起进 system 提示词（`开心(眯眼笑)/坏笑(抿嘴偷笑不怀好意)/…`），
让 LLM 把情绪词和真实画面对上号、选图不再盲猜。

但那张表是照**原作者那批素材**逐张校对写的。一旦换成自己导入的素材，它就开始
**"骗" LLM**：词表说「开心 = 眯眼笑」，而 `开心_001.png` 实际是"弯眼红晕露齿笑"。

**解决（两层）**：

1. **`face_lib` 增加旁路覆盖**：`face_keywords_hint()` 优先读
   `data/faces/_descriptions.json`（经 `_get_desc_override()`，只加载一次），
   `_FACE_DESC` 退化为"没有自有描述时的默认值"。文件不存在时行为**完全不变**（已实测）。
2. **新工具 `D:\QQBot\tools\describe_faces.py`**：用视觉模型对 `data/faces/` 的
   **实际图片**重新生成描述。默认 dry-run，`--apply` 才写文件；会剔除失效 key。

**踩到的两个坑（都值得记）**：

- 一开始让模型「一次看 3 张再概括」，结果它**逐张描述再拼接**：
  `不满 → 斜眼撇嘴托腮撇嘴托腮撇嘴`、`惊讶 → 瞪眼张嘴瞪眼张嘴瞪眼嘟嘴`。
  → 改为**只看代表图**（`--sample` 默认 1）+ 提示词明确禁止逐张描述，输出立刻干净。
- 关键词**必须用 `face_lib._tags_from_stem()` 提取**，不能自己按 `_` 前缀切：
  库对中文名取的是**末 2 个汉字**（`打哈欠_001 → 哈欠`、`打招呼_001 → 招呼`、
  `抱东西_002 → 东西`）。按前缀切会得到 `打哈欠` 这种对不上的 key，描述白生成。
  （实测踩到，有 3 个词没配上，已修）

**生成结果（12 个关键词 / 40 张）**：

| 词 | 新描述（照实际图片） | 原表（原作者素材） |
|---|---|---|
| 开心 | 弯眼红晕露齿笑 | ~~眯眼笑~~ |
| 委屈 | 垂眉大眼波浪嘴黄脸 | ~~瘪嘴要哭~~ |
| 生气 | 红脸冒火瞪眼张嘴 | ~~鼓脸瞪眼~~ |
| 疑惑 | 斜眼挑眉撇嘴 | ~~歪头冒问号~~ |
| 慌张 | 红脸瞪眼张嘴滴汗 | ~~手忙脚乱冒汗~~ |

日志确认：`自有素材画面描述已加载: 12 条`；
提示词变为 `不满(斜眼皱眉撇嘴)/坏笑(挑眉斜眼咧嘴黄脸)/…`（不再骗 LLM）。

> 导入新素材后**重跑一次** `describe_faces.py --apply` 即可。
> ⚠️ 每张图一次视觉调用，注意 TPM（见 §4.7.13 末尾）。
> 备份：`huanmeng\_backup-facedesc-<时间戳>\`。

#### 4.7.15 🎯 生产失败的真正根因：`thinking=False`（一举解释 fav/mood **和**表情包）

**背景**：§4.7.10 的 `||` 修复后，线上仍连续出现非 JSON（14:14、14:27 两轮）。
一度以为只是"残留抖动"。但把 8 次实验按**是否等于生产配置**重新排列后，规律极干净——
失败**精确聚集在「真实历史 + `thinking=False`」**，而这正是生产默认值。

**决定性的三连对照**（同一消息 `retest`、同一份 100 条真实历史，**只改 `thinking`**）：

| thinking | 结果 |
|---|---|
| **False**（当时的默认） | ❌ `诶，主人这是要复测嘛…`（纯散文）→ `fav=+0 mood=`，**无 `[FACE:]`** |
| **None**（跟随 API 默认） | ✅ `{"replies":["收到，retest 上线～","信号满格，主人听得到吧 [FACE:招呼]",…],"fav":1,"mood":"开心"}` |
| **True** | ✅ `{"replies":["回路收到啦，主人～","这边回话是通的哦，识图也还在线呢[FACE:开心]",…],"fav":1,"mood":"开心"}` |

→ **关掉思考时，模型会退化成散文、丢掉整个 JSON 帧。** 这一条同时是
**fav/mood 恒空**与**表情包发不出去**的根因：走 salvage 就没有 fav/mood；
没有 JSON 帧，模型也写不出 `[FACE:xxx]`。

**修复**（`core/pipeline.py:831`）：`thinking = False` → **`thinking = None`**
（跟随 API 默认；本模型默认即开启），仅 deep 命中的长问题显式 `True`。

**代价（务必知情）**：每次回复**慢约 1.5s**、多花 reasoning token（实测 300~380 字）。
换来格式与功能正确，值得。备份：`huanmeng\_backup-thinking-<时间戳>\`。

> ❌ **纠正 §4.7.10 里"合规率 0/4 → 5/7"的说法**：那个统计把"空历史 / 思考开启"
> 的成功案例混了进来，掩盖了真正的规律。**按生产配置算，`||` 修复后仍是 0/4 全失败**
> （14:14、14:27 + 两次复现）。真正的修复是本节这条。

> 🚫 **§4.7.13 的结论也要随之收窄**：当时**否决 `response_format` 是对的**
> （它确实引入空返回，反而更糟），但"fav/mood 只能忍"的结论**是错的** ——
> **根本不用动 `llm.py`，改 `thinking` 默认值就够了。**
> 后来者不要再往 FC 路径加 `response_format`。

#### 4.7.16 表情包导向：从"鼓励常发"改为"可选、别刻意"（用户要求）

用户反馈：**「没必要让机器人一直发表情」**。

原因出在提示词里三处在**主动推着它发图**：

| 文件 | 原文（催发） |
|---|---|
| `data/skills/10_format_group.md` | 【表情包：多发表情（重要）】…**鼓励常发**…「拿不准就先来一张」 |
| `data/skills/11_format_private.md` | 「**私聊可以大方用**…一轮带 1~2 张很正常…**多一点也行**」 |
| `data/skills/60_face_lib.md` | 【表情包（重要，**要多发**）】…「**要常发**」…「欢迎多来几张」 |

**改法**（三处统一）：
- 标题改为「表情包：可选，别刻意」，删掉「要多发 / 要常发 / 鼓励常发 / 拿不准就先来一张 / 欢迎多来几张」
- 明确 **「发不发都行，顺其自然：多数回复不带图是正常的，不必为了发而发」**
- 收紧为 **「一次回复最多 1 张」**，并禁止连着几轮都发图
- 另删掉「可以整句只有 `[FACE:大哭]`、单独占一拍」—— 不允许发"只有图没有字"的消息

实测验证（`_build_system_text` + `_build_skill_refs`，群聊/私聊各一遍）：
旧措辞 **0 处残留**，新措辞（顺其自然 / 发不发都行 / 可选，别刻意 / 最多 1 张）**全部命中**。
备份：`huanmeng\_backup-facepush-<时间戳>\`。

> 还想更彻底？两个现成开关：
> - QQ 里发 **`/~key face_inline off`** —— 不再注入逐句配图规则，退回"整条回复**至多 1 张**、且发在所有文字之后"的旧行为
> - 把 `data/faces/` 清空 —— 词表为空，模型根本不知道能发图

#### 4.7.17 ⚠️ `/~reload` **不会**重载技能文件（两处文档长期写错）

**排查中发现**：QQ 里发 `/~reload` 走的是命令表的 `modules/commands.py:983 cmd_reload`：

```python
async def cmd_reload(...):
    from modules.judge import reload_keywords
    reload_config()        # 只重读 bot_config.toml 等配置
    reload_keywords()      # 只重载判断关键词
    # ← 没有 reload_skill_cache()
```

它**不碰** `services/llm.py` 的技能缓存（`_skill_sections`）。真正会重载技能的是
`bot.py:269 Bot.handle_reload()`（调了 `reload_skill_cache()`），但它只能由
**控制文件** `data/control.txt` 或 `main.py:59` 触发 —— 而控制文件监听器
（`bot.py:400 _bg_control_watcher`）的**启动调用在 `bot.py:140` 被注释掉了**
（注释原文："删除启动，方法体保留为死代码"）。**即该入口是死的。**

**结论**：

| 改什么 | 生效方式 |
|---|---|
| `config/bot_config.toml`（模型名、回复兴趣等） | `/~reload` **有效**（走 `reload_config()`） |
| `config/.env` 的 KEY | 必须**重启进程**（`load_dotenv` 不覆盖已有环境变量） |
| **`data/skills/*.md`（人格锁、格式、表情、提醒…）** | **必须重启幻梦**，`/~reload` **无效** |

> ⚠️ 这直接推翻了本文 §4.4 与 §7、以及 `README.md` 里"改完人格发 `/~reload` 热加载"的说法。
> 本次改表情导向就是**靠重启**才生效的（重启日志 `提示词已加载: 26 个章节`）。
> 历史教训对得上：§4.4 角色卡替换当年之所以"生效"，多半也是因为之后重启过。

#### 4.7.18 搜索功能修复（`search_web` 无法调用）

**用户反馈**：机器人的 `search_web` 无法正常调用。日志实证：

```
search:perform_search:73  执行 DeepSeek 原生搜索
search:perform_search:81  ⚠️ DeepSeek 原生搜索异常: No module named 'requests'，回退 Agent 搜索
search:perform_search:86  DeepSeek 搜索无结果
FC: 工具 search_web 返回 35 字符          ← 实际内容就是"暂无搜索结果"
```

**两个互相独立的缺陷，缺一都不通**：

**① 缺包 → 整个搜索模块 import 失败**
`modules/web_search.py:19-20` 和 `modules/local_search.py:15-16` 都是**模块级**
`import requests` / `from bs4 import BeautifulSoup`，而 `requirements.txt` **只声明了
`ddgs` 和 `httpx`，没有 `requests`/`bs4`**。
→ `from modules.web_search import ds_native_search` 时整模块抛 ImportError，
**连真正的回退实现 `agent_search` 也一起不可用**。

已装 `requests 2.34.2` + `beautifulsoup4 4.15.0`，并**补齐 `requirements.txt`**
（连带把 §5.4 漏掉的 sqlalchemy/greenlet/aiosqlite/pillow/numpy/psutil 与
fastapi/uvicorn 一并写进去）。

**② `perform_search` 的"回退"是空壳（真代码 bug）**
`modules/search.py` 注释写着「Step 3: Agent 搜索（回退）」，但正文只有：

```python
if result_text is None:
    set_search_cache(query, result_text)
    logger.info("DeepSeek 搜索无结果: '%s...'", query[:40])
    return f"{search_tip}\n\n暂无搜索结果。"      # ← 没调用任何回退实现
```

而上一级的 `ds_native_search` 走**官方** `api.deepseek.com/responses` + 环境变量
`DEEPSEEK_KEY`；本部署走中转站、该 key 为空 → **必然抛异常**。
两者叠加 = `search_web` **永远**返回"暂无搜索结果"。

**修复**：接上真正的回退链 `ds_native → agent_search → local_search`，
并让此前**从未被使用过**的 `source` 参数（`/~search baidu xxx` 的那个）真正生效。

**⚠️ 但修复后实测发现：抓取源本身正被反爬拦截**（与代码无关）

| 级别 | 实测 |
|---|---|
| `ds_native_search` | ❌ `RuntimeError: DEEPSEEK_KEY 未配置` |
| `agent_search`（带相关性打分门） | ⚠️ 时好时坏：`南宁 天气` 拿到相关结果；`马头节奏` 全 0 分被**正确拒收** |
| `local_search` 百度 | ⚠️ **先好后坏**：起初 3 个查询全相关，随后触发**图形验证码** |
| `local_search` 必应 | ❌ 持续返回**无关结果**（同一查询两次分别得到"央视网"和"Office 激活工具"，而页面 title 却是正确查询词） |

百度最终被拦成：`HTTP 200 → https://wappass.baidu.com/static/captcha/tuxing_v2.html`，
`c-container` 命中 0。

**已排除**系统代理干扰：`ProxyEnable=0`、无 TUN 网卡、默认路由走本地路由器
（Clash 服务在跑但未接管流量）→ 属**高频抓取触发的 IP 级反爬**。

**故回退策略取「宁缺毋滥」**：`source="all"` 时**只走百度**
（必应的无关结果被当成"搜索结果"发给用户，比老实说"没搜到"更糟）；
想强制必应用 `/~search bing <关键词>`。

> 💡 **要真正稳定，唯一可靠路径是 `ds_native_search`** —— 官方 Responses API 的
> **服务端 web_search**，不抓页面、不碰反爬。用户当天就提供了官方 key，见下。

**✅ 最终解决（10-01 15:00）—— 又挖出第二个坑：模型选错了**

用户在 `config/.env` 配好官方 `DEEPSEEK_KEY` 之后，`ds_native_search` 能跑了，但
**返回的不是搜索结果**。dump 原始响应后发现：

| 模型 | 实测 |
|---|---|
| `deepseek-flash`（代码原用） | ❌ **根本不执行 web_search** —— 把工具调用当**纯文本**吐出来（`<｜tool▁calls▁begin｜>web_search<｜tool▁arg_key｜>query…`），或直接答"我没有可用的搜索工具"，返回的全是训练知识 |
| **`deepseek-v4-pro`** | ✅ 真的产生 `web_search_call`（`search` + `open_page` 打开中国天气网/中央气象台），并综合出**带当日实时信息**的答案 |

**诊断依据**：`output` 数组里 `deepseek-flash` 只有 `['reasoning','message']`，而
`v4-pro` 是 `['reasoning','web_search_call','reasoning','web_search_call',…,'message']`；
flash 的 reasoning 原文写着「**但我们没有可用的搜索工具？**」。
`tool_choice` 强制也救不了 flash（它仍答"我无法直接获取实时天气数据"）。
顺带确认：该 key 可用模型为 `deepseek-flash` / `deepseek-v4-pro`；
`{"type":"web_search"}` 是正确工具名（`web_search_preview` 会被丢弃）。

**改动**（`modules/web_search.py`，`ds_native_search` 的 payload）：

```python
"model": "deepseek-v4-pro",          # 原 deepseek-flash，实测不执行搜索
"tools": [{"type": "web_search"}],
"tool_choice": "required",           # 强制真搜，否则偶发凭记忆作答
```

**⚠️ 模型名清单：别试图换成任何 flash**（2026-10-01 实测）

官方 `/responses` 只认两个模型名，报错原文：
> `The supported API model names are deepseek-flash, deepseek-v4-pro, but you passed deepseek-v4.1-flash.`

| 名称 | 来源 | 结果 |
|---|---|---|
| `deepseek-flash` | **官方** | 接受，但 `web_search_call=0` —— **不搜** |
| `deepseek-v4-flash` | 官方（宽松接受） | 接受，`web_search_call=0` —— **不搜** |
| **`deepseek-v4-pro`** | **官方** | ✅ 真搜（`search` + `open_page`） |
| `deepseek-v4.1-flash` | **中转站**命名（带 `deepseek/` 前缀） | ❌ 官方直接 **400** |
| `deepseek/deepseek-v4.1-flash` | 中转站 | 官方不认；中转站 `/responses` 虽**接受**但 `web_search_call=0` —— **同样不搜** |

→ **服务端联网搜索只有 `deepseek-v4-pro` 一条路，没有便宜的 flash 版本可选。**
但**不影响日常开销**：机器人主回复仍在用中转站的 `deepseek-v4.1-flash`
（便宜快速），`v4-pro` 只在**搜索那一次调用**里用，且只在搜索被触发时才发生。

**实测（重启后、走 bot 同一条 `.env` 加载路径）**：

| 查询 | 耗时 | 结果 |
|---|---|---|
| 南宁今天天气 | 3.7s | ✅ 今日真实天气（10月1日 25~35℃） |
| 马头节奏是什么梗 | 10.2s | ✅ 正确答出 TheShy 黑称的来历 |
| **DeepSeek V4 发布了没有** | 5.3s | ✅ **"已于 2026 年 4 月 24 日正式发布"** —— 而 flash 凭训练知识答"尚未发布" |

→ **搜索从此不再依赖网页抓取**，反爬问题（百度验证码 / 必应垃圾结果）与搜索彻底脱钩。
`agent_search` 与 `local_search` 退化为"官方搜索不可用时的兜底"，保留未动。

备份：`huanmeng\_backup-websearch-<时间戳>\`、`huanmeng\_backup-search-<时间戳>\`、
`huanmeng\_backup-env-<时间戳>\`。

#### 4.7.19 「search_web 仍失效」的复查：其实坏的是 `weather` 指令

**用户反馈**：搜索修好后仍说 `search_web` 失效。复查日志发现**那次根本没触发 search_web**。

**现场还原**（用户消息 `@大肥鱼 今日江阴天气`）：

```
pipeline: @机器人检测 → 直接回复
LLM原始输出: {"replies":[…],"calls":[{"cmd":"weather","args":"江阴"}]}   ← 选了 weather 指令
CALL执行: weather
weather:query_weather:36 查询天气: city=江阴
weather:query_weather:50 ERROR 天气查询失败:              ← 错误信息是空的
```

**两点澄清**：

| 疑问 | 事实 |
|---|---|
| 为什么没走 `search_web`？ | ① 该消息**是 @ 机器人**，而 `auto_search_if_needed` 注明「**仅对非 @ 消息生效**」→ 自动搜索不介入；② @ 时由 LLM 自己决定调不调工具，它选了更对口的 **`weather` 指令**（走 `60s.viki.moe` 天气 API）。**这个选择本身是对的** |
| 那到底什么坏了？ | **`weather` 指令的网络超时**，与 `search_web` 无关 |

**`weather` 超时根因**：`modules/weather.py:39` 原为 `httpx.AsyncClient(timeout=10.0)`。实测该 API：

```
连续 4 次: 2.7s / 2.4s / 2.4s / 1.6s      ← 平时很快
再测 3 次: 2.7s / 1.4s / 12.4s            ← ★ 偶发 12.4s，超过 10s 就挂
```

而 `except Exception as e: logger.error("天气查询失败: %s", e)` 里 `str(e)` **是空的**，
日志只剩 `天气查询失败: ` —— 极易被误判成"API 挂了"。实际只是超时。

**修复**：`timeout=10.0` → **`25.0`**。备份 `huanmeng\_backup-weather-<时间戳>\`。

**同时复查 `search_web` 本身：FC 全链路实测完全正常**：

```
LLM → tool_calls: [('search_web', "{'query': '马头节奏 梗 什么意思'}")]
搜索词优化 → 执行 DeepSeek 原生搜索 → 搜索完成: 632字符（约 10s）
FC: 工具 search_web 返回 632 字符
回复: 查到啦主人～「马头」是英雄联盟选手 TheShy 姜承録的外号…
```

> 📌 **给排查者**：`@机器人` 的消息**不会**走自动搜索（`auto_search_if_needed` 仅对非 @ 生效），
> 联网与否由 LLM 自己决定。想**确定性地**验证搜索，请在 QQ 里发
> **`/~search <关键词>`** —— 它直接调 `perform_search`，不经过 LLM 决策。

#### 4.7.20 `weather` 工具「调不动」的完整根因（三层缺陷叠加）

**用户反馈**：`weather` 工具无法正常调用。日志实证：

```
15:09:20.777  查询天气: city=江阴                    ← API 成功（约 3s，§4.7.19 的超时修复生效）
15:09:23.833  指令执行完成 [weather]: 无返回值（已自行发送）
15:09:23.835  ERROR   playwright 库未安装!
15:09:23.835  WARNING [WeatherCard] 生成失败，回退到纯文本模式
15:09:23.836  （之后没有任何发送 —— 日志直接跳到 15:09:40）
```

用户看到的是：机器人说"好嘞，江阴的天气我这就给主人跑一遍哦～"，然后**一片沉默**。
**三层缺陷，每一层都足以单独搞坏它**：

**① `send_weather_card` 契约写反（关键）** —— `modules/changelog.py`

```python
Returns:
    成功返回 None（已自行发送）；失败/缺依赖返回文本      ← docstring 声明的契约
...
if not img_path:
    return None  # 让调用方用原始纯文本方式处理           ← 实际却返回 None
```

而调用方 `commands.py:cmd_weather` 的判据是：

```python
card_result = await send_weather_card(...)
if card_result is not None:        # ← 只有非 None 才发纯文本
    ...发 build_weather_report...
```

→ 失败时的 `None` 被理解成"卡片已自行发送" → **纯文本分支永不执行** → 彻底沉默。
（注：同文件的 `send_card_image` 契约是**对的**：成功 None / 失败返回错误文本。）

**② 纯文本回退的语言键根本不存在**
修好 ① 之后，回退文本立刻暴露出满屏裸占位符：

```
[LANG:weather.talk_user]
[LANG:weather.talk_temp_range]
[LANG:weather.aqi_moderate]…
```

因为 `config/lang.toml` 的 `[weather]` 段**只有 3 个键**
（`prompt_input` / `searching` / `fallback_error`），而 `build_weather_report()`
共需要 **15 个键**；`utils/format_lang.py:77` 在键缺失时直接返回 `[LANG:key]` 裸串。

→ **两个 bug 互相掩盖**：① 让回退永不执行，所以从没人发现 ②。
已在 `lang.toml` 补全 15 个键（`talk_*` / `table_header_*`）。

**③ chromium 路径被写死成 Linux 路径（卡片本体起不来）**
`modules/changelog.py:_ensure_browser()`：

```python
_browser = await _playwright_instance.chromium.launch(
    headless=True,
    executable_path="/usr/bin/chromium-browser",      # ← 原作者 Linux 部署的路径
```

Windows 上即便装了 playwright，该路径也不存在 → 启动必然失败 →
**天气 / 快递 / 更新日志所有卡片**一起退化成纯文本。

**修复**：新增 `_find_chromium_executable()` 按平台探测，**优先复用本机已有的 Chrome**
（`C:\Program Files\Google\Chrome\Application\chrome.exe`），
**省掉 `playwright install chromium` 的 ~150MB 下载**；实在找不到才交给 playwright 自带的。

> 补充两点事实：
> - `requirements.txt` 其实**早就声明了** `playwright>=1.40.0`，只是从没装过。
> - README §5.4 写的"playwright 未安装但实测不影响" —— 那句**只对 `/~help` 成立**
>   （help 卡片已迁到 Pillow），对 **weather / box / changelog 卡片完全不成立**。README 已更正。

**验证**：

```
[Playwright] 使用浏览器: C:\Program Files\Google\Chrome\Application\chrome.exe
[Playwright] Chromium 启动成功（极致加速已启用）
卡片生成: OK  80.0 KB
```

**遗留（故意未改，属历史代码卫生）**：截图用的是 `type='jpeg'`（`changelog.py:651`），
而文件名一律 `.png`（`card_*.png` / `weather_*.png` / `box_*.png`）——
**内容是 JPEG、扩展名却是 PNG**。原作者的 Linux 部署里这些卡片是能正常发出的，
说明 NapCat/QQ 按字节嗅探、不依赖扩展名，故**不动它**，以免给 changelog/box 卡片引入回归。

备份：`huanmeng\_backup-weather-<时间戳>\`、`_backup-weathercard-<时间戳>\`、
`_backup-lang-<时间戳>\`。

#### 4.7.21 群聊「只理我、不理别人」= 群不在白名单

**用户反馈**：群聊里无法正常响应除我以外的人。

**根因**：`core/dispatcher.py:339`

```python
if is_group and chat_id not in cfg.group_list and user_id != cfg.admin_qq:
    ...
    return   # 陌生群：无论是否指令，一律不进管道（:356）
```

即：**不在 `group_list` 里的群，除 admin 外一律不响应**；admin 因 v2.3.49 加的
"管理员豁免"被放行（`:337-338` 注释写明本意：让管理员进新群能调试、能加白名单）。
→ 外在表现就是"**只有我说话它理，别人说话它当没听见**"。

而当时 `config/adapter_config.toml` 写的是 `group_list = [<GROUP_1>]`，
**实际在用的群 `<GROUP_2>` 根本不在名单里** —— 这正是 §6 待办表里挂了一下午的那条，
现在终于以"症状"的形式浮了上来。

**修复**：

```toml
group_list = [<GROUP_1>, <GROUP_2>]
```

**生效方式**：`group_list` 属于**配置**（`core/config.py:451` 从 `adapter_config.toml` 读取），
所以 QQ 里发 **`/~reload` 就能生效、不必重启** —— 这一点与 `data/skills/*.md` 正相反（见 §4.7.17）。
本次为稳妥仍重启了一次，已确认运行进程读到 `group_list = [<GROUP_1>, <GROUP_2>]`。

> 📌 **以后再遇到"只有我能触发"**：第一件事就是查这个群在不在 `group_list`。
> 私聊同理 —— `private_whitelist = [<OWNER_QQ>, <FRIEND_QQ_1>]`（留空 = 不限制）。
> 另外**戳一戳**走的是同一套判断（`:192`），行为一致，别只看消息路径。

> ⚠️ **白名单只是第一道门，还有第二道：回复兴趣阈值**。
> `modules/judge.py:288-294`：进管道后还要 `interest_score >= reply_threshold` 才回，
> 而 `bot_config.toml` 的 `回复兴趣 = 8`（偏高 → 偏沉默）。
> 所以"加了白名单还是不太理人"是正常的，需要下调阈值。
>
> **不用改文件，QQ 里就能管**（管理员指令）：
>
> | 命令 | 作用 |
> |---|---|
> | `/~owner glist` | 看群/私聊白名单 |
> | `/~owner gadd <群号>` | 加群进白名单 |
> | `/~owner gremove <群号>` | 移出白名单 |
> | `/~owner gset <群号>` | 看该群的覆盖设置 |
> | `/~owner gset <群号> reply <阈值>` | **单独调这个群的阈值**（推荐，不动全局） |
> | `/~owner get bot.reply_threshold` / `set bot.reply_threshold 6` | 看/改全局阈值 |

备份：`huanmeng\_backup-grouplist-<时间戳>\`。

#### 4.7.22 `/~owner gadd` 报"未知操作" —— 用户照抄了帮助里的尖括号

**用户反馈**：执行 `/~owner gadd` 得到"未知操作: gadd"。

**现场**（日志实证）：

```
指令解析: prefix=/~ cmd=owner args=['gadd', '<<GROUP_3>>'] user=<OWNER_QQ>
指令执行完成 [owner]: 未知操作: gadd
```

用户输入的是 `/~owner gadd <<GROUP_3>>` —— **把帮助文案里的占位符尖括号一起打进去了**。
于是 `_owner_legacy`（`commands.py`）的守卫

```python
if action == "gadd" and len(args) >= 2 and args[1].isdigit():
```

里 `'<<GROUP_3>>'.isdigit()` 为 **False** → 一路落到函数末尾
`return f"未知操作: {action}"` → 用户看到"未知操作: gadd"，
**完全看不出是参数格式问题**（这个报错极具误导性）。

**两层修复**：

1. **即时**：把该群加进白名单。回给用户的正确写法是
   `/~owner gadd <GROUP_3>`（**不要尖括号**）。
2. **根治**：`handle_command` 解析完参数后，统一剥掉「**整体**被括号/引号包裹」的参数
   （新增 `modules/commands.py::_strip_arg_wrapper()`）：

   ```
   '<<GROUP_3>>' → <GROUP_3>      【关键词】 → 关键词      (123) → 123
   '"带引号"'      → 带引号           《书名》   → 书名
   '正常文本'      不变                'a<b'      不变          '<>'  不变
   ```

   仅在首尾**成对**、且中间内容非空时才剥离 —— 所以参数里正常出现的尖括号不受影响。

> 📌 **通用教训**：帮助文案里的 `<群号>` / `【关键词】` 是占位符约定，
> 但用户（哪怕很懂技术）会照抄。**容错应该做在解析层**，而不是让命令静默落到
> "未知操作"。同类命令（`gremove` / `padd` / `premove` / `gset`…）现在一并受益。

**验证**：重启后 `group_list = [<GROUP_1>, <GROUP_2>, <GROUP_3>]` 三者全部生效。

#### 4.7.23 绘图/视频报 `Illegal header value b'Bearer '` —— 缺 `AGNES_API_KEY`

**用户反馈**（群聊里）：

```
@尿 图片生成失败喵~ (不扣次数)
错误: LocalProtocolError: Illegal header value b'Bearer '
```

**根因**：`modules/agnes.py` 的绘图/视频 key 从环境变量读，而 `.env` 里**从来没配过**：

| 功能 | 环境变量 | 服务 |
|---|---|---|
| 文生图 `/~draw` | `AGNES_API_KEY` | `https://v2.cloudmist.cloud/v1`（模型 `gpt-image-2`） |
| 文生视频 `/~video`、`/~img2video` | `AGNES_KEY` 或 `AGNES_API_KEY` | `https://apihub.agnes-ai.com/v1` |

`_headers()` 于是拼出 `Authorization: Bearer `（**后面什么都没有**）→
`h11` 判定为非法 header 值 → 抛 `LocalProtocolError`。这条原始异常又被
`_bg_gen_image()` 当成 `result["error"]` **原样贴进群里**，用户完全看不懂。

**当时 `.env` 只有**：`RELAY_KEY` / `RELAY_URL` / `DEEPSEEK_KEY` / `DEEPSEEK_URL`
（`ZHIPU_KEY` 也空）—— **没有任何 AGNES 配置**。

**修复（两层）**：

1. **代码（已做）**：在三个入口加**前置守卫**，key 为空就直接返回可读提示，
   不再让它变成协议异常 —— `_gen_image()` / `_gen_image_with_ref()` / `_gen_video()`。
   现在会回：

   > 绘图服务未配置 API Key：请在 config/.env 里填 AGNES_API_KEY（绘图用）后重启幻梦。

2. **配置（需用户提供 key）**：这两个是**第三方服务**，要去对应平台申请：

   ```ini
   # config/.env
   AGNES_API_KEY=<API_KEY> 的 token>    # 文生图（/~draw）
   AGNES_KEY=<API_KEY> 的 key>              # 文生视频（/~video、/~img2video）
   ```

   ⚠️ 改完 `.env` 必须**重启幻梦**（`load_dotenv` 不覆盖已存在的环境变量，见 §7）。

> 📌 `data/update_log.md:4419` 记过：绘图 key 曾经是**硬编码在源码里的 CloudMist token**，
> 后来才改成读环境变量。所以老部署那份 key 没被带过来 —— 本部署自然就是空的。

> ⚠️ 本次改 `agnes.py` 时**没有先备份**（改动是纯新增的 3 个前置 `if` 守卫、
> 未删改任何原有逻辑，风险很低）。后来者若要动这个文件，请先备份。

#### 4.7.24 绘图改造：没有 CloudMist key → 改用**中转站**文生图（已实测可用）

**用户反馈**：没有 Agnes/CloudMist 的 key，但发现**中转站 key 本身就能调文生图模型**
（`black-forest-labs/flux-1.1-pro`、`bytedance/jimeng_t2i_v30` 等）。

**实测过程（结论有反转，值得记全）**：

| 尝试 | 结果 |
|---|---|
| `flux-1.1-pro` / `jimeng_t2i_v30` → `POST /v1/images/generations` | ❌ `scheduler.route_not_supported`（"model does not support request path"） |
| 同上 → `/v1/images/edits`、`/v1/chat/completions`、`/v1/responses`、`/v1/messages`、`/v1/embeddings`、`/v1/audio/speech`、`/v1/moderations` | ❌ **全部被拒** |
| 其他拼法 `/v1/image/generations`、`/v1/images/generate`、`/v1/generate`、`/v1/tasks` | ❌ 404（这些路径根本不存在） |
| **`openai/gpt-image-1` → `POST /v1/images/generations`** | ✅ **成功**，返回 `b64_json` |

→ **这个中转站的 OpenAI 形状文生图是通的，但要用 `openai/gpt-image-1`。**
用户提到的那两个模型需要别的调用形状（可能是异步任务 API），OpenAI 形状下 7 条路径全被拒。
另外该站 `/models` **不含任何图片模型**（213 个都是对话模型），所以不能靠它来发现可用图模型。

**尺寸坑**：本项目 `_resolve_size()` 默认给 `1536x864`（16:9），
而中转站的 gpt-image-1 **只认三档**：

```
Invalid size '1536x864'. Supported sizes are 1024x1024, 1024x1536, 1536x1024, and auto.
```

→ 新增 `_normalize_size_for_openai()` 按宽高比就近归一：
`1536x864 → 1536x1024`、`864x1536 → 1024x1536`、其余 → `1024x1024`。

**实现**（`modules/agnes.py`）：新增 `_draw_backend()`，策略为
**有 `AGNES_API_KEY` 就走 CloudMist（原行为，支持自定义尺寸）；否则回落中转站**：

```python
RELAY_DRAW_MODEL = os.environ.get("RELAY_DRAW_MODEL", "openai/gpt-image-1")
```

可用环境变量 `RELAY_DRAW_MODEL` 覆盖模型名（**不用改代码**）。
`_gen_image()` 与 `_gen_image_with_ref()` 都改用选中的后端与 key。

**实测（两条路径都真跑通）**：

| 能力 | 端点 | 耗时 | 结果 |
|---|---|---|---|
| 文生图 `/~draw` | `POST {RELAY}/images/generations` | **56s** | ✅ 1536×1024 / 2.7 MB |
| 参考图生图 | `POST {RELAY}/images/edits` | **112s** | ✅ 返回 `b64_json` |

出图质量很好（实测「一只橘猫坐在窗台上，阳光，写实摄影风格」高度贴合）。

> ⚠️ **视频仍不可用**：`/~video`、`/~img2video` 走 `apihub.agnes-ai.com`，**仍需要 `AGNES_KEY`**。
> 中转站能否文生视频**本次未验证**，别当成可用。

> ⚠️ **耗时提示**：单张 **56~112 秒**。绘图本身是后台任务（不阻塞聊天），
> 但用户等待明显变长，且**每张都消耗中转站额度**。

> 📌 **备份说明**：本次与 §4.7.23 是同一次连续改动，**改造前的原始 `agnes.py` 未单独备份**。
> 事后补建了一个**改造后**的还原点：`huanmeng\_backup-agnes-relaydraw-<时间戳>\`。

#### 4.7.25 绘图一键开关（`/~key draw on|off`）

**用户要求**：能不能一键开关该功能。（背景：单张 56~112 秒、每张都消耗中转站额度，需能临时关掉。）

**做法**：**复用框架已有的测试项开关机制**（`modules/features.py` + `/~key` 指令），
没有另造一套。新增注册项：

```python
"draw": {
    "aliases": ("绘图", "画图", "绘画", "文生图", "ai画图", "作画"),
    "default": True,
    "desc": "AI 文生图 / 图生图（/~draw）",
    "affects": "关闭后 /~draw 与 LLM 的绘图能力都不可用，直接回一句提示，不影响其它功能",
}
```

**三处联动**（只关指令入口是不够的）：

| # | 位置 | 作用 |
|---|---|---|
| ① | `modules/features.py` | 注册开关，`/~key` 列表里自动出现 |
| ② | `modules/agnes.py::cmd_draw` | 关闭时**最先**返回提示 —— 连 `help` 都不给，且**不消耗每日配额** |
| ③ | `services/llm.py::_build_dynamic_command_list` | 关闭时把 `/~draw` **从 LLM 的指令清单里剔除** |

**③ 才是关键**：LLM 是靠指令清单知道"我能画图"的。只关入口不关清单，它仍会**幻觉调用**，
用户只会收到"功能已关闭" —— **体验上像是坏了**。为此新增 `_FEATURE_HIDDEN_CMDS`
（feature → 要隐藏的指令名）与 `_cmd_hidden_by_feature()`；
以后任何"要连 LLM 一起关"的功能都能挂上去。

**怎么用**（QQ 里发，仅管理员）：

```
/~key                 看所有测试项及当前状态
/~key draw off        关闭绘图
/~key draw on         打开绘图
/~key 绘图 off        中文别名也行
/~key draw reset      恢复默认（= 开启）
```

⚠️ **不用重启、不用改代码** —— 开关存在 `data/features.json`，
`is_enabled()` 是运行时读取，改完**立即生效**。

**实测 8 项全过**：

```
1) 注册表里有 draw: draw / draw          5) 关闭后清单含 /~draw : False   ← 关键
2) 默认状态: True                        6) 关闭后 /~draw 返回 : 绘图功能当前已关闭喵~
3) 开启时清单含 /~draw : True               （管理员可在 QQ 里发 /~key draw on 打开）
4) 关闭后 is_enabled: False              7) reset 后恢复默认: True
                                         8) 恢复后清单含 /~draw : True
```

改动文件：`modules/features.py`、`modules/agnes.py`、`services/llm.py`。

#### 4.7.26 增加「看动图」的能力（GIF / 动图 WebP 多帧合成）

**用户要求**：能不能增加看 gif 的能力。

**问题**：`services/image_api.py` 的预处理链路是
`PIL.Image.open(...)` →（转 RGB / 缩放）→ `save(PNG)` —— 而 **PIL 默认停在第 0 帧**，
所以机器人"看 GIF"**其实只看了一帧**，动作与表情变化全部丢失。
（日志里 `图片预处理: GIF(300x300) → PNG …` 能看出**格式判断是对的**，但内容只有首帧。）

**方案**：新增 `_compose_animated_frames()` —— 均匀抽取 ≤6 帧（含首尾），
等比缩放后拼成 **3 列网格图**，每格左上角标**帧序号**，再交给视觉模型。

设计要点：

- **只花一次视觉调用的 token**（比发多张图便宜），且一张图就能看出"动作怎么变"
- **非动图 / 取帧失败 → 返回 `(None, 0)`，完全走回原来的单帧路径**（对静态图零影响）
- 动图时**给提示词追加一段说明**（这一步必须做）：告诉模型这是连续帧网格、
  要描述动作变化 —— 否则它会当成一张普通拼图、只描述画面，网格就白拼了

**A/B 实测**（自造一个"红球从左向右移动"的 4 帧 GIF）：

| | 模型回答 |
|---|---|
| **A：只给第一帧**（改造前） | 「纯白背景中央有一个黑色数字"1"，左下角有一个红色圆点。」← 只有静态一帧 |
| **B：给多帧网格**（改造后） | 「**红球在白色方块内从左下角平滑移动至右下角，共四帧。**」← 准确说出运动 |

**参数**（都在 `_compose_animated_frames` 签名里，便于调）：
`max_frames=6`、`cols=3`、`cell=320`、`gap=6` → 6 帧时输出 972×646，未超 2048 缩放上限。

**改动**：`services/image_api.py`（新增两个函数 + 预处理接入 + 提示词补充）。

> 💡 **顺带受益**：动图 WebP 走同一套逻辑（`n_frames` 对动图 WebP 同样有效）。

> ⚠️ **缓存注意（容易误判成"没生效"）**：识别结果按**图片内容的 MD5** 缓存。
> 同一个 GIF 如果**在改造前**被识别过，改完代码后**仍会命中那条旧缓存**（首帧版描述）。
> 想让它重新识别，把 `data\Image_description_cache.txt` 置为 `{}` 即可（见 §4.7.9）；
> 换一张没发过的动图也能立刻验证。

备份：`huanmeng\_backup-gif-<时间戳>\`。

#### 4.7.27 【备忘·未执行】换成别的 QQ 号要改哪些地方

> **状态**：用户 2026-10-04 问「能不能使用别的 qq 号」，选择**暂不更换、仅确认可行性**。
> 本节只是把调研结论沉淀下来，**没有修改任何配置或代码**。真要换号时照下表做即可。

**结论：可行，不需要改代码**，只是改配置 + 复制文件 + 重新登录一次。
账号被硬编码在 **3 个文件** + **3 个按 QQ 号命名的配置文件**里：

| # | 位置 | 改什么 | 漏了的后果 |
|---|---|---|---|
| 1 | `NapCat\loadNapCat.template.js:23` | `const ACCOUNT = '<BOT_QQ>'` | 免扫码失效，每次都要扫码 |
| 2 | `NapCat\start-napcat.bat:20-21` | `NAPCAT_QUICK_ACCOUNT` + 密码 MD5 | 密码回退失效（用 `tools\set_qq_password.ps1` 重配） |
| 3 | `huanmeng\config\bot_config.toml:7` | `bot的qq号 = <新号>` | 机器人认不出自己的消息、@ 判断错乱 |
| 4 | **`NapCat\config\onebot11_<新号>.json`** | **必须存在**，从旧号那份**照抄改名** | ⚠️ **幻梦连不上 8099** —— 最易漏的一条 |
| 5 | `NapCat\config\napcat_<新号>.json` | 照抄旧的 | 日志级别等配置丢失 |
| 6 | `NapCat\config\napcat_protocol_<新号>.json` | 照抄旧的 | 协议配置丢失 |
| 7 | `D:\QQBot\QQProfile` | 建议改名备份 + 新建空目录 | 残留旧号登录态，可能报"账号已登录" |
| 8 | 登录 | 新号扫码或密码登录一次 | — |
| 9 | `config\roles.toml` 的 admin | **不要动** | 那是**主人号**，不是机器人号 |
| 10 | 群 / 私聊白名单 | 新号进的群要重新加 | 新号在群里"只理你一个人"（见 §4.7.21） |

**第 4 条是重点**：`onebot11_<BOT_QQ>.json` 里存着 **WS 服务端 8099** 那段配置
（`websocketServers[0]`，name=`HuanMengWsServer`）。新号首次登录时 NapCat 会按**自己的
默认值**生成 `onebot11_<新号>.json`，**很可能不含这个 WS 服务** —— 结果就是
"NapCat 起得来、幻梦死活连不上"。所以**要预先从旧号那份复制改名**，别赌它自动生成对。

**好消息**：新号的账号数据在 `C:\Users\<用户>\Documents\Tencent Files\<新号>\nt_qq`，
与旧号**天然隔离**，`--user-data-dir` 那套隔离机制**不用改**（见 §4.7.2）。

**想两个号同时跑**是另一回事，工作量大得多：需要第二套 NapCat 实例（第二个 profile）、
**第二个 WS 端口**、第二份幻梦配置与进程，`launcher.ps1` 也要改。本节不覆盖。

#### 4.7.28 【备忘】管理指令会重写配置文件并**丢掉所有注释**

**发现经过**：2026-10-04 复盘时发现 `config/adapter_config.toml` 的格式变了 ——

```
group_list = [ <GROUP_1>, <GROUP_2>, <GROUP_3>,]      ← 多了空格和尾逗号
```

而我当初写在那里的解释性注释（"不在名单里的群，除群主外一律不响应…"）**全都不见了**。

**原因**：管理员指令（`whitelist_add` / `group_set` / `config_set`）内部是
`toml.load()` → 改字段 → `toml.dumps()` → **整文件覆盖写回**，
而 `toml.dumps()` **不保留注释、也无法保留原格式**。

**这意味着**：每次在 QQ 里发 `/~owner gadd ...` 或 `/~owner gset <群> reply <n>`，
被改的那个配置文件里的**注释都会被清空**。同类受影响的还有 `bot_config.toml` 等。

**影响评估**：**功能不受影响**。实测改写后的文件 `toml.load` 正常，
`group_list` / `private_whitelist` / `group_settings` 全部读得到（尾逗号在 TOML 1.0 里合法）。
**但教训是**：别把重要说明只写在配置文件的注释里 ——
**要沉淀的知识写进本日志**，这里才是不会被覆盖的地方。

**顺带确认这些指令已被实际使用**（也说明 §4.7.22 的解析容错修复生效了）：

```
group_list        = [<GROUP_1>, <GROUP_2>, <GROUP_3>]
private_whitelist = [<OWNER_QQ>, <FRIEND_QQ_1>, <FRIEND_QQ_2>]        ← 新增 <FRIEND_QQ_2>
group_settings    = {'<GROUP_3>': {'reply_threshold': 8}, '<GROUP_1>': {'reply_threshold': 4}}
```

> 注意 `<GROUP_1>` 被设成阈值 **4**（更爱插话）、`<GROUP_3>` 是 **8**（较沉默）—— 都是用户自己调的。

#### 4.7.29 补加群 `<GROUP_4>`，并发现一个「设了参数却不生效」的坑

**用户要求**：把 `<GROUP_4>` 加入白名单。

**执行**：调 `modules/admin.py::whitelist_add("group", <GROUP_4>)`
—— 与 QQ 指令 `/~owner gadd` **完全同一条代码路径**（读 TOML → append → 写回 → reload），
不用手改文件，避免格式与指令产物不一致。备份：
`huanmeng\_backup-grouplist2-<时间戳>\`。

结果：`group_list = [<GROUP_1>, <GROUP_2>, <GROUP_3>, <GROUP_4>]`，重启后已确认生效。

> ⚠️ **发现一个容易踩的坑**：配置文件里**早就存在**
> ```toml
> [group_settings.<GROUP_4>]
> at_only = true
> reply_threshold = 4
> ```
> 但 `group_list` 里**没有这个群** —— 说明用户之前调过 `gset`，而那些设置**一直是睡着的**：
> `/~owner gset` 只写 `[group_settings.<群>]`，**不会顺手把群加进白名单**（它俩是两件事）。
> 非白名单群里，非 admin 的消息在 `dispatcher.py:339` 就被 `return` 掉了，
> 根本走不到读 `group_settings` 的那一步（见 §4.7.21）。
>
> **教训**：调群参数前先确认**这个群已经在 `group_list` 里**，否则参数白设。
> 一条命令搞定的写法是 `/~owner wl add group <群号> atonly`（加白名单 + 同时开 @仅模式）。

**该群当前的群设置**（重启后实测读到）：

```
{'reply_threshold': 4, 'at_only': True, 'welcome_msg': '', 'cmd_whitelist': None, 'nicknames': {}}
```

→ **`at_only = True` 意味着「只有被 @ 时才回话」**（`pipeline.py:539`：
`elif at_only: should_reply = is_mentioned`），不会主动插话。
如果期望它在群里自由接话，需要关掉：

| 目的 | 指令 |
|---|---|
| 加群进白名单 | `/~owner wl add group <群号>` |
| 加白名单 + 同时开 @仅 | `/~owner wl add group <群号> atonly` |
| **关掉 @仅（让它自由接话）** | `/~owner wl gset <群号> default` |
| 开 @仅 | `/~owner wl gset <群号> atonly` |
| 调该群回复阈值 | `/~owner gset <群号> reply <0-10>` |
| 看全部白名单 | `/~owner wl show` |

> 归口提醒：`wl gset` 的 `default` 是把 **`at_only` 置 false**（见 `commands.py:3378-3379`），
> 而不是"重置整个群设置"—— 名字有点误导，但**不会**动你的 `reply_threshold`。

#### 4.7.30 群聊共享记忆：新增「全局共享笔记本」层

**用户要求**：bot 能在群聊中共享记忆。

**现状诊断（为什么换个群就像重新认识）**：**所有**记忆都是按会话隔离的 ——

| 存储 | 隔离粒度 |
|---|---|
| `data/memory_<chat_id>.md` 长期摘要 | 每群/每人一份 |
| `data/notes/<chat_id>.md` 笔记本 | 每群一份（注入标题原文就写着"**只在当前群生效，其它群看不到**"） |
| `data/stm/stm_<chat_id>.json` 短期记忆 | 每群一份 |
| `data/user_profiles.json` 用户档案 | **连档案都是按群分的**（键是 `g<群号>:<QQ>`，同一个主人在两个群是两份） |
| 好感度 | 同理（`g<群号>:<QQ>` / `p<QQ>`） |

**铁证**：用户的**私聊**笔记里躺着属于**别的群**的事实 ——

```
- [10-04] 群:<GROUP_3> 主人拉 bot 进的新群，暂不在白名单…
- [10-12] QQ:<MOM_QQ> 昵称尹红，自称张嘉铭妈妈，是主人…的妈妈
```

它们记在 `notes/<OWNER_QQ>.md`（私聊那份），所以**只有私聊时用得上** —— 换个群就失忆。

**设计取舍（关键）**：**没有**把各群记忆互相开放 —— 那会让 A 群的私事漏进 B 群，
是隐私事故。改为新增一层**显式写入**的全局共享笔记本：

- 用保留 chat_id **`_shared`**（真实 chat_id 都是纯数字，绝不冲突）→ `data/notes/_shared.md`
- 注入到**每一个**群聊与私聊（`load_notes` 现在拼两段：先全局、后本群）
- **必须显式加 `global` 前缀**才写进全局层，**默认仍写本群**（默认行为不变）
- 沿用 `bot_notes` 原有的隐私过滤（手机号/身份证/银行卡/详细住址命中即拒，`_PRIVACY_PATTERNS`）
- 全局层上限更克制：**40 条**（单群是 100 条）、每次注入 **20 条** —— 因为它进的是**所有**会话

**序号防混淆**：全局段注入编号是 `G1/G2…`，本群段是 `1/2…`，**两套独立**。
LLM 改全局要写 `"global fix G3 <新内容>"`；`cmd_note` 对 `G3` / `g3` / `3` 三种写法都容错。

**用法**：

| 指令 | 作用 |
|---|---|
| `/~note` | 看本群 / 私聊笔记（原行为） |
| `/~note <内容>` | 记到本群（原行为） |
| **`/~note global <内容>`** | **记到全局层（所有群/私聊可见）** |
| `/~note global` | 查看全局层 |
| `/~note global fix G3 <新内容>` | 改全局第 G3 条 |
| `/~note global del G2` | 删全局第 G2 条 |
| `/~note global clear` | 清空全局层（仅管理员） |

`global` 也可写 `全局` / `共享` / `shared` / `g`。

LLM 侧经 `calls` 调 note，判定标准已写进技能 —— 一句话：
**「这条信息换到别的群还成立吗？」** 成立 → args 加 `global ` 前缀；只在本群成立 → 不加。

**改动文件**：`core/bot_notes.py`（共享层常量 / `add_note` 分档上限 / `load_notes` 拼两段 /
`cmd_note` 解析 global 前缀）、`data/skills/20_command_tools.md`（5b 增判定规则）、
`data/skills/40_reminders.md`（两处提醒各加一句）、`data/self_knowledge.md`（记忆分层描述）。

**实测（8 项全过）**：

- 在**自己没有该条**的群 `<GROUP_4>` 里 `load_notes` → **同时**看到全局段 `G1. 主人喜欢美式`
  和它**自己的** 2 条本群笔记 → **隔离未被破坏，全局层生效**
- `global fix G1` / `global fix 2`（裸数字）/ `global del G2` / 中文别名 `全局` 全部正确
- 重启后启动日志 `提示词已加载: 26 个章节`，真实注入链路含【全局共享】+ `G1` 编号 + 【本群专属】

> ⚠️ 技能文件改动**必须重启**才生效（§4.7.17：`/~reload` **不重载技能**）。

> 📌 **全局层目前是空的** —— 测试数据已清理，等功能真正被用起来。
> 用户的私聊笔记里有一批**天然属于全局层**的事实（主人学嵌入式、大肥鱼的形象设定、
> 尹红是主人的妈妈、语音识别项目…），可考虑迁移，但**迁移前应逐条与用户确认**（涉及隐私判断）。

#### 4.7.31 把私聊笔记里跨群通用的事实迁入全局层（用户选定 4 条）

**用户决定**：迁移 ①~④，**⑤（尹红是主人的妈妈）不迁**。

**迁移内容**（`notes/<OWNER_QQ>.md` → `notes/_shared.md`，**保留原始日期**）：

| 原日期 | 内容 |
|---|---|
| 10-01 | 主人经常热重载框架，reload 期间发来的消息不会回复、重启后也没有相关记忆 |
| 10-01 | 大肥鱼的官方形象：蓝发女仆装Q版鲸鱼娘，配「鲸圆券」「100000000 token」梗图 |
| 10-01 | 主人打算正式从 STM32 起步学嵌入式（连 PCB 一起搞），ESP32 只是给 harness 试手 |
| 10-12 | 给 bot 接语音识别：ESP32 + INMP441 采音，ASR 接 SenseVoice 和千问，只剩调试 |

**做法上的两个刻意选择**：

1. **没用 `add_note()`** —— 它会给条目打上**今天**的日期标签，抹掉 provenance。
   这里直接构造 `- [原日期] 内容` 写入，**保留原始日期**。迁移前仍用
   `_privacy_kind()` 过了一遍（4 条全部无隐私命中、无超长），与 `add_note` 的过滤等价。
2. **是"移动"不是"复制"** —— 写入全局层后把这 4 条从私聊笔记里**删除**。
   否则每次私聊注入会同时出现全局版和本群版**两份重复内容**（浪费 token，还可能让 LLM 困惑）。
   私聊笔记保留 2 条：`群:<GROUP_3>` 的行政条目、以及**⑤尹红**。

**验证（跨群可见性 —— 这才是真正的收益）**：

| 会话 | 全局事实命中 | 含【全局共享】 | 含"尹红" |
|---|---|---|---|
| 群 `<GROUP_1>`（原本**没有**这些笔记） | **4/4** | ✅ | ❌ **正确：没进全局层** |
| 群 `<GROUP_4>` | 4/4 | ✅ | ✅（**它自己**的笔记里本来就有，与本迁移无关） |
| 私聊 `<OWNER_QQ>` | 4/4 | ✅ | ✅（⑤仍留在私聊笔记里，未迁移） |

→ 关键结论：**`<GROUP_1>` 这种从来没记过这些的群，现在也全都知道了；而 ⑤ 确实没被带进全局层。**

> ✅ **无需重启**：`_load_lines()` 每次都从磁盘读文件（无缓存），改完**立即生效**。

备份：`huanmeng\_backup-notes-migrate-<时间戳>\`（迁移前的 6 份笔记原件）。

#### 4.7.32 让机器人能读本机文件（`/~file`）—— 三道闸的只读访问

**用户要求**：「将其脱离沙箱，使其对电脑文件只读能力」。经确认：**幻梦**读文件，范围**只给指定几个目录**。

**先澄清前提（重要）**：幻梦**根本不在沙箱里** —— 进程链是 `python.exe main.py` ← `cmd.exe`，
以用户身份正常运行，**拥有全部文件权限**。它读不了文件**不是被沙箱挡住，而是没有这个功能**
（`read` 指令读的是**网页正文**，见 `help_card.py`）。所以这不是"脱离沙箱"，而是**新增一项受控能力**。

**安全设计：三道闸，缺一不可**

| 闸 | 规则 | 位置 |
|---|---|---|
| ① 身份 | **只有主人（`admin_qq`）** | `file_read.cmd_file` |
| ② 路径 | 只在 `data/read_allow.txt` 列出的目录（含子目录）内 | `file_read.is_allowed` |
| ③ 内容 | 只读不写；敏感文件名硬拒；文件 ≤256KB；返回 ≤4000 字 | `file_read` 各函数 |

**① 为什么不用 `cfg.is_admin()`**：它把「**分群 OP**」也算管理员
（`config.py:238`：`user_id in self.group_owners[group_id]`）—— 那等于把文件读取权
发给你指派过的**所有群管理**。文件访问比"能不能用管理指令"敏感得多，故**收紧到只有主人本人**。

**② 目录穿越的防御**：先 `Path.resolve()` 再比对白名单 —— 所以
`D:\QQBot\..\..\Windows\win.ini` 会被 resolve 成 `D:\Windows\win.ini` 后**正确拒绝**（实测）。

**③ 敏感文件名硬编码拒绝**（**不受白名单影响**）：`.env` / `credentials*` /
`*.key|.pem|.pfx|.p12` / `id_rsa` / 浏览器 cookie 目录等；文件名含
`password|secret|token|apikey|_key` 也拒。

**白名单**（`data/read_allow.txt`，一行一个目录，`#` 注释，**改完立即生效、不用重启**）：

```
C:\Users\Lenovo\Desktop      C:\Users\Lenovo\Documents
C:\Users\Lenovo\Downloads    C:\Users\Lenovo\Pictures
D:\QQBot                     D:\esp
```

**用法**（仅主人）：

```
/~file <路径>           读文件 / 列目录
/~file <路径> 3000      指定最多返回多少字（上限 4000）
/~file allow            查看当前白名单
```

LLM 也看得到这个指令（`help_card` + 指令清单均已注册），所以可以直接说"看看 D:\QQBot\SESSION-LOG.md"。
但**执行时仍按消息发送者判断身份** —— JSON CALL 传的是 `caller_id`（真实发送者），
**不是**"群里有没有管理员"，所以群友要求读文件会被拒绝。

**实测（9 + 3 个用例全过）**：

| 用例 | 结果 |
|---|---|
| 主人读白名单内文本 | ✅ 返回内容（带行数/字节/编码） |
| 列目录 | ✅ 列出条目 + 大小 |
| **非主人请求** | 🚫 拒绝 |
| **`C:\Windows\win.ini`（范围外）** | 🚫 拒绝 |
| **`D:\QQBot\..\..\Windows\win.ini`（穿越）** | 🚫 拒绝（resolve 后逃不出去） |
| **`.env`（敏感）** | 🚫 拒绝（硬规则） |
| 真图片 | ✅ 返回 `[CQ:image,...]`，会作为图片发出 |
| 1.9 GB 压缩包 | 🚫 拒绝（超 256KB） |
| `NapCatWinBootMain.exe` | 🚫 拒绝（二进制不当文本读） |

> ⚠️ **风险提示（务必记住）**：读到的内容**会发到聊天里**，群里其他人也看得到。
> 所以**不要把含密码/密钥/私人文件的目录加进白名单**。
> **想立刻取消这个能力**：把 `data/read_allow.txt` 清空（只留注释）即可，所有读取马上失效。

改动文件：**新增** `modules/file_read.py`、`data/read_allow.txt`；
**修改** `modules/commands.py`（注册 `file`/`文件`/`看文件` + import）、
`modules/help_card.py`（描述 + 归入"创作"分类）。

> ⚠️ **勘误 + 已移除（重要）**：本节是**理解偏差**的产物。用户随后的澄清是
> 「**只是让 bot 能看一下屏幕上的内容而已**」（见下节 §4.7.33）。
> 经用户确认，该功能**已整体移除** ——
> `modules/file_read.py` 与 `data/read_allow.txt` 已移入
> `huanmeng\_backup-fileread-removed-<时间戳>\`，
> `commands.py` 的 import 与 `COMMAND_MAP` 注册、`help_card.py` 的描述与分类条目
> **全部摘除**；重启后实测 `/~file`、`/~文件`、`/~看文件` 均**不存在**，
> LLM 指令清单里也已消失。
> **本节保留仅作记录**（安全闸的设计与实测结论仍有参考价值），**不代表当前有该功能**。

#### 4.7.33 让机器人「看屏幕」—— 本机截屏 + 视觉理解（`/~screen`）

**用户澄清**：§4.7.32 理解偏了。用户原意是「**只是让 bot 能看一下屏幕上的内容而已**」。
特此更正，并记录真正的实现。

**先查现有能力，发现两个问题**：

1. **`/~sys shot` 依赖一个没在跑的 PC 客户端** —— 它调
   `services/pc_status.py::request_screenshot()`，而后者一看 `_client_writer is None`
   就直接返回 `None` → `/~sys shot` 只能回"截屏失败（PC 客户端未连接或超时）"。
   那套 TCP 客户端（`scripts/pc_status_reporter.py`，端口 58890）是为
   「**机器人跑在服务器、主人电脑是另一台**」的场景设计的。
2. **更要紧：`/~sys shot` 截完屏只是把图转发给用户，机器人自己没"看"**
   —— 全程**没有任何视觉理解**。

而**幻梦就跑在这台电脑上**，所以根本不需要那个客户端。

**实现**：

① `services/image_api.py::recognize_image()` 新增三个参数
`image_bytes` / `prompt_override` / `use_cache`：

   - `image_bytes`：**本地图片字节**，传了就跳过 HTTP 下载
     （httpx 不支持 `file://`，这是喂本地图的唯一干净办法）
   - `prompt_override`：截图要用不同的问法，不能复用"表情包"那套提示词
   - `use_cache=False`：截图**每张都不同** —— 写 MD5 缓存既永不命中、又会撑大
     `image_repo.jsonl`，所以截图**既不读也不写**缓存

② **新增 `modules/screen.py`**：
   - `grab_screen()`：Pillow `ImageGrab.grab(all_screens=True)`（含多显示器）
   - 缩到最长边 1600、JPEG q85 再送模型（兼顾看清文字与 token 成本）
   - 同时落盘一份到 `data/img_temp/screen_*.jpg`（便于发给用户 / 事后排查）

③ **新增 `/~screen` 指令**（别名 `screen` / `屏幕` / `看屏幕`）：

```
/~screen            截屏并描述屏幕上有什么
/~screen <问题>     带着问题看屏幕（例：/~screen 现在在玩什么游戏）
/~screen send       只发截图，不做理解
```

④ **`/~sys shot` 加了本机回退**：PC 客户端没连上时直接用 `grab_screen()`，
不再因为那个客户端没开就让整条截屏链路失效。

**安全**：**仅主人**（判断的是**消息发送者**）。理由同 §4.7.32 ——
屏幕上可能是任何私密内容，而描述**会发到聊天里**，群里其他人也看得到。

**实测（真实截屏，非模拟）**：

```
截屏完成: 1600x1000 → 148824 bytes
耗时: 5.1s
描述: 屏幕显示DeepSeek Harness程序窗口，当前为对话页面，标题"查看D盘qqbot文件夹并交接工作"。
      左侧为会话历史列表，右侧对话区显示AI分析截屏功能问题，指出 /~sys shot 依赖未运行的
      PC客户端，建议直接本地截屏并给视觉模型喂本地图片。底部输入框旁有"完全权限"选项，
      右下角有二次元人物挂件。
```

→ **准确读出了窗口、标题、左右栏结构、对话区的技术内容、甚至右下角挂件**，
证明"看屏幕"真的通了（视觉模型 `deepseek/deepseek-v4.1-flash`，走中转站）。

改动文件：`services/image_api.py`（三参数）、**新增** `modules/screen.py`、
`modules/commands.py`（注册 + `/~sys shot` 回退）、`modules/help_card.py`（描述 + 分类）。

> 📌 **尚未解决**：`/~sys` 的**状态卡片**部分（当前窗口标题、在听什么歌）**仍依赖那个
> PC 客户端** —— 那部分要 `pywin32` 读前台窗口（`win32gui.GetForegroundWindow`），
> **本次没做**。若也要脱离客户端，可作为下一步。
> → **已在下节 §4.7.34 完成**。

#### 4.7.34 让妈妈能问「他在干什么」+ `/~sys` 脱离 PC 客户端（**并补上一个隐私漏洞**）

**用户要求**：① 妈妈（QQ `<MOM_QQ>`）在群里问「我在干什么」时，机器人**直接看屏幕并回答她**；
② 「没运行的 PC 客户端也改了吧」。

═══ 先做②，因为它顺带暴露了一个安全洞 ═══

**`/~sys` 不再依赖 PC 客户端**

`services/pc_status.py::get_pc_status()` 原来是「客户端没上报就返回 `None`」，
于是 `/~sys` 永远是"暂无 PC 状态数据"。那套 TCP 客户端
（`scripts/pc_status_reporter.py`，端口 58890）是给
「**机器人跑服务器、主人电脑是另一台**」设计的 —— 而本部署里幻梦**就在这台电脑上**。

**做法**：新增 `services/pc_local.py`，**直接复用 reporter 里的采集函数**
（该脚本有 `if __name__ == "__main__": run()` 守卫，导入无副作用），
按它 `run()` 里的组装逻辑产出**结构完全一致**的 dict；
`get_pc_status()` 在客户端无数据时回落调用它。**渲染层一行未改。**

- 新装 `pywin32`（前台窗口必需）、`websocket-client`（音乐，来自本机
  `ws://localhost:9863` 的歌词服务，**与 PC 客户端无关**）
- 实测：`window` = "查看D盘qqbot文件夹并交接工作 — DeepSeek Harness"、
  句柄 1077、内存 142.7 MB、CPU 2.9%、内存 48.6%、3 块盘、电池 97%
- `/~sys card` 卡片渲染成功（86 KB，占位符全替换、数据真实）
- 环境说明：`wmi` 未装 → 无电压（要 LibreHardwareMonitor，纯装饰，跳过）；GPU 需 `pynvml`

**⚠️ 随之发现的隐私漏洞（本次一并修复）**

`cmd_sys` **原本没有任何权限校验** —— 任何群友都能：

- `/~sys` → 看到主人的**前台窗口标题**、CPU/内存、电池
- `/~sys shot` → **把主人屏幕截图直接发到群里**

**而且我同一天刚给 `/~sys shot` 加了「客户端没连上就本机截屏」的回退**，
等于把这个洞从「用不了」变成「能用」—— **属自己引入的放大效应**，必须立刻堵。

**修复**：给 `cmd_sys` 补上与 `/~screen` **完全相同**的身份闸
（主人本人 + `data/screen_allow.txt`），保证"能看屏幕"只有**一个入口、一套判定**，不再有旁路。
实测：群友 `/~sys` 与 `/~sys shot` 均被拒；妈妈与主人正常。

═══ 再做①：看屏幕授权名单 ═══

**新增 `data/screen_allow.txt`**（一行一个 QQ，可跟说明，`#` 注释，**改完立即生效**）：

```
<MOM_QQ>  主人的妈妈
```

`modules/screen.py` 的闸门从「仅主人」改为「**主人本人 或 在名单里**」，
判断的始终是**消息发送者**（不是"群里有没有主人"）。

**技能规则**（`20_command_tools.md` 新增 9b、`40_reminders.md` 新增一条）：

有人问「**主人在干什么 / 在忙什么 / 在玩什么**」这类**主人当下状态**的问题时，
**必须用 calls 调 `screen` 看一眼再答，不许凭空猜**；并明确：
权限由程序判定、**被拒就正常聊天带过**（不解释权限规则、不反复重试）、
**只回答被问到的那个问题，不要罗列屏幕上的无关内容**（尤其别复述聊天记录/文件内容）。

**实测（真实截屏，非模拟）**：

| 触发者 | 结果 |
|---|---|
| 任意群友（未授权） | 🚫 "看屏幕只有主人和他授权的人能用喵~" |
| **妈妈（已授权）** | ✅ **真截屏并描述**：「主人正在使用 DeepSeek Harness 工具进行开发工作，主要涉及查看 D 盘 qqbot 文件夹、编写本机采集模块、渲染卡片以及测试隐私权限校验。」 |
| 主人本人 | ✅ 放行 |

新增 `/~screen allow` 查看授权名单。

> 📌 **一个刻意的留白**：机器人现在**会在群里响应妈妈**，但它**不知道她是你妈妈** ——
> 因为 §4.7.31 迁移全局笔记时，你选择了**不把「尹红是主人的妈妈」放进全局层**（只留在私聊笔记）。
> 结果在群里它只知道"这个 QQ 有看屏幕授权"，不知道关系。
> 若希望它称呼得当（"妈妈，他在写代码呢"），需要把那条放进全局层或单独注入 —— **待你决定**。

改动文件：**新增** `services/pc_local.py`、`data/screen_allow.txt`；
**修改** `services/pc_status.py`（本机回落）、`modules/screen.py`（授权名单 + `allow` 子命令）、
`modules/commands.py`（`/~sys` 补权限闸 + `/~sys shot` 本机回退）、`modules/help_card.py`（描述）、
`data/skills/20_command_tools.md`、`data/skills/40_reminders.md`。

#### 4.7.35 授权名单「身份标注」—— 只在她说话时生效，**不写全局**

**用户要求**：不要走全局笔记，**只给授权名单加身份标注**。

**实现**：`data/screen_allow.txt` 从"一行一个 QQ"升级为「**QQ + 身份标注**」：

```
<MOM_QQ>  妈妈
```

- `modules/screen.py` 新增 `viewer_labels() -> {QQ: 标注}`、`viewer_label(qq) -> str`；
  `allowed_viewers()` 仍是 QQ 集合，**权限判定逻辑不变**（避免改出权限漏洞）。

**注入位置**：`core/pipeline.py` 的 `extra_info` 组装段，紧跟已有的 `【主人提示】` 之后：

```
【说话人身份】现在跟你说话的 尹红（QQ <MOM_QQ>）是你的妈妈。回答时可以自然称呼，但别刻意强调这层关系。
```

**三个刻意的设计**：

1. **只在本人说话的那一刻注入** —— 不是全局记忆、**不入 `notes/`**，
   所以**不会扩散到别的群**，也不会被机器人在别处提起。这正是用户要的范围。
2. **主人本人不注入**（`int(user_id) != admin_qq` 才注入）—— 主人自己的关系不需要提示。
3. **标注写法必须能读成「是你的___」** —— 所以写 `妈妈` 而不是 `主人的妈妈`
   （否则会变成"是你的主人的妈妈"）。这条已写进 `screen_allow.txt` 的注释，避免后来人写错。

**实测**：

```
viewer_labels()          → {<MOM_QQ>: '妈妈'}
viewer_label(<MOM_QQ>) → '妈妈'
viewer_label(<OWNER_QQ>) → ''      （主人不在名单）
viewer_label(999)        → ''      （路人）

[尹红]  会注入 → 【说话人身份】现在跟你说话的 尹红（QQ <MOM_QQ>）是你的妈妈。…
[路人]  不注入
```

另加了一行 INFO 日志 `注入说话人身份: <名字>(<QQ>) → 你的妈妈`，
方便事后确认它是否真的触发（排查时不用猜）。

> ⚠️ **端到端仍需真人验证**：注入发生在 `process_message` 内联，无法离线单测。
> 让妈妈在群里问一句「他在干什么」，日志里应出现「注入说话人身份」，
> 回复里应自然带上称呼。

改动：`data/screen_allow.txt`（格式升级 + 注释）、`modules/screen.py`（三个函数）、
`core/pipeline.py`（注入 + 日志）。

#### 4.7.36 【事故·10-14 14:14】OneBot 8099 未监听 —— NapCat 崩溃后的「已登录」脏状态

**用户报告**：onebot8099 未监听。

**现场取证**：

- `netstat -ano | findstr :8099` → **只有一条 `SYN_SENT`**（幻梦在不停重试），**没有 LISTENING**
- 幻梦日志每 5 秒刷一次：`ERROR 连接异常: [WinError 1225] 远程计算机拒绝网络连接`
- NapCat 日志（`napcat-20261014-141057.log`）：
  ```
  10-14 14:11:03 [info] [NapCat] [Core] NapCat.Core Version: 4.18.28
  10-14 14:11:03 [info] [WebUi] WebUi User Panel Url: http://127.0.0.1:6099/webui?token=…
  10-14 14:11:04 [info] 正在快速登录  <BOT_QQ>
  10-14 14:11:04 [error] 当前账号(<BOT_QQ>)已登录,无法重复登录      ← 根因
  ```
- **6099 WebUI 是活的** → NapCat 核心起来了、**只是没登录成功**，
  所以 OneBot 的 WS 服务端**从未建立**

**上游原因**（前一天的日志）：

```
10-13 23:22:19 [error] [NapCat] [UtilityProcess] Worker进程退出，退出码: 1073807364
10-13 23:22:19 [warn]  Worker进程意外退出 (1/3)，正在尝试重新拉起...
Process exited.
[start-napcat] NapCatWinBootMain exited with code 0
```

→ **10-13 23:22 一次 worker 崩溃**留下脏登录态：QQ 侧认为该账号"已登录"，
于是下次启动时 NapCat 的快速登录被拒。

**处置**：彻底清干净再重启 ⚠️（`launcher.ps1` **会跳过已在运行的 NapCat**，
所以**必须先杀干净**，否则脏状态原封不动）：

1. **逐个核对命令行** —— 只杀**含 `QQProfile` 的 `QQ.exe`**
   （本次 4 个：主进程 + gpu/network/node 三个子进程）和 `NapCatWinBootMain.exe`；
   **个人 QQ（`AppData\Roaming\QQ`）一个都没碰**（当时也没在运行）
2. 确认 6099 已关闭、无 `QQProfile` 残留
3. `launcher.ps1` 重新拉起

**结果**：

```
10-14 14:14:22 [info] 正在快速登录  <BOT_QQ>        ← 这次没报错
10-14 14:14:23 [info] [OneBot] [WebSocket Server] Server Started
幻梦 14:14:27: 已连接到 NapCat (ws://127.0.0.1:8099/)
```

**验证**：`8099 / 6099 / 58888 / 58889 / 58890 / 58891 / 59400` **全部监听**；
日志里 20 条 ERROR **全是停机期间的重连失败**（14:13:47~14:14:22），
**恢复后零新增**。

> 📌 **排查口诀（下次直接照做）**：
> 1. `netstat -ano | findstr :8099` —— 只有 `SYN_SENT`、没有 `LISTENING` = **服务端没起**
> 2. **同时看 6099** —— 6099 活着说明 NapCat 核心在、问题在**登录**；
>    6099 也死了才是进程整个没了（两种情况的处置不同）
> 3. 翻 `NapCat\napcat-*.log` 找 `已登录,无法重复登录` / `Worker进程退出`
> 4. 解法：按 `QQProfile` 精确杀掉 `QQ.exe` + `NapCatWinBootMain`，再跑 `launcher.ps1`
>
> ⚠️ **别直接 `launcher.ps1` 了事** —— 它跳过已在运行的 NapCat，脏状态不会自愈。

> 💡 **一个容易误判的点**：`Get-CimInstance -Filter "Name='python.exe'"` 会列出
> **两个 `main.py`**，但它们**互为父子**（同一父 PID、同一启动时刻），
> 且 8099 上只有**一条 ESTABLISHED** —— **不是重复实例、不会双回复**。
> 判据看 `ParentProcessId`，**别看数量**。

#### 4.7.37 【记忆污染排查·10-16】全局笔记注入范围过宽（**我自己引入的**）

**用户报告**：出现记忆污染与上下文不对应。

**排查过程与结论**（先摆事实，不猜）：

| 检查项 | 结果 |
|---|---|
| `data/notes/_shared.md` 内容 | ✅ 干净，只有 §4.7.31 迁入的 4 条，机器人**没有**往里乱写 |
| `context_cache.json` 结构 | ✅ **按会话正确隔离**（9 个会话各一份 `current/blocks/summaries`），内容归属也对得上 |
| 跨会话成员串场扫描 | ✅ 未发现"别群成员 QQ"出现在本会话上下文里 |
| **全局笔记注入范围** | ❌ **发现问题**（详见下） |

**❌ 问题一：全局共享层被注入到了「别人的私聊」**

用户原话是「在**群聊**中共享记忆」，但 §4.7.30 的初版实现里
`load_notes()` 只排除了 `SHARED_ID` 本身 —— 于是**所有会话**都会拼上全局段，
**包括 `<FRIEND_QQ_1>`、`<FRIEND_QQ_2>` 这两个「朋友私聊」**。

后果：在**别人的私聊**里，机器人上下文中也带着主人的私人事实
（"主人经常热重载框架"、"主人打算学嵌入式"、"语音识别项目"…）——
**这是把主人的私事外泄给第三方**，是明确的扩散错误，不是设计意图。

**修复**（`core/bot_notes.py` 新增 `_is_share_scope()`）：

> 只在**群聊**（在 `group_list` 里）与**主人自己的私聊**注入全局段；
> **别人的私聊一律不注入**；读不到配置时**按"不注入"处理**（隐私优先）。

实测：

```
<GROUP_1>    群（白名单）     注入=True   含【全局共享】=True
<GROUP_3>   群（白名单）     注入=True   含【全局共享】=True
<GROUP_2>   群（白名单）     注入=True   含【全局共享】=True
<OWNER_QQ>   主人私聊         注入=True   含【全局共享】=True
<FRIEND_QQ_1>   ★别人的私聊      注入=False  含【全局共享】=False   ← 已堵住
<FRIEND_QQ_2>   ★别人的私聊      注入=False  含【全局共享】=False   ← 已堵住
```

同步改了 `data/skills/20_command_tools.md` 里"任何群/私聊都能看到"的措辞。

**⚠️ 问题二（已发现，未改）：同一事实被记到错误的 scope，导致"碎片化记忆"**

- `data/notes/<FRIEND_QQ_1>.md`（**私聊**）里写着：
  `群友「感恩花糕」在群里自我介绍，昵称=感恩花糕，暂未知QQ号`
- `data/notes/<GROUP_3>.md`（**那个群**）里写着：
  `群友:感恩花糕 群<GROUP_3>成员，从下午起持续辱骂大肥鱼…`

同一个人、同一件事，**被拆进两个 scope**。后果就是用户描述的那种
"**换个地方问，它知道的就不一样**"。

**根因**：`/~note` 只能写到**当前会话**；机器人在私聊里学到"关于某个群的事"时，
**没有语法可以把它记到那个群**，只能就近记在当前私聊里 —— 那条笔记就永远
在群里用不上。

**✅ 问题二的修法（已实现，2026-10-16）**：给 note 加「**指定落点**」语法 ——
`g<群号>` / `p<QQ>` / `c<会话号>`：

```
/~note g<GROUP_3> 群友感恩花糕经常在群里辱骂大肥鱼    ← 记到那个群
/~note p<OWNER_QQ> 主人喜欢美式                      ← 记到那个私聊
/~note g<GROUP_1>                                    ← 查看那个群的笔记
/~note g<GROUP_1> fix 2 新内容 / del 1                ← 改/删那个群的条目
```

⚠️ **写「别的」会话需要管理员权限**（`_allowed_to_write_other`）——
否则任何人都能往别的群塞笔记、污染别人的记忆。写**自己**的会话不需要。

**语法冲突已避开**：`g` 单独出现 = 全局（原有别名），`g<数字>` = 指定群 ——
正则 `^([gpc])(\d{5,12})$` 要求后面必须是数字，两者不会相互误判。

实测 6 项全过（含"非管理员写别群被拒""非管理员写自己私聊放行""global 仍可用"）。
技能（`20_command_tools.md` 5b、`40_reminders.md`）已同步教 LLM 何时用指定落点。

**⚠️ 问题三（数据质量，小）**：`data/notes/<GROUP_1>.md` 有一条
`[QQ:Leo] 是早泄zako，主人亲自认证` —— **QQ 位置写的是名字 `Leo` 而不是数字**。
是 LLM 生成笔记时把昵称填进了 QQ 字段。不影响功能，但属格式不合规。

> 📌 **本次没能复现的**：用户说的"上下文不对应"如果指的是
> "**回复内容与消息对不上**"（例如答非所问、提到别的会话的事），
> 我在 `context_cache.json` / `msglog` / 日志里**都没找到实例** ——
> 需要用户给出**具体是哪一次、哪个群、它说了什么**，我再定向查。
> 现有的三处发现（注入过宽 / scope 碎片 / 格式不合规）都能解释"记忆污染"，
> 但未必是用户看到的全部。

### 4.7.37 补：跨会话泄漏通道的**逐一排除**

用户确认症状是「**它在 A 群提了 B 群的事**」。我把 `extra_info` 里
**所有可能的跨会话注入源**逐个查了一遍：

| 通道 | 位置 | 结论 |
|---|---|---|
| `get_top_memories` | `pipeline.py:567` | ✅ 只读 `memory_{chat_id}.md`（`load_memories` 按会话取文件） |
| `search_msglog` | `pipeline.py:646` | ✅ 只读 `msglog_{chat_id}.jsonl`（路径就是按 chat_id 拼的） |
| `memory_link`（**框架自带的跨聊天关联**） | `pipeline.py:636-640` | ✅ `data/memory_links.json` **不存在** → 从未建立任何关联 → 注入为空 |
| `context_cache` | `save_context` | ✅ 按会话隔离（9 个会话各一份，实测内容归属正确） |
| `load_memories` | `memory.py:100` | ✅ 按会话取文件（含私聊 persona 覆盖，仍是确定的一份） |
| **全局共享笔记层** | `bot_notes.load_notes` | ❌ **唯一的跨会话注入源** —— 见 §4.7.30/37 |

→ **结论**：「A 群提了 B 群的事」来源就是**我加的全局笔记层**。
它那 4 条是"主人在别处说过的事"，被注入到**每一个群聊和主人私聊**，
于是机器人会在任意群里提起。

> ⚠️ **这里有一个需求层面的矛盾**：用户先前要求「**在群聊中共享记忆**」（§4.7.30），
> 现在又观察到「**A 群提了 B 群的事**」是困扰 ——
> **这两件事本质上是同一机制的两面**。可选的处理：
> 1. **清空全局层**（`_shared.md` → 只留注释）：彻底不再跨群共享，
>    改为靠新增的 `g<群号>` 指定落点把事实记到"它真正属于的会话"
> 2. **保留但收紧**：只留"主人身份/机器人自身设定"这类**绝不敏感**的条目
> 3. 维持现状：接受"换个群不失忆"带来的跨群提及
>
> ✅ **用户 2026-10-16 的决定：保持现状（选项 3）** —— 全局层**不改**。
> 那 4 条继续注入群聊与主人私聊。
> **后来者请注意**：这是用户**知情后的选择**（我已把矛盾明确摆出），
> 不要当成"遗留 bug"再去改它。真正的修复是**记录侧**的改进
> （`g<群号>` 指定落点，已实现），而不是把全局层删掉。

> 💡 **顺带发现的运维缺口**：**日志不记录机器人的回复正文**，
> 只有 `PIPE 回复判断完成 → should_reply=...` 这样的决策日志。
> 所以"它到底说了什么"事后**查不到**，排查此类问题只能靠 `context_cache` 反推。
> 建议后续加一个"回复留档"（写进 msglog 或单独文件），否则此类投诉无法取证。
> **（未做 —— 待用户决定是否要。）**

改动：`core/bot_notes.py`（新增 `_is_share_scope` + `load_notes` 收紧 + 措辞）、
`data/skills/20_command_tools.md`（措辞）。

#### 4.7.38 【人设卡失效·10-16】成人内容"过于敏感" 与 兜底路径丢人设字段

**用户报告**：bot 对成人内容过于敏感，**轻微玩笑都会使人设卡失效**。

**排查（先排除，再定性）**：

| 检查项 | 结果 |
|---|---|
| 技能/提示词里有没有内容审查规则 | ❌ **一条都没有**（全项目扫 `色情/成人/R18/NSFW/违规/审查` 无命中） |
| 有没有审查插件 | ❌ 插件只有 `bg_tasks`、`dice` |
| `preset.py`（`{{...}}` 临时人设，即"人设卡"） | ✅ 极简，**无任何内容过滤**；但注意 `_presets` 是**内存字典**，重启即丢 |
| **模型层实测**（轻微荤玩笑→略露骨，要求输出 JSON） | ✅ **中转站与官方两边、4 个用例全部正常**，没有人拒绝，**也都守住了 JSON 格式** |

→ **模型不会因为成人内容"拒绝"或"破格式"**。但实测里它的回应是**回避式**的，例如：

> 「呜哇主人好色喵，人家可是**正经**鲸鱼娘才不会讲那种笑话呢喵」
> 「呜哇**不可以**那里不可以啦喵！……主人你太坏了喵！」

**在角色内，但确实是端着/推挡** —— 这就是用户体感上的"过于敏感"。

**而"人设卡失效"是另一条独立链路**，日志里有直接证据：

```
[21:00:38] INFO (llm:generate_multi_reply_with_tools:1800)
           LLM 输出非 JSON 但内容完整，已救回直接使用（110 字原始输出）
[21:00:38] INFO (llm:_parse_reply:2151) JSON回复解析: 1句 fav=+0 calls=0 mood=
                                                                    ↑ mood 为空
（同一份日志里正常回复是 mood=淡定 / mood=开心）
```

追到源码，`_salvage_plain_reply()` 的产出是：

```python
payload = {"replies": sentences, "fav": 0}      # ← 根本没有 mood 字段
```

→ **只要模型因任何原因吐了非 JSON，这条回复就丢人设字段**（mood 空）、好感度也不涨。
`pipeline.py:845` 的旧复盘已经记过同类因果链（思考模式关闭 → 退化散文 → 走兜底），
但**兜底函数自身丢 mood 的问题一直没修**。

> ⚠️ **一个与用户假设不符的事实**：日志里**唯一**那次兜底的现场，用户消息是
> `科大讯飞吗...`（**技术问题**），不是成人内容；而模型那次 `reasoning=353字` ——
> 是**长推理链**让它跑偏丢了 JSON 帧。
> 也就是说"成人内容 → 人设卡失效"这条因果**在日志里没有实例支撑**，
> 但两处修复各自独立成立（回避=提示词问题；兜底=代码问题）。

**修复 ①（提示词：治"端着/回避"）**

- `data/skills/00_core.md` 的 `persona_lock`（最高优先级段）新增一条
  **【尺度：别端着】**：主人的荤玩笑/调情/调戏**都要接**（害羞/嘴硬/反撩/顺梗都行），
  **严禁**用「正经」「不可以」「这样不好」挡回去，也不许说教讲道理 ——
  明确点名这是"最典型的人格突变：读起来就是个客服"；
  真过头时用**角色语气**轻轻带过（"这个人家可不依喵～"）而不是讲道理。
  对平民：可接梗吐槽，但不主动开这类话题。
- `data/skills/40_reminders.md` 同步一条同名提醒（该文件位于**注意力最高处**，
  按仓库自己的复盘，行为塑造类规则放这里最有效）。

**修复 ②（代码：治"人设卡失效"）**

`services/llm.py`：

- 新增 `_infer_mood()` —— 从救回的正文里**粗推**心情词
  （线索表取自 `face_lib` 的情绪词：害羞/生气/委屈/开心/惊讶/疑惑/不满/坏笑，兜底「平静」），
  **不改变回复内容**，只保证 mood 不为空
- `_salvage_plain_reply()` 的 payload 改为
  `{"replies": [...], "fav": _SALVAGE_FAV, "mood": _infer_mood(txt)}`
- 新增常量 `_SALVAGE_FAV = 1`（原来硬编码 `0` → 模型偶尔不吐 JSON 时好感度**永远不涨**）；
  想保守改回 0 即可

**实测**：

```
兜底 mood 推断:  害羞 ✅  生气 ✅  开心 ✅  平静 ✅
完整 payload:   {"replies": ["呜呜主人好坏哦…"], "fav": 1, "mood": "害羞"}
（"惊讶"用例只是文本 38 字 < min_chars=40 被当碎片丢弃 —— 属既有设计，非本次逻辑问题）
```

> 📌 **未做**：`/~note` 之外，**日志仍不记录机器人回复正文**（§4.7.37 已记为缺口），
> 所以"它到底怎么回的"事后依然查不到。若此类投诉再来，仍会缺少现场。

改动：`services/llm.py`（`_infer_mood` / `_SALVAGE_FAV` / payload）、
`data/skills/00_core.md`、`data/skills/40_reminders.md`。

#### 4.7.39 【多次超时·10-20】中转站瞬时故障 + 两个暴露出来的自身缺陷

**用户报告**：多次超时，帮查原因。

**时间线（日志 + 实测交叉印证）**：

| 时段 | 表现 |
|---|---|
| 15:38 之前 | 回复耗时 **2–8 秒**，一切正常 |
| **15:38 ~ 15:51** | 几乎每条都是 `PIPE LLM生成完成 耗时180.0xs → 0句`，**全部失败** |
| 15:55 起（现场实测） | 中转站 **1.8s**、官方 **1.0s** —— 已恢复 |

→ **触发原因是外部 API 一次约 13 分钟的瞬时故障/严重变慢**，机器人端当时无解。

**但暴露了两个机器人自身的缺陷（本次已修）**：

**缺陷 ①：明明有可用的第二条腿，却完全没用上**

`DEEPSEEK_KEY`（官方 `api.deepseek.com`）当时**是通的**（实测 1.0s），
但 `bot_config.toml` 里 4 个模型全部 `provider = RELAY`，**代码里没有任何回落逻辑** ——
中转站一挂，机器人只能干等到放弃。

**缺陷 ②：熔断器存在，却只接在 judge 路径上**

`llm.py:950` 起有模型级熔断（连续 3 次失败 → 冷却 180s，指数退避），
日志里它**确实打开了 6 次**：

```
[15:38:48] 熔断[deepseek-v4.1-flash] 连续3次失败 → 冷却180s(第1次熔断)
[15:43:12] ... 第1次熔断
[15:50:41] ... 冷却360s(第2次熔断)        ← 指数退避
```

但 `is_model_circuit_open()` **全项目只被调用过一次**（`call_judgment_pipeline` 里）。
**回复路径（`call_llm_with_tools`）从不检查熔断** → 熔断期间每条消息仍然
`60s（主）→ 60s（json_mode 补救）→ 60s（再补救）= 180s` 才罢休。

> 💡 **一个排查时的假线索**：日志里模型名显示 `deepseek/deepseek-v4`，
> 而配置里是 `deepseek/deepseek-v4.1-flash` —— 一度以为是配置写错。
> 实际是日志 `model_cfg.name[:20]` **截断**（"deepseek/deepseek-v4" 正好 20 字符）。
> 模型没配错。

**修复（`services/llm.py`）**：

1. **新增 `_fallback_model()`** —— 主通道不是官方时，返回一个官方通道的
   `ModelConfig`（`name=deepseek-flash`，`provider=deepseek`，用 `.env` 里的
   `DEEPSEEK_KEY/DEEPSEEK_URL`）。**已在官方通道上就返回 None**，杜绝自我递归。
2. **回复路径接上熔断** —— `call_llm_with_tools` 开头检查：
   - 熔断打开 **且有**备用通道 → **直接**走备用（不碰主通道）
   - 熔断打开 **且无**备用通道 → **立刻失败**（不再白等 60s）
3. **超时/失败时回落一次** —— 两个 except 分支里，若允许回落则用官方通道重试
   **一次**（新增内部参数 `_allow_fallback`，备用通道自己失败时置 False）。

**实测**：

```
场景 A：主通道指向不可达地址
  → 主通道 5s 超时 → 自动切官方 → 共 7.7s → 回复:'我是你的AI助手…'   ✅
  （原来：180s 后发"未返回有效句子"）

熔断快速路径（连续 3 次失败后）：
  第 4 次调用 0.9s 直接走备用，不再等主通道超时              ✅

递归保护：_fallback_model(备用通道) == None                   ✅
```

**保留的诊断工具**（仓库 `scripts/` 下同类命名已有先例）：
`scripts/_diag_latency.py`（测 thinking/工具对延迟的影响）、
`scripts/_diag_failover.py`（造一个坏主通道验证故障转移）。

> ⚠️ **代价提醒**：走备用通道时用的是**官方 API 按量计费**，价格与中转站不同；
> 且只在"主通道连不上/超时/熔断"时才触发，正常情况不产生额外费用。

改动：`services/llm.py`（`_fallback_model` + `call_llm_with_tools` 三处）。

#### 4.7.40 【配置变更·10-20】把群 <GROUP_5> 的回复欲望降到最低

**用户要求**：把 bot 在群 `<GROUP_5>` 的回复欲望降低。

**做法**：该群原先**没有分群设置**，走全局 `回复兴趣 = 8`。现在写入：

```toml
[group_settings.<GROUP_5>]
reply_threshold = 10
```

**阈值语义（别搞反）**：`兴趣度(0~10) >= 阈值` 才回复 → **阈值越高越沉默**。
所以"降低回复欲望" = **调高阈值**。10 是有效上限（兴趣满分 10），
也就是**只在该群兴趣度打满时才主动插话**，其余一律不打扰。

用 `modules/admin.py::group_set()` 写入（与 `/~owner gset ... reply` 同一条代码路径），
写完重启加载。备份：`huanmeng\_backup-threshold-<时间戳>\`。

**验证**：运行进程读到 `<GROUP_5> 生效阈值 = 10 (全局 8)`；
重启后 8099/6099 均在监听、**0 ERROR**。

> 📌 **不受影响的部分**（阈值只作用于"未被 @"的普通消息）：
> · **@机器人** → 直接回（`pipeline.py` 里 `is_mentioned` 就置 `should_reply=True`，不看阈值）
> · **私聊** → 直接回
> · 指令（`/~xxx`）→ 走指令拦截，不看阈值

**当前全量阈值格局**：

| 会话 | 阈值 | 性格 |
|---|---|---|
| `<GROUP_1>` | 4 | 爱搭话 |
| `<GROUP_4>` | 4 | 爱搭话 |
| `<GROUP_3>` | 8 | 正常 |
| **`<GROUP_5>`** | **10** | **几乎不主动说话** |
| 其它（全局） | 8 | 正常 |

> 💡 想再静音到"只有被 @ 才回"：用 `/~owner wl gset <GROUP_5> atonly`
> （那是**二值开关**，比阈值更彻底）；用 `/~owner wl gset <GROUP_5> default` 恢复。

#### 4.7.41 【新开关·10-20】群 <GROUP_5>「除了被@，不看任何信息」

**用户要求**：让 bot 在该群**除了被 @，不看任何信息**。

**与 `at_only` 的关键区别（别混）**：

| 开关 | 语义 |
|---|---|
| `at_only = true` | 只是**不回复**；消息**仍会读进来**，仍写上下文、仍进长期记忆、仍判定 |
| **`ignore_unmentioned = true`**（本次新增） | **连看都不看**：未 @ 的消息在 dispatcher 里**直接丢弃** |

**丢弃意味着这些都不会发生**：不进 msglog / 不计统计（`record_message`）/
不进 SQLite 全文索引 / 不做图片识别 / 不写上下文（`append_to_context`）/
不入队 / 不花任何判断 API。

**实现**（`core/dispatcher.py`，位置在白名单检查之后、录制消息之前）：

```python
if is_group and not is_command:
    _gs_iu = cfg.group_settings.get(chat_id, {}) or {}
    if _gs_iu.get("ignore_unmentioned"):
        _mentioned = bool(
            re.search(rf'\[CQ:at,qq={bot_qq}[,\]]', _raw)      # CQ 形态
            or re.search(rf'@{bot_qq}(?!\d)', _raw)             # 文本形态
            or re.search(rf'@{bot_qq}(?!\d)', msg_content or "")
        )
        if not _mentioned:
            return          # 丢弃，什么都不记
```

**两个刻意的设计**：

1. **指令（`/~xxx`）例外放行** —— 那是明确的操作请求，不是"群里的信息"；
   否则该群的 `/~note`、`/~screen`、`/~owner` 会一起失效。
2. **管理员不豁免** —— 用户原话"除了被@，不看任何信息"，连主人自己没 @ 说的话也丢。

> ⚠️ **踩到一个真坑（后来者注意）**：`core/config.py:425` 重建 `group_settings` 时
> **按白名单键逐个取值**。新加的 `ignore_unmentioned` 若不在那里登记，
> **TOML 里写了也读不到**（`v.get` 取不到 → 字典里没这个键）。
> 已在 `config.py` 补登记，并留了注释。

**配置**（`config/adapter_config.toml`）：

```toml
[group_settings.<GROUP_5>]
reply_threshold = 10
ignore_unmentioned = true
```

**验证**：

- 6 种 @ 形态判定全部正确（含 `@<BOT_QQ>` 这类**相似号不误判** —— `(?!\d)` 保护）
- 重启后**日志立刻出现丢弃记录**：
  `[16:15:32] 只看@模式：丢弃未@消息 chat=<GROUP_5> from=C26114514-汉语言科学与技术-黄子鹤`
- 该群 `msglog_<GROUP_5>.jsonl` **停止增长**（122 条，最后写入 16:14:36，早于重启 16:15）
- 运行进程读到 `只看@ = True | 阈值 = 10`；8099/6099 在监听、**0 ERROR**

> ✅ **戳一戳也已静音（2026-10-20 同日追加）**：用户要求"在该群里连戳一戳也不响应"。
> 戳一戳走的是 `EventDispatcher._handle_notice` 的 `notice_type=notify / sub_type=poke`
> 分支（**独立于消息管道**），所以必须**单独加闸** ——
> 否则前面那条"丢弃未@消息"根本管不到它。
>
> 实现（`core/dispatcher.py:199` 附近，在白名单检查之后、`handle_poke_event` 之前）：
> ```python
> if is_group:
>     _gs_poke = cfg.group_settings.get(group_id, {}) or {}
>     if _gs_poke.get("ignore_unmentioned"):
>         logger.debug("戳一戳忽略(该群设为只看@): group=%d from=%s", group_id, sender_name)
>         return
> ```
> 管理员同样不豁免，与消息管道口径一致。
>
> **验证方式（合成事件 + 打桩，不产生真实副作用）**：
> `scripts/_verify_poke_gate.py` 直接构造 poke 事件调 `_handle_notice`，
> 并把 `handle_poke_event` 换成记录桩：
>
> ```
> ✅ 只看@的群 <GROUP_5>  → 预期拦住 → 实际拦住（桩一次都没被调用）
> ✅ 普通群   <GROUP_1>  → 预期放行 → 实际放行（未误伤）
> ```
>
> 运行中的进程确认已加载：`dispatcher.py` 改于 16:18:01，幻梦启动于 16:18:19；0 ERROR。
> 重启后日志里 `只看@模式：丢弃未@消息` 已出现 **2 次**（真实事件）。

> 💡 **恢复**：把 `ignore_unmentioned` 改回 `false`（或删掉该行）即可 ——
> **消息和戳一戳会一起恢复**（两者共用同一个开关，不存在只恢复一半的情况）。
> 备份：`huanmeng\_backup-blindmode-<时间戳>\`。

#### 4.7.42 【发布准备·10-26】把项目整理成可公开的 GitHub 留档

**用户要求**：把该 qqbot 项目提交到 GitHub 留档。

**结论：可以发布，但必须先做三件事** —— 脱敏、排除运行数据、补来源声明。

**① 许可与出处（决定"能不能发"）**

`huanmeng/LICENSE` 是 **MIT License，Copyright (c) 2026 Trusler**，
上游仓库为 `https://github.com/Trusler258/huanmeng-qqbot`。

→ **MIT 允许发布与修改**，但**必须保留 `LICENSE` 与版权声明**，
并且应明确说明"这是部署留档/修改版，非原创"。已在输出 README 末尾追加
「## 来源与许可」段落说明这一点。

**② 直接推送原目录会出的事故（实测确认存在）**

| 风险项 | 实情 |
|---|---|
| 明文密钥 | 仓库根目录有 **`api key.txt`**（35 字符 `sk-391...`，就是官方 DeepSeek key） |
| 凭据文件 | `huanmeng/config/.env`（22 行 key）、`NapCat/config/`（WebUI token、passkey） |
| 账号数据 | `QQProfile`、`QQProfile.bak-*`、`qrcode.jpg/png` |
| 个人隐私 | `config/roles.toml` 含 **1281 个不同号码**（昵称映射）；`data/` 里全是 `memory_*.md`、`msglog/`、`notes/`、`fav.json`、`huanmeng.db` |
| 文档里也有 | `README.md`/`SESSION-LOG.md` 含 **NapCat WebUI token（12 位十六进制）**、本人/机器人/妈妈/好友 QQ、15 个群号 |
| 体积 | 原目录约 **720 MB**（huanmeng 535MB 含 .venv 与 data、NapCat 146MB、_downloads 39MB）→ GitHub 会直接撑爆 |

**③ 做法：写了一个白名单式的发布准备脚本**

`tools/prepare_github_publish.ps1`（**已加 UTF-8 BOM**）——
只复制明确允许的内容到 `_publish_github\`，逐个文本文件脱敏，并在结束前**自检**：

- **白名单复制**：顶层文档/脚本、`tools/`、`huanmeng/` 源码（排除 `.venv`/`data`/`__pycache__`/`_backup-*`/`.last-*`/`*.log`/`*.db`）、
  `data/` 里**只取提示词与模板**（`skills/`、`templates/`、`self_knowledge.md`、`assistant_kb.md`、`update_log.md`、两个 `.mermaid`、`faces/README.md`、`faces/_descriptions.json`）、
  NapCat 的 4 个部署脚本
- **配置只留 `example.*` 模板**，真实的 `adapter_config.toml` / `bot_config.toml` / `roles.toml` / `.env` 一律排除
- **脱敏**：14 个字面量（token、3 个 QQ、7 个群号）→ 占位符；正则兜底处理
  `sk-` 开头的 key、`NAPCAT_QUICK_ACCOUNT` / `NAPCAT_QUICK_PASSWORD_MD5`、`.env` 里的各类 KEY
- **自检**：扫输出目录，发现任何残留就报红并列出，**不给推送**

**验收结果**：

```
文件总数: 389 | 体积: 5.6 MB | 脱敏过的文件: 21
占位符写入: <BOT_QQ> 35 次 / <OWNER_QQ> 20 / <MOM_QQ> 11 /
            <FRIEND_QQ_1> 9 / <GROUP_1> 27 / <NAPCAT_WEBUI_TOKEN> 10 / <QQ_PASSWORD_MD5> 4
原始号码残留: <BOT_QQ> / <OWNER_QQ> / <MOM_QQ> / <GROUP_1> / <GROUP_5>  → 均 0 个文件
敏感文件: api key.txt / .env / roles.toml / QQProfile / qrcode.jpg → 全部未进入输出
MIT LICENSE 与来源声明 → 均在
```

**④ 过程中踩到 / 修掉的两个坑**

1. **`.ps1` 必须带 UTF-8 BOM** —— 无 BOM 时 Windows PowerShell 5.1 按 GBK 解析，
   中文注释直接导致语法错误（`Unexpected token ')'`）。edit 工具会去掉 BOM，改完要补回。
2. **自检的 `-match` 假阳性** —— PowerShell 的 `-match` **默认不区分大小写**，
   把百度搜索结果 URL 里的随机串 `...PsK-IA-b5HmY0A71TAPW5H00...` 误判成 `sk-` 开头的 key。
   已改用 **`-cmatch`（区分大小写）+ 更严格模式** `(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}`。
   **判断依据**：`[regex]::IsMatch` 与 `-match` 结果不一致时，差异几乎总是大小写。

> ⚠️ **强烈建议顺手删掉 `D:\QQBot\api key.txt`** —— 它是 35 字符的官方 DeepSeek key 明文，
> 而同一个 key 已经在 `huanmeng\config\.env` 里了，这个文件纯属冗余的泄露面。

---

## 5. 跨项目：DSH 小鲸鱼余额挂件（10-01）

**不属本目录**，但同属本会话，一并记录。

- 插件：`~/.dsh/profiles/desktop/node_modules/dsh-whale-widget`（v0.3.17）
- 问题：`DEEPSEEK_API_KEY` 凭据里存的是**中转站 Key**，插件拿它请求**官方**
  `api.deepseek.com/user/balance` → 401；而官方账号路径被「API Key 永远优先」挡住
- 证据：账本 `.dshw-usage.json` 里 `accounting.active = bd52f96396e224bac5369ef6-CNY`，
  而 `sha256('dsh-account:default')[:24]` 正是该值 → 之前显示的余额本就来自 DSH 官方账号路径
- 修复：`lib/index.js` 的 `fetchBalance()` 开头插入账号路径优先（2 行）
  ```js
  const accountFirst = await fetchAccountBalance()
  if (accountFirst) return accountFirst
  ```
- 备份 `lib/index.js.orig-backup`，说明见插件目录 `PATCH-NOTES.md`
- 生效需**重启 DSH**（宿主代码无法热重载）；用户反馈重建后显示 ¥22.71 ✓
- ⚠️ 升级插件会覆盖该补丁

---

## 6. 未完成 / 待办

| 项 | 说明 |
|---|---|
| ⏳ **验证密码回退** | 只在快速登录失败时才触发，**正常启动验证不到**（见 §4.7.3：已连续两次没验证到）。要验证需人为制造失败条件，或等腾讯回收会话 |
| ⏳ **13:38:50 NapCat 死因未查明** | 无退出日志（强杀或崩溃），QQ 自身日志 `nt_data\log\qq-log_*.log` 也在 13:39:00 断掉。要根治可查 Windows 事件查看器；重启后一切正常 |
| ✅ ~~`fastapi` + `uvicorn`~~ | **已完成**（10-01 14:06）：已装 fastapi 0.142.2 / uvicorn 0.54.0，棋局服务起在 `127.0.0.1:59400`，启动日志已无 ERROR（见 §4.7.11） |
| ✅ ~~好感度/心情长期失效~~ | **已修复**（10-01 14:29）：真正根因是 `pipeline.py:831` 的 `thinking = False` —— **关思考时模型会丢掉整个 JSON 帧**，退化成散文后走 salvage（那里 `fav` 硬编码 0、没有 `mood` 字段）。已改为跟随 API 默认（见 §4.7.15） |
| ⏳ 表情包端到端实测 | 同一根因：没有 JSON 帧 → 模型写不出 `[FACE:xxx]`。修 `thinking` 后**直接调用已实测产出** `[FACE:招呼]`/`[FACE:开心]`，但**经 QQ 真正发出图片这一步还没验过**（需在群里发条带情绪的消息，看日志有没有 `逐句配图: 正文内联 N 张`） |
| ✅ ~~`_TAG_DESC` 与素材不匹配~~ | **已解决**：新增 `data/faces/_descriptions.json` 旁路 + `tools/describe_faces.py`，画面描述改由**实际图片**生成，不再用原作者的（见 §4.7.14） |
| ⏳ 回复延迟上升约 1.5s | `thinking` 默认改为「跟随 API 默认（开启）」的代价。若更在意速度而不在意 fav/mood，可在 `pipeline.py:831` 改回并接受功能失效 |
| ✅ ~~图片缓存 14 条独白前缀~~ | **已刷新**：`data\Image_description_cache.txt` 置为 `{}`，图片再被发送时自动重建干净描述 |
| ⏳ `data/faces` 素材导入 | 目录 + `README.md` + 工具 `tools\import_faces.py` 已就绪，**已试水导入 40 张**（命中 40/40，`表情库加载: 151 关键词, 40 文件`）。要扩充就跑工具的 `--apply`（机器人小号去重后还有 667 张可导，每次调用都消耗额度） |
| 🎚️ 表情频率（已调低） | 提示词已从「鼓励常发」改为「可选、别刻意，一次最多 1 张」（见 §4.7.16）。还想更少：QQ 里发 `/~key face_inline off`（退回"整条至多 1 张、发在最后"），或清空 `data/faces/` |
| ⚠️ 改 `data/skills/*.md` 必须重启 | `/~reload` 只重读 `bot_config.toml` 等配置，**不重载技能缓存**；控制文件那条备用通道是死代码（见 §4.7.17） |
| ✅ ~~搜索 `search_web` 无法调用~~ | **已彻底修复**（10-01 15:00）：①`requests`/`bs4` 没装 → 模块 import 失败；②`perform_search` 的"回退"是空壳；③**`ds_native_search` 用了 `deepseek-flash`，而它根本不执行 web_search** → 改用 `deepseek-v4-pro` + `tool_choice:"required"`（见 §4.7.18） |
| ✅ ~~抓取搜索被反爬拦截~~ | **已绕过**：搜索现在走官方 Responses API 的服务端 web_search，**不抓网页**，反爬与之无关 |
| ✅ ~~`weather` 指令偶发失败~~ | **已修复**（10-01 15:05）：API 偶发慢到 12.4s，而代码 `timeout=10.0` → 超时（见 §4.7.19） |
| ✅ ~~`weather` 卡片调不动~~ | **已修复**（10-01 15:15）：三层缺陷叠加 —— ①`send_weather_card` 失败时返回 `None`（契约写反）致回退分支永不执行→静默；②回退要的 15 个 `[weather.*]` 语言键在 `lang.toml` 里**根本不存在**；③chromium 路径写死成 Linux 的 `/usr/bin/chromium-browser`。均已修（见 §4.7.20） |
| ⏳ 卡片扩展名与实际格式不符 | 截图输出 JPEG（`type='jpeg'`）却命名 `.png`（weather/box/changelog 共用）。实测发得出去（NapCat 按字节嗅探），**故意未改**以免回归 |
| ⏳ 开机自启 | 尚未配置（可加计划任务，登录时跑 `launcher.ps1`） |
| ⏳ `main.py` 启动横幅 | 仍硬编码打印"幻梦 QQ Bot"，仅 console 可见，QQ 里看不到 |
| ✅ ~~群白名单只配了 `<GROUP_1>`~~ | **已补加** `<GROUP_2>`、`<GROUP_3>`（10-01 17:09）。此前非白名单群里只有 admin 能触发，症状是"机器人在群里只理我一个人"（见 §4.7.21） |
| ✅ ~~`/~owner gadd` 报"未知操作"~~ | **已修复**（10-01 17:09）：用户照抄了帮助里的 `<群号>` 尖括号 → `args[1].isdigit()` 为 False。已加 `_strip_arg_wrapper()` 做解析层容错（见 §4.7.22） |
| ✅ ~~绘图完全没配 key~~ | **已解决**（10-04 09:32）：**改用中转站的 `openai/gpt-image-1`**（无需第三方账号），文生图 56s / 参考图生图 112s 均实测跑通（见 §4.7.23、§4.7.24）。**并加了 `/~key draw on|off` 一键开关**（见 §4.7.25） |
| ✅ ~~看 GIF 只看第一帧~~ | **已修复**（10-04 22:35）：新增多帧网格合成 + 提示词说明，A/B 实测能准确说出动作变化（见 §4.7.26） |
| 🔴 视频仍无 key | `/~video`、`/~img2video` 走 `apihub.agnes-ai.com`，仍需 `AGNES_KEY`；中转站能否文生视频**未验证** |
| ⏳ `QQProfile.bak-224627` | 重置 profile 时的备份，确认无误后可删 |

---

## 7. 常用命令速查

```powershell
# 启动 / 停止 / 状态（桌面快捷方式等价）
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1 -Stop
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1 -Status

# 实时二维码（推荐，随时扫）
http://127.0.0.1:8899/
powershell -ExecutionPolicy Bypass -File D:\QQBot\tools\grab_qr.ps1      # 抓一张到 qrcode.jpg

# NapCat 登录页（码失效时在这里刷新）
http://127.0.0.1:6099/webui?token=<NAPCAT_WEBUI_TOKEN>

# 只重启幻梦（改完 .env 必须重启；改 data/skills/*.md 也必须重启 —— /~reload 不重载技能，见 §4.7.17）
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*D:\QQBot\huanmeng*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
cd D:\QQBot\huanmeng; .venv\Scripts\python.exe -X utf8 main.py

# 接口自检（换 API / 换模型后必跑）
# ⚠️ 必须带 -X utf8，否则它打印 ✓ 时会 UnicodeEncodeError 崩掉、结果全丢（见 §4.7.6）
cd D:\QQBot\huanmeng; .venv\Scripts\python.exe -X utf8 relay_test.py

# 查看最新 NapCat 日志的登录相关行
$l = Get-ChildItem D:\QQBot\NapCat\napcat-*.log | Sort-Object LastWriteTime -Descending | Select -First 1
Get-Content $l | Select-String '快速登录|密码登录|二维码|WebSocket服务|ErrCode'

# 安全终止 NapCat 实例（★只认 QQProfile，绝不用可执行路径判断！）
Get-CimInstance Win32_Process -Filter "Name='QQ.exe'" |
  Where-Object { $_.CommandLine -like '*QQProfile*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

⚠️ **判据铁律**：识别 NapCat 实例**只能靠命令行里的 `QQProfile`**。
个人 QQ 是 `Tencent\QQNT\QQ.exe`、NapCat 是 `Tencent\qqnt\QQ.exe`，**仅大小写不同**，
而 PowerShell 的 `-like`/`-match` **不区分大小写**——本会话已因此误杀过用户个人 QQ 两次。

⚠️ **`launcher.ps1` 必须保持 UTF-8 with BOM**。PS 5.1 读无 BOM 的 `.ps1` 会按 ANSI 解码，
脚本里的中文会导致解析失败。用编辑器改过后若报错，执行：
```powershell
$p='D:\QQBot\launcher.ps1'
$t=[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)
[IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding($true)))
```

---

## 8. 故障速查（精简版，详版见 README §6）

| 现象 | 首查 |
|---|---|
| 幻梦一直 `远程计算机拒绝网络连接` | NapCat 是否登录成功、8099 是否监听 |
| 扫码后 worker 崩溃、会话写不进 | **两个 QQ 实例共用 profile** → 检查 `--user-data-dir` 是否生效 |
| `ErrCode 10` | 风控。手机与电脑同一网络，或电脑连手机热点后重扫 |
| `ErrCode 3` | 二维码过期（发新码即可） |
| `当前账号已登录,无法重复登录` 且进程退出 | 隔离 profile 登录态损坏 → 改名备份 `QQProfile`、新建空目录、重新扫码一次 |
| 双击启动器没反应 | 看最新 `napcat-*.log`；启动器已自动清理孤儿进程、改用时间戳日志 |
| 机器人回空消息 | 中转站是否丢弃 `thinking` 参数（跑 `relay_test.py -X utf8`） |
| 日志里大段 `UnicodeEncodeError` / `Logging error` | **假警报，功能正常**——emoji 撞 GBK，属噪声。确认启动命令带 `-X utf8`（见 §4.7.1） |
| `relay_test.py` 跑到最后突然崩溃 | 同上，`✓` 撞 GBK。带 `-X utf8` 重跑（见 §4.7.6） |
| `launcher.ps1 -Status` 报"全部未运行/未监听" | 若在受限沙箱（无 WMI）下，这是**假红灯**。用 `netstat -ano` 复核（见 §4.7.4） |
| 机器人不回话 | 群是否在白名单；`回复兴趣`（当前 8，越高越沉默） |
| 改人格没生效 | ①只改了 `bot_config.toml`，`00_core.md` 的人格锁没改（人格锁优先级最高）；②**改 skills 后没重启幻梦** —— `/~reload` 不重载技能（见 §4.7.17） |

---

## 9. 安全与注意事项

- `config/.env` 含中转站 Key；`.credentials.yaml`（DSH）含 Key —— 均勿外传或提交仓库
- WebUI token `<NAPCAT_WEBUI_TOKEN>` 等同登录权限，WebUI 已限定本机
- `start-napcat.bat` 现含 QQ 密码的 MD5（非明文，但 MD5 弱，勿外传该文件）
- 机器人使用第三方 QQ 协议库，**存在账号被腾讯风控/封禁的风险**，务必使用小号
- 全部服务以当前用户身份运行，未提权
