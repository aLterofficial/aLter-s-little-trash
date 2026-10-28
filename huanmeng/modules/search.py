"""
搜索模块（从 commands.py 抽离）
- DeepSeek Responses API 原生搜索（优先）
- Agent 多源搜索（百度+Bing+深度抓取，回退）
- 本地搜索器（终版回退）
- 搜索缓存集成
"""

from __future__ import annotations

import asyncio
import re
from typing import Optional

import httpx

from core.logger import get_logger
from modules.judge import get_cached_search, set_search_cache, is_realtime_query, keyword_need_search
from utils.format_lang import format_lang

logger = get_logger("search")


def _is_continuation(query: str) -> bool:
    """判断 query 是否为"承接前文"的短句（自身无实体词/事实对象）。

    命中"搜搜看吧?/去查查/再搜下/帮我查下/是吗"这类无实体词承接句时，搜索必须
    依赖上下文补主题，否则搜了个寂寞。凡含明确实体语义的搜索词都不算承接句。
    """
    q = (query or "").strip()
    if len(q) > 8:
        return False
    # 纯动作/疑问承接，无事实对象
    continuation = (
        "搜搜", "搜下", "搜一搜", "去搜", "再搜", "帮我搜", "搜搜看", "去查",
        "查查", "查下", "查一查", "帮你查", "查查看", "查一下",
        "是吧", "是吗", "真的吗", "真的假", "对不对", "对吧", "看看", "查吗",
    )
    return any(k in q for k in continuation)


async def perform_search(
    query: str,
    sender_name: str = "",
    user_id: int = 0,
    chat_id: int = 0,
    limit: int = 4,
    source: str = "all",
    is_group: bool = False,
    context: str = "",
) -> Optional[str]:
    """
    执行搜索：缓存 → Agent级搜索（百度+bing+百科并行）→ 格式化 → 写缓存/记忆。

    context：最近对话上下文（可选）。当 query 是承接句（如"搜搜看吧?")自身无实体词时，
    用于给 DeepSeek 搜索补充"搜什么"的主题上下文，避免搜到无关内容或搜了个寂寞。
    """
    # 承接句无实体词：把前文并入 query 前缀
    if context and len(query.strip()) <= 8 and _is_continuation(query):
        merged = f"{context[:200]} | 聚焦搜索：{query}"
        logger.info("搜索承接句，合并上下文补主题: query=%r → %r", query[:30], merged[:80])
        query = merged
    # ── Step 1: 缓存命中检查 ──
    cached = get_cached_search(query)
    if cached:
        logger.info("搜索缓存命中: '%s...'", query[:30])
        return cached

    from services.sender import send_by_chat_type
    search_tip = f"🔍 web_search ['{query[:60]}{'…' if len(query)>60 else ''}']"

    # ── Step 2: DeepSeek Responses API 原生搜索（优先）──
    logger.info("执行 DeepSeek 原生搜索: '%s...' (user=%s)", query[:40], sender_name)
    result_text = None
    try:
        from modules.web_search import ds_native_search
        result_text = await asyncio.wait_for(ds_native_search(query), timeout=45.0)
    except asyncio.TimeoutError:
        logger.warning("DeepSeek 原生搜索超时，回退 Agent 搜索")
    except Exception as e:
        logger.warning("DeepSeek 原生搜索异常: %s，回退 Agent 搜索", e)

    # ── Step 3: 回退链：Agent 多源 → 本地多源 ──────────────────
    # ★ 2026-10-01 修复（重要）：原代码这一段注释写着「Agent 搜索（回退）」，
    #   但正文只有 `return "暂无搜索结果。"` —— **根本没调用任何回退实现**。
    #   而上一级的 DeepSeek 原生搜索走官方 `api.deepseek.com/responses` + 环境变量
    #   `DEEPSEEK_KEY`；本部署走中转站、该 key 为空 → 必然抛异常。
    #   两者叠加的结果：search_web 永远返回"暂无搜索结果"，且每次都在日志里报一次
    #   异常（见 SESSION-LOG §4.7.18）。
    #   现在按 ds_native → agent_search（带相关性打分）→ local_search（不过门）
    #   逐级回退，任一级拿到非空结果即停。
    if not (result_text and result_text.strip()):
        try:
            from modules.web_search import agent_search
            result_text = await asyncio.to_thread(agent_search, query, limit, False)
            if result_text and result_text.strip():
                logger.info("Agent 搜索命中: %d 字符", len(result_text))
            else:
                logger.info("Agent 搜索无相关结果，继续回退本地搜索")
        except Exception as e:
            logger.warning("Agent 搜索失败: %s", e)

    if not (result_text and result_text.strip()):
        try:
            from modules.local_search import get_searcher
            # ★ 必应在本机被反爬投喂**无关结果**（2026-10-01 实测：同一查询两次分别
            #   返回"央视网"和"Office 激活工具"，而页面 title 却是正确的查询词）
            #   → 属网络侧问题，改选择器无解。百度实测多个查询全部相关。
            #   故 source="all" 时**只走百度，宁缺毋滥** —— 把无关结果当"搜索结果"
            #   发给用户，比老实说"没搜到"更糟。想强制必应：/~search bing <关键词>
            use_source = "baidu" if source == "all" else source
            result_text = await asyncio.to_thread(
                lambda: get_searcher().run_search(query, source=use_source, limit=limit)
            )
            if result_text and result_text.strip():
                logger.info("本地搜索命中: %d 字符 (source=%s)", len(result_text), use_source)
        except Exception as e:
            logger.warning("本地搜索失败: %s", e)

    if not (result_text and result_text.strip()):
        logger.info("全部搜索源均无结果: '%s...'", query[:40])
        return f"{search_tip}\n\n暂无搜索结果。"

    # 截断保护
    max_len = min(limit * 400, 3000)
    if len(result_text) > max_len:
        result_text = result_text[:max_len] + "..."

    result_text = f"{search_tip}\n\n{result_text}"
    logger.info("搜索完成: '%s...' → %d字符\n%s", query[:30], len(result_text), result_text[:800])

    # ── Step 3: 写入缓存 + 记忆 ──
    realtime = is_realtime_query(query)
    set_search_cache(query, result_text, realtime=realtime)

    if sender_name and chat_id:
        try:
            from modules.memory import save_search_memory
            await asyncio.to_thread(
                save_search_memory, query, result_text, sender_name, user_id, chat_id,
            )
        except Exception as e:
            logger.warning("写入搜索记忆失败: %s", e)

    return result_text

