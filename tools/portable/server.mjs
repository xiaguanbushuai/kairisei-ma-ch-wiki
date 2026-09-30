#!/usr/bin/env node
/**
 * 乖离性百万亚瑟王国服资料站 —— 便携版本地服务
 *
 * 零依赖：只用 Node 内置模块，双击 start.cmd 即可运行。
 * 目录约定（相对本文件所在目录）：
 *   web/              Vite 构建产物（index.html + assets/ + data/）
 *   images/thumbs/    卡面缩略图缓存
 *   images/full/      卡面原图（可选，极简版不含；缺失时自动回落到缩略图）
 *   runtime/node.exe  便携 Node 运行时
 */
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const ROOT = path.dirname(fileURLToPath(import.meta.url))
const WEB_DIR = path.join(ROOT, 'web')
const THUMB_DIR = path.join(ROOT, 'images', 'thumbs')
const FULL_DIR = path.join(ROOT, 'images', 'full')

const HOST = '127.0.0.1'
const PORT_CANDIDATES = [5173, 5174, 5175, 5176, 5180, 8080, 8888, 0]
// 调试用：KAIRI_PORT 指定端口，KAIRI_NO_OPEN=1 不自动打开浏览器。
const FIXED_PORT = Number(process.env.KAIRI_PORT) || 0
const NO_OPEN = process.env.KAIRI_NO_OPEN === '1'

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
}

function isFile(target) {
  try {
    return fs.statSync(target).isFile()
  } catch {
    return false
  }
}

/** 拼接路径并防止 ../ 越界。 */
function safeJoin(base, rel) {
  const baseResolved = path.resolve(base)
  const target = path.resolve(baseResolved, rel)
  if (target !== baseResolved && !target.startsWith(baseResolved + path.sep)) return null
  return target
}

function send(res, file, cacheControl) {
  let stat
  try {
    stat = fs.statSync(file)
  } catch {
    return notFound(res)
  }
  const type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream'
  res.writeHead(200, {
    'Content-Type': type,
    'Content-Length': stat.size,
    'Cache-Control': cacheControl || 'no-cache',
  })
  fs.createReadStream(file).pipe(res)
}

function notFound(res) {
  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
  res.end('404 Not Found')
}

const IMG_CACHE = 'public, max-age=604800'

function handle(req, res) {
  let urlPath
  try {
    urlPath = decodeURIComponent((req.url || '/').split('?')[0])
  } catch {
    return notFound(res)
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { 'Content-Type': 'text/plain; charset=utf-8' })
    return res.end('405 Method Not Allowed')
  }

  // 缩略图：优先于 /cardimg 匹配，顺序不能反。
  if (urlPath.startsWith('/cardimg/thumb/')) {
    const file = safeJoin(THUMB_DIR, urlPath.slice('/cardimg/thumb/'.length))
    if (file && isFile(file)) return send(res, file, IMG_CACHE)
    return notFound(res)
  }

  // 原图：有就用，没有（极简版）回落到缩略图，避免详情页出现裂图。
  if (urlPath.startsWith('/cardimg/')) {
    const rel = urlPath.slice('/cardimg/'.length)
    const full = safeJoin(FULL_DIR, rel)
    if (full && isFile(full)) return send(res, full, IMG_CACHE)
    const thumb = safeJoin(THUMB_DIR, rel)
    if (thumb && isFile(thumb)) return send(res, thumb, IMG_CACHE)
    return notFound(res)
  }

  // 静态资源。
  const rel = urlPath === '/' ? 'index.html' : urlPath.replace(/^\/+/, '')
  const file = safeJoin(WEB_DIR, rel)
  if (file && isFile(file)) {
    // assets/ 下文件名带内容哈希，可永久缓存；其余不缓存以便替换数据。
    const cache = urlPath.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache'
    return send(res, file, cache)
  }

  // 兜底回落到 index.html（本项目用 hash 路由，正常不会走到这里）。
  const index = path.join(WEB_DIR, 'index.html')
  if (isFile(index)) return send(res, index, 'no-cache')
  notFound(res)
}

/** 从候选端口里挑一个能监听的，0 表示交给系统随机分配。 */
function listen(server, ports) {
  return new Promise((resolve, reject) => {
    const tryPort = (i) => {
      if (i >= ports.length) return reject(new Error('没有可用端口'))
      const port = ports[i]
      const onError = (err) => {
        if (err.code === 'EADDRINUSE' || err.code === 'EACCES') {
          server.removeListener('error', onError)
          tryPort(i + 1)
        } else {
          reject(err)
        }
      }
      server.once('error', onError)
      server.listen(port, HOST, () => {
        server.removeListener('error', onError)
        resolve(server.address().port)
      })
    }
    tryPort(0)
  })
}

function openBrowser(url) {
  if (NO_OPEN) return
  try {
    spawn('cmd', ['/c', 'start', '""', url], { detached: true, stdio: 'ignore', windowsHide: true }).unref()
  } catch {
    /* 打不开就算了，窗口里已打印地址 */
  }
}

const server = http.createServer((req, res) => {
  try {
    handle(req, res)
  } catch (err) {
    console.error('[错误]', err && err.message)
    if (!res.headersSent) res.writeHead(500, { 'Content-Type': 'text/plain; charset=utf-8' })
    res.end('500 Internal Server Error')
  }
})

if (!isFile(path.join(WEB_DIR, 'index.html'))) {
  console.error('')
  console.error('  [错误] 未找到 web/index.html，包目录可能不完整。')
  console.error('')
  process.exit(1)
}

listen(server, FIXED_PORT ? [FIXED_PORT] : PORT_CANDIDATES)
  .then((port) => {
    const url = `http://${HOST}:${port}/`
    const thumbCount = fs.existsSync(THUMB_DIR)
      ? fs.readdirSync(THUMB_DIR).reduce((sum, dir) => {
          try {
            return sum + fs.readdirSync(path.join(THUMB_DIR, dir)).length
          } catch {
            return sum
          }
        }, 0)
      : 0
    console.log('')
    console.log('  ┌──────────────────────────────────────────────┐')
    console.log('  │  乖离性百万亚瑟王国服资料站 · 便携版           │')
    console.log('  └──────────────────────────────────────────────┘')
    console.log('')
    console.log(`  地址：${url}`)
    console.log(`  图库：缩略图 ${thumbCount} 张　原图 ${isFile(path.join(FULL_DIR, '.keep')) || fs.existsSync(FULL_DIR) ? '已包含' : '未包含（自动用缩略图代替）'}`)
    console.log('')
    console.log('  浏览器应已自动打开；若没有，请手动复制上面的地址访问。')
    console.log('  >>> 关闭本窗口即停止服务 <<<')
    console.log('')
    openBrowser(url)
  })
  .catch((err) => {
    console.error('')
    console.error('  [错误] 启动失败：' + (err && err.message))
    console.error('')
    process.exit(1)
  })

process.on('SIGINT', () => {
  console.log('\n  正在停止服务……')
  server.close(() => process.exit(0))
  setTimeout(() => process.exit(0), 500)
})
