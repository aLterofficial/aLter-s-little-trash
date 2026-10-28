# -*- coding: utf-8 -*-
"""测真实 FC 调用的延迟：thinking 开/关 + 带工具 + 长上下文。"""
import os
import sys
import time

sys.path.insert(0, r'D:\QQBot\huanmeng')
os.chdir(r'D:\QQBot\huanmeng')
from dotenv import load_dotenv
load_dotenv(r'D:\QQBot\huanmeng\config\.env', override=True)
from openai import OpenAI

KEY = os.getenv('RELAY_KEY')
URL = os.getenv('RELAY_URL')
MODEL = 'deepseek/deepseek-v4.1-flash'

TOOLS = [{
    "type": "function",
    "function": {
        "name": "note",
        "description": "维护笔记本",
        "parameters": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
}, {
    "type": "function",
    "function": {
        "name": "search",
        "description": "联网搜索",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}]

# 模拟一份真实规模的上下文（约 3000 字）
LONG = ('主人：今天在写嵌入式，STM32 的 GPIO 配置卡了好久。\n'
        '大肥鱼：主人又卡住啦～要不要人家帮你理一下寄存器？\n') * 30


def run(tag, thinking, tools, ctx_len_label):
    body = {
        'model': MODEL,
        'max_tokens': 1000,
        'temperature': 0.4,
        'messages': [
            {'role': 'system', 'content': '你是大肥鱼，蓝发女仆装鲸鱼娘，说话用「喵」结尾。★★★ 必须输出 JSON：{"replies":["..."],"fav":0} ★★★'},
            {'role': 'user', 'content': LONG + '\n当前消息：主人：然后呢'},
        ],
    }
    if tools:
        body['tools'] = TOOLS
    if thinking is not None:
        body['extra_body'] = {'thinking': {'type': 'enabled' if thinking else 'disabled'}}
    c = OpenAI(api_key=KEY, base_url=URL, timeout=120, max_retries=0)
    t0 = time.time()
    try:
        r = c.chat.completions.create(**body)
        dt = time.time() - t0
        msg = r.choices[0].message
        rc = getattr(msg, 'reasoning_content', '') or ''
        tc = len(getattr(msg, 'tool_calls', []) or [])
        txt = (msg.content or '')
        print('  %-22s %6.1fs  输出%4d字 推理%4d字 tools=%d  %s'
              % (tag, dt, len(txt), len(rc), tc, 'JSON✅' if txt.strip().startswith('{') else '非JSON'))
    except Exception as e:
        print('  %-22s %6.1fs  ❌ %s: %s' % (tag, time.time() - t0, type(e).__name__, str(e)[:100]))


print('  === 延迟实测（上下文约 %d 字）===' % len(LONG))
run('无工具/thinking关', False, False, '')
run('无工具/thinking开', True, False, '')
run('带工具/thinking关', False, True, '')
run('带工具/thinking开', True, True, '')
