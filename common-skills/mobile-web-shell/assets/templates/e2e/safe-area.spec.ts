import { expect, test } from '@playwright/test'

/**
 * 安全区骨架。把选择器和路由换成目标应用的值。
 *
 * CDP 的 Emulation.setSafeAreaInsetsOverride 只在 Chromium 可用；
 * 它模拟的是浏览器上报给页面的安全区，不覆盖 iOS 状态栏的真实绘制。
 */
const TAB_ROUTE = '/#/'
const TAB_PAGE_SELECTOR = '[data-testid="home-page"]'
const TAB_TITLE_SELECTOR = '[data-testid="home-title"]'
const TABBAR_LAST_ITEM = '[data-testid="app-tabbar"] > :last-child'
const SAFE_AREA = { top: 59, bottom: 34, left: 0, right: 0 }

test('安全区内标题不被状态栏遮挡，页面根从视口顶端开始', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'CDP 安全区模拟只在 Chromium 可用')

  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' })
  await page.setViewportSize({ width: 393, height: 852 })
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Emulation.setSafeAreaInsetsOverride', { insets: SAFE_AREA })

  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: { data: [] } }))
  await page.goto(TAB_ROUTE)

  await expect(page.locator('meta[name="viewport"]')).toHaveAttribute('content', /viewport-fit=cover/)
  await expect(page.locator(TAB_PAGE_SELECTOR)).toBeVisible()
  await expect(page.locator(TAB_TITLE_SELECTOR)).toBeVisible()

  const titleBox = await page.locator(TAB_TITLE_SELECTOR).boundingBox()
  expect(titleBox).not.toBeNull()
  expect(titleBox!.y).toBeGreaterThanOrEqual(SAFE_AREA.top)

  // 页面根必须从视口顶端开始，背景才能延伸到状态栏后面。
  const rootBox = await page.locator(TAB_PAGE_SELECTOR).boundingBox()
  expect(rootBox).not.toBeNull()
  expect(rootBox!.y).toBeLessThanOrEqual(0.5)

  // 底部最后一项留出 Home Indicator 安全区。
  const lastItem = await page.locator(TABBAR_LAST_ITEM).boundingBox()
  expect(lastItem).not.toBeNull()
  expect(852 - lastItem!.y - lastItem!.height).toBeGreaterThanOrEqual(SAFE_AREA.bottom - 1)
})
