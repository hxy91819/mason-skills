# 交互细节与去网页感

“像 App”不是换一套好看的颜色，而是把浏览器默认行为逐项收掉，同时保留用户真正需要的选择、复制和滚动。

## 下拉刷新

- 只在有列表或数据读取的页面开启。聊天、地图、横向表格等和下拉手势冲突的页面不开。
- 刷新回调调用页面已有的加载函数，并在 `finally` 里停止刷新；不要复制一份加载逻辑。
- 刷新时露出的是页面容器之外的画布，颜色要从根节点色板取，不能写死浅色。
- 刷新指示器如果是框架自带的白底，深色模式下要覆盖成卡片色，否则下拉时露白。
- 普通 Vue/React 没有原生下拉刷新时，可以用触摸序列 + `overscroll-behavior` 自建，或引入一个只做下拉刷新的轻量组件；不要为了下拉刷新引入整套 UI 框架。

## 边缘右滑返回

iOS 主屏幕模式没有系统返回手势。应用级补一个：

- 文档级监听 `touchstart` / `touchmove` / `touchend` / `touchcancel`，只安装一次。
- 起点在屏幕左缘 24px 内；水平向右超过 80px；方向锁定前（约 10px）如果竖向位移大于水平位移，立刻让位给页面滚动。
- 输入框聚焦、`contenteditable` 聚焦、从横向可滚动容器内起手、Tab 页、页面栈只有一页时跳过。
- 方向确认后，如果事件可取消，`preventDefault()` 阻止浏览器横向回弹；竖向监听保持 passive，不影响滚动。
- 返回动作由调用方注入（`enabled()` + `onBack()`），适配器不读路由配置。
- 普通 Vue/React 用 Router 的 `history.back()` 或 `navigate(-1)`；不要在适配器里 import Router。

## 滚动边界

```css
html, body { overscroll-behavior: none; }
.page-scroll, .uni-scroll-view { overscroll-behavior: contain; }
```

- 外层 `none` 防止滚动链把整个页面拖出外壳（iOS 回弹、Android 下拉刷新）。
- 内部滚动区 `contain` 让滚动在容器边界停止，不继续传给父级。
- 不要给所有元素设 `overflow: hidden` 来“解决”滚动；那会把正常页面滚动也杀掉。

## 文本选择与长按

```css
html, body { -webkit-tap-highlight-color: transparent; }
.theme-page {
  -webkit-touch-callout: none;
  -webkit-user-select: none;
  user-select: none;
}
.theme-page input,
.theme-page textarea,
.theme-page [contenteditable],
.theme-page .selectable-text {
  -webkit-touch-callout: default;
  -webkit-user-select: text;
  user-select: text;
}
```

- `user-select` 和 `touch-callout` 可继承，所以不要用 `*` 直接压到原生 `input`/`textarea`；那会让输入框失去原生选择行为。
- 明确标出可复制正文（聊天回答、规则说明、错误详情），给它们 `.selectable-text` 或等价类。
- 点击高亮只关 `-webkit-tap-highlight-color`，不要连带关掉 focus ring。

## 系统弹窗与主题

系统弹窗、Toast、ActionSheet 通常挂在 `body` 上，不在页面容器内。它们读不到页面容器上的主题变量。

- 把 `data-theme` 和整份色板写到 `document.documentElement`，弹窗样式统一读根变量。
- 覆盖框架弹窗的 `background-color`、文字色、分隔线、按下态；不要只改标题。
- 下拉刷新露出的画布和刷新指示器也读同一组变量。
- 深浅色切换时，根色板和 `meta[name=theme-color]` 一起变；不要只看 `prefers-color-scheme`。

## 输入语义

| 内容 | 属性 |
| --- | --- |
| 时间（含冒号） | 文本键盘，不强制 `type="time"` |
| 人数、数量 | `type="number"` + `inputmode="numeric"` |
| 搜索 | `inputmode="search"` + `enterkeyhint="search"` |
| 手机号 | `type="tel"` + `inputmode="tel"` |
| 邮箱 | `type="email"` + `inputmode="email"` |
| 下一项/完成 | `enterkeyhint="next"` / `enterkeyhint="done"` |

uni-app 的 `confirm-type` 映射到 `enterkeyhint`；普通 Vue/React 直接写 `enterkeyhint`。验收时读渲染后的 DOM 属性，不读源码。

## 动效与反馈

- Tab 切换用 160–200ms 淡入；子页从右侧推入 240–300ms；返回时反向。动效是空间关系的提示，不是装饰。
- 按钮按下缩放 0.98 或颜色变深，120ms 左右；不要给所有元素加 transition。
- 键盘焦点用 `:focus-visible` 画 outline，不要去掉默认焦点样式而不给替代。
- 尊重 `prefers-reduced-motion: reduce`，把动画和过渡压到接近 0。
- 页面切换动画只作用在页面根，不要给列表每项加进入动画；长列表会卡。

## 首屏与空状态

- 慢接口用骨架屏，骨架的宽高跟真实块走，颜色取主题的悬停/卡片色；不要用一张全屏 loading 图。
- 空状态用真实空文案，不要“正在读取”闪一下再变空列表。
- 首屏背景色、状态栏色、TabBar 色在 HTML/CSS 里先给默认值，运行时再按主题覆盖，避免白闪。
- 固定底栏、悬浮按钮、Toast 都要加底部安全区；不要假设 100vh 等于可用高度。

## 检查清单

- 下拉刷新只在列表页生效，深色下不露白。
- 子页左缘右滑能返回；Tab 页、页面中部、输入框聚焦、横向滚动容器内不误触。
- 页面滚到边界后，不会把整个外壳拖出回弹。
- 标题、按钮、TabBar 标签长按不弹系统菜单；聊天正文和规则说明可以长按复制。
- 系统弹窗、Toast、ActionSheet 在浅色/深色下都跟应用主题。
- 输入框的键盘类型和确认键语义正确。
- 首屏没有白闪，切换页面没有明显跳动，减少动效设置下动画基本消失。
