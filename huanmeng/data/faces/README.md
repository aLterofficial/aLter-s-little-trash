# data/faces —— 表情包素材目录

## 为什么这里是空的

仓库**未附带**素材（原作者说明为"部分私有模块未包含"）。
缺素材时的行为：LLM 写的 `[FACE:xxx]` 标记会被正常剥离，**只是不配图**，文字回复完全不受影响。

## 放进来就能用

把图片直接丢进本目录即可，**无需改任何代码**。支持 `.jpg` `.jpeg` `.png` `.gif` `.webp`。

### 命名规则（文件名即关键词来源）

两种写法都支持、可混用：

| 写法 | 例子 | 命中逻辑 |
|---|---|---|
| **中文名** | `眯眼开心.jpg`、`开心_01.png` | 取文件名里所有 2~4 字的汉字片段 → 命中「开心」 |
| **英文标签** | `happy_026.png`、`cat_shizuku_wink_76.png` | 经 `modules/face_lib.py` 的 `_TAG_CN` 表映射成中文词 |

**推荐格式：`<情绪词>_<编号>.png`**（如 `开心_01.png`、`生气_03.png`）——最直观、命中率最高。

### 48 个规范情绪词（提示词里给 LLM 的可用清单）

```
开心  坏笑  得意  害羞  大哭  委屈  失落  生气  不满  慌张  大喊  惊讶
疑惑  无聊  疲惫  不舍  道歉  祝贺  加油  拒绝  饿    闭眼  睡觉  困
打哈欠 发呆  打招呼 挥手  眨眼  抱猫  抱玩偶 抱蛋糕 抱爱心 抱花  抱东西
端东西 吃东西 吃冰淇淋 喝饮料 逗猫  敬礼  没问题 蹦跳  偷看  张望
站着  坐着  趴着
```

★ **强烈建议用这 48 个词之一命名**：它们正是 system 提示词里告诉 LLM「你可以发哪些图」的清单。
用别的词也能被匹配（文件名里任意汉字片段都是关键词），但 LLM 想不到去用，等于白放。

### 英文标签表在哪

`D:\QQBot\huanmeng\modules\face_lib.py` 的 `_TAG_CN`（第 37 行起）。
每个英文标签对应一个中文主词 + 若干别名，例如 `"smirk": ("坏笑", "得意", "偷笑")`。

### ⚠️ 换素材后要重新生成「画面描述」

`modules/face_lib.py` 内置的 `_FACE_DESC`（48 个主词 → 一句话画面简述）是照
**原作者那批素材**逐张校对写的。你导入自己的图之后它会开始"骗"LLM：
词表说「得意」是抬下巴嘚瑟，而你的 `得意_01.png` 其实是别的画面。

**不用手改代码** —— 跑一次生成器即可，它会按**实际图片**重新描述：

```powershell
cd D:\QQBot\huanmeng
.venv\Scripts\python.exe -X utf8 D:\QQBot\tools\describe_faces.py            # 先预览
.venv\Scripts\python.exe -X utf8 D:\QQBot\tools\describe_faces.py --apply    # 写入
```

结果写在 `data/faces/_descriptions.json`，`face_lib` 会**优先使用它**
（`_FACE_DESC` 退化为"没有自有描述时的默认值"）。重启幻梦后生效，
日志出现 `自有素材画面描述已加载: N 条`。

> 本目录当前的 `_descriptions.json` 就是给已导入的 40 张素材生成的。
> ⚠️ 每张图一次视觉调用，会消耗中转站额度。

## 本机已确认的可用素材来源

两批 QQ 表情缓存（**文件名是纯数字，需要重命名才能用**）：

| 来源 | 路径 | 数量 |
|---|---|---|
| 机器人小号 <BOT_QQ> | `%USERPROFILE%\Documents\Tencent Files\<BOT_QQ>\nt_qq\nt_data\Emoji\` | 800 张 |
| 你的主号 <OWNER_QQ> | `%USERPROFILE%\Documents\Tencent Files\<OWNER_QQ>\nt_qq\nt_data\Emoji\` | 1308 张 |

用 `D:\QQBot\tools\import_faces.py` 可以**自动逐张识别情绪并重命名导入**
（调视觉模型打标，映射到上面 48 个词之一）。

## 生效方式

`face_lib._init()` 是**懒加载**——首次真正用到表情时才扫描目录。所以新增图片后：

- **重启幻梦**（⚠️ `/~reload` 不会重载技能/表情库，见 SESSION-LOG §4.7.17），或
- 重启幻梦

生效后日志里会出现：`表情库加载: N 关键词, M 文件`；缺目录时则是
`表情目录不存在: ...\data\faces`。
