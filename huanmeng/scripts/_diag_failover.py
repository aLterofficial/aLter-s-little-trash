# -*- coding: utf-8 -*-
"""实测故障转移：主通道坏掉时，是否自动切到官方 API 并成功拿到回复。"""
import asyncio
import os
import sys
import time

sys.path.insert(0, r'D:\QQBot\huanmeng')
os.chdir(r'D:\QQBot\huanmeng')
from dotenv import load_dotenv
load_dotenv(r'D:\QQBot\huanmeng\config\.env', override=True)

from core.config import ModelConfig, get_config
from services.llm import call_llm_with_tools, is_model_circuit_open, circuit_status

cfg = get_config()
MSGS = [
    {'role': 'system', 'content': '你是大肥鱼，说话用「喵」结尾。'},
    {'role': 'user', 'content': '用一句话介绍你自己'},
]

# 造一个"主通道"：地址指向一个必然拒绝连接的端口
bad = ModelConfig()
bad.name = 'deepseek/deepseek-v4.1-flash'
bad.provider = 'RELAY'
bad.url = 'http://127.0.0.1:9/v1'      # discard 端口，必失败
bad.key = 'sk-invalid'
bad.maxtoken = 300

print('=== 场景 A：主通道不可达，应自动切到官方 API ===')
t0 = time.time()
r = asyncio.run(call_llm_with_tools(bad, MSGS, [], max_tokens=120, temperature=0.4,
                                    timeout=5.0, scene='diag_failover'))
dt = time.time() - t0
print('  耗时      : %.1fs' % dt)
print('  返回内容  : %r' % (r.content or '')[:90])
print('  是否成功  : %s' % ('✅ 拿到了回复（备用通道生效）' if (r.content or '').strip() else '❌ 空'))
print('  该模型熔断: %s' % is_model_circuit_open(bad))
print('  熔断快照  : %s' % circuit_status())
