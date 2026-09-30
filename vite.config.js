import fs from 'node:fs'
import path from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 卡面图不复制进工程（共 5.5GB），直接按顺序在下列目录里查找并流式返回。
// 顺序：缩略图缓存 -> 资源集原图。可用 KAIRI_IMAGE_ROOT 覆盖原图目录。
const DEFAULT_IMAGE_ROOT = 'D:/新建文件夹 (2)/kairisei-ma-cn602-server/resource-set/resources/image'
const IMAGE_ROOT = process.env.KAIRI_IMAGE_ROOT || DEFAULT_IMAGE_ROOT
const THUMB_ROOT = path.resolve('.cache/thumbs')

function createImageHandler(roots) {
  const resolved = roots.filter(Boolean).map((root) => path.resolve(root))
  return (req, res, next) => {
    const rel = decodeURIComponent((req.url || '').split('?')[0]).replace(/^\/+/, '')
    if (!rel || rel.includes('..')) return next()
    for (const root of resolved) {
      const file = path.resolve(root, rel)
      if (!file.startsWith(root + path.sep)) continue
      let stat
      try {
        stat = fs.statSync(file)
      } catch {
        continue
      }
      if (!stat.isFile()) continue
      res.setHeader('Content-Type', 'image/png')
      res.setHeader('Cache-Control', 'public, max-age=86400')
      fs.createReadStream(file).pipe(res)
      return
    }
    next()
  }
}

function cardImagePlugin() {
  return {
    name: 'kairi-card-images',
    configureServer(server) {
      // 注意顺序：/cardimg/thumb 必须先注册，否则会被 /cardimg 吃掉。
      server.middlewares.use('/cardimg/thumb', createImageHandler([THUMB_ROOT]))
      server.middlewares.use('/cardimg', createImageHandler([IMAGE_ROOT]))
    },
    configurePreviewServer(server) {
      server.middlewares.use('/cardimg/thumb', createImageHandler([THUMB_ROOT]))
      server.middlewares.use('/cardimg', createImageHandler([IMAGE_ROOT]))
    },
  }
}

export default defineConfig({
  plugins: [vue(), cardImagePlugin()],
  server: {
    port: 5173,
    host: '127.0.0.1',
    fs: { strict: false },
  },
  build: {
    chunkSizeWarningLimit: 12000,
  },
})
