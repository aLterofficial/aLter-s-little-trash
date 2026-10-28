# 会话交接日志（SESSION-LOG）

### 包含了一些注意项与内容凭据
---


##  路径与凭据速查（该部分仅作示例参考，但应确保路径结构与此保持一致以防止相对路径寻取失败）

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

##  架构

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

# 注意 **profile 隔离是硬需求**：QQ 从 Windows 已知文件夹 API 取数据目录（**不是** `%APPDATA%` 环境变量）。
# 两个 QQ 实例共用同一 profile 会导致"扫码确认后 worker 进程崩溃、会话写不进去"。

---

####  `data/faces` 表情素材：目录已建好，素材需自行导入

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


| 来源 | 路径 | 数量 |
|---|---|---|
| 机器人小号 <BOT_QQ> | `%USERPROFILE%\Documents\Tencent Files\<BOT_QQ>\nt_qq\nt_data\Emoji\` | 800 张（去重后 **707**） |
| 你的主号 <OWNER_QQ> | `%USERPROFILE%\Documents\Tencent Files\<OWNER_QQ>\nt_qq\nt_data\Emoji\` | 1308 张 |

**新增工具 `D:\QQBot\tools\import_faces.py`**：用视觉模型逐张识别情绪 → 从 48 个规范词里
选一个 → 复制成 `data/faces/<情绪词>_<编号>.png`。特性：

- **默认 dry-run**，加 `--apply` 才真写文件
- 自动**滤除 `Thumb/` 缩略图**并按内容 **MD5 去重**
- 复用 `[model.picture]` 配置（跟随 `bot_config.toml` 的 provider 切换）
- 调用时**带 `extra_body={"thinking":{"type":"disabled"}}`** 否则 `content` 为空、打标全废



用法：

```powershell
cd D:\QQBot\huanmeng
.venv\Scripts\python.exe -X utf8 D:\QQBot\tools\import_faces.py --limit 40             # 预览
.venv\Scripts\python.exe -X utf8 D:\QQBot\tools\import_faces.py --limit 40 --apply     # 导入
```




###  群聊共享记忆：新增「全局共享笔记本」层

### bot 能在群聊中共享记忆。


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
