/**
 * 移动 Web 外壳 Service Worker 模板。
 *
 * 手写实现，不引入 Workbox。构建时由 vite-sw-version.mjs 在产物里替换
 * __SW_VERSION__；版本变化才会安装新的 SW。部署时把本文件放到
 * src/static/sw.js，并让服务器从根作用域提供 /sw.js。
 */

// 占位符在构建时替换；缓存名带版本，activate 时据此清理旧缓存。
const SW_VERSION = '__SW_VERSION__'
const CACHE_PREFIX = 'app-shell-h5'
const CACHE_NAME = `${CACHE_PREFIX}-${SW_VERSION}`
const INDEX_URL = '/index.html'
const OFFLINE_URL = '/static/offline.html'
const PRECACHE_URLS = ['/', INDEX_URL, OFFLINE_URL]
const DEFAULT_NOTIFICATION_URL = '/'

/**
 * 预缓存应用外壳。
 *
 * 首次访问时页面尚未被 SW 接管，入口 HTML 里的 JS/CSS 请求不会进入 fetch 事件；
 * 因此额外从 index.html 提取 /assets/ 资源补缓存，否则首次离线刷新只有 HTML
 * 而没有脚本，应用外壳无法渲染。
 */
async function precache() {
  const cache = await caches.open(CACHE_NAME)
  await cache.addAll(PRECACHE_URLS)

  const indexResponse = await cache.match(INDEX_URL)
  if (!indexResponse)
    return

  const html = await indexResponse.text()
  const assetUrls = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map(match => match[1])
  // 单个资源失败不拖垮 install；入口 HTML 和离线页已经由 addAll 保证。
  await Promise.all([...new Set(assetUrls)].map(url => cache.add(url).catch(() => undefined)))
}

/**
 * 导航请求网络优先：成功后把最新外壳写入 /index.html；
 * 网络失败先回缓存的 index.html，再回离线页。
 */
async function handleNavigation(request) {
  const cache = await caches.open(CACHE_NAME)
  try {
    const response = await self.fetch(request)
    if (!response.ok)
      throw new Error(`navigation failed: ${response.status}`)
    await cache.put(INDEX_URL, response.clone())
    return response
  }
  catch {
    const cachedIndex = await cache.match(INDEX_URL)
    if (cachedIndex)
      return cachedIndex
    const cachedRoot = await cache.match('/')
    if (cachedRoot)
      return cachedRoot
    return (await cache.match(OFFLINE_URL)) || Response.error()
  }
}

/**
 * 带 hash 的 /assets/ 与 /static/ 资源缓存优先：
 * 文件名变化即内容变化，命中缓存后无需回源；未命中时回源并补缓存。
 */
async function handleAsset(request) {
  const cache = await caches.open(CACHE_NAME)
  const cached = await cache.match(request)
  if (cached)
    return cached

  const response = await self.fetch(request)
  if (response.ok && response.type === 'basic')
    await cache.put(request, response.clone())
  return response
}

self.addEventListener('install', (event) => {
  event.waitUntil(precache())
})

self.addEventListener('activate', (event) => {
  // 新版本激活后只保留当前版本的缓存，避免旧 hash 资源长期占用空间。
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys
        .filter(key => key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME)
        .map(key => caches.delete(key)),
    )),
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event

  // 非 GET 请求（提交、删除、上传等）一律直通网络，不参与缓存。
  if (request.method !== 'GET')
    return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin)
    return

  // API 请求（含 SSE 流式响应）绝不缓存，直接交给浏览器网络栈。
  if (url.pathname.startsWith('/api/'))
    return

  // 所有页面导航走网络优先；hash 路由下入口都是 / 或 /index.html。
  if (request.mode === 'navigate') {
    event.respondWith(handleNavigation(request))
    return
  }

  if (url.pathname.startsWith('/assets/') || url.pathname.startsWith('/static/'))
    event.respondWith(handleAsset(request))
})

// 应用确认更新后通知当前等待中的 SW 立即接管；controllerchange 由页面负责刷新。
self.addEventListener('message', (event) => {
  if (event.data?.type === 'SKIP_WAITING')
    self.skipWaiting()
})

/** 推送 payload 来自后端，只接受字符串字段，避免异常数据破坏通知展示。 */
function readPushPayload(event) {
  if (!event.data)
    return {}
  try {
    const payload = event.data.json()
    return payload && typeof payload === 'object' ? payload : {}
  }
  catch {
    return {}
  }
}

/** 后端发送 Web Push 后，这里只负责展示系统通知。 */
self.addEventListener('push', (event) => {
  const payload = readPushPayload(event)
  const title = typeof payload.title === 'string' && payload.title
    ? payload.title
    : '有新内容'
  const body = typeof payload.body === 'string' ? payload.body : '打开应用查看最新内容。'
  const url = typeof payload.url === 'string' && payload.url.startsWith('/')
    ? payload.url
    : DEFAULT_NOTIFICATION_URL
  const options = {
    body,
    data: { url },
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
  }
  // 同一对象重复投递时用 tag 替换旧通知，避免至少一次语义产生重复气泡。
  if (typeof payload.tag === 'string' && payload.tag)
    options.tag = payload.tag
  event.waitUntil(self.registration.showNotification(title, options))
})

/** 点击通知时聚焦已有同源窗口；没有窗口则新开默认页。 */
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const requestedUrl = event.notification.data?.url
  const target = new URL(
    typeof requestedUrl === 'string' && requestedUrl.startsWith('/')
      ? requestedUrl
      : DEFAULT_NOTIFICATION_URL,
    self.location.origin,
  ).href
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const existing = windows.find(client => new URL(client.url).origin === self.location.origin)
    if (existing) {
      await existing.focus()
      if (existing.url !== target && typeof existing.navigate === 'function')
        await existing.navigate(target)
      return
    }
    await self.clients.openWindow(target)
  })())
})
