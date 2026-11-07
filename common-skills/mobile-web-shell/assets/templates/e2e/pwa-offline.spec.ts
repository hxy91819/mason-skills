import type { Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { readFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, join, resolve } from 'node:path'
import { expect, test } from '@playwright/test'

/**
 * 离线与更新骨架。先执行生产构建，再运行本测试。
 *
 * 自带一个极小静态服务器，模拟发布环境的 `/sw.js` 重写、缓存头和 SPA fallback；
 * 否则测到的是 dev server 的行为，不是发布后的行为。
 *
 * 替换：APP_HOME、APP_SHELL_SELECTOR、UPDATE_PROMPT_TEXT、RELOAD_BUTTON_TEXT。
 * 如果首页需要登录，把 APP_HOME 指向登录页，并把 APP_SHELL_SELECTOR 换成登录页根节点。
 */
const DIST_DIR = resolve(process.cwd(), 'dist')
const SW_PATH = join(DIST_DIR, 'static', 'sw.js')
const APP_HOME = '/'
const APP_SHELL_SELECTOR = '[data-testid="app-shell"]'
const UPDATE_PROMPT_TEXT = '有新版本'
const RELOAD_BUTTON_TEXT = '立即刷新'

const CONTENT_TYPES: Record<string, string> = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
}

let server: Server
let origin = ''
let originalSwSource = ''
let swSource = ''

function cacheControl(pathname: string): string {
  if (pathname.startsWith('/assets/'))
    return 'public, max-age=31536000, immutable'
  if (pathname.startsWith('/static/'))
    return 'public, max-age=86400'
  return 'no-cache'
}

async function serveFile(pathname: string): Promise<{ body: Buffer, type: string }> {
  const filePath = join(DIST_DIR, pathname)
  try {
    const body = await readFile(filePath)
    return { body, type: CONTENT_TYPES[extname(filePath)] || 'application/octet-stream' }
  }
  catch {
    // 与 Caddy `try_files {path} /index.html` 一致：无扩展名的未知路径回退入口 HTML。
    if (extname(pathname))
      throw new Error(`静态文件不存在: ${pathname}`)
    return { body: await readFile(join(DIST_DIR, 'index.html')), type: CONTENT_TYPES['.html'] }
  }
}

test.beforeAll(async () => {
  originalSwSource = await readFile(SW_PATH, 'utf8')
  if (!originalSwSource.includes('const SW_VERSION ='))
    throw new Error('未找到构建后的 sw.js，请先执行生产构建')
  swSource = originalSwSource

  server = createServer(async (request, response) => {
    const pathname = decodeURIComponent(new URL(request.url || '/', 'http://127.0.0.1').pathname)

    if (pathname === '/sw.js') {
      response.writeHead(200, {
        'Cache-Control': 'no-cache',
        'Content-Type': CONTENT_TYPES['.js'],
        'Service-Worker-Allowed': '/',
      })
      response.end(swSource)
      return
    }

    // API 直通网络，验证 SW 不把它写进 Cache Storage。
    if (pathname.startsWith('/api/')) {
      response.writeHead(200, { 'Cache-Control': 'no-store', 'Content-Type': CONTENT_TYPES['.json'] })
      response.end(JSON.stringify({ data: [] }))
      return
    }

    try {
      const file = await serveFile(pathname === '/' ? '/index.html' : pathname)
      response.writeHead(200, {
        'Cache-Control': cacheControl(pathname),
        'Content-Type': file.type,
      })
      response.end(file.body)
    }
    catch {
      response.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' })
      response.end('Not Found')
    }
  })

  await new Promise<void>((resolvePromise, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolvePromise)
  })
  origin = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
})

test.afterAll(async () => {
  await new Promise<void>((resolvePromise, reject) => {
    server.close(error => error ? reject(error) : resolvePromise())
  })
})

test.beforeEach(() => {
  swSource = originalSwSource
})

test('首次加载后 SW 激活，断网刷新可渲染外壳，API 不进入缓存', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Service Worker 行为只在 Chromium 验收')

  await page.goto(APP_HOME)
  await expect(page.locator(APP_SHELL_SELECTOR)).toBeVisible()

  // ready 只在 install 的预缓存完成后 resolve，说明外壳已可离线使用。
  const activeState = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready
    return registration.active?.state
  })
  expect(activeState).toBe('activated')

  // 首次加载时 SW 还没有控制页面；再导航一次，让后续请求走 SW。
  await page.reload()
  await expect(page.locator(APP_SHELL_SELECTOR)).toBeVisible()
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)

  const apiResponse = await page.evaluate(async () => {
    const response = await fetch('/api/cache-probe')
    return response.json()
  })
  expect(apiResponse).toEqual({ data: [] })

  const cachedUrls = await page.evaluate(async () => {
    const urls: string[] = []
    for (const name of await caches.keys()) {
      const cache = await caches.open(name)
      for (const request of await cache.keys())
        urls.push(request.url)
    }
    return urls
  })
  expect(cachedUrls.some(url => new URL(url).pathname.startsWith('/api/'))).toBe(false)
  expect(cachedUrls.some(url => new URL(url).pathname === '/index.html')).toBe(true)
  // install 阶段已从 index.html 提取并缓存带 hash 的 JS/CSS。
  expect(cachedUrls.some(url => new URL(url).pathname.startsWith('/assets/'))).toBe(true)

  // 断网刷新：导航回退缓存的 index.html，JS/CSS 来自缓存，应用外壳仍挂载。
  await page.context().setOffline(true)
  await page.reload()
  await expect(page.locator(APP_SHELL_SELECTOR)).toBeVisible()
  await page.context().setOffline(false)
})

test('发版后新 SW 进入 waiting，确认后只刷新一次', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'Service Worker 行为只在 Chromium 验收')

  await page.goto(APP_HOME)
  await expect(page.locator(APP_SHELL_SELECTOR)).toBeVisible()
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready
  })

  // 先让现有 SW 控制页面，否则新版本会直接激活，不会进入 waiting。
  await page.reload()
  await expect(page.locator(APP_SHELL_SELECTOR)).toBeVisible()
  await expect.poll(() => page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)

  const nextVersion = `e2e-update-${Date.now()}`
  swSource = originalSwSource.replace(
    /const SW_VERSION = '[^']+'/,
    `const SW_VERSION = '${nextVersion}'`,
  )

  // 重新加载时浏览器检查到 sw.js 字节变化，新 SW 安装后停在 waiting。
  await page.reload()
  await expect(page.getByText(UPDATE_PROMPT_TEXT)).toBeVisible()

  const waitingState = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration()
    return registration?.waiting?.state ?? null
  })
  expect(waitingState).toBe('installed')

  // 确认后 postMessage SKIP_WAITING，新 SW 激活触发 controllerchange，页面只刷新一次。
  const navigation = page.waitForEvent('framenavigated')
  await page.getByText(RELOAD_BUTTON_TEXT, { exact: true }).click()
  await navigation
  await expect(page.locator(APP_SHELL_SELECTOR)).toBeVisible()
  const cacheNames = await page.evaluate(() => caches.keys())
  expect(cacheNames.some(name => name.includes(nextVersion))).toBe(true)
})
