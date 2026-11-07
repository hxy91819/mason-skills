/**
 * 读取宿主 fetch。
 * 只负责把函数交出去；ReadableStream 怎么拼回 Response 由请求适配器处理。
 * 没有可用流式 fetch 的环境返回 null，适配器改走框架请求 API。
 */
export function readNativeFetch(): typeof fetch | null {
  if (typeof globalThis.fetch !== 'function') {
    return null
  }
  return globalThis.fetch
}
