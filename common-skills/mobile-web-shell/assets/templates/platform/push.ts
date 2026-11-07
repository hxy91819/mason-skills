/**
 * Web Push 浏览器适配器。
 *
 * 浏览器权限、PushManager 与 Service Worker 访问全部收敛在这里；页面只消费
 * 纯状态结果和订阅 payload，业务代码不直接触碰浏览器对象。
 */

export type PushPermission = 'granted' | 'denied' | 'default' | 'unsupported'

export type PushUnsupportedReason
  = | 'unsupported'
    | 'ios-install-required'
    | 'insecure-context'

export interface PushCapability {
  supported: boolean
  reason?: PushUnsupportedReason
}

export type PushUiStatus
  = | 'unsupported'
    | 'ios-install-required'
    | 'insecure-context'
    | 'server-disabled'
    | 'permission-denied'
    | 'subscribed'
    | 'unsubscribed'
    | 'demo-disabled'

export interface PushUiState {
  status: PushUiStatus
  canToggle: boolean
  switchValue: boolean
  description: string
}

export interface PushStateInput {
  capability: PushCapability
  serverEnabled: boolean
  permission: PushPermission
  subscribed: boolean
  demoMode: boolean
}

export interface PushSubscriptionPayload {
  endpoint: string
  p256dh: string
  auth: string
}

/**
 * 把平台能力与权限翻译为可展示的开关状态。
 *
 * 纯函数，便于在 Node 单测中覆盖不支持、未授权、已订阅等分支，
 * 不需要伪造整个浏览器环境。
 */
export function resolvePushUiState(input: PushStateInput): PushUiState {
  if (input.demoMode) {
    return {
      status: 'demo-disabled',
      canToggle: false,
      switchValue: false,
      description: '演示环境不会发送真实推送。',
    }
  }
  if (!input.capability.supported) {
    if (input.capability.reason === 'ios-install-required') {
      return {
        status: 'ios-install-required',
        canToggle: false,
        switchValue: false,
        description: 'iPhone / iPad 需先添加到主屏幕，再从主屏幕打开。系统通知仅支持 iOS 16.4 及以上。',
      }
    }
    if (input.capability.reason === 'insecure-context') {
      return {
        status: 'insecure-context',
        canToggle: false,
        switchValue: false,
        description: '通知需要 HTTPS 安全连接，请通过正式地址打开。',
      }
    }
    return {
      status: 'unsupported',
      canToggle: false,
      switchValue: false,
      description: '当前浏览器不支持系统通知，可换用最新版 Chrome 或 Safari。',
    }
  }
  if (!input.serverEnabled) {
    return {
      status: 'server-disabled',
      canToggle: false,
      switchValue: false,
      description: '服务端尚未启用通知，请联系管理员配置推送密钥。',
    }
  }
  if (input.permission === 'denied') {
    return {
      status: 'permission-denied',
      canToggle: false,
      switchValue: false,
      description: '通知权限已被拒绝，请到系统设置中允许本应用发送通知。',
    }
  }
  if (input.subscribed) {
    return {
      status: 'subscribed',
      canToggle: true,
      switchValue: true,
      description: '已开启。发布新内容时会收到系统通知。',
    }
  }
  return {
    status: 'unsubscribed',
    canToggle: true,
    switchValue: false,
    description: '开启后，发布新内容时会收到系统通知。',
  }
}

function isIos(navigator: Navigator): boolean {
  const userAgent = navigator.userAgent || ''
  const touchMac = /Macintosh/i.test(userAgent) && navigator.maxTouchPoints > 1
  return /iPhone|iPad|iPod/i.test(userAgent) || touchMac
}

function isStandalone(): boolean {
  if (typeof globalThis.matchMedia === 'function') {
    if (globalThis.matchMedia('(display-mode: standalone)').matches) {
      return true
    }
  }
  // iOS Safari 添加到主屏幕后暴露非标准 standalone；只在运行时收窄，
  // 不把 Safari 专属字段带进跨端类型。
  const navigator = globalThis.navigator as Navigator & { standalone?: boolean }
  return navigator?.standalone === true
}

