/** 跨站跳转。没有地址栏的环境自行替换为空实现或原生导航。 */
export function assignLocation(url: string): void {
  globalThis.location.assign(url)
}
