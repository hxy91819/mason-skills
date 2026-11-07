/**
 * 查询已渲染的宿主节点。
 * 业务不访问 document；拿到节点后的滚动和测量仍由调用方决定。
 * 没有 DOM 的环境返回 null，调用方改走框架自己的选择器查询。
 */
export function hasH5Document(): boolean {
  return globalThis.document != null
}

export function queryH5(selector: string, parent?: ParentNode | null): HTMLElement | null {
  // parent 省略时从 document 查；显式传入 null 表示上级节点不存在，直接放弃。
  const scope = parent === undefined ? globalThis.document : parent
  if (!scope) {
    return null
  }
  return scope.querySelector(selector) as HTMLElement | null
}
