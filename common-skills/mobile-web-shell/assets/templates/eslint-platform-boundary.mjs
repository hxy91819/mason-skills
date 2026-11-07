/**
 * 平台适配层边界的 ESLint flat config 片段。
 *
 * 用法：
 *   import { platformBoundaryConfig } from './eslint-platform-boundary.mjs'
 *   export default [...baseConfig, ...platformBoundaryConfig()]
 *
 * 目录不同时传 { files, allowedFiles }；需要额外拦截的宿主属性传
 * { extraProps }；需要禁止的浏览器专用库传 { extraImports }。
 */

export const browserHostProps = [
  'window',
  'document',
  'navigator',
  'location',
  'visualViewport',
  'localStorage',
  'sessionStorage',
  'fetch',
  'history',
  'XMLHttpRequest',
]

const browserHostMessage = '浏览器宿主对象只能在平台适配层访问；业务侧请调用适配层函数'

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function platformBoundaryConfig(options = {}) {
  const files = options.files ?? ['src/platform/**']
  const allowedFiles = options.allowedFiles ?? files
  const props = [...new Set([...browserHostProps, ...(options.extraProps ?? [])])]
  const propPattern = props.map(escapeRegExp).join('|')

  return [
    {
      rules: {
        // 裸全局名在适配层也不允许，统一走 globalThis。
        'no-restricted-globals': [
          'error',
          ...props.map(name => ({ name, message: browserHostMessage })),
        ],
        // globalThis.xxx 能绕过 no-restricted-globals，这里把宿主属性一次拦住。
        'no-restricted-properties': [
          'error',
          ...props.map(property => ({
            object: 'globalThis',
            property,
            message: browserHostMessage,
          })),
        ],
        // 类型断言和方括号访问能绕过属性规则，一并把这两条路堵上。
        'no-restricted-syntax': [
          'error',
          {
            selector: `MemberExpression[object.type='TSAsExpression'][object.expression.name='globalThis'][property.name=/^(${propPattern})$/]`,
            message: browserHostMessage,
          },
          {
            selector: `MemberExpression[object.type='TSAsExpression'][object.expression.type='TSAsExpression'][object.expression.expression.name='globalThis'][property.name=/^(${propPattern})$/]`,
            message: browserHostMessage,
          },
          {
            selector: `MemberExpression[object.name='globalThis'][computed=true][property.value=/^(${propPattern})$/]`,
            message: browserHostMessage,
          },
        ],
        ...(options.extraImports
          ? {
              'no-restricted-imports': ['error', { paths: options.extraImports }],
            }
          : {}),
      },
    },
    {
      // 平台适配层是浏览器宿主对象的唯一入口。
      files: allowedFiles,
      rules: {
        'no-restricted-properties': 'off',
        'no-restricted-syntax': 'off',
      },
    },
  ]
}
