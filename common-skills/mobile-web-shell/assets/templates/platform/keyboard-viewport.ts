/**
 * 可见视口与软键盘适配器。
 * 业务只调用 observeKeyboardViewport；visualViewport、innerHeight、matchMedia 都留在这里。
 *
 * uni-app 小程序端没有 visualViewport，可在同名导出里改用
 * uni.onKeyboardHeightChange，并返回 { open, height: null, top: 0, insetBottom }。
 * 见 references/platform-boundary.md 的框架差异。
 */
export interface KeyboardViewport {
  open: boolean
  /** 可见区域高度；键盘未打开时为 null。 */
  height: number | null
  /** 可见区域相对布局视口的上偏移；键盘未打开时为 0。 */
  top: number
  /** 键盘盖住布局视口底部的高度。底部弹窗用它把底边抬到可见区域内。 */
  insetBottom: number
}

export interface KeyboardViewportOptions {
  /** 键盘关闭时的布局视口高度基线。 */
  baseline?: () => number
  /** 当前是否有可编辑元素聚焦。 */
  isEditing?: () => boolean
  /** 是否为粗指针（手机/平板）设备。 */
  isCoarsePointer?: () => boolean
  /** 可见区域缩小多少像素才认为是键盘；默认 120。 */
  threshold?: number
}

export function observeKeyboardViewport(
  update: (value: KeyboardViewport) => void,
  options: KeyboardViewportOptions = {},
): () => void {
  const viewport = globalThis.visualViewport
  if (!viewport) {
    return () => {}
  }

  const baseline = options.baseline ?? (() => globalThis.innerHeight)
  const isCoarsePointer = options.isCoarsePointer
    ?? (() => globalThis.matchMedia('(pointer: coarse)').matches)
  const isEditing = options.isEditing ?? (() => {
    const active = globalThis.document.activeElement
    return active?.tagName === 'TEXTAREA' || active?.tagName === 'INPUT'
  })
  const threshold = options.threshold ?? 120

  let layoutHeight = baseline()
  let open = false

  const refresh = () => {
    const editing = isEditing()
    // 聚焦本身不能证明键盘打开（桌面/硬件键盘）；键盘关闭时更新基线。
    if (!editing && !open) {
      layoutHeight = baseline()
    }

    open = isCoarsePointer()
      && viewport.scale === 1
      && (editing || open)
      && layoutHeight - viewport.height > threshold

    const insetBottom = open
      ? Math.max(0, Math.round(layoutHeight - viewport.offsetTop - viewport.height))
      : 0

    update({
      open,
      height: open ? viewport.height : null,
      top: open ? viewport.offsetTop : 0,
      insetBottom,
    })
  }

  viewport.addEventListener('resize', refresh)
  // 键盘弹出时 iOS 可能只改 offsetTop，不触发 resize。
  viewport.addEventListener('scroll', refresh)
  globalThis.addEventListener('resize', refresh)
  globalThis.document.addEventListener('focusin', refresh)
  globalThis.document.addEventListener('focusout', refresh)
  refresh()

  return () => {
    viewport.removeEventListener('resize', refresh)
    viewport.removeEventListener('scroll', refresh)
    globalThis.removeEventListener('resize', refresh)
    globalThis.document.removeEventListener('focusin', refresh)
    globalThis.document.removeEventListener('focusout', refresh)
  }
}
