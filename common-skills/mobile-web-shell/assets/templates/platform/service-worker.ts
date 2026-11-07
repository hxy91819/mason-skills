/**
 * Service Worker 注册与更新提示适配器。
 *
 * 是否生产环境由调用方传入 enabled；适配器不读构建变量，也不直接弹框架弹窗。
 * 新 SW 进入 waiting 后调用 onUpdateReady，由应用层决定提示样式；用户确认后
 * 调用 update.apply()，适配器只在 controllerchange 时刷新一次页面。
 */
export interface ServiceWorkerUpdate {
  apply: () => void
}

export interface RegisterServiceWorkerOptions {
  /** 生产构建传 true；开发模式传 false（没有 /sw.js 产物）。默认允许注册。 */
  enabled?: boolean
  url?: string
  scope?: string
  onUpdateReady?: (update: ServiceWorkerUpdate) => void
  onError?: (error: unknown) => void
}

export function registerServiceWorker(options: RegisterServiceWorkerOptions = {}): void {
  if (options.enabled === false) {
    return
  }

  const container = globalThis.navigator?.serviceWorker
  if (!container) {
    return
  }

  const url = options.url ?? '/sw.js'
  const scope = options.scope ?? '/'
  let prompted = false
  let reloading = false

  const applyUpdate = (worker: ServiceWorker) => {
    if (reloading) {
      return
    }
    // 只监听一次 controllerchange：新 SW 接管后刷新一次，避免循环刷新。
    container.addEventListener('controllerchange', () => {
      if (reloading) {
        return
      }
      reloading = true
      globalThis.location.reload()
    }, { once: true })
    worker.postMessage({ type: 'SKIP_WAITING' })
  }

  const promptUpdate = (worker: ServiceWorker) => {
    if (prompted) {
      return
    }
    prompted = true
    options.onUpdateReady?.({ apply: () => applyUpdate(worker) })
  }

  container
    .register(url, { scope, updateViaCache: 'none' })
    .then((registration) => {
      // 页面在旧 SW 控制下打开时，新版本可能已完成安装并处于 waiting。
      if (registration.waiting && container.controller) {
        promptUpdate(registration.waiting)
      }

      registration.addEventListener('updatefound', () => {
        const installing = registration.installing
        if (!installing) {
          return
        }
        installing.addEventListener('statechange', () => {
          // 首次安装时没有 controller，不提示更新；只有旧版本被替换才提示。
          if (installing.state === 'installed' && container.controller) {
            promptUpdate(installing)
          }
        })
      })
    })
    .catch((error) => {
      // 浏览器禁用 SW 或非安全上下文时注册会失败，不影响应用正常使用。
      options.onError?.(error)
    })
}
