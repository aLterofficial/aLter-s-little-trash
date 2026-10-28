### 大量ai内容警告，只是本人在第一次尝试部署qqbot时的alpha归档，内容可靠性待审核。
# 本项目可视作对幻梦的部分功能在windows上的部分封装，其目的在于在无linux的设备上快速部署幻梦架构的机器人，对已安装linux环境或希望使用astrbot的用户参考性有限。


---


---


### 命令行

```powershell
# 启动 / 停止 / 查看状态
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1 -Stop
powershell -ExecutionPolicy Bypass -File D:\QQBot\launcher.ps1 -Status

# NapCat 登录页
http://127.0.0.1:6099/webui?token=<NAPCAT_WEBUI_TOKEN>

# 只重启幻梦
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*D:\QQBot\huanmeng*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
cd D:\QQBot\huanmeng; .venv\Scripts\python.exe main.py

# 换 API / 换模型后先自检
cd D:\QQBot\huanmeng; .venv\Scripts\python.exe relay_test.py
```

> ⚠️ **`launcher.ps1` 必须保存为 UTF-8 with BOM**。Windows PowerShell 5.1 读取无 BOM 的
> `.ps1` 会按 ANSI 解码，脚本里的中文会导致解析失败。用编辑器改动后若出现乱码报错，


**注意**：改 `.env` 里的 Key 必须**重启进程**，`/~reload` 无效——因为 `load_dotenv`
不会覆盖进程里已存在的环境变量。

---


### WS 地址

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


###  模型与中转站

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





### 免扫码自动登录的实现

NapCat 通过 `process.argv` 里的 `-q`/`--qq` 判断是否快速登录
（`napcat.mjs:82700`，取该标志**后面那个 token** 当账号）。
而 `NapCatWinBootMain.exe` 只会把**唯一一个额外参数**包装成 `-q <参数>` 转发给 QQ.exe，
那个位置必须留给 `--user-data-dir`（profile 隔离是硬需求）。于是 NapCat 把
`--user-data-dir=...` 当成了账号名，快速登录必然失败、每次都要扫码。

解法：`loadNapCat.template.js` 在 `napcat.mjs` 加载**之前**改写 `process.argv`，
把第一个 `-q` 后面的 token **覆盖**成真实账号（不是追加——`findIndex` 只认第一个）。
`start-napcat.bat` 每次启动都从模板复制出 `loadNapCat.js`。

**该模板有三个必须遵守的约束**

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


---


---

## 安全提示

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
