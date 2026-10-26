// qr_server.mjs - live QR viewer for NapCat login
//
// Why: relaying a static QR image through chat wastes 30-60s per round trip and the
// code only lives ~2 minutes. This serves a tiny local page that always shows the
// CURRENT NapCat QR (read straight from NapCat's cache file), auto-refreshing every
// 3 seconds, so the user can scan whenever they are ready.
//
// Routes:
//   /            auto-refreshing HTML page
//   /qr.png      current QR bytes (no-store)
//   /status.json { exists, ageSeconds, remainingSeconds, generatedAt, port8099 }
//
// No dependencies. Port 8899.

import http from 'node:http'
import { readFile, stat } from 'node:fs/promises'

const QR_PATH = 'D:\\QQBot\\NapCat\\cache\\qrcode.png'
const PORT = 8899
const VALID_MS = 123000 // NapCat rotates roughly every 2 minutes

const HTML = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>NapCat 登录二维码（实时）</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  :root { color-scheme: dark; }
  body { margin:0; min-height:100vh; display:flex; flex-direction:column;
         align-items:center; justify-content:center; gap:18px;
         background:#12121a; color:#e8e8f0;
         font:15px/1.6 "Microsoft YaHei",system-ui,sans-serif; }
  h1 { font-size:19px; margin:0; font-weight:600; letter-spacing:.5px; }
  .card { background:#fff; padding:14px; border-radius:14px;
          box-shadow:0 10px 40px rgba(0,0,0,.55); }
  img { display:block; width:264px; height:264px; image-rendering:pixelated; }
  .meta { font-size:13px; color:#9a9ab0; text-align:center; }
  .ok   { color:#4ade80; } .warn { color:#fbbf24; } .bad { color:#f87171; }
  .hint { max-width:460px; text-align:center; font-size:13px; color:#8b8ba3; }
  code { background:#22222e; padding:2px 6px; border-radius:5px; }
</style>
</head>
<body>
  <h1>NapCat 登录二维码</h1>
  <div class="card"><img id="qr" alt="二维码"></div>
  <div class="meta" id="meta">加载中…</div>
  <div class="hint">
    用<b>机器人小号</b>的手机 QQ 扫码（不要用主号）。<br>
    手机需与电脑连同一个 Wi-Fi；码每约 2 分钟自动换，本页会自动跟随，<b>看到就扫</b>。
  </div>
<script>
  const img = document.getElementById('qr');
  const meta = document.getElementById('meta');
  async function tick() {
    img.src = '/qr.png?t=' + Date.now();
    try {
      const r = await fetch('/status.json?t=' + Date.now());
      const s = await r.json();
      if (!s.exists) { meta.textContent = '等待 NapCat 生成二维码…'; meta.className = 'meta warn'; return; }
      const rem = Math.round(s.remainingSeconds);
      if (rem > 25) { meta.innerHTML = '<span class="ok">● 二维码有效</span>　剩余约 ' + rem + ' 秒'; meta.className = 'meta'; }
      else          { meta.innerHTML = '<span class="warn">● 即将过期</span>　约 ' + Math.max(rem,0) + ' 秒后自动换新码'; meta.className = 'meta'; }
      if (s.port8099) { meta.innerHTML = '<span class="ok">● 8099 已监听 —— 已登录成功，无需再扫</span>'; }
    } catch (e) { meta.textContent = '状态读取失败'; meta.className = 'meta bad'; }
  }
  tick();
  setInterval(tick, 3000);
</script>
</body>
</html>`

const server = http.createServer(async (req, res) => {
  const url = (req.url || '/').split('?')[0]

  if (url === '/qr.png') {
    try {
      const buf = await readFile(QR_PATH)
      res.writeHead(200, {
        'Content-Type': 'image/png',
        'Cache-Control': 'no-store, no-cache, must-revalidate',
        'Pragma': 'no-cache',
      })
      res.end(buf)
    } catch {
      res.writeHead(404, { 'Content-Type': 'text/plain', 'Cache-Control': 'no-store' })
      res.end('no qrcode yet')
    }
    return
  }

  if (url === '/status.json') {
    let exists = false, ageSeconds = -1, generatedAt = null
    try {
      const st = await stat(QR_PATH)
      exists = true
      ageSeconds = (Date.now() - st.mtimeMs) / 1000
      generatedAt = st.mtime.toISOString()
    } catch {}
    const port8099 = await checkPort()
    const body = JSON.stringify({
      exists,
      ageSeconds: exists ? Number(ageSeconds.toFixed(1)) : null,
      remainingSeconds: exists ? Number((VALID_MS / 1000 - ageSeconds).toFixed(1)) : 0,
      generatedAt,
      port8099,
    })
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' })
    res.end(body)
    return
  }

  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
  res.end(HTML)
})

// lightweight TCP probe for the OneBot port
import net from 'node:net'
function checkPort() {
  return new Promise((resolve) => {
    const s = net.connect({ host: '127.0.0.1', port: 8099 })
    const done = (v) => { try { s.destroy() } catch {} ; resolve(v) }
    s.setTimeout(600)
    s.once('connect', () => done(true))
    s.once('timeout', () => done(false))
    s.once('error', () => done(false))
  })
}

server.listen(PORT, '127.0.0.1', () => {
  console.log(`qr viewer ready -> http://127.0.0.1:${PORT}/`)
  console.log(`watching ${QR_PATH}`)
})
