/**
 * 全屏模式下的边缘右滑返回。
 *
 * 在文档级监听触摸，从屏幕左缘窄带内起手、以水平向右为主且超过阈值时
 * 触发调用方注入的返回动作。页面栈、Tab 页判定由调用方注入，适配器不读路由配置。
 */
export interface EdgeSwipeBackOptions {
  /** 当前是否允许手势返回（非 Tab 页且页面栈里还有上一页）。 */
  enabled: () => boolean
  /** 手势成立后的返回动作。 */
  onBack: () => void
}

const EDGE_WIDTH = 24
const TRIGGER_DISTANCE = 80
const DIRECTION_LOCK = 10

/** 起点必须落在屏幕左缘的窄带内。 */
export function isEdgeSwipeStart(clientX: number): boolean {
  return clientX >= 0 && clientX <= EDGE_WIDTH
}

/** 只有水平向右、且位移足够大，才认为是一次返回手势。 */
export function shouldTriggerEdgeSwipeBack(startX: number, startY: number, endX: number, endY: number): boolean {
  const dx = endX - startX
  const dy = endY - startY
  return dx >= TRIGGER_DISTANCE && Math.abs(dy) <= dx * 0.6
}

export function installEdgeSwipeBack(options: EdgeSwipeBackOptions): () => void {
  const doc = globalThis.document
  if (!doc) {
    return () => {}
  }

  let startX = 0
  let startY = 0
  let lastX = 0
  let lastY = 0
  let tracking = false
  let cancelled = false

  // 输入框聚焦时不抢手势，避免用户正在编辑时被返回打断。
  const isEditing = (): boolean => {
    const active = doc.activeElement
    if (!active) {
      return false
    }
    if (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA') {
      return true
    }
    return active instanceof HTMLElement && active.isContentEditable
  }

  // 从横向可滚动容器内起手时让位给容器本身。
  const isInsideHorizontalScroller = (target: EventTarget | null): boolean => {
    let node = target instanceof Element ? target : null
    while (node) {
      if (node instanceof HTMLElement) {
        const style = globalThis.getComputedStyle(node)
        if ((style.overflowX === 'auto' || style.overflowX === 'scroll')
          && node.scrollWidth > node.clientWidth + 2) {
          return true
        }
      }
      node = node.parentElement
    }
    return false
  }

  const onTouchStart = (event: TouchEvent) => {
    tracking = false
    cancelled = false
    if (event.touches.length !== 1) {
      return
    }
    const touch = event.touches[0]
    if (!isEdgeSwipeStart(touch.clientX)) {
      return
    }
    if (!options.enabled() || isEditing() || isInsideHorizontalScroller(event.target)) {
      return
    }
    startX = touch.clientX
    startY = touch.clientY
    lastX = startX
    lastY = startY
    tracking = true
  }

  const onTouchMove = (event: TouchEvent) => {
    if (!tracking || event.touches.length !== 1) {
      return
    }
    const touch = event.touches[0]
    lastX = touch.clientX
    lastY = touch.clientY
    const dx = lastX - startX
    const dy = lastY - startY
    // 先锁方向：竖滑或向左的手势立刻交还给页面滚动。
    if (dx < 0 || Math.abs(dy) > Math.max(DIRECTION_LOCK, Math.abs(dx))) {
      cancelled = true
      tracking = false
      return
    }
    // 方向确定后阻止页面横向回弹；竖向监听仍是被动模式，不影响滚动。
    if (dx > DIRECTION_LOCK && event.cancelable) {
      event.preventDefault()
    }
  }

  const onTouchEnd = () => {
    if (!tracking) {
      return
    }
    tracking = false
    if (cancelled) {
      return
    }
    if (shouldTriggerEdgeSwipeBack(startX, startY, lastX, lastY)) {
      options.onBack()
    }
  }

  const onTouchCancel = () => {
    tracking = false
    cancelled = false
  }

  doc.addEventListener('touchstart', onTouchStart, { passive: true })
  doc.addEventListener('touchmove', onTouchMove, { passive: false })
  doc.addEventListener('touchend', onTouchEnd, { passive: true })
  doc.addEventListener('touchcancel', onTouchCancel, { passive: true })
  return () => {
    doc.removeEventListener('touchstart', onTouchStart)
    doc.removeEventListener('touchmove', onTouchMove)
    doc.removeEventListener('touchend', onTouchEnd)
    doc.removeEventListener('touchcancel', onTouchCancel)
  }
}
