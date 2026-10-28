"""
Agnes AI 多模态生成模块
- /~draw <prompt>    文生图
- /~video <prompt>   文生视频
- /~img2video        图生视频 (需引用/回复图片)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import uuid
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.logger import get_logger
from services.sender import get_ws_manager

logger = get_logger("agnes")

# 文生图：CloudMist（gpt-image-2，base64 返回）
# key 从环境变量读取（config/.env 里配置 AGNES_API_KEY），禁止硬编码入库
AGNES_BASE = "https://v2.cloudmist.cloud/v1"
AGNES_API_KEY=<API_KEY> "")

# 文生视频：原 Agnes 服务（保持旧配置，与新图服务分离）
AGNES_VIDEO_BASE = "https://apihub.agnes-ai.com/v1"
CST = timezone(timedelta(hours=8))
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "agnes_output"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_api_key() -> str:
    # 运行时读取，避免 .env 加载晚于模块 import 导致取到空
    return os.environ.get("AGNES_API_KEY", "") or AGNES_API_KEY


def _video_api_key() -> str:
    return os.environ.get("AGNES_KEY", "") or os.environ.get("AGNES_API_KEY", "")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }


def _video_headers() -> dict:
    return {
        "Authorization": f"Bearer {_video_api_key()}",
        "Content-Type": "application/json",
    }


# ════════════════════════════════════════════════════════════
#  绘图后端选择（★ 2026-10-01 新增）
# ════════════════════════════════════════════════════════════
# 背景：CloudMist（`AGNES_API_KEY`）是原作者用的图源，要单独申请 key。
#   而**中转站本身就能文生图** —— 实测 `openai/gpt-image-1` 走标准
#   `POST {RELAY_URL}/images/generations` 可用，返回 `b64_json`，
#   与 `_gen_image()` 既有的解析逻辑**完全兼容**，无需额外申请第三方账号。
#
#   ⚠️ 同站的 `black-forest-labs/flux-1.1-pro` / `bytedance/jimeng_t2i_v30`
#      **不要用**：路由会拒（`scheduler.route_not_supported`），它们要别的调用形状，
#      `images/generations`、`images/edits`、`chat/completions` 三种标准路径全被拒。
#
# 策略：有 `AGNES_API_KEY` → 走 CloudMist（原行为，支持自定义尺寸）；
#       否则 → 回落中转站（尺寸必须归一化，见下）。
RELAY_DRAW_MODEL = os.environ.get("RELAY_DRAW_MODEL", "openai/gpt-image-1")

# 中转站 gpt-image-1 实测**只认这三档**，传自定义尺寸会被拒：
#   Invalid size '1536x864'. Supported sizes are 1024x1024, 1024x1536, 1536x1024, and auto.
_OPENAI_IMAGE_SIZES = ("1024x1024", "1024x1536", "1536x1024")


def _draw_backend() -> tuple[str, str, str]:
    """选出绘图后端，返回 (base_url, api_key, model)；都不可用则返回 ('','','')。"""
    cm_key = _get_api_key().strip()
    if cm_key:
        return AGNES_BASE, cm_key, "gpt-image-2"
    relay_key=<API_KEY> "").strip()
    relay_url = os.environ.get("RELAY_URL", "").strip().rstrip("/")
    if relay_key and relay_url:
        return relay_url, relay_key, RELAY_DRAW_MODEL
    return "", "", ""


def _normalize_size_for_openai(size: str) -> str:
    """把任意 WxH 归一化到 gpt-image-1 支持的三档（按宽高比就近映射）。

    本项目 `_resolve_size()` 默认给 `1536x864`（16:9），而中转站的 gpt-image-1
    会直接拒绝它 —— 必须映射，否则每张图都报 Invalid size。
    """
    s = (size or "").strip().lower()
    if s in _OPENAI_IMAGE_SIZES:
        return s
    parts = s.split("x")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        w, h = int(parts[0]), int(parts[1])
        if w > h * 1.15:
            return "1536x1024"      # 横向
        if h > w * 1.15:
            return "1024x1536"      # 竖向
    return "1024x1024"


# ── 配额管理 ────────────────────────────────────────────

_QUOTA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DRAW_LIMIT = 5  # 每人每天画图次数（admin 无限）
DEFAULT_VIDEO_LIMIT = 4  # 每人每天视频次数


def _load_quota(filename: str) -> dict:
    p = _QUOTA_DIR / filename
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"daily_reset": "", "users": {}}


def _save_quota(filename: str, data: dict):
    _QUOTA_DIR.mkdir(parents=True, exist_ok=True)
    (_QUOTA_DIR / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_daily_reset(data: dict) -> dict:
    today = datetime.now(CST).strftime("%Y-%m-%d")
    if data.get("daily_reset") != today:
        data["daily_reset"] = today
        for uid in data.get("users", {}):
            data["users"][uid]["used"] = 0
    return data


def _get_user_quota(data: dict, user_id: int, default_limit: int) -> tuple[int, int]:
    """返回 (剩余, 上限)"""
    uid = str(user_id)
    u = data.setdefault("users", {}).setdefault(uid, {"used": 0, "limit": default_limit})
    u.setdefault("limit", default_limit)
    left = u["limit"] - u.get("used", 0)
    return left, u["limit"]


def _use_quota(data: dict, user_id: int, default_limit: int = DEFAULT_DRAW_LIMIT) -> int:
    """扣除一次用量，返回剩余次数"""
    uid = str(user_id)
    data.setdefault("users", {}).setdefault(uid, {"used": 0, "limit": default_limit})
    data["users"][uid]["used"] = data["users"][uid].get("used", 0) + 1
    return data["users"][uid]["limit"] - data["users"][uid]["used"]


def check_and_use_draw(user_id: int) -> tuple[bool, int, int]:
    """返回 (允许, 剩余, 上限) — 不扣量，只检查；admin 无限"""
    from core.config import get_config
    if get_config().is_admin(user_id):
        return True, 999, 0  # 0=无限，显示为 ∞
    data = _load_quota("draw.json")
    data = _check_daily_reset(data)
    left, limit = _get_user_quota(data, user_id, DEFAULT_DRAW_LIMIT)
    return left > 0, left, limit


def commit_draw(user_id: int) -> int:
    """画图成功后扣量，返回剩余次数；admin 不扣"""
    from core.config import get_config
    if get_config().is_admin(user_id):
        return 999
    data = _load_quota("draw.json")
    data = _check_daily_reset(data)
    remaining = _use_quota(data, user_id, DEFAULT_DRAW_LIMIT)
    _save_quota("draw.json", data)
    return remaining


def check_and_use_video(user_id: int) -> tuple[bool, int, int]:
    """返回 (允许, 剩余, 上限) — 不扣量，只检查"""
    data = _load_quota("video.json")
    data = _check_daily_reset(data)
    left, limit = _get_user_quota(data, user_id, DEFAULT_VIDEO_LIMIT)
    return left > 0, left, limit


def commit_video(user_id: int) -> int:
    data = _load_quota("video.json")
    data = _check_daily_reset(data)
    remaining = _use_quota(data, user_id, DEFAULT_VIDEO_LIMIT)
    _save_quota("video.json", data)
    return remaining


def owner_quota_get(kind: str, qq: str = "") -> str:
    """/~owner draw|video get [QQ]"""
    fn = f"{kind}.json"
    data = _check_daily_reset(_load_quota(fn))
    lim = DEFAULT_DRAW_LIMIT if kind == "draw" else DEFAULT_VIDEO_LIMIT
    if qq:
        left, limit = _get_user_quota(data, int(qq), lim)
        return f"QQ {qq}: 已用 {limit-left}/{limit} (剩余 {left})"
    lines = [f"今日{kind}用量:"]
    for uid, u in data.get("users", {}).items():
        left = u.get("limit", lim) - u.get("used", 0)
        lines.append(f"  {uid}: {left}/{u.get('limit',lim)}")
    return "\n".join(lines) if len(lines) > 1 else f"今日暂无{kind}用量记录"


def owner_quota_set(kind: str, qq: str, value: int):
    """/~owner draw|video set <QQ> <值>"""
    fn = f"{kind}.json"
    data = _check_daily_reset(_load_quota(fn))
    data.setdefault("users", {}).setdefault(qq, {"used": 0, "limit": value})
    data["users"][qq]["limit"] = value
    _save_quota(fn, data)


def owner_quota_reset(kind: str = ""):
    """/~owner draw|video reset [kind]  无 kind=全部"""
    kinds = [kind] if kind else ["draw", "video"]
    for k in kinds:
        fn = f"{k}.json"
        _save_quota(fn, {"daily_reset": "", "users": {}})


# ── API 调用 ────────────────────────────────────────────

# 预设比例 → 尺寸映射表（默认 16:9）
# gpt-image 原生支持 1024x1024/1536x1024/1024x1536，也支持自定义如 1536x864
_ASPECT_RATIOS: dict[str, str] = {
    "1:1":   "1024x1024",
    "square": "1024x1024",
    "3:2":   "1536x1024",
    "landscape": "1536x1024",
    "2:3":   "1024x1536",
    "portrait": "1024x1536",
    "16:9":  "1536x864",
    "wide":   "1536x864",
    "9:16":  "864x1536",
    "tall":   "864x1536",
    "4:3":   "1152x864",
    "3:4":   "864x1152",
}


def _resolve_size(raw: str) -> str:
    """解析比例/尺寸参数 → 规范的 WxH 字符串

    支持: 16:9 / 1:1 / 1024x1024 / 1536x864 / wide / square / portrait / landscape
    默认 16:9 → 1536x864
    """
    raw = raw.strip().lower()
    if not raw:
        return "1536x864"  # 默认 16:9
    if "x" in raw and raw.replace("x", "").isdigit():
        return raw  # 直接的 WxH 格式
    if ":" in raw:
        mapped = _ASPECT_RATIOS.get(raw)
        if mapped:
            return mapped
    mapped = _ASPECT_RATIOS.get(raw)
    if mapped:
        return mapped
    return "1536x864"  # 无法识别 → 默认 16:9


def _err_text(e: Exception, resp=None) -> str:
    """异常 → 简短可读错误文本（HTTP 状态码 + 响应体摘要）"""
    if resp is not None:
        try:
            body = resp.text[:200].replace("\n", " ")
            return f"HTTP {resp.status_code}: {body}"
        except Exception:
            pass
    s = str(e).strip()
    if hasattr(e, "response") and getattr(e, "response") is not None:
        try:
            body = e.response.text[:200].replace("\n", " ")
            return f"HTTP {e.response.status_code}: {body}"
        except Exception:
            pass
    if not s:  # httpx 超时等 str 为空
        return type(e).__name__
    return f"{type(e).__name__}: {s[:180]}"


async def _gen_image(prompt: str, size: str = "1536x864", reference_image_url: str = "") -> dict | None:
    """文生图（支持参考图） → 成功 {local_path}，失败 {"error": 文本}"""
    # ★ 2026-10-01：改为「有 CloudMist key 走 CloudMist，否则回落中转站」。
    #   原来 key 为空时 `_headers()` 会拼出 `Authorization: Bearer `（后面什么都没有），
    #   h11 直接抛 `LocalProtocolError: Illegal header value b'Bearer '` —— 那条原始异常
    #   还会被当成 result["error"] 原样贴进群里，用户完全看不懂。
    base, api_key, model = _draw_backend()
    if not base:
        return {"error": "绘图服务未配置：config/.env 里既没有 AGNES_API_KEY，"
                         "也没有可用的 RELAY_KEY / RELAY_URL。"}
    if reference_image_url:
        return await _gen_image_with_ref(prompt, size, reference_image_url)

    # 中转站的 gpt-image-1 只认三档尺寸；CloudMist 的 gpt-image-2 支持自定义
    if model != "gpt-image-2":
        size = _normalize_size_for_openai(size)

    body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    logger.info("文生图: model=%s size=%s base=%s", model, size, base)
    try:
        # 复杂 prompt 生成可能超过 2 分钟，超时放宽到 300s
        async with httpx.AsyncClient(timeout=300, verify=False) as c:
            r = await c.post(f"{base}/images/generations", json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
            img = data.get("data", [{}])[0]
            if img.get("b64_json"):
                raw = base64.b64decode(img["b64_json"])
                path = DATA_DIR / f"draw_{uuid.uuid4().hex[:8]}.png"
                path.write_bytes(raw)
                return {"local_path": str(path)}
            url = img.get("url", "")
            if url:
                path = DATA_DIR / f"draw_{uuid.uuid4().hex[:8]}.png"
                async with httpx.AsyncClient(timeout=60, verify=False) as c2:
                    r2 = await c2.get(url)
                    path.write_bytes(r2.content)
                return {"url": url, "local_path": str(path)}
            return {"error": f"响应中无图片数据: {str(data)[:180]}"}
    except Exception as e:
        err = _err_text(e)
        logger.warning("文生图失败: %s", err)
        return {"error": err}


async def _download_image(url: str, dest: Path) -> bool:
    """下载图片到本地（带 UA，失败返回 False）"""
    try:
        async with httpx.AsyncClient(timeout=60, verify=False, headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get(url)
            r.raise_for_status()
            if len(r.content) < 1024:
                return False  # 太小视为无效（可能是错误页）
            dest.write_bytes(r.content)
            return True
    except Exception as e:
        logger.warning("参考图下载失败 [%s]: %r", type(e).__name__, e)
        return False


async def _gen_image_with_ref(prompt: str, size: str, ref_url: str) -> dict | None:
    """参考图生图：multipart /images/edits 优先，JSON URL 兜底，失败 {"error": 文本}"""
    # ★ 2026-10-01：与 _gen_image 同样改为「有 CloudMist key 走 CloudMist，否则回落中转站」。
    #   实测中转站的 openai/gpt-image-1 **同样支持 /images/edits**（HTTP 200，约 112s，返回 b64_json）。
    base, api_key, model = _draw_backend()
    if not base:
        return {"error": "绘图服务未配置：config/.env 里既没有 AGNES_API_KEY，"
                         "也没有可用的 RELAY_KEY / RELAY_URL。"}
    if model != "gpt-image-2":
        size = _normalize_size_for_openai(size)
    logger.info("参考图生图: model=%s size=%s base=%s", model, size, base)
    import io
    ref_path = DATA_DIR / f"ref_{uuid.uuid4().hex[:8]}.png"
    if not await _download_image(ref_url, ref_path):
        logger.warning("参考图下载失败，退回纯文生图")
        return await _gen_image(prompt, size)

    last_err = ""
    # 方式一：官方 multipart /images/edits
    try:
        with open(ref_path, "rb") as f:
            files = {"image": (ref_path.name, io.BytesIO(f.read()), "image/png")}
            form = {
                "model": model,
                "prompt": prompt,
                "n": "1",
                "size": size,
            }
            async with httpx.AsyncClient(timeout=300, verify=False) as c:
                h = {"Authorization": f"Bearer {api_key}"}  # multipart 不能带 JSON Content-Type
                r = await c.post(f"{base}/images/edits", data=form, files=files, headers=h)
                if r.status_code == 404:
                    raise RuntimeError("edits endpoint not available")
                r.raise_for_status()
                img = r.json().get("data", [{}])[0]
                if img.get("b64_json") or img.get("url"):
                    return await _save_image_result(img)
                last_err = f"响应中无图片数据: {str(img)[:150]}"
    except Exception as e:
        last_err = _err_text(e)
        logger.warning("multipart edits 失败: %s，尝试 JSON URL 兜底", last_err)

    # 方式二：JSON body {"image": url}（部分中转站支持）
    try:
        body = {
            "model": model,
            "prompt": prompt,
            "image": ref_url,
            "n": 1,
            "size": size,
        }
        async with httpx.AsyncClient(timeout=300, verify=False) as c:
            h2 = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            r = await c.post(f"{base}/images/edits", json=body, headers=h2)
            r.raise_for_status()
            img = r.json().get("data", [{}])[0]
            if img.get("b64_json") or img.get("url"):
                return await _save_image_result(img)
            last_err = last_err or f"响应中无图片数据: {str(img)[:150]}"
    except Exception as e:
        last_err = last_err or _err_text(e)
        logger.warning("参考图生图失败: %s", last_err)
    finally:
        ref_path.unlink(missing_ok=True)
    return {"error": last_err or "未知错误"}


async def _save_image_result(img: dict) -> dict:
    """从 API 响应的 data[0] 保存图片 → {local_path}"""
    if img.get("b64_json"):
        raw = base64.b64decode(img["b64_json"])
        path = DATA_DIR / f"draw_{uuid.uuid4().hex[:8]}.png"
        path.write_bytes(raw)
        return {"local_path": str(path)}
    url = img.get("url", "")
    if url:
        path = DATA_DIR / f"draw_{uuid.uuid4().hex[:8]}.png"
        async with httpx.AsyncClient(timeout=60, verify=False) as c2:
            r2 = await c2.get(url)
            path.write_bytes(r2.content)
        return {"url": url, "local_path": str(path)}
    raise ValueError("响应中无图片数据")


async def _gen_video(prompt: str, image_url: str = "",
                     width: int = 1152, height: int = 768,
                     num_frames: int = 241, frame_rate: int = 24) -> dict | None:
    """文生视频 / 图生视频 → 成功 {url, local_path}，失败 {"error": 文本}，503 自动重试"""
    # ★ 同 _gen_image：视频走 AGNES_KEY / AGNES_API_KEY，空 key 同样会拼出非法 `Bearer `
    if not _video_api_key().strip():
        return {"error": "视频服务未配置 API Key：请在 config/.env 里填 AGNES_KEY（或 AGNES_API_KEY）后重启幻梦。"}
    body = {
        "model": "agnes-video-v2.0",
        "prompt": prompt or "make this image into a short video",
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "frame_rate": frame_rate,
    }
    if image_url:
        body["image"] = image_url

    # 创建任务（503 重试 3 次）
    data = None
    create_err = ""
    for retry in range(3):
        try:
            async with httpx.AsyncClient(timeout=60, verify=False) as c:
                r = await c.post(f"{AGNES_VIDEO_BASE}/videos", json=body, headers=_video_headers())
                if r.status_code in (503, 502, 500, 429):
                    create_err = f"HTTP {r.status_code}: {r.text[:150]}"
                    await asyncio.sleep(5)
                    continue
                r.raise_for_status()
                data = r.json()
                break
        except Exception as e:
            create_err = _err_text(e)
            await asyncio.sleep(5)
    if not data:
        return {"error": create_err or "创建视频任务失败（重试 3 次均失败）"}

    video_id = data.get("video_id", "") or data.get("id", "")

    # 轮询结果（最多 60 次 × 3s = 3 分钟）
    for attempt in range(60):
        await asyncio.sleep(3)
        try:
            async with httpx.AsyncClient(timeout=30, verify=False) as c:
                r2 = await c.get(
                    f"https://apihub.agnes-ai.com/agnesapi?video_id={video_id}",
                    headers=_video_headers(),
                )
                if r2.status_code == 503:
                    continue
                r2.raise_for_status()
                d2 = r2.json()
                status = d2.get("status", "")
                if status == "completed":
                    video_url = d2.get("remixed_from_video_id", "")
                    if video_url:
                        path = DATA_DIR / f"video_{uuid.uuid4().hex[:8]}.mp4"
                        async with httpx.AsyncClient(timeout=120, verify=False) as c3:
                            r3 = await c3.get(video_url)
                            path.write_bytes(r3.content)
                        return {"url": video_url, "local_path": str(path)}
                    return {"error": f"任务完成但无视频地址: {str(d2)[:150]}"}
                if status == "failed":
                    err_detail = str(d2.get("error") or d2)[:200]
                    logger.warning("视频任务失败: %s %s", video_id, err_detail)
                    return {"error": f"视频任务失败: {err_detail}"}
        except Exception:
            pass
    logger.warning("视频任务超时: %s", video_id)
    return {"error": f"视频任务超时（3 分钟未完成，video_id={video_id}）"}


# ── 发送 ────────────────────────────────────────────────

async def _send_media(local_path: str, group_id: int, is_group: bool, user_id: int, media_type: str):
    """发送图片/视频到 QQ"""
    cq_type = "image" if media_type == "image" else "video"
    normalized = local_path.replace("\\", "/")
    cq_msg = f"[CQ:{cq_type},file=file:///{normalized}]"

    mgr = get_ws_manager()
    payload = {
        "action": "send_group_msg" if is_group else "send_private_msg",
        "params": {"message": cq_msg},
    }
    if is_group:
        payload["params"]["group_id"] = group_id
    else:
        payload["params"]["user_id"] = user_id
    await mgr.send(payload)


async def _bg_gen_video(user_id, group_id, is_group, prompt, image_url="",
                         width=1152, height=768, num_frames=241, frame_rate=24):
    """后台视频生成——不阻塞聊天"""
    try:
        result = await _gen_video(prompt, image_url=image_url,
                                  width=width, height=height,
                                  num_frames=num_frames, frame_rate=frame_rate)
        if result:
            remaining = commit_video(user_id)
            await _send_media(result["local_path"], group_id, is_group, user_id, "video")
            tip = f"[CQ:at,qq={user_id}] 视频好了喵~ (今日剩余 {remaining}/{DEFAULT_VIDEO_LIMIT})"
        elif result and result.get("error"):
            tip = f"[CQ:at,qq={user_id}] 视频生成失败喵~ (不扣次数)\n错误: {result['error'][:350]}"
        else:
            tip = f"[CQ:at,qq={user_id}] 视频生成失败喵~ 换一种描述试试？(不扣次数)"
    except Exception as e:
        logger.warning("后台视频生成异常: %s", e)
        tip = f"[CQ:at,qq={user_id}] 视频生成失败喵~ 换一种描述试试？(不扣次数)"

    from services.sender import send_by_chat_type
    chat_id = group_id if is_group else user_id
    await send_by_chat_type(tip, chat_id, is_group, user_id)


# ── 命令 ────────────────────────────────────────────────

async def _bg_gen_image(user_id, group_id, is_group, prompt, size, ref_url="", left=0, limit=0):
    """后台图片生成——不阻塞聊天（模式同 _bg_gen_video）"""
    try:
        result = await _gen_image(prompt, size, reference_image_url=ref_url)
        if result and not result.get("error"):
            remaining = commit_draw(user_id)
            await _send_media(result["local_path"], group_id, is_group, user_id, "image")
            limit_str = f"{limit}" if limit else "∞"
            tip = f"[CQ:at,qq={user_id}] 画好了喵~ (今日用量 {remaining}/{limit_str})"
        elif result and result.get("error"):
            err = result["error"]
            tip = f"[CQ:at,qq={user_id}] 图片生成失败喵~ (不扣次数)\n错误: {err[:350]}"
        else:
            tip = f"[CQ:at,qq={user_id}] 图片生成失败喵~ 换一种描述试试？(不扣次数)"
    except Exception as e:
        logger.warning("后台图片生成异常: %s", e)
        tip = f"[CQ:at,qq={user_id}] 图片生成失败喵~ 换一种描述试试？(不扣次数)"

    from services.sender import send_by_chat_type
    chat_id = group_id if is_group else user_id
    await send_by_chat_type(tip, chat_id, is_group, user_id)


async def cmd_draw(args, user_id, group_id, sender_name, is_group, bot_qq, raw_message=""):
    """
    /~draw <提示词>          文生图（默认 16:9）
    /~draw 16:9 <提示词>     指定比例（1:1 3:2 2:3 16:9 9:16 4:3 3:4）
    /~draw 1024x1024 <提示词> 指定像素尺寸
    /~draw help              查看帮助
    引用图片 + /~draw <提示词>  以引用图片为参考图生成
    """
    from utils.format_lang import format_lang
    # ★ 2026-10-04: 一键开关 —— QQ 里发 `/~key draw off` 即可停用（存 data/features.json，
    #   **不用改代码也不用重启**）。放在最前面，关闭时**连 help 都不给**、
    #   也**不消耗每日配额**，避免用户误以为还能用。
    from modules.features import is_enabled as _feat_on
    if not _feat_on("draw"):
        return "绘图功能当前已关闭喵~（管理员可在 QQ 里发 /~key draw on 打开）"
    if args and args[0].lower() == "help":
        return format_lang("help.detail.draw")
    if not args:
        return "用法: /~draw <提示词>  如 /~draw 一只坐在樱花树下的猫娘\n/~draw 16:9 樱花猫娘  指定比例\n引用图片 + /~draw  以引用图片为参考图\n/~draw help 查看完整参数"

    # 配额检查
    ok, left, limit = check_and_use_draw(user_id)
    if not ok:
        return f"今日画图次数已用完喵~ ({limit}/{limit})，明天再来吧！"

    # 解析：第一个参数可能是比例/尺寸，其余是 prompt
    size = "1536x864"  # 默认 16:9
    prompt_parts = []
    for a in args:
        if "x" in a and a.replace("x", "").isdigit():
            # 直接的 WxH 格式
            size = a
        elif a.lower() in _ASPECT_RATIOS or (":" in a and a.replace(":", "").isdigit()):
            # 比例别名（16:9 / wide / square 等）
            size = _resolve_size(a)
        else:
            prompt_parts.append(a)
    prompt = " ".join(prompt_parts) if prompt_parts else " ".join(args)

    # 提取引用图片作为参考图
    ref_url = ""
    if raw_message:
        import re as _re
        m = _re.search(r'\[CQ:reply[^\]]*id=([^\],]+)', raw_message)
        if m:
            reply_id = m.group(1)
            try:
                from services.sender import get_ws_manager
                mgr = get_ws_manager()
                data = await mgr.call_api("get_msg", {"message_id": int(reply_id)})
                if data:
                    # 从 message 段提取图片 URL
                    for seg in data.get("message", []):
                        if seg.get("type") == "image":
                            ref_url = seg.get("data", {}).get("url", "")
                            if ref_url:
                                break
                    # CQ 码兜底
                    if not ref_url:
                        raw = data.get("raw_message", "") or ""
                        m2 = _re.search(r'\[CQ:image[^\]]*url=([^,\]]+)', raw)
                        if m2:
                            ref_url = m2.group(1)
            except Exception as e:
                logger.warning("提取引用图片失败: %s", e)

    # 生成任务 ID 并发送进度提示
    task_id = uuid.uuid4().hex[:8]
    prompt_short = prompt[:60] + "..." if len(prompt) > 60 else prompt
    chat_id = group_id if is_group else user_id
    left_str = f"{left}" if limit else "∞"  # limit=0 表示 admin 无限
    limit_str = f"{limit}" if limit else "∞"
    ref_hint = " [参考图]" if ref_url else ""
    tip = f"开始生成图片{ref_hint}: [{prompt_short}] | 模型: GPT Image 2 | 任务ID: {task_id} | 比例: {size} | 今日用量: {left_str}/{limit_str}"
    from services.sender import send_by_chat_type
    await send_by_chat_type(tip, chat_id, is_group, user_id)

    # 后台生成，不阻塞聊天（模式同 cmd_video）
    asyncio.create_task(_bg_gen_image(
        user_id, group_id, is_group, prompt, size,
        ref_url=ref_url, left=left, limit=limit,
    ))
    return f"图片生成任务已提交喵~ 好了会发出来 (任务ID: {task_id})"


async def cmd_video(args, user_id, group_id, sender_name, is_group, bot_qq):
    """
    /~video <提示词>  文生视频
    /~video <提示词> 512x512  指定尺寸
    /~video help       查看详细帮助
    """
    from utils.format_lang import format_lang
    if args and args[0].lower() == "help":
        return format_lang("help.detail.video")
    if not args:
        return "用法: /~video <提示词>  如 /~video 樱花飘落的街道\n/~video help 查看完整参数"

    # 配额检查（不扣量）
    ok, left, limit = check_and_use_video(user_id)
    if not ok:
        return f"今日视频次数已用完喵~ ({limit}/{limit})，明天再来吧！"

    chat_id = group_id if is_group else user_id
    tip = f"正在生成视频喵~ 需要几分钟 (今日剩余 {left}/{limit})..."
    from services.sender import send_by_chat_type
    await send_by_chat_type(tip, chat_id, is_group, user_id)

    # 解析参数
    prompt_parts = []
    size_w, size_h = 1152, 768
    num_frames = 241
    frame_rate = 24
    for a in args:
        al = a.lower()
        if "x" in a and al.replace("x", "").isdigit():
            parts = a.split("x")
            size_w, size_h = int(parts[0]), int(parts[1])
        elif al.isdigit():
            val = int(al)
            if val > 50:
                num_frames = val
            else:
                frame_rate = val
        else:
            prompt_parts.append(a)
    prompt = " ".join(prompt_parts) if prompt_parts else " ".join(args)

    # 后台生成，不阻塞聊天
    asyncio.create_task(_bg_gen_video(
        user_id, group_id, is_group, prompt,
        width=size_w, height=size_h,
        num_frames=num_frames, frame_rate=frame_rate,
    ))
    return f"视频生成任务已提交喵~ (今日剩余 {left}/{limit}) 好了会 @你"


async def cmd_img2video(args, user_id, group_id, sender_name, is_group, bot_qq, raw_message=""):
    """
    /~img2video <图片URL>  将图片转为视频
    /~img2video <图片URL> 512x512  指定尺寸
    /~img2video help       查看详细帮助
    """
    from utils.format_lang import format_lang
    if args and args[0].lower() == "help":
        return format_lang("help.detail.img2video")
    if not args:
        return "用法: /~img2video <图片URL> [描述] [尺寸]\n/~img2video help 查看完整参数"

    # 配额检查（不扣量）
    ok, left, limit = check_and_use_video(user_id)
    if not ok:
        return f"今日视频次数已用完喵~ ({limit}/{limit})，明天再来吧！"

    chat_id = group_id if is_group else user_id
    tip = f"正在图生视频喵~ 需要几分钟 (今日剩余 {left}/{limit})..."
    from services.sender import send_by_chat_type
    await send_by_chat_type(tip, chat_id, is_group, user_id)

    prompt_parts = []
    img_url = ""
    size_w, size_h = 1152, 768
    for a in args:
        al = a.lower()
        if a.startswith("http"):
            img_url = a
        elif "x" in a and al.replace("x", "").isdigit():
            parts = a.split("x")
            size_w, size_h = int(parts[0]), int(parts[1])
        else:
            prompt_parts.append(a)
    prompt = " ".join(prompt_parts)

    # 没有提供 URL → 尝试从引用/原始消息中提取图片URL
    if not img_url and raw_message:
        import re as _re
        m = _re.search(r'\[CQ:image[^\]]*url=([^,\]]+)', raw_message)
        if not m:
            m = _re.search(r'http[^\s,\]]+\.(?:png|jpg|jpeg|gif|webp)(?:\?[^\s,\]]*)?', raw_message, _re.I)
        if m:
            img_url = m.group(1) if m.lastindex else m.group(0)

    if not img_url:
        return "需要提供图片URL喵~\n用法: /~img2video <图片URL> [描述] [尺寸]\n也可以引用/回复一张图片，然后 /~img2video\n/~img2video help 查看完整参数"

    asyncio.create_task(_bg_gen_video(
        user_id, group_id, is_group, prompt,
        image_url=img_url, width=size_w, height=size_h,
    ))
    return f"图生视频任务已提交喵~ (今日剩余 {left}/{limit}) 好了会 @你"
