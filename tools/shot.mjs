/**
 * 通过 CDP 对页面截图 + 抓取正文文本（免依赖，Node 22 自带 fetch / WebSocket）。
 *
 * 用法（通常直接跑 tools/shot.sh，它负责拉起和关闭 Chrome）：
 *   # 1) 手动启动 Chrome（headless + 调试端口），路径换成你自己的 chrome.exe
 *   chrome --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
 *     --remote-debugging-port=9222 --user-data-dir=/tmp/cprof about:blank
 *
 *   # 2) 截图
 *   node tools/shot.mjs <url> <out.png> [--width 1440] [--height 1000] [--wait 2500] [--text out.txt]
 */
import fs from 'node:fs/promises'

const args = process.argv.slice(2)
const url = args[0]
const out = args[1]
if (!url || !out) {
  console.error('用法: node tools/shot.mjs <url> <out.png> [--width n] [--height n] [--wait ms] [--text file]')
  process.exit(1)
}
const opt = (name, def) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 ? args[i + 1] : def
}
const width = Number(opt('width', 1440))
const height = Number(opt('height', 1000))
const waitMs = Number(opt('wait', 2500))
const textOut = opt('text', null)
const jsExpr = opt('js', null)
const fullPage = args.includes('--full')
const port = Number(opt('port', 9222))
const CDP = `http://127.0.0.1:${port}`

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function newTarget(targetUrl) {
  const res = await fetch(`${CDP}/json/new?${encodeURIComponent(targetUrl)}`, { method: 'PUT' })
  if (!res.ok) throw new Error(`/json/new 失败: ${res.status} ${await res.text()}`)
  return res.json()
}

class Conn {
  constructor(ws) {
    this.ws = ws
    this.id = 0
    this.pending = new Map()
    this.listeners = []
    ws.addEventListener('message', (event) => {
      const msg = JSON.parse(event.data)
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id)
        this.pending.delete(msg.id)
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result)
      } else if (msg.method) {
        for (const fn of this.listeners) fn(msg)
      }
    })
  }

  send(method, params = {}) {
    const id = ++this.id
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      this.ws.send(JSON.stringify({ id, method, params }))
      setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id)
          reject(new Error(`CDP 超时: ${method}`))
        }
      }, 30000)
    })
  }

  once(method, timeout = 20000) {
    return new Promise((resolve) => {
      const fn = (msg) => {
        if (msg.method === method) {
          this.listeners = this.listeners.filter((f) => f !== fn)
          resolve(msg.params)
        }
      }
      this.listeners.push(fn)
      setTimeout(() => {
        this.listeners = this.listeners.filter((f) => f !== fn)
        resolve(null)
      }, timeout)
    })
  }
}

const target = await newTarget('about:blank')
const ws = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve)
  ws.addEventListener('error', reject)
})
const conn = new Conn(ws)

await conn.send('Page.enable')
await conn.send('Runtime.enable')
await conn.send('Emulation.setDeviceMetricsOverride', {
  width,
  height,
  deviceScaleFactor: 2,
  mobile: false,
})

const loaded = conn.once('Page.loadEventFired', 20000)
await conn.send('Page.navigate', { url })
await loaded
await sleep(waitMs)

// 可选：截图前在页面里执行一段 JS（例如拖动滑杆、点击按钮后再截图）
if (jsExpr) {
  const r = await conn.send('Runtime.evaluate', { expression: jsExpr, returnByValue: true, awaitPromise: true })
  console.log('js ->', String(JSON.stringify(r?.result?.value) ?? 'undefined').slice(0, 300))
  await sleep(400)
}

const shot = await conn.send('Page.captureScreenshot', {
  format: 'png',
  captureBeyondViewport: fullPage,
})
await fs.writeFile(out, Buffer.from(shot.data, 'base64'))
console.log(`screenshot -> ${out}`)

const evalRes = await conn.send('Runtime.evaluate', {
  expression: 'document.body.innerText',
  returnByValue: true,
})
const text = evalRes?.result?.value || ''
if (textOut) {
  await fs.writeFile(textOut, text, 'utf8')
  console.log(`text -> ${textOut} (${text.length} 字符)`)
} else {
  console.log('--- innerText ---')
  console.log(text.slice(0, 4000))
}

const errors = await conn.send('Runtime.evaluate', {
  expression: 'window.__vueErrors ? JSON.stringify(window.__vueErrors) : "none"',
  returnByValue: true,
})
console.log('vue errors:', errors?.result?.value)

ws.close()
await fetch(`${CDP}/json/close/${target.id}`).catch(() => {})
process.exit(0)
