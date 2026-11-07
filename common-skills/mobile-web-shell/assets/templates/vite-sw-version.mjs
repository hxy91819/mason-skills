import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'

/**
 * 构建时替换 Service Worker 里的版本占位符。
 *
 * 用法：
 *   import { serviceWorkerVersionPlugin } from './vite-sw-version.mjs'
 *   plugins: [serviceWorkerVersionPlugin()]
 *
 * 选项：
 *   swPath       产物内的 SW 路径，默认 static/sw.js
 *   placeholder  版本占位符，默认 __SW_VERSION__
 *   version      版本字符串或返回版本的函数；默认毫秒级时间戳
 *
 * 必须在静态资源拷贝完成后的 closeBundle 阶段写入；dev 模式不注册 SW。
 */
export function serviceWorkerVersionPlugin(options = {}) {
  const swPath = options.swPath ?? 'static/sw.js'
  const placeholder = options.placeholder ?? '__SW_VERSION__'
  let outDir = ''

  return {
    name: 'app-service-worker-version',
    apply: 'build',
    enforce: 'post',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir)
    },
    closeBundle() {
      const file = join(outDir, swPath)
      if (!existsSync(file))
        return

      const source = readFileSync(file, 'utf8')
      if (!source.includes(placeholder))
        return

      const version = typeof options.version === 'function'
        ? options.version()
        : options.version ?? new Date().toISOString().replace(/\D/g, '').slice(0, 17)
      writeFileSync(file, source.replaceAll(placeholder, version))
    },
  }
}
