import { expect, test } from '@playwright/test'

/**
 * 键盘布局骨架。把选择器和路由换成目标应用的值。
 *
 * 浏览器模拟只验证“代码是否按 visualViewport 坐标布局”：
 * - 输入区底边应等于 offsetTop + height；
 * - 页面根顶边应等于 offsetTop；
 * - TabBar 隐藏、页头收起、输入内容保留。
 * iOS 真正把布局视口上推、键盘动画和系统表单辅助栏仍需真机确认。
 */
const APP_ROUTE = '/#/'
const PAGE_SELECTOR = '[data-testid="composer-page"]'
const INPUT_SELECTOR = '[data-testid="composer-input"]'
const SEND_SELECTOR = '[data-testid="composer-send"]'
const TABBAR_SELECTOR = '[data-testid="app-tabbar"]'
const LARGE_HEADER_SELECTOR = '[data-testid="large-header"]'
const KEYBOARD_HEIGHT = 460

for (const theme of ['light', 'dark'] as const) {
  test(`键盘开关时页面和输入区使用可见区域坐标 ${theme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 393, height: 852 })

    await page.addInitScript((keyboardHeight) => {
      const viewport = new EventTarget()
      Object.assign(viewport, { height: keyboardHeight, offsetTop: 0, scale: 1 })
      Object.defineProperty(globalThis, 'visualViewport', { value: viewport, configurable: true })

      // 桌面 Chromium 默认 pointer: fine；键盘适配器只在粗指针设备上判定键盘。
      const nativeMatchMedia = globalThis.matchMedia.bind(globalThis)
      globalThis.matchMedia = ((query: string) => {
        if (query.includes('pointer: coarse')) {
          return {
            matches: true,
            media: query,
            onchange: null,
            addEventListener() {},
            removeEventListener() {},
            addListener() {},
            removeListener() {},
            dispatchEvent() { return false },
          } as MediaQueryList
        }
        return nativeMatchMedia(query)
      }) as typeof globalThis.matchMedia
    }, KEYBOARD_HEIGHT)

    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: { data: [] } }))
    await page.goto(APP_ROUTE)

    const pageRoot = page.locator(PAGE_SELECTOR)
    const input = page.locator(INPUT_SELECTOR)
    const send = page.locator(SEND_SELECTOR)
    const tabbar = page.locator(TABBAR_SELECTOR)
    const largeHeader = page.locator(LARGE_HEADER_SELECTOR)

    await expect(pageRoot).toBeVisible()
    await expect(tabbar).toBeVisible()
    await input.fill('保留这条尚未发送的补充')

    for (const offsetTop of [0, 35]) {
      await page.evaluate(({ height, offsetTop }) => {
        Object.assign(globalThis.visualViewport!, { height, offsetTop, scale: 1 })
        globalThis.visualViewport!.dispatchEvent(new Event('resize'))
      }, { height: KEYBOARD_HEIGHT, offsetTop })

      await expect(tabbar).toBeHidden()
      await expect(largeHeader).toBeHidden()

      await expect.poll(async () => {
        const box = await input.boundingBox()
        return box ? Math.abs(box.y + box.height - (offsetTop + KEYBOARD_HEIGHT)) : Number.POSITIVE_INFINITY
      }).toBeLessThanOrEqual(2)

      const rootBox = await pageRoot.boundingBox()
      expect(rootBox).not.toBeNull()
      expect(Math.abs(rootBox!.y - offsetTop)).toBeLessThanOrEqual(2)
      await expect(input).toHaveValue('保留这条尚未发送的补充')
      await expect(send).toBeVisible()
    }

    // 键盘关闭后恢复布局和 TabBar。
    await page.evaluate(() => {
      Object.assign(globalThis.visualViewport!, { height: 852, offsetTop: 0, scale: 1 })
      globalThis.visualViewport!.dispatchEvent(new Event('resize'))
    })
    await expect(tabbar).toBeVisible()
    await expect(input).toHaveValue('保留这条尚未发送的补充')

    // 键盘未收起时程序化跳到其他页面，也必须恢复其他页面的 TabBar。
    await page.evaluate(() => {
      Object.assign(globalThis.visualViewport!, { height: 460, offsetTop: 0, scale: 1 })
      globalThis.visualViewport!.dispatchEvent(new Event('resize'))
    })
    await page.evaluate(() => {
      globalThis.location.hash = '/'
    })
    await expect(tabbar).toBeVisible()
  })
}