async def auto_search_if_needed(
    msg: str,
    sender_name: str,
    user_id: int,
    chat_id: int,
    is_group: bool = False,
    context: str = "",
) -> Optional[str]:
    """
    自动搜索：根据关键词和实时性判断是否需要搜索。
    仅对非 @ 消息生效。

    context：最近对话上下文（可选）。用于"搜搜看吧?"这类承接句补主题。
    
    Returns:
        搜索结果文本；不需要搜索时返回 None
    """
    from modules.judge import needs_search as _needs_search_judge
    
    msg_lower = msg.lower()

    # ★ 预检：用户拒搜 → 跳过（与 core/tools.py 保持一致）
    no_search_patterns = [
        r'不[要需用]搜', r'别搜', r'不[要需用]查', r'不用搜索',
        r'不[是要能].*[搜查找]', r'别[去再].*[搜查找]',
        r'你[自己]的(?:回答|想法|看法|意见|思考)',
        r'(?:不要|不想|不需要).*搜索', r'(?:而)?不是.*搜索',
        r'搜[索到]了?[什么啥]', r'不要.*[网上去]?找',
    ]
    if any(re.search(p, msg_lower) for p in no_search_patterns):
        logger.info("自动搜索跳过（用户拒搜）: '%s...'", msg[:30])
        return None

    # 快速关键词匹配
    if keyword_need_search(msg):
        logger.info("自动搜索触发（关键词）: '%s...'", msg[:30])
        return await perform_search(msg, sender_name=sender_name, user_id=user_id, chat_id=chat_id, is_group=is_group, context=context)

    # 实时话题判断
    if is_realtime_query(msg):
        logger.info("自动搜索触发（实时话题）: '%s...'", msg[:30])
        return await perform_search(msg, sender_name=sender_name, user_id=user_id, chat_id=chat_id, is_group=is_group, context=context)

    # 回退到模型判断（较慢，仅前面都没命中时）；承接句必须带上下文才能判断"搜什么"
    need_model = await _needs_search_judge(msg, context)
    if need_model:
        logger.info("自动搜索触发（模型判断）: '%s...'", msg[:30])
        return await perform_search(msg, sender_name=sender_name, user_id=user_id, chat_id=chat_id, is_group=is_group, context=context)

    return None