export function getPushCapability(): PushCapability {
  const navigator = globalThis.navigator
  if (!navigator) {
    return { supported: false, reason: 'unsupported' }
  }
  // iOS 浏览器标签页即使暴露 PushManager 也不能订阅，必须从主屏幕 PWA 打开。
  if (isIos(navigator) && !isStandalone()) {
    return { supported: false, reason: 'ios-install-required' }
  }
  if (globalThis.isSecureContext === false) {
    return { supported: false, reason: 'insecure-context' }
  }
  const hasPushManager = 'PushManager' in globalThis
  const hasNotification = 'Notification' in globalThis
  if (!navigator.serviceWorker || !hasPushManager || !hasNotification) {
    return { supported: false, reason: 'unsupported' }
  }
  return { supported: true }
}

export function getPushPermission(): PushPermission {
  if (typeof globalThis.Notification === 'undefined') {
    return 'unsupported'
  }
  const permission = globalThis.Notification.permission
  if (permission === 'granted' || permission === 'denied' || permission === 'default') {
    return permission
  }
  return 'default'
}

function base64UrlToBytes(value: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = globalThis.atob(base64)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) {
    bytes[index] = raw.charCodeAt(index)
  }
  return bytes
}

async function getReadyRegistration(): Promise<ServiceWorkerRegistration> {
  const container = globalThis.navigator?.serviceWorker
  if (!container) {
    throw new Error('当前浏览器不支持 Service Worker，无法开启通知。')
  }

  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      container.ready,
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error('后台服务尚未就绪，请刷新页面后重试。')),
          8000,
        )
      }),
    ])
  }
  finally {
    if (timer) {
      clearTimeout(timer)
    }
  }
}

async function getExistingSubscription(): Promise<PushSubscription | null> {
  const registration = await globalThis.navigator?.serviceWorker?.getRegistration()
  if (!registration) {
    return null
  }
  return registration.pushManager.getSubscription()
}

function toPayload(subscription: PushSubscription): PushSubscriptionPayload {
  const json = subscription.toJSON()
  const keys = json.keys
  if (!json.endpoint || !keys?.p256dh || !keys.auth) {
    throw new Error('浏览器返回的订阅信息不完整，请重试。')
  }
  return {
    endpoint: json.endpoint,
    p256dh: keys.p256dh,
    auth: keys.auth,
  }
}

/**
 * 请求系统权限并创建浏览器订阅；已有订阅时直接复用，保证幂等。
 */
export async function requestPushSubscription(
  publicKey: string,
): Promise<PushSubscriptionPayload> {
  const capability = getPushCapability()
  if (!capability.supported) {
    throw new Error('当前环境不支持系统通知。')
  }
  if (!publicKey.trim()) {
    throw new Error('通知公钥缺失，请联系管理员。')
  }

  let permission = getPushPermission()
  if (permission === 'denied') {
    throw new Error('通知权限已被拒绝，请到系统设置中允许后重试。')
  }
  if (permission !== 'granted') {
    permission = await globalThis.Notification.requestPermission()
  }
  if (permission !== 'granted') {
    throw new Error(
      permission === 'denied'
        ? '通知权限已被拒绝，请到系统设置中允许后重试。'
        : '未获得通知权限，暂时无法开启。',
    )
  }

  const registration = await getReadyRegistration()
  const existing = await registration.pushManager.getSubscription()
  if (existing) {
    return toPayload(existing)
  }

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64UrlToBytes(publicKey),
  })
  return toPayload(subscription)
}

/**
 * 读取当前浏览器订阅；Service Worker 尚未注册时安全返回 null。
 */
export async function readPushSubscription(): Promise<PushSubscriptionPayload | null> {
  if (!getPushCapability().supported) {
    return null
  }
  const subscription = await getExistingSubscription()
  return subscription ? toPayload(subscription) : null
}

/**
 * 取消浏览器本地订阅并返回原 endpoint，供页面同步删除服务端记录。
 */
export async function removePushSubscription(): Promise<string | null> {
  const subscription = await getExistingSubscription()
  if (!subscription) {
    return null
  }
  const endpoint = subscription.endpoint
  const removed = await subscription.unsubscribe()
  if (!removed) {
    throw new Error('取消浏览器订阅失败，请稍后重试。')
  }
  return endpoint
}
