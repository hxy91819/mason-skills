# Web Push

## 能力矩阵

| 条件 | 结果 |
| --- | --- |
| 浏览器没有 `PushManager` / `Notification` / `serviceWorker` | 不支持 |
| 非安全上下文（`isSecureContext === false`） | 需要 HTTPS |
| iOS/iPadOS 且不是主屏幕 standalone | 先“添加到主屏幕” |
| iOS 版本低于 16.4 | 不支持 |
| 服务端未配置 VAPID | 服务端未启用，开关不可用 |
| 权限 `denied` | 被拒绝，引导去系统设置 |
| 权限 `granted` 且已有订阅 | 已订阅，可关闭 |
| 权限 `granted` 且无订阅 | 未订阅，可开启 |

iOS 的 `isIos()` 要同时识别 `iPhone|iPad|iPod` 和 “Macintosh + `maxTouchPoints > 1`” 的 iPadOS 桌面模式。`isStandalone()` 先看 `matchMedia('(display-mode: standalone)')`，再看 iOS Safari 的非标准 `navigator.standalone`。

## 状态机

把权限、能力、服务端开关和订阅状态翻译成页面状态，不要把这些分支散落在模板里：

```ts
type PushUiStatus =
  | 'unsupported'
  | 'ios-install-required'
  | 'insecure-context'
  | 'server-disabled'
  | 'permission-denied'
  | 'subscribed'
  | 'unsubscribed'
  | 'demo-disabled'
```

`resolvePushUiState()` 是纯函数，输入能力、服务端开关、权限、是否已订阅、是否演示模式，输出 `{ status, canToggle, switchValue, description }`。这样可以在 Node 单测里覆盖所有分支，不需要伪造整个浏览器。

## 订阅流程

1. 读能力；不支持就停，给出原因。
2. 校验 VAPID 公钥非空；缺失时报“通知公钥缺失”。
3. 权限 `denied` 直接报错；`default` 时调用 `Notification.requestPermission()`；仍未授予就停。
4. 等 `navigator.serviceWorker.ready`，加超时（例如 8 秒），避免后台未就绪时无限等待。
5. `registration.pushManager.getSubscription()`；已有订阅直接复用，保证幂等。
6. 没有订阅时 `subscribe({ userVisibleOnly: true, applicationServerKey })`。公钥是 base64url，要转成 `Uint8Array`，不要直接传字符串。
7. 把 `endpoint`、`keys.p256dh`、`keys.auth` 交给服务端；字段不全时抛错，不要提交半条订阅。

取消订阅：先 `subscription.unsubscribe()`，成功后把原 `endpoint` 交给服务端删除。服务端删除失败时，浏览器已经退订；下次开启会生成新 endpoint，旧记录需要服务端清理策略。

## Service Worker

`push` 事件：

- 只接受字符串字段：`title`、`body`、`url`、`tag`、`icon`、`badge`。
- `url` 只接受以 `/` 开头的站内路径；其他值回退默认页。
- 用 `tag` 替换同一业务对象的重复通知，避免后端至少一次投递产生多个气泡。
- 必须 `event.waitUntil(self.registration.showNotification(...))`。

`notificationclick`：

1. `event.notification.close()`。
2. 取 `notification.data.url`，仍只接受站内路径。
3. `clients.matchAll({ type: 'window', includeUncontrolled: true })`。
4. 已有同源窗口：`focus()`；需要时 `navigate(target)`。
5. 没有窗口：`clients.openWindow(target)`。

## VAPID

- `VAPID_PUBLIC_KEY`、`VAPID_PRIVATE_KEY`、`VAPID_SUBJECT` 三项要么全填、要么全空。
- `VAPID_SUBJECT` 用 `mailto:` 或 `https://`。
- 服务端未启用时，前端显示“服务端未启用”，不要报错，也不要把开关做成可点但无效。
- 密钥只放在服务端环境变量，前端只拿公钥。

## 测试

### 订阅 UI

- 用 Playwright 的 `context.grantPermissions(['notifications'], { origin })` 授予权限。
- 用 `addInitScript` 替换 `PushManager.prototype.getSubscription` / `subscribe`，返回固定订阅；这样不依赖外部 FCM/APNs。
- mock `/api/push/public-key`、`POST /api/push/subscriptions`、`DELETE /api/push/subscriptions?endpoint=...`，断言请求体和删除的 endpoint。
- 覆盖：不支持、iOS 未安装、服务端关闭、权限拒绝、已订阅、未订阅。

### Service Worker 推送

- 用系统 Chromium 的 headless 模式（Playwright `channel: 'chromium'`）；默认 headless shell 不提供通知权限。
- 开 CDP `ServiceWorker.enable`，等 `workerRegistrationUpdated` 拿到 `registrationId`。
- 发 `ServiceWorker.deliverPushMessage`：

```ts
await cdp.send('ServiceWorker.deliverPushMessage', {
  origin,
  registrationId,
  data: JSON.stringify({ title: '新内容', body: '点击查看', url: '/#/home', tag: 'item-1' }),
})
```

- 用 `registration.getNotifications()` 断言标题、正文、`data.url`。
- 点击通知的行为在 headless 里不容易真实触发；至少单测 `notificationclick` 的 URL 校验和窗口选择逻辑。

### 真机边界

以下必须真机验证，浏览器模拟不能替代：

- iOS 主屏幕安装后的 standalone 外壳与通知权限。
- 真实 APNs/FCM 送达、系统通知样式、点击后唤起应用。
- 通知权限被拒绝后，从系统设置重新开启的路径。
- 国内网络下推送服务的可达性。

## 测试骨架

`assets/templates/e2e/` 没有包含完整的 web-push 骨架，因为它高度依赖后端契约。实现时按上面的 mock 和 CDP 手法写，至少覆盖“订阅 UI 状态机”和“SW 展示通知”两条。
