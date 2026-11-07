# 键盘与视口

## iOS 的视口模型

iOS 弹出软键盘时，通常**不缩小布局视口**（layout viewport，`innerWidth/innerHeight` 基本不变），只缩小**可见视口**（visual viewport）。可见视口还可能整体上推，`visualViewport.offsetTop` 大于 0。

后果：

- 框架导航栏、TabBar 和所有 `position: fixed` 元素跟着布局视口走，会被键盘盖住，或者被推出屏幕。
- 只用 `window.innerHeight` 算高度，键盘打开后输入框仍然在键盘下面。
- 只用 `visualViewport.height` 而不加 `offsetTop`，页面顶部会错位。

正确做法：键盘打开时，贴键盘的容器使用可见区域坐标：

```ts
top = visualViewport.offsetTop
height = visualViewport.height
insetBottom = innerHeight - visualViewport.offsetTop - visualViewport.height
```

`insetBottom` 是键盘盖住布局视口底部的高度。底部弹窗用它把底边抬到可见区域底边，而不是把整个弹窗往上推一个固定值。

## 判断键盘是否打开

不要听到 `resize` 就认为键盘打开了：地址栏收起、页面缩放、横竖屏切换、浏览器分屏都会触发 `resize`。一个够用的判断：

```ts
const editing = document.activeElement?.tagName === 'TEXTAREA'
  || document.activeElement?.tagName === 'INPUT'

open = matchMedia('(pointer: coarse)').matches
  && visualViewport.scale === 1
  && (editing || previouslyOpen)
  && baseline - visualViewport.height > 120
```

- `pointer: coarse` 排除桌面鼠标环境；桌面浏览器拉窗口也会让 `innerHeight` 变小。
- `scale === 1` 排除双指缩放；缩放时可见区域也会变小。
- 必须有输入框聚焦，或键盘已经处于打开状态；否则浏览器栏变化会被误判。
- 120px 是经验阈值，能过滤大多数浏览器栏和地址栏变化；不同机型可以调，但不要降到几十像素。
- `baseline` 在键盘关闭时跟随 `innerHeight` 更新；键盘打开期间不要更新，否则阈值会漂移。

监听 `visualViewport` 的 `resize` / `scroll`、`window` 的 `resize`、文档的 `focusin` / `focusout`。`scroll` 事件用于捕获 `offsetTop` 变化；只监听 `resize` 会漏掉可见区域上推。

## 布局

- 键盘打开时隐藏 TabBar，收起大页头，把可见区域留给内容和输入框。TabBar 不隐藏会被键盘顶到屏幕外，或者盖住输入区。
- 整页铺满用 `height: 100dvh`，保留 `100vh` 作为回退。`dvh` 会跟随动态视口变化；这是“禁止 `vh`”的唯一合理例外。
- 整页输入页的根容器在键盘打开时用 `position: fixed` + `top: offsetTop` + `height: visualViewport.height`，并自己让出 `env(safe-area-inset-top)`。不要叠加框架导航栏的 `--window-top`。
- 键盘关闭后恢复原布局，保留输入内容。程序化跳转离开输入页时，也要恢复其他页面的 TabBar；不要在页面 `onUnmounted` 里假设键盘已经收起。

## uni-app 的 `--window-top` 陷阱

uni-app H5 在 `navigationStyle: custom` 下，`--window-top` 仍然可能不是 0。它表示框架认为的窗口顶部偏移，不等于键盘打开时的 `visualViewport.offsetTop`。

错误做法：

```ts
top = visualViewport.offsetTop + windowTop
```

键盘把可见区域上推时，这会多减一条导航栏高度，状态栏下出现一条空带，输入区也被顶高。正确做法是键盘打开时只用 `visualViewport.offsetTop`，导航栏在键盘打开时本来就应该隐藏或盖住。

普通 Vue/React 没有 `--window-top`，但同样不要把 `innerHeight`、`offsetTop` 和固定导航栏高度混着加。

## 表单与底部弹窗

- 普通表单优先放文档流，让页面自己滚动。把输入框放在固定底栏，键盘一弹就要处理“底栏、键盘、滚动位置”三套坐标。
- 底部弹窗（bottom sheet）内含输入框时：
  - 用 `insetBottom` 把弹窗底边抬到可见区域底边；
  - 弹窗最大高度不超过 `visualViewport.height`；
  - 确认按钮留在弹窗底部，不要放在输入框下方远处；
  - 键盘弹出后，输入框和确认按钮都必须在可见区域内。
- 必须在 iPhone 真机验证。浏览器模拟 `visualViewport` 只能验证代码读取的坐标，模拟不出 iOS 把布局视口上推、键盘动画和系统表单辅助栏。

## 输入语义

按内容选键盘，不要一律 `type="text"`：

| 内容 | 建议 |
| --- | --- |
| 时间（含冒号） | 保留文本键盘，避免原生 time picker 改变输入格式 |
| 人数、数量 | `type="number"` + `inputmode="numeric"` |
| 搜索 | `inputmode="search"` + `enterkeyhint="search"` |
| 手机号 | `type="tel"` + `inputmode="tel"` |
| 邮箱 | `type="email"` + `inputmode="email"` |
| 下一项/完成 | `enterkeyhint="next"` / `enterkeyhint="done"` |

uni-app 的 `confirm-type` 会映射为 `enterkeyhint`；普通 Vue/React 直接写 `enterkeyhint`。验收时断言渲染后的 `inputmode`、`type`、`enterkeyhint`，不要只检查源码里的属性。

## 测试手法

在 Playwright 里注入可控的 `visualViewport`：

```ts
await page.addInitScript(() => {
  const viewport = new EventTarget()
  Object.assign(viewport, { height: 852, offsetTop: 0, scale: 1 })
  Object.defineProperty(globalThis, 'visualViewport', { value: viewport, configurable: true })
})
```

打开输入框后分别设 `offsetTop = 0` 和 `35`，派发 `resize`：

```ts
await page.evaluate((offsetTop) => {
  Object.assign(globalThis.visualViewport!, { height: 460, offsetTop })
  globalThis.visualViewport!.dispatchEvent(new Event('resize'))
}, offsetTop)
```

断言：

- 输入区底边 `y + height` 等于 `offsetTop + 460`（允许 2px 误差）。
- 页面根顶边等于 `offsetTop`，状态栏下没有导航栏空带。
- TabBar 隐藏，输入内容保留，发送按钮可见。
- 键盘关闭后 TabBar 恢复；程序化跳到其他页面时也要恢复。

完整骨架见 `assets/templates/e2e/keyboard-layout.spec.ts`。

## 已知不可修复

iOS 键盘上方的 ∧ ∨ ✓ 表单辅助栏由 WebKit 绘制，网页没有受支持的 API 可以隐藏。`autocomplete`、`autocorrect`、输入类型只影响填充、纠错和键盘类型，不承诺隐藏整栏。不要为此写兼容代码，也不要在交付说明里把它算成缺陷。
