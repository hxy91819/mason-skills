# 对比报告的图片对比格式

improving-mobile-product-ux 产出的 HTML 对比报告，逐项问题的修改前/修改后截图按本文件的组件与配对规则呈现。

## 组件选择规则

- **滑块对比（默认）**：修改前与修改后是同一页面、同一区域、近似同视口的截图时，用滑块组件把两张图叠加，拖动即在同一坐标系下对比。审计报告截图（390×844）与复查截图（393×852 / 402×874）宽高比差异 <1%，可直接配对；两档复查视口都存在时，手机滑块用 iPhone 16（393×852）这张，iPhone 17 的截图作为普通小图附在旁边。桌面回归也必须使用同一滑块组件，配对 `1920 × 1080` 的修改前／后截图。
- **并排小图**：整页长截图（fullPage）或修改前后取景范围不一致时，滑块对比没有意义，保持并排缩略图 + 点击放大。
- 每个问题至少有一组手机滑块和一组桌面滑块；无法配对时在该问题内说明原因，并提供同一状态的替代截图证据。

## 桌面回归证据

1. 在修改代码前，以相同路径、角色、数据、页面状态、滚动位置和缩放截取 `1920 × 1080` 浏览器视口基线。
2. 修改后用完全相同的条件再次截取；不要用 fullPage 图与 viewport 图配对。
3. 将两张桌面图放入现有 `.cmp` 滑块组件，保留 `.cmp-slider`、拖动手柄和“修改前／修改后”标签，不另造比较控件。
4. 在报告中明确写出桌面结论：桌面功能、信息层级、布局和交互没有被破坏；因本次改动产生的有意设计优化单独标注，不把它误报为回归。

## 滑块组件（直接复制，按需改 src/alt）

```html
<!-- 一处滑块对比 = 一个 .cmp；before 为底层全幅，after 由滑块控制裁剪宽度 -->
<div class="cmp">
  <div class="cmp-wipe">
    <img class="cmp-before" src="before.png" alt="修改前">
    <div class="cmp-clip"><img class="cmp-after" src="after.png" alt="修改后"></div>
    <span class="cmp-tag cmp-tag-l">修改前</span><span class="cmp-tag cmp-tag-r">修改后</span>
    <div class="cmp-handle"></div>
  </div>
  <input type="range" class="cmp-slider" min="0" max="100" value="50" aria-label="拖动对比修改前后">
</div>
```

```css
.cmp-wipe { position:relative; overflow:hidden; border:1px solid #dbe3ed; border-radius:10px; background:#fff; line-height:0; }
.cmp-wipe img { width:100%; display:block; }
/* after 覆盖层锚定右缘：左改前 / 右改后 */
.cmp-clip { position:absolute; top:0; right:0; bottom:0; overflow:hidden; width:50%; }
.cmp-clip img { position:absolute; top:0; right:0; height:100%; width:auto; max-width:none; }
.cmp-handle { position:absolute; top:0; bottom:0; left:50%; width:2px; background:#d61f69; }
.cmp-tag { position:absolute; top:8px; padding:2px 8px; border-radius:4px; background:rgba(15,23,42,.82); color:#fff; font-size:11px; font-weight:700; line-height:16px; }
.cmp-tag-l { left:8px; } .cmp-tag-r { right:8px; }
.cmp-slider { width:100%; margin:10px 0 0; accent-color:#d61f69; }
```

```js
// after 图按整幅宽度定位，滑块只改裁剪宽度，两幅图才严格同位可比
for (const cmp of document.querySelectorAll('.cmp')) {
  const slider = cmp.querySelector('.cmp-slider');
  const clip = cmp.querySelector('.cmp-clip');
  const handle = cmp.querySelector('.cmp-handle');
  const afterImg = cmp.querySelector('.cmp-clip img');
  const wipe = cmp.querySelector('.cmp-wipe');
  const fit = () => { afterImg.style.width = wipe.clientWidth + 'px'; };
  const move = () => {
    // 滑块值 = 分割线位置；after 覆盖层锚定右缘，宽度取补数
    clip.style.width = (100 - slider.value) + '%';
    handle.style.left = slider.value + '%';
  };
  slider.addEventListener('input', move);
  addEventListener('resize', fit);
  fit(); move();
}
```

注意：`.cmp-clip img` 的宽度必须在 JS 里锁为容器宽度（`fit()`），不能只在 CSS 写 `width:100%`——否则裁剪宽度变化时 after 图会跟着缩放，两图错位。
