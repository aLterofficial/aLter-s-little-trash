# -*- coding: utf-8 -*-
"""验证：ignore_unmentioned 的群里，戳一戳是否被真正拦住。

做法：合成 poke 事件直接调用 Dispatcher._handle_notice；
把 handle_poke_event 打桩（记录是否被调用），避免真的发消息/调 LLM。
"""
import asyncio
import os
import sys

sys.path.insert(0, r'D:\QQBot\huanmeng')
os.chdir(r'D:\QQBot\huanmeng')

from core.config import get_config
import core.dispatcher as D

cfg = get_config()
BOT = int(cfg.bot_qq)
GATED = <GROUP_5>          # 已设 ignore_unmentioned
NORMAL = <GROUP_1>         # 普通群

calls = []


def fake_poke(**kw):
    calls.append(kw)

async def noop_poke(**kw):
    calls.append(kw)


D.handle_poke_event = noop_poke      # 打桩

# 用一个不经 __init__ 的实例（闸之前用不到任何 self 状态）
disp = object.__new__(D.EventDispatcher)


def make_event(gid):
    return {
        "notice_type": "notify",
        "sub_type": "poke",
        "target_id": BOT,           # 戳的是 bot
        "user_id": 123456789,
        "group_id": gid,
    }


def run(gid, label, expect_blocked):
    calls.clear()
    try:
        asyncio.run(D.EventDispatcher._handle_notice(disp, make_event(gid)))
        err = None
    except Exception as e:
        err = e
    blocked = len(calls) == 0
    ok = (blocked == expect_blocked) and err is None
    print('  %s %-22s 群=%-12s 预期%s → 实际%s%s'
          % ('✅' if ok else '❌', label, gid,
             '拦住' if expect_blocked else '放行',
             '拦住' if blocked else '放行',
             ('  异常:%s' % type(err).__name__) if err else ''))


print('  配置：900...<GROUP_5> 的 ignore_unmentioned =',
      cfg.group_settings.get(GATED, {}).get('ignore_unmentioned'))
print()
run(GATED, '只看@的群：戳一戳', True)
run(NORMAL, '普通群：戳一戳', False)
