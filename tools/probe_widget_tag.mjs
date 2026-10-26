// 判定小鲸鱼账本里的 accountTag 来自哪条取数路径
//   API Key 路径 : sha256(<key>)            slice(0,24)
//   官方账号路径 : sha256('dsh-account:'+id) slice(0,24)
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

const LEDGER = 'C:/Users/Lenovo/.dsh/.dshw-usage.json'
const h = (s) => createHash('sha256').update(s).digest('hex').slice(0, 24)

const led = JSON.parse(readFileSync(LEDGER, 'utf8'))
const active = led?.accounting?.active || '(无)'
console.log('账本 accounting.active =', active)

// 当前 DEEPSEEK_API_KEY（= 中转站 key）会算出的 tag
const env = readFileSync('D:/QQBot/huanmeng/config/.env', 'utf8')
const relayKey = env.split(/\r?\n/).find((l) => l.startsWith('RELAY_KEY='))?.split('=')[1].trim() || ''
console.log('sha256(当前中转站Key)[:24] =', h(relayKey))

// 官方账号路径的可能取值
const candidates = {
  'dsh-account:default': h('dsh-account:default'),
}
for (const [label, v] of Object.entries(candidates)) {
  console.log(`sha256(${label})[:24] =`, v)
}

console.log('')
console.log('结论:')
const prefix = active.replace(/-CNY$/, '')
if (prefix === h(relayKey)) console.log('  → 账本来自【API Key 路径】（即当时用的是官方 Key）')
else if (prefix === h('dsh-account:default')) console.log('  → 账本来自【DSH 官方账号路径】（未登录时回退的固定标识）')
else console.log('  → 来自【官方账号路径 + 真实 accountId】(dsh-account:<某个id>)，说明你的 DSH 确实登录了 DeepSeek 账号')
