"""
图片识别 API 服务（原 llm/Image_recognition.py）
- ✅ 使用异步 httpx 下载图片（不再阻塞事件循环）
- 图片 MD5 缓存（带条目上限 + TTL 过期）
- 调用视觉 LLM 生成图片描述
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI

from core.logger import get_logger
from core.config import get_config, ModelConfig
from utils.format_lang import format_lang

logger = get_logger("image_api")

# ── 缓存配置 ────────────────────────────────────────────────
_CACHE_DIR = Path(__file__).resolve().parent.parent / "data"
_CACHE_FILE = _CACHE_DIR / "Image_description_cache.txt"
_CACHE_MAX_ENTRIES = 1000      # 最大缓存条数
_CACHE_TTL_SECONDS = 30 * 24 * 3600  # 30 天过期


class ImageCache:
    """带容量限制和 TTL 的图片描述缓存"""
    
    def __init__(self, cache_path: Path = _CACHE_FILE):
        self.cache_path = cache_path
        self._cache: dict[str, any] = {}
        self._dirty = False
        self._load()

    def _load(self):
        """从文件加载缓存"""
        if not self.cache_path.exists():
            return
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                if os.path.getsize(self.cache_path) > 0:
                    self._cache = json.load(f)
            logger.debug("图片缓存已加载: %d 条", len(self._cache))
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("缓存文件损坏或不可读: %s, 将从空缓存开始", e)
            self._cache = {}

    def _save(self):
        """保存缓存到文件（仅脏标记为 True 时才写盘）"""
        if not self._dirty:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=4)
            self._dirty = False
            logger.debug("图片缓存已写入磁盘: %d 条", len(self._cache))
        except Exception as e:
            logger.error("写入缓存文件失败: %s", e)

    def get(self, md5_hash: str) -> Optional[str]:
        """
        查询缓存。命中时返回描述文本，未命中返回 None。
        同时检查 TTL 过期。
        """
        import time
        entry = self._cache.get(md5_hash)
        if entry is None:
            return None
        
        timestamp = entry.get("t", 0)
        if time.time() - timestamp > _CACHE_TTL_SECONDS:
            del self._cache[md5_hash]
            self._dirty = True
            logger.debug("缓存过期(MD5=%s...)", md5_hash[:12])
            return None
        
        desc = entry.get("desc", "")
        logger.info("图片识别缓存命中 MD5=%s... → '%s...'", md5_hash[:12], desc[:40])
        return desc

    def set(self, md5_hash: str, description: str):
        """写入缓存，超限时淘汰最旧条目"""
        import time
        
        # 容量限制：超过上限时删除最旧的 20%
        if len(self._cache) >= _CACHE_MAX_ENTRIES:
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1].get("t", 0),
            )
            remove_count = max(1, len(sorted_entries) // 5)
            for k, _ in sorted_entries[:remove_count]:
                del self._cache[k]
            logger.debug("缓存清理: 移除 %d 条旧数据 (当前 %d 条)",
                       remove_count, len(self._cache))

        self._cache[md5_hash] = {
            "desc": description,
            "t": time.time(),
        }
        self._dirty = True
        self._save()

    def flush(self):
        """强制刷盘"""
        self._save()


# ── 全局缓存实例 ────────────────────────────────────────────
_image_cache: Optional[ImageCache] = None


def _get_cache() -> ImageCache:
    global _image_cache
    if _image_cache is None:
        _image_cache = ImageCache()
    return _image_cache


# ── 动图（GIF / 动图 WebP）多帧合成 ──────────────────────────
# ★ 2026-10-04 新增。
# 问题：`PIL.Image.open()` 默认**停在第 0 帧**，直接 `save()` 只会得到第一帧 ——
#   动图的动作/表情变化全部丢失。原实现正是如此，所以机器人"看 GIF"其实只看了一帧。
# 方案：均匀抽取 ≤max_frames 帧（含首尾），按阅读顺序拼成一张网格图，
#   每格左上角标序号，再交给视觉模型 —— 一张图就能看出"动作怎么变的"，
#   且只花**一次**视觉调用的 token（比发多张图便宜）。
def _fit_into_cell(img, cell: int, PILImage):
    """等比缩放到不超过 cell×cell 的方框内（contain，不裁剪）。"""
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    scale = min(cell / w, cell / h, 1.0)
    if scale < 1.0:
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), PILImage.LANCZOS)
    return img


def _compose_animated_frames(_img, max_frames: int = 6, cols: int = 3, cell: int = 320, gap: int = 6):
    """把动图若干帧拼成一张网格图。

    Returns:
        (PIL.Image, 实际帧数)；**非动图或取帧失败返回 (None, 0)** → 调用方走原来的单帧路径。
    """
    try:
        n = int(getattr(_img, "n_frames", 1) or 1)
    except Exception:
        return None, 0
    if n <= 1:
        return None, 0

    if n <= max_frames:
        idxs = list(range(n))
    else:
        idxs = sorted({int(round(i * (n - 1) / (max_frames - 1))) for i in range(max_frames)})

    import io as _io
    from PIL import Image as _PILImage
    from PIL import ImageDraw as _ImageDraw

    frames = []
    for i in idxs:
        try:
            _img.seek(i)
            frames.append(_fit_into_cell(_img.convert("RGB").copy(), cell, _PILImage))
        except Exception:
            break
    if len(frames) < 2:
        return None, 0

    rows = (len(frames) + cols - 1) // cols
    w = cols * cell + (cols - 1) * gap
    h = rows * cell + (rows - 1) * gap
    canvas = _PILImage.new("RGB", (w, h), (24, 24, 24))
    draw = _ImageDraw.Draw(canvas)
    for k, fr in enumerate(frames):
        r, c = divmod(k, cols)
        x = c * (cell + gap)
        y = r * (cell + gap)
        canvas.paste(fr, (x + (cell - fr.width) // 2, y + (cell - fr.height) // 2))
        # 序号底色：便于模型理解"这是第几帧 / 时间顺序"
        draw.rectangle([x, y, x + 20, y + 15], fill=(0, 0, 0))
        draw.text((x + 6, y + 2), str(k + 1), fill=(255, 255, 255))
    return canvas, len(frames)


# ── 公共 API ────────────────────────────────────────────────

async def recognize_image(image_url: str, image_model: ModelConfig, chat_id: int = 0,
                          image_bytes: bytes | None = None,
                          prompt_override: str | None = None,
                          use_cache: bool = True) -> str:
    """
    识别图片并返回文字描述。
    
    流程：
    1. 用 httpx 异步下载图片
    2. 计算 MD5，查缓存
    3. 缓存未命中时调用视觉 LLM
    4. 写入缓存
    
    Args:
        image_url: 图片 URL
        image_model: 视觉模型配置
        image_bytes: **本地图片字节**（★ 2026-10-04 新增）。传了就**跳过下载**——
            用于本机截图这类"没有 URL"的场景（httpx 不支持 file://）。
        prompt_override: 覆盖默认识别提示词（截图场景需要不同的问法）
        use_cache: 是否读写 MD5 缓存。截图每次都不同，缓存无用且会撑大仓库 → 传 False
        
    Returns:
        图片描述文字
    """
    cache = _get_cache()
    
    # ── Step 1: 取图片内容（本地字节优先，否则下载）──
    if image_bytes is not None:
        image_content = image_bytes
        logger.info("[chat=%d] 使用传入的本地图片: %d bytes", chat_id, len(image_content))
    else:
        logger.info("[chat=%d] 开始下载图片: %s...", chat_id, image_url[:60])
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(image_url)
                if resp.status_code != 200:
                    raise Exception(f"HTTP {resp.status_code}")
                image_content = resp.content
            logger.info("[chat=%d] 图片下载成功: %d bytes", chat_id, len(image_content))
        except Exception as e:
            logger.error("图片下载失败: %s", e)
            raise Exception(f"图片下载失败: {e}")

    # ── Step 2: 计算哈希 + 查缓存 ──
    md5_hex = hashlib.md5(image_content).hexdigest()
    if use_cache:
        cached_desc = cache.get(md5_hex)
        if cached_desc is not None:
            return cached_desc

    # ── Step 3: 调用视觉 LLM ──
    logger.info("[chat=%d] 调用视觉模型识别图片 (MD5=%s...) model=%s", chat_id, md5_hex[:12], image_model.name)
    try:
        client = OpenAI(api_key=image_model.key, base_url=image_model.url, timeout=20.0)
        
        # 构建提示词（支持 i18n；prompt_override 优先 —— 截图场景需要不同问法）
        # ★ 明确要求直接输出，禁推理过程（Qwen3.5-4B 等推理模型会把内容塞 reasoning_content）
        prompt_text = prompt_override or format_lang(
            "image.recognition_prompt",
            default="请直接描写图片中的内容，不要输出任何推理或思考过程。若你认为这张图片可能是用于表达情绪的表情包，这时请着重输出他表达的情绪元素（其他的也要有，但是情绪元素至少有4点）。直接输出描述，不超过70字。",
        )
        
        # ── 图片预处理：PIL 转 PNG + 大图压缩 ──
        import io as _io
        from PIL import Image as _PILImage
        _preprocessed = image_content  # 默认不转换
        _n_frames = 0                  # >1 表示这是动图合成出来的多帧网格
        try:
            _img = _PILImage.open(_io.BytesIO(image_content))
            _orig_fmt = _img.format or "?"
            _orig_size = _img.size
            # ★ 动图先做多帧合成（否则下面的 save 只会拿到第一帧）
            _anim, _n_frames = _compose_animated_frames(_img)
            if _anim is not None:
                logger.info("[chat=%d] 动图多帧合成: %d 帧 → 网格 %s（原 %s）",
                            chat_id, _n_frames, f"{_anim.size[0]}x{_anim.size[1]}", f"{_orig_size[0]}x{_orig_size[1]}")
                _img = _anim
            # 转 RGB（处理 RGBA/P/CMYK 等模式）
            if _img.mode not in ("RGB", "L"):
                _img = _img.convert("RGB")
            # 大图缩放：长边 > 2048 等比缩小
            _max_dim = 2048
            if max(_img.size) > _max_dim:
                _ratio = _max_dim / max(_img.size)
                _new_size = (int(_img.size[0] * _ratio), int(_img.size[1] * _ratio))
                _img = _img.resize(_new_size, _PILImage.LANCZOS)
            # 输出为 PNG 字节
            _buf = _io.BytesIO()
            _img.save(_buf, format="PNG", optimize=True)
            _preprocessed = _buf.getvalue()
            logger.info("[chat=%d] 图片预处理: %s(%s) → PNG %d bytes → %d bytes",
                       chat_id, _orig_fmt, f"{_orig_size[0]}x{_orig_size[1]}",
                       len(image_content), len(_preprocessed))
        except Exception as _e:
            logger.warning("[chat=%d] PIL预处理跳过: %s, 使用原始数据", chat_id, _e)

        # ★ 动图网格：必须告诉模型这是"连续帧"，否则它会当成一张普通拼图，
        #   只描述画面而说不出动作变化 —— 那就白合成了。
        if _n_frames > 1:
            prompt_text += (
                "\n【注意】这张图是**同一段动图的连续帧网格**（每格左上角数字是帧序号，"
                "按从左到右、从上到下的时间顺序排列）。请优先描述**动作是怎么变化的**"
                "（从第 1 帧到最后一帧发生了什么），不要只描述某一帧的静态画面。"
            )

        # 异步包装，避免阻塞事件循环
        import base64 as _b64
        b64 = _b64.b64encode(_preprocessed).decode()
        data_uri = f"data:image/png;base64,{b64}"
        loop = asyncio.get_running_loop()
        response = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=image_model.name,
                    max_tokens=300,
                    temperature=0.3,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {"type": "image_url", "image_url": {"url": data_uri}},
                            ],
                        },
                    ],
                    stream=False,
                    # ★ 关思考（与 llm.py:1207 的短判断调用对齐）。不关的话推理模型会把
                    # 答案全塞进 reasoning_content、content 返回空 → 触发下方"从推理链
                    # 提取描述"兜底 → 把模型复述提示词的独白当成描述存下（再被 [:200]
                    # 截断），并被 MD5 永久缓存，同一张图以后每次都返回这段垃圾。
                    extra_body={"thinking": {"type": "disabled"}},
                ),
            ),
            timeout=25.0,
        )
        import re as _re
        msg = response.choices[0].message
        # 优先从独立 reasoning_content 字段取推理链
        reasoning = getattr(msg, "reasoning_content", "") or ""
        description = msg.content or ""
        # 智谱视觉 Thinking 模型的 content 可能内嵌 <think>...</think> 标签
        think_stripped = _re.sub(r'<\s*think\s*>.*?<\s*/\s*think\s*>', '', description, flags=_re.DOTALL | _re.IGNORECASE).strip()
        if think_stripped and think_stripped != description:
            logger.debug("[chat=%d] 剥离 %d 字符的 <think> 块", chat_id, len(description) - len(think_stripped))
            description = think_stripped
        if reasoning:
            logger.debug("[chat=%d] 推理链 reasoning_content (%d chars): %s...", chat_id, len(reasoning), reasoning[:100])
            # ★ 兜底：content 空但 reasoning 有内容时（推理模型），从 reasoning 提取描述
            if not description.strip():
                import re as _re2
                _cleaned = _re2.sub(r'^\s*\d+\.\s*\*\*[^*]*\*\*：?\s*', '', reasoning)
                _cleaned = _re2.sub(r'^\s*[\-\*]\s*', '', _cleaned, flags=_re2.MULTILINE)
                _cleaned = _cleaned.strip().replace("\n", " ")
                if _cleaned:
                    description = _cleaned[:200]
                    logger.info("[chat=%d] 从推理链提取描述 (model=%s): %s...", chat_id, image_model.name, description[:50])
        logger.info("[chat=%d] 图片识别成功 (model=%s): %s...", chat_id, image_model.name, description[:50])

    except asyncio.TimeoutError:
        logger.error("图片识别超时(25s), model=%s, MD5=%s...", image_model.name, md5_hex[:12])
        raise Exception(f"图片识别超时(25s), model={image_model.name}")
    except Exception as e:
        logger.error("图片识别失败: %s (model=%s)", e, image_model.name)
        raise Exception(f"图片识别失败: {e}")

    # ── Step 4: 写入缓存（空描述不缓存）──
    # ★ use_cache=False（如本机截图）：既不读也不写 —— 截图每张都不同，
    #   写缓存只会把 image_repo.jsonl 撑大，且下次永远不会命中。
    if not use_cache:
        logger.debug("[chat=%d] use_cache=False，跳过缓存与仓库写入", chat_id)
        return description
    if description and description.strip():
        cache.set(md5_hex, description.strip())
        # ★ 写入图片仓库
        _save_to_repo(md5_hex, description.strip(), author="", chat_id=0)
    else:
        logger.warning("图片识别结果为空，不缓存 (MD5=%s... model=%s)", md5_hex[:12], image_model.name)
    return description


# ════════════════════════════════════════════════════════════
#  图片仓库（JSONL 持久化，hash → 描述）
# ════════════════════════════════════════════════════════════

_REPO_FILE = _CACHE_DIR / "image_repo.jsonl"


def _save_to_repo(md5_hex: str, description: str, author: str = "", chat_id: int = 0):
    """写入图片描述到仓库（去重）"""
    try:
        import time as _time
        # 去重检查：如果已有相同 md5 则不重复写入
        existing = _load_repo()
        if md5_hex in existing:
            return
        entry = {
            "md5": md5_hex,
            "desc": description,
            "author": author[:30],
            "chat_id": chat_id,
            "time": _time.time(),
        }
        with open(_REPO_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.debug("图片仓库追加: MD5=%s... → '%s'", md5_hex[:12], description[:30])
    except Exception as e:
        logger.warning("图片仓库写入失败: %s", e)


def _load_repo() -> dict[str, dict]:
    """加载图片仓库，返回 {md5: {desc, author, time, chat_id}}"""
    repo: dict[str, dict] = {}
    if not _REPO_FILE.exists():
        return repo
    try:
        for line in _REPO_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            repo[entry["md5"]] = entry
    except Exception:
        pass
    return repo


async def save_image_description(
    md5_hex: str,
    description: str,
    author: str = "",
    chat_id: int = 0,
):
    """供外部调用的异步保存接口"""
    _save_to_repo(md5_hex, description, author=author, chat_id=chat_id)


def lookup_image_description(keyword: str) -> list[dict]:
    """
    按描述关键词搜索图片仓库，返回匹配条目列表。
    也支持按 MD5 精确查找。
    """
    repo = _load_repo()
    kw = keyword.lower()
    results = []
    for md5, entry in repo.items():
        desc = entry.get("desc", "").lower()
        if kw in desc or kw in md5.lower():
            results.append(entry)
    # 按时间倒序
    results.sort(key=lambda e: e.get("time", 0), reverse=True)
    return results[:5]


def get_recent_image_descriptions(chat_id: int = 0, limit: int = 3) -> list[dict]:
    """获取指定对话的最近图片描述（chat_id=0 返回全局最近）"""
    repo = _load_repo()
    if chat_id:
        items = [e for e in repo.values() if e.get("chat_id") == chat_id]
    else:
        items = list(repo.values())
    items.sort(key=lambda e: e.get("time", 0), reverse=True)
    return items[:limit]
