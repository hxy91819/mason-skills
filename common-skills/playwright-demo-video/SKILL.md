---
name: playwright-demo-video
description: 手动启动的 Playwright 验收与演示视频录制流水线：带虚拟光标与点击波纹、可视化文件上传、自动裁剪等待时间、TTS 旁白字幕与双端手机框合成。
disable-model-invocation: true
triggers:
  - user
---

# Playwright 验收与演示视频录制

仅在用户显式调用 `$playwright-demo-video` 时使用。用确定性 Playwright 脚本录制真实系统操作，配合虚拟光标、TTS 配音、样式化字幕与 ffmpeg 自动剪辑，产出适合发版前视觉验收或客户演示的 16:9 HD MP4。

核心分工：**大模型负责编写分镜与脚本，Playwright 负责确定性点击与录屏**（零推理等待、可重复出片）。

## 1. 准备独立工作目录与工具链

所有临时脚本、原始 `.webm`、中间切片和 Python 虚拟环境放在隔离目录（如 `/tmp/demo-recorder` 或会话 scratch 目录），不污染目标业务仓库。

- **Playwright**：直接复用目标项目已安装的 `@playwright/test`（通过 `createRequire` 加载），无须重复下载浏览器。
- **TTS 与 ffmpeg**（免 root、跨机可复现）：
  ```bash
  uv venv <work>/venv
  uv pip install --python <work>/venv/bin/python edge-tts imageio-ffmpeg pillow
  ```
  `imageio-ffmpeg` 自带支持 `ass` / `overlay` / `tpad` / `xfade` 滤镜的静态 `ffmpeg`。

本 Skill 自带三个可直接复制或引用的脚本（路径相对于已加载 Skill 根目录）：
- `scripts/cursor-helper.mjs`：虚拟光标、点击波纹、聚焦高亮、`DemoActor` 与 `TimelineRecorder`。
- `scripts/compose-video.py`：TTS 配音、`.ass` 字幕、章节标题卡、手机外框合成与防定格自动剪辑。
- `scripts/generate-demo-photos.py`：用 Pillow 生成清晰带标注的示例 JPG（避免上传 1×1 空白图导致缩略图不可辨）。

## 2. 编写分镜与录制脚本

先确认待录制的端到端节点、账号角色、视口形态（纯桌面、纯手机或桌面+手机接力）及测试数据策略（若目标为共享/UAT 环境，记录生成的测试单号，避免硬编码唯一约束字段如回路码/单号，优先沿用系统建议值或时间戳后缀）。

### 录制硬约束（防踩坑）

1. **虚拟光标与操作节奏**
   - 对每个 `BrowserContext` 调用 `await ctx.addInitScript(CURSOR_INIT_SCRIPT)`，确保跨跳转与刷新持续显示。
   - 关键导航、提交、状态切换按钮用 `actor.humanClick(locator)`（贝塞尔平滑移动 + 高亮框 + 点击波纹）；表单输入用 `actor.fastFill` / `actor.fastSelect` 快速填完，保持流畅节奏。
   - 避免对已在视口内的下拉浮层（React Popover / Autocomplete）强行 `scrollIntoViewIfNeeded()` 引发失焦卸载；`DemoActor.centerOf` 已内置视口检查。

2. **可视化文件上传（避免“上传时画面没变化”）**
   - 切勿把整个上传过程包进 `tl.skipWait`。用 `actor.humanUpload(...)` 或遵循四步：**滚动到槽位 → 游标移至可见按钮并高亮 → 仅对网络上传与确认调用 `tl.skipWait` → 确认后 `dwell(400)` 让缩略图与“已确认”标签清晰出现**。
   - 批量必拍上传（如 10–20 张）可视化演示前 2–3 张，其余用 `tl.skipWait` 静默批传，再滚动展示结果。

3. **只保留有效动作区间**
   - 每个镜头用 `tl.beginScene(id, { track, title, badge, narration, titleCard })` 声明；操作放在 `tl.record(actor, ...)` 中，页面跳转、API 响应等待、重加载等用 `tl.skipWait(actor, ...)` 跳过。
   - 切换上下文重新加载页面时，把 `page.goto(...)` 与就绪等待放在 `tl.record` 之前，天然零等待镜头。

4. **Playwright 录屏保存与排错顺序**
   - `catch` 中先打印原始异常并对每个页面拍错误截图（`error-desktop.png` / `error-mobile.png`），再于 `finally` 清理，防止 `finally` 吞掉根因。
   - 必须严格按顺序收尾：`await ctx.close()` → `await video.saveAs(path)` → `await browser.close()`；在 `browser.close()` 之后调用 `saveAs` 会报 `Target page, context or browser has been closed`。
   - 将 `desktopWallSec` / `mobileWallSec` 写入 `timeline.json` 的 `meta`，供合成器自动校准 WebM 实际时长与墙钟偏差。

## 3. 旁白编写与音画防定格对齐

- **旁白长度匹配动作**：按约 5 字/秒（`DEMO_TTS_RATE="+12%"`）控制每段旁白字数，使 `audio_dur` 接近该镜头剪裁后的 `raw` 动作时长。
- **合成命令**：
  ```bash
  <work>/venv/bin/python <skill_root>/scripts/compose-video.py <work>/timeline.json <output.mp4>
  ```
  常用环境变量：`DEMO_TTS_VOICE`（默认 `zh-TW-HsiaoChenNeural`，大陆普通话可用 `zh-CN-XiaoxiaoNeural` / `zh-CN-YunyangNeural`）、`DEMO_TTS_RATE`（默认 `+12%`）、`DEMO_FONT_NAME`（默认 `Noto Sans CJK TC`，简体环境可设为 `Noto Sans CJK SC`）。
- **检查防定格指标**：合成器会打印每段的 `raw`、`stretch`、`audio`、`freeze_pad` 与 `final`。它会自动对略短于旁白的画面做微幅放慢（最高 `1.38x` 时长）以保持游标持续运动；若仍有镜头 `freeze_pad > 2.0s`，精简该段旁白或补充结果页展示动作后重跑合成，不靠长时间定格硬凑。

## 4. 交付前视觉验收

生成 MP4 后必须抽帧检查，确认无黑屏、字幕遮挡、乱码或排版错位：
```bash
<work>/venv/bin/python <skill_root>/scripts/compose-video.py <work>/timeline.json <output.mp4> --verify-dir <work>/verify
```
用图片读取工具抽查片头卡、桌面端操作、手机端外框排版、上传后缩略图及终态画面，并核对终端输出的视音轨流信息，全部通过后再交付成片路径与测试数据清理说明。
