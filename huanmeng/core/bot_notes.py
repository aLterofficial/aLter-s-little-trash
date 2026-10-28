"""
幻梦的笔记本 — LLM 主动维护的长期记忆

与 modules/memory.py 的区别：
- memory.py 是被动摘要（自动从群聊提取压缩）
- 本模块是主动笔记（LLM 判断值得记才写，如群内关系/称呼/约定/黑话）

存储：data/notes/<chat_id>.md，一行一条 `- [MM-DD] 内容`
上限 MAX_NOTES 条，超出自动淘汰最旧（保留文件不无限膨胀）

用法：
- LLM 通过 calls 调 note 指令写入（见 main_skill.md 笔记本规则）
- 用户可用 /~note 查看/增删
- 上下文注入见 core/pipeline.py 的 extra_info 组装
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

logger = get_logger("notes")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NOTES_DIR = DATA_DIR / "notes"

MAX_NOTES = 100          # 单群笔记上限，超出淘汰最旧

# 隐私保护：命中即拒绝写入（2026-09-11 全量语料审查发现 msglog 含群友真实住址）
_PRIVACY_PATTERNS = [
    (r"1[3-9]\d{9}", "手机号"),
    (r"\d{17}[\dXx]", "身份证号"),
    (r"\d{16,19}", "银行卡号"),
    (r"[\u4e00-\u9fa5]{2,8}(省|市)[\u4e00-\u9fa5]{0,10}(区|县|市)[\u4e00-\u9fa5A-Za-z0-9]{0,20}(路|街|道|号|室|楼|栋|小区)", "详细住址"),
]


def _privacy_kind(text: str) -> str:
    """返回命中的隐私类型，无则空串"""
    for pat, kind in _PRIVACY_PATTERNS:
        if re.search(pat, text):
            return kind
    return ""
INJECT_LIMIT = 40        # 注入上下文的最大条数（省 token，最新的优先）
LINE_MAX = 200           # 单条笔记最大长度

# ── 全局共享笔记层（★ 2026-10-04 新增）────────────────────────
# 动机：原来笔记**只在本群生效**（load_notes 的标题就是这么写的），于是
#   「主人是谁 / 机器人自己的设定 / 跨群通用的约定」记在 A 群，B 群就完全不知道，
#   换个群等于重新认识一遍 —— 用户明确要求「bot 能在群聊中共享记忆」。
#
# 做法：用一个**保留的 chat_id `_shared`**（真实 chat_id 都是纯数字，绝不冲突），
#   其内容注入到**每一个**群聊与私聊。
#
# ⚠️ 为什么不直接把各群笔记互相开放：那会让 A 群的私事漏进 B 群（隐私事故）。
#   所以全局层必须**显式写入**（args 里带 global 前缀），并沿用同一套隐私过滤。
SHARED_ID = "_shared"
SHARED_MAX_NOTES = 40    # 全局层会注入到所有会话，条数要比单群更克制
SHARED_INJECT_LIMIT = 20 # 每次注入全局层的最大条数


def _note_file(chat_id) -> Path:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    return NOTES_DIR / f"{chat_id}.md"


def _load_lines(chat_id) -> list[str]:
    f = _note_file(chat_id)
    if not f.exists():
        return []
    try:
        return [ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as e:
        logger.warning("读取笔记失败 %s: %s", chat_id, e)
        return []


def _save_lines(chat_id, lines: list[str]) -> None:
    try:
        _note_file(chat_id).write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        logger.warning("写入笔记失败 %s: %s", chat_id, e)


def add_note(chat_id, text: str) -> str:
    """追加一条笔记，返回给调用方（LLM/用户）的提示语"""
    text = (text or "").strip().replace("\n", " ")
    if not text:
        return "笔记内容为空，没记"
    if len(text) > LINE_MAX:
        text = text[:LINE_MAX] + "…"

    kind = _privacy_kind(text)
    if kind:
        logger.warning("拒绝记录疑似隐私(%s): %s", kind, text[:40])
        return f"这条含疑似{kind}，涉及隐私我就不记了"

    lines = _load_lines(chat_id)
    tag = datetime.now().strftime("%m-%d")
    entry = f"- [{tag}] {text}"

    # 完全重复的不重复记
    if any(text in ln for ln in lines):
        return f"这条已经记过了：{text}"

    lines.append(entry)
    cap = SHARED_MAX_NOTES if str(chat_id) == SHARED_ID else MAX_NOTES
    if len(lines) > cap:
        lines = lines[-cap:]
    _save_lines(chat_id, lines)
    if str(chat_id) == SHARED_ID:
        logger.info("新增笔记 chat=%s【全局共享】: %s", chat_id, text[:60])
        return f"已记到全局共享笔记本（所有群都看得到）：{text}"
    logger.info("新增笔记 chat=%s: %s", chat_id, text[:60])
    return f"已记下：{text}"


def _is_share_scope(chat_id) -> bool:
    """全局共享层**该不该注入**这个会话。

    ★ 2026-10-16 收紧。用户原话是「在**群聊**中共享记忆」，但初版实现把全局层
      注入了**所有**会话 —— 于是**别人的私聊**（<FRIEND_QQ_1> / <FRIEND_QQ_2>）里，
      机器人也能看到主人的私人事实（重载框架、学嵌入式、语音识别项目…），
      这等于把主人的私事外泄给第三方，是错误的扩散。

    现规则：**只在群聊、以及主人自己的私聊里注入**；别人的私聊不注入。
    读不到配置时**按"不注入"处理** —— 隐私优先，宁可少共享也不外泄。
    """
    try:
        from core.config import get_config
        cfg = get_config()
        cid = int(chat_id)
    except Exception:
        return False
    try:
        if cid in set(getattr(cfg, "group_list", []) or []):
            return True
        if cid == int(getattr(cfg, "admin_qq", 0) or 0):
            return True
    except Exception:
        return False
    return False


def load_notes(chat_id, limit: int = INJECT_LIMIT) -> str:
    """加载笔记文本用于注入上下文（带序号，方便 LLM 用 fix/del 精确操作）；无笔记返回空串。

    ★ 2026-10-04: 现在会拼**两段** —— 先「全局共享」（跨群通用），再「本群专属」。
    两段的序号空间**刻意分开**：全局段用 G1/G2…，本群段用 1/2…，
    这样 LLM 不会把两边序号搞混（改全局要写 "global fix G3 <新内容>"）。
    ★ 2026-10-16: 全局段**只注入群聊与主人私聊**，见 `_is_share_scope`。
    """
    parts: list[str] = []

    # ── 第一段：全局共享（群聊 + 主人私聊；别人的私聊**不注入**）──
    if str(chat_id) != SHARED_ID and _is_share_scope(chat_id):
        shared = _load_lines(SHARED_ID)
        if shared:
            total_s = len(shared)
            shown_s = shared[-min(total_s, SHARED_INJECT_LIMIT):]
            start_s = total_s - len(shown_s) + 1
            parts.append(
                f"【你的笔记本·全局共享】共 {total_s} 条（**群聊和主人的私聊都能看到**）。"
                "这里只该放**跨群通用**的事实：主人是谁、你自己的设定、通用约定与偏好；"
                "只在某个群里发生的事**不要**放这里。\n"
                "改全局某条 → args 写 \"global fix G<序号> <新内容>\"；"
                "删 → \"global del G<序号>\"；新增全局 → args 写 \"global <内容>\"：\n"
                + "\n".join(f"G{i}. {ln.lstrip('- ')}" for i, ln in enumerate(shown_s, start=start_s))
            )

    # ── 第二段：本群 / 私聊专属 ──
    lines = _load_lines(chat_id)
    if lines:
        total = len(lines)
        start = max(1, total - limit + 1)
        shown = lines[start - 1:]
        parts.append(
            f"【你的笔记本·本群专属】共 {total} 条群内信息（只在当前会话生效，其它群看不到）。"
            "新增直接写内容；改某条写 \"fix <序号> <新内容>\"；删某条写 \"del <序号>\""
            "（都通过 calls 调 note，args 填这些）：\n"
            + "\n".join(f"{i}. {ln.lstrip('- ')}" for i, ln in enumerate(shown, start=start))
        )

    return "\n\n".join(parts)


def list_notes(chat_id, scope: str = "") -> str:
    """给用户看的笔记列表（scope 用于标明是哪个群的笔记，直观确认隔离）"""
    lines = _load_lines(chat_id)
    title = f"笔记本·{scope}" if scope else "笔记本"
    if not lines:
        return f"【{title}】还是空的~ 说「记一下xxx」我就会记下来"
    out = [f"【{title}】共 {len(lines)} 条："]
    out.extend(f"{i}. {ln.lstrip('- ')}" for i, ln in enumerate(lines, 1))
    return "\n".join(out)


def delete_note(chat_id, index: int) -> str:
    """按序号删除（序号来自 list_notes，从 1 开始）"""
    lines = _load_lines(chat_id)
    if not lines:
        return "笔记本是空的"
    if index < 1 or index > len(lines):
        return f"序号超出范围（当前 {len(lines)} 条）"
    removed = lines.pop(index - 1)
    _save_lines(chat_id, lines)
    return f"已删除：{removed.lstrip('- ')}"


def update_note(chat_id, index: int, new_text: str) -> str:
    """修改第 index 条笔记（序号来自 load_notes/list_notes，从 1 开始）"""
    new_text = (new_text or "").strip().replace("\n", " ")
    if not new_text:
        return "新内容为空，没改"
    if len(new_text) > LINE_MAX:
        new_text = new_text[:LINE_MAX] + "…"

    kind = _privacy_kind(new_text)
    if kind:
        return f"新内容含疑似{kind}，涉及隐私就不改了"

    lines = _load_lines(chat_id)
    if not lines:
        return "笔记本是空的"
    if index < 1 or index > len(lines):
        return f"序号超出范围（当前 {len(lines)} 条，用 /~note 查看）"
    old = lines[index - 1].lstrip("- ")
    tag = datetime.now().strftime("%m-%d")
    lines[index - 1] = f"- [{tag}] {new_text}"
    _save_lines(chat_id, lines)
    logger.info("修改笔记 chat=%s #%d: %s → %s", chat_id, index, old[:30], new_text[:60])
    return f"已改第{index}条：{old} → {new_text}"


def clear_notes(chat_id) -> str:
    lines = _load_lines(chat_id)
    n = len(lines)
    _save_lines(chat_id, [])
    return f"已清空 {n} 条笔记"


def note_count(chat_id) -> int:
    return len(_load_lines(chat_id))


def _allowed_to_write_other(user_id, bot_qq) -> bool:
    """是否允许写**别的会话**的笔记（= 管理员）。"""
    from core.config import get_config
    cfg = get_config()
    allowed = set()
    for v in (getattr(cfg, "admin_qq", 0), bot_qq):
        try:
            if v:
                allowed.add(int(v))
        except (ValueError, TypeError):
            pass
    try:
        return int(user_id) in allowed
    except (ValueError, TypeError):
        return False


async def cmd_note(args, user_id, group_id, sender_name, is_group, bot_qq):
    """笔记本指令 /~note

    /~note                     查看本会话笔记
    /~note <内容>              手动记一条（本会话）
    /~note fix <序号> <新内容>  修改某条
    /~note del <序号>           删除某条
    /~note clear               清空（仅管理员）

    ★ 全局共享层：用法前加 `global`（或 全局/共享）→ 所有群聊与主人私聊可见
      例：/~note global 主人喜欢美式

    ★ 指定落点（2026-10-16 新增）：用法前加 `g<群号>` / `p<QQ>` / `c<会话号>`，
      把事实记到**它真正属于的会话**。写**别的**会话需要管理员权限。
      例：/~note g<GROUP_3> 群友感恩花糕经常在群里辱骂大肥鱼
          /~note p<OWNER_QQ> 主人喜欢美式
          /~note g<GROUP_1>            查看那个群的笔记
    """
    cur_chat_id = group_id if is_group else user_id
    chat_id = cur_chat_id
    scope = "本群" if is_group else "私聊"
    a = list(args or [])

    # ── 解析可选的 global 前缀 ──
    is_global = bool(a) and str(a[0]).lower() in ("global", "g", "全局", "共享", "shared")
    if is_global:
        a = a[1:]
        chat_id = SHARED_ID
        scope = "全局共享"
    elif a:
        # ── 解析可选的「指定落点」前缀 ──
        # ★ 动机：`/~note` 原本只能写**当前会话**，于是机器人在私聊里学到
        #   "关于某个群的事"时只能就近记在私聊里 —— 那条笔记在群里永远用不上
        #   （实测：`notes/<FRIEND_QQ_1>.md` 里存着"群友感恩花糕…"，
        #    而该事实真正属于群 <GROUP_3>，导致"换个地方问它知道的就不一样"）。
        # ⚠️ 写**别人**的会话必须管理员 —— 否则任何人都能污染别群的记忆。
        _m = re.match(r'^([gpc])(\d{5,12})$', str(a[0]).strip().lower())
        if _m:
            _kind, _num = _m.group(1), int(_m.group(2))
            _label = {'g': '群', 'p': '私聊', 'c': '会话'}[_kind]
            if _num != cur_chat_id and not _allowed_to_write_other(user_id, bot_qq):
                return "记到别的会话需要管理员权限喵~"
            chat_id = _num
            scope = f"{_label}{_num}"
            a = a[1:]

    if not a:
        return list_notes(chat_id, scope=scope)

    def _idx(tok) -> int | None:
        """序号容错：允许 G3 / g3 / 3 三种写法（全局段注入时用的是 G 前缀）"""
        t = str(tok).lstrip("Gg")
        return int(t) if t.isdigit() else None

    head = str(a[0]).lower()
    if head in ("del", "delete", "删除", "-"):
        n = _idx(a[1]) if len(a) >= 2 else None
        if n is None:
            return "用法: /~note del <序号>（序号用 /~note 查看）"
        return delete_note(chat_id, n)
    if head in ("fix", "edit", "改", "修改"):
        n = _idx(a[1]) if len(a) >= 2 else None
        if n is None or len(a) < 3:
            return "用法: /~note fix <序号> <新内容>（序号用 /~note 查看）"
        return update_note(chat_id, n, " ".join(a[2:]))
    if head in ("clear", "清空"):
        from core.config import get_config
        cfg = get_config()
        allowed = set()
        for v in (getattr(cfg, "admin_qq", 0), bot_qq):
            try:
                if v:
                    allowed.add(int(v))
            except (ValueError, TypeError):
                pass
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            uid = 0
        if uid not in allowed:
            return "清空笔记本需要管理员权限"
        return clear_notes(chat_id)

    # 其余情况：手动记一条
    return add_note(chat_id, " ".join(str(x) for x in a))
