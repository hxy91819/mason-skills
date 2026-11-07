/** 去掉 hash、前导斜杠和 query，得到路由表里的页面路径。 */
export function normalizePageRoute(route: string): string {
  return route.replace(/^#\/?/, '').replace(/^\//, '').split('?')[0].replace(/\/$/, '')
}

/** 地址栏里的 hash 页面路径。没有 hash、或启动时还是空 hash，返回空字符串。 */
export function readHashRoute(): string {
  const hash = globalThis.location?.hash ?? ''
  if (!hash || hash === '#' || hash === '#/') {
    return ''
  }
  return normalizePageRoute(hash)
}

/**
 * 浏览器前进/后退会改地址，但不经过应用路由的导航钩子。
 * 没有浏览器历史的环境返回空的取消函数。
 */
export function watchBrowserHistory(listener: () => void): () => void {
  const onChange = () => listener()
  globalThis.addEventListener('hashchange', onChange)
  globalThis.addEventListener('popstate', onChange)
  return () => {
    globalThis.removeEventListener('hashchange', onChange)
    globalThis.removeEventListener('popstate', onChange)
  }
}
