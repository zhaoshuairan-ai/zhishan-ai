/* 智膳 AI · Service Worker
 *
 * 缓存策略（安全优先）：
 * 1. /api/ 下的所有请求一律「仅网络」，绝不缓存，避免旧分析结果覆盖新结果或泄露数据；
 * 2. 页面导航：网络优先，离线时回退到缓存的 index.html 或离线提示页；
 * 3. 静态资源（JS/CSS/图片/字体）：stale-while-revalidate，后台静默更新；
 * 4. 只处理同源 GET 请求；跨域（如模型 API）一律直连。
 */

const VERSION = 'fsai-v5'
const STATIC_CACHE = `${VERSION}-static`
const HTML_CACHE = `${VERSION}-html`

const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
]

/**
 * 预缓存「应用外壳」：index.html 里引用的构建产物文件名带哈希，
 * 无法在源码里写死，因此安装时先取 index.html，解析出 /assets/*.js|css 再缓存。
 * 这样首次访问后断网，页面仍能启动并显示离线提示，而不是白屏。
 */
async function precacheAppShell() {
  try {
    const response = await fetch('/index.html', { cache: 'no-store' })
    if (!response || !response.ok) return
    const htmlCache = await caches.open(HTML_CACHE)
    await htmlCache.put('/index.html', response.clone())
    const text = await response.text()
    const assetUrls = Array.from(text.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g), (match) => match[1])
    const staticCache = await caches.open(STATIC_CACHE)
    await Promise.all(assetUrls.map((url) => staticCache.add(url).catch(() => undefined)))
  } catch {
    /* 离线安装时失败不影响后续运行时缓存 */
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(HTML_CACHE)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => caches.open(STATIC_CACHE))
      .then((cache) => cache.add('/offline.html').catch(() => undefined))
      .then(() => precacheAppShell())
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => !key.startsWith(VERSION))
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  )
})

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/assets/') ||
    /\.(?:js|css|png|jpg|jpeg|webp|svg|woff2?|ttf|ico)$/i.test(url.pathname)
  )
}

async function networkFirst(request) {
  const cache = await caches.open(HTML_CACHE)
  try {
    const response = await fetch(request)
    if (response && response.ok) {
      cache.put(request, response.clone())
    }
    return response
  } catch (error) {
    const cached = (await cache.match(request)) || (await cache.match('/index.html'))
    if (cached) return cached
    const offline = await caches.match('/offline.html')
    if (offline) return offline
    throw error
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE)
  const cached = await cache.match(request)
  const network = fetch(request)
    .then((response) => {
      if (response && response.ok) cache.put(request, response.clone())
      return response
    })
    .catch(() => undefined)
  return cached || (await network) || Response.error()
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  // 接口数据一律不缓存：保证看到的是服务器上的最新结果
  if (url.pathname.startsWith('/api/')) return

  if (request.mode === 'navigate') {
    event.respondWith(networkFirst(request))
    return
  }

  if (isStaticAsset(url)) {
    event.respondWith(staleWhileRevalidate(request))
  }
})

// 允许页面通知 SW 立即更新
self.addEventListener('message', (event) => {
  if (event.data === 'SKIP_WAITING') self.skipWaiting()
})
