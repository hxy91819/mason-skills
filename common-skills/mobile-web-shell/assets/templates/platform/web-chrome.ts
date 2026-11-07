/**
 * 浏览器外壳适配器：把调用方给的颜色写入 theme-color meta。
 * 颜色取页面背景还是导航栏，由应用层按当前页决定；这里不判断页面。
 */
export function setThemeColor(color: string): void {
  const doc = globalThis.document
  const meta = doc?.querySelector('meta[name="theme-color"]')
  if (!meta) {
    return
  }
  meta.setAttribute('content', color)
}

/**
 * 把当前主题和整份色板写到文档根节点。
 *
 * 系统弹窗、下拉刷新和 iOS 回弹露出的是页面容器之外的画布，拿不到页面
 * 容器上按主题注入的变量；统一在根节点同步一份，页面外区域读同一组变量。
 */
export function setDocumentPalette(theme: string, cssVariables: string): void {
  const root = globalThis.document?.documentElement
  if (!root) {
    return
  }
  root.dataset.theme = theme
  for (const declaration of cssVariables.split(';')) {
    const splitAt = declaration.indexOf(':')
    if (splitAt <= 0) {
      continue
    }
    const name = declaration.slice(0, splitAt).trim()
    const value = declaration.slice(splitAt + 1).trim()
    if (name.startsWith('--') && value) {
      root.style.setProperty(name, value)
    }
  }
}
