"""本机 PC 状态采集 —— 让 `/~sys` 不再依赖那个独立的 PC 客户端。

═══ 为什么需要这个 ═══

`services/pc_status.py` 的 `_PC_DATA` 全靠一个**独立的 TCP 客户端**
（`scripts/pc_status_reporter.py`，端口 58890）上报。而本部署里它**根本没在跑**，
于是 `/~sys` 的卡片、文本状态全是空的（"暂无 PC 状态数据"）。

那套设计是给「**机器人跑在服务器、主人电脑是另一台**」的场景准备的 ——
可本部署里幻梦**就跑在主人这台电脑上**，让机器自己给自己发 TCP 上报纯属绕远路。

═══ 做法 ═══

就地在**本机**采集，并**直接复用 reporter 里的采集函数**
（该脚本有 `if __name__ == "__main__": run()` 守卫，导入无副作用），
按 `run()` 里那段组装逻辑产出**结构完全一致**的 dict ——
这样 `pc_status.py` 的卡片/文本渲染**一行都不用改**，只是数据来源从
"别人报给我"变成"我自己取"。

依赖：`psutil`（已装）、`pywin32`（窗口信息，2026-10-04 新装）、
`websocket-client`（音乐，来自 `ws://localhost:9863`，与 PC 客户端无关）。
"""

from __future__ import annotations

import importlib.util
import socket
import time
from pathlib import Path

from core.logger import get_logger

logger = get_logger("pc_local")

_REPORTER = Path(__file__).resolve().parent.parent / "scripts" / "pc_status_reporter.py"

_mod = None            # 模块缓存；False 表示加载失败（避免反复重试）
_cache: dict | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 5.0       # 采集有成本（句柄数/进程扫描），5 秒内复用


def _reporter():
    """惰性加载 reporter 模块（只加载一次）。失败返回 None。"""
    global _mod
    if _mod is not None:
        return _mod or None
    try:
        spec = importlib.util.spec_from_file_location("_pc_reporter", _REPORTER)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)          # __main__ 守卫保证不会跑 run()
        _mod = m
        logger.info("已加载本机采集模块: %s", _REPORTER.name)
        return m
    except Exception as e:
        logger.warning("加载 pc_status_reporter 失败，/~sys 将无数据: %s", e)
        _mod = False
        return None


def collect(force: bool = False) -> dict | None:
    """就地采集一份与 PC 客户端上报**结构一致**的状态 dict。失败返回 None。"""
    global _cache, _cache_ts
    now = time.time()
    if not force and _cache is not None and now - _cache_ts < _CACHE_TTL:
        return dict(_cache)

    m = _reporter()
    if m is None:
        return None

    data: dict = {"hostname": socket.gethostname()}

    # ── 前台窗口（对应 reporter run() 的 556-591 行）──
    try:
        proc_info, title, proc = m.get_window_title()
        if title:
            data["window"] = title
        if proc:
            data["app"] = proc
        if proc_info:
            data["app_detail"] = proc_info
            data["app_handles"] = proc_info.get("proc_handle_count", 0)
            data["app_mem_mb"] = round(proc_info.get("proc_mem_rss", 0) / 1048576, 1)
    except Exception as e:
        logger.debug("窗口信息采集失败: %s", e)

    # ── FPS（DWM 帧计时；首次调用通常拿不到，属正常）──
    try:
        fps = m.get_fps()
        if fps:
            data["fps"] = fps
    except Exception as e:
        logger.debug("FPS 采集失败: %s", e)

    # ── 音乐（来自本机 ws://localhost:9863 的歌词服务，与 PC 客户端无关）──
    try:
        raw = m._query_music()
        if raw and raw.get("song"):
            raw["player"] = m.detect_music_player()
            data["music"] = raw
    except Exception as e:
        logger.debug("音乐信息采集失败: %s", e)

    # ── 系统信息（psutil：CPU/内存/磁盘/网络/电池/开机时长）──
    try:
        data.update(m._get_system_info() or {})
    except Exception as e:
        logger.warning("系统信息采集失败: %s", e)

    # 至少要有点东西才算成功
    if len(data) <= 1:
        return None

    _cache, _cache_ts = data, now
    return dict(data)
