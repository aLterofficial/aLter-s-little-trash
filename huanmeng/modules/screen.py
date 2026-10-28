"""/~screen — 看屏幕：**本机直接截屏 + 视觉理解**（仅主人）。

═══ 为什么单独做这个 ═══

原 `/~sys shot` 有两个问题：

1. **依赖一个独立的 PC 客户端**（`services/pc_status.py` 的 TCP 58890 接收端）。
   本部署里那个客户端（`scripts/pc_status_reporter.py`）**根本没在跑**，
   `request_screenshot()` 一看 `_client_writer is None` 就直接失败。
   —— 那套设计是给「机器人跑在服务器、主人电脑是另一台」的场景准备的。
2. **更要紧**：`/~sys shot` 截完屏**只是把图转发给用户**，机器人自己**没有看**
   （全程没有任何视觉理解）。而用户要的是"让 bot 看一下屏幕上的内容"。

幻梦**就跑在这台电脑上**，所以直接本地截屏最直接 —— 不需要任何客户端、不需要网络。

═══ 安全 ═══

**仅主人可用**（屏幕上可能是任何私密内容，而描述**会发到聊天里**，
群里其他人也看得到）。判断的是**消息发送者**，所以群友要求截图会被拒绝。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from core.logger import get_logger

logger = get_logger("screen")

_ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = _ROOT / "data" / "img_temp"
ALLOW_FILE = _ROOT / "data" / "screen_allow.txt"   # 看屏幕授权名单（主人以外的人）

MAX_WIDTH = 1600        # 截屏送给视觉模型前的最长边（兼顾看清文字与 token 成本）
JPEG_QUALITY = 85

_PROMPT = (
    "这是一张电脑屏幕截图。请直接描述屏幕上显示的内容：正在用什么程序、"
    "当前窗口/页面是什么、屏幕上的主要信息（如果是文字、代码、网页或对话框，"
    "说清它的内容要点）。不要输出任何推理或思考过程，直接给描述，不超过 120 字。"
)
_PROMPT_WITH_Q = (
    "这是一张电脑屏幕截图。请看着这张截图回答下面的问题，"
    "不要输出推理过程，直接给答案，不超过 150 字。\n用户想知道：{q}"
)


def grab_screen():
    """本地截取屏幕（含所有显示器）。返回 PIL Image；失败抛异常。"""
    from PIL import ImageGrab
    # all_screens=True 才能覆盖多显示器（Windows 支持）
    try:
        return ImageGrab.grab(all_screens=True)
    except TypeError:
        # 老版本 Pillow 没有 all_screens 参数
        return ImageGrab.grab()


def _prepare(img, max_width: int = MAX_WIDTH):
    """缩放并转 RGB，返回 (PIL Image, 宽, 高)。"""
    from PIL import Image as _PILImage
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((max_width, int(h * ratio)), _PILImage.LANCZOS)
    return img


async def capture_and_describe(question: str = "", chat_id: int = 0) -> tuple[str, Path | None]:
    """截屏 + 让视觉模型看。返回 (描述文本, 截图文件路径)。截图路径可能为 None。"""
    loop = asyncio.get_running_loop()

    # ── 1. 本地截屏（放线程池，ImageGrab 是阻塞的）──
    try:
        img = await loop.run_in_executor(None, grab_screen)
    except Exception as e:
        logger.error("本机截屏失败: %s", e)
        return f"截屏失败：{e}\n（Pillow 的 ImageGrab 在 Windows 上依赖 GDI，一般不会失败）", None

    img = _prepare(img)
    w, h = img.size

    # ── 2. 落盘一份（既便于发给用户，也便于排查）──
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SHOT_DIR / f"screen_{time.strftime('%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}.jpg"
    try:
        await loop.run_in_executor(
            None, lambda: img.save(path, format="JPEG", quality=JPEG_QUALITY)
        )
    except Exception as e:
        logger.warning("截图落盘失败: %s", e)
        path = None

    buf = __import__("io").BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    raw = buf.getvalue()
    logger.info("截屏完成: %dx%d → %d bytes → %s", w, h, len(raw), path.name if path else "(未落盘)")

    # ── 3. 交给视觉模型 ──
    from core.config import get_config
    from services.image_api import recognize_image
    cfg = get_config()
    prompt = _PROMPT_WITH_Q.format(q=question) if question.strip() else _PROMPT
    try:
        desc = await recognize_image(
            "", cfg.image_model, chat_id=chat_id,
            image_bytes=raw, prompt_override=prompt, use_cache=False,
        )
    except Exception as e:
        logger.error("屏幕理解失败: %s", e)
        return f"截屏成功，但看不太懂（视觉模型调用失败）：{e}", path
    return (desc or "").strip() or "截屏成功，但没能看出什么内容。", path


def viewer_labels() -> dict[int, str]:
    """读取**看屏幕授权名单** → `{QQ: 身份标注}`（无标注则值为空串）。

    格式：`data/screen_allow.txt`，一行一个 QQ 号，后面可跟身份说明，
    `#` 注释。改完立即生效（每次调用都重读）。

    ⚠️ 名单里的人可以让机器人截图并发到聊天里 —— 只放信得过的人。
    """
    out: dict[int, str] = {}
    try:
        if not ALLOW_FILE.exists():
            return out
        for raw in ALLOW_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split(None, 1)
            head = parts[0].strip()
            if head.isdigit():
                out[int(head)] = parts[1].strip() if len(parts) > 1 else ""
    except Exception as e:
        logger.warning("读取看屏幕授权名单失败: %s", e)
    return out


def allowed_viewers() -> set[int]:
    """允许触发看屏幕的 QQ 集合（不含主人本人）。"""
    return set(viewer_labels())


def viewer_label(qq) -> str:
    """返回该 QQ 的**身份标注**（如"妈妈"）；不在名单或没标注则返回空串。

    ★ 用途：让机器人在**这个人本人说话时**知道该怎么称呼 ——
      见 `core/pipeline.py` 的「【说话人身份】」注入。
      刻意做成"只在本人说话那一刻生效"，**不写进全局笔记本**，
      所以不会扩散到别的群、也不会变成机器人的通用知识。
    """
    try:
        return viewer_labels().get(int(qq), "")
    except (TypeError, ValueError):
        return ""


async def cmd_screen(args, user_id, group_id, sender_name, is_group, bot_qq):
    """/~screen — 让 bot 看一眼当前屏幕（**主人本人，或授权名单里的人**）

    /~screen            截屏并描述屏幕上有什么
    /~screen <问题>     带着问题看屏幕（例：/~screen 现在在玩什么游戏）
    /~screen send       只把截图发出来，不做理解
    """
    from core.config import get_config
    cfg = get_config()

    # ── 身份闸：主人本人，或在 screen_allow.txt 里 ──
    # 判断的是**消息发送者**，不是"群里有没有主人"。
    # ★ 2026-10-04: 新增授权名单 —— 用户的妈妈（<MOM_QQ>）在群里问
    #   "他在干什么" 时需要能触发。名单只放信得过的人：屏幕内容可能包含
    #   任何私密信息，而描述**会发到聊天里**。
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = 0
    try:
        owner = int(getattr(cfg, "admin_qq", 0) or 0)
    except (TypeError, ValueError):
        owner = 0
    if not uid or (uid != owner and uid not in allowed_viewers()):
        logger.warning("未授权者尝试看屏幕: user=%s group=%s", user_id, group_id)
        return "看屏幕只有主人和他授权的人能用喵~"

    a = list(args or [])
    chat_id = group_id if is_group else user_id

    # 查看授权名单（只有能通过上面闸门的人才看得到）
    if a and str(a[0]).lower() in ("allow", "名单", "授权"):
        viewers = allowed_viewers()
        lst = "\n".join(f"  {q}" for q in sorted(viewers)) if viewers else "  （空）"
        return (f"主人：{owner}（始终有权限）\n"
                f"另外授权的人：\n{lst}\n\n"
                f"要增减就编辑：{ALLOW_FILE}")

    # 只要图，不要理解
    if a and str(a[0]).lower() in ("send", "图", "截图", "shot"):
        loop = asyncio.get_running_loop()
        try:
            img = await loop.run_in_executor(None, grab_screen)
        except Exception as e:
            return f"截屏失败：{e}"
        img = _prepare(img)
        SHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SHOT_DIR / f"screen_{time.strftime('%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}.jpg"
        await loop.run_in_executor(None, lambda: img.save(path, format="JPEG", quality=JPEG_QUALITY))
        return f"[CQ:image,file=file:///{path.as_posix()}]"

    question = " ".join(str(x) for x in a).strip()
    desc, _path = await capture_and_describe(question=question, chat_id=chat_id)
    return f"👀 屏幕上现在是这样：\n{desc}"
