#!/usr/bin/env python3
"""把一轮 PPT 版式验收渲染成单文件 HTML 报告：问题卡（红框标注 + 前后对照滑块）+ 逐页覆盖记录。

报告形态：
  - 所有区块默认折叠（details），顶部提供「全部展开 / 全部收起」，方便逐块审查。
  - 「问题与修复」是主结构：每个 finding 一张卡。卡上半部是红框标注截图
    （box 圈出问题位置 + 短标签 label + 一句话说明 short），下半部是该问题的
    改前/改后对照滑块图（一个图框内竖条切换，仅当两图都真实存在才渲染）。
  - 「逐页覆盖记录」每页一卡：逐页观察、页级 before/after 对照（页级复验用）与标尺图。

输入 `--data <json>`：

    {
      "target": "/abs/deck.html",
      "mode": "review",                        // review | fix；默认 review
      "status": "reviewed",                    // reviewed | fixed | clean | incomplete
      "pageCount": 1,                          // 实际总页数，不是已截图数
      "contract": {"页画布": "1920x1080", "页边距": "82px", "区块间隔": "28px"},
      "commands": [{"cmd": "node measure-deck.js ...", "result": "采集 1 页 plain/ruler；视觉结论见逐页观察"}],
      "pages": [
        {"id": "p1", "title": "发布验收",
         "before": "/tmp/x/before-p1.png",
         "beforeRuler": "/tmp/x/before-p1-ruler.png",
         "review": {"before": "1920x1080 演示视口：右上角验收表缩至 240px 宽，放行状态无法辨认；打开原图放大后可读。页眉版本标识和主标题均清晰。",
                    "interaction": "本页为静态标题和验收表，没有可操作控件；交互检查不适用。"}}
      ],
      "findings": [
        {"id": "V2", "severity": "blocking", "kind": "readability", "page": "p1",
         "title": "关键验收表在投影尺度无法读出放行状态",
         "short": "验收表缩至 240px，放行状态不可辨。",            // 一句话说明，缺省用 title
         "label": "验收表 240px",                                   // 红框旁短标签，缺省用 id
         "img": "/tmp/x/before-p1.png",                             // 红框坐标空间所指截图，缺省该页 before
         "box": [918, 60, 300, 180],                                // 红框像素坐标 [x,y,w,h]；或 boxPct:[l,t,w,h]
         "why": "验收表是判断能否发布的唯一证据，字段名与状态都不可辨；放大原图可读不能补足演示画面缺口。",
         "before": "验收表显示宽度 240px；投影视口 1920x1080",
         "fix": "建议扩大现有验收表的显示尺寸，利用主区空间呈现结果列；复验时在同一投影视口能直接辨认字段名和放行状态。本轮只读，尚未执行。",
         "where": "deck.html:191 .acceptance-shot", "resolution": "open",
         "beforeImg": "/tmp/x/before-p1.png", "afterImg": null}     // 该问题对照图；缺省回落页级 before/after
      ],
      "kept": [{"what": "页眉版本标识与主标题之间的留白", "why": "图上空带把版本信息与本页判断分组，避免将版本标识读成验收结论；两组文字在投影尺度均可辨，留白没有遮挡证据。"}],
      "pending": ["尚待制作方确认的事项；非空时不能 clean/fixed"],
      "limits": ["..."]
    }

target、pages（非空、唯一 id）及每页 before 必填；after 可省略，此时只展示现状。
beforeRuler/afterRuler 可分别省略，绝不互相代替。resolution 为 open（默认）/fixed/kept；
fixed 要有实际 fix，kept 要有 resolutionReason，待制作方执行的建议保持 open。
mode=fix 或旧格式 status=fixed 表示本轮有修改，缺 after 的页明确标为未复验。
缺 pageCount、逐页 review.before/interaction、修复后的 after/review.after，或存在 limits 时，
状态降为 incomplete；有未处理 findings 时不能宣称 clean/fixed。默认只读，无发现且证据齐全
才是 clean，否则为 reviewed。观察文字是审查者的证据记录，脚本无法证明 Agent 真的看过图。
旧字段仍可读取；旧数据缺覆盖记录时报告会说明缺口，不追认旧审查为完整验收。

finding 新字段（均可选，向后兼容）：box / boxPct（红框坐标，像素或百分比）、label（短标签）、
short（一句话说明）、img（标注所用截图）、beforeImg/afterImg（该问题对照图，缺省回落页级）。
红框坐标基于 img 指向截图的像素空间；box 无效（非数字、w/h<=0）时记入 limits 并省略红框，不猜坐标。
对照滑块只在改前改后两张图都真实存在时渲染，缺 afterImg 只显示红框现状，不伪造改后图。

图片按路径读取并内嵌成 data URI，同一文件只内嵌一次；
装了 Pillow 时缩到 `--max-width` 并转 JPEG（单文件报告控制在几 MB），没装就原样内嵌 PNG。
红框百分比换算优先读 PNG 头，其次 Pillow；两者都不可用时该 finding 降级为纯文字并在 limits 说明。
引用的图片缺失或 Pillow 解码失败时退出 3，不覆盖已有报告；无 Pillow 时必须在浏览器核对解码。
参数错误退出 2，成功退出 0。
--check 只读校验并打印 JSON 聚合（覆盖页数、未处理数、真实状态及缺口），不写报告。

用法：
  build-report.py --data findings.json --out /tmp/ppt-visual-review/report.html [--max-width 1600]
  build-report.py --data findings.json --check
"""

import argparse
import base64
import html
import io
import json
import pathlib
import sys
from string import Template

SEV = {
    "blocking": ("阻断", "#d92d20"),
    "should": ("应改", "#d97706"),
    "optional": ("可选", "#2563eb"),
}
RES = {"open": "待处理", "fixed": "已修复", "kept": "保留"}
KIND = {
    "rhythm": "节奏",
    "cross-page": "跨页一致",
    "slack": "留白",
    "symmetry": "对称",
    "scale": "档位",
    "readability": "投影可读性",
    "evidence": "证据可见性",
    "correspondence": "图文对应",
    "comparison": "比较对象",
    "interaction": "交互",
    "connector": "连接符对齐",
    "overflow": "截断溢出",
    "image": "图片质量",
    "occlusion": "遮挡",
    "contrast": "对比度",
    "font": "字体",
}


def data_uri(path: pathlib.Path, max_width: int) -> str:
    raw = path.read_bytes()
    try:
        from PIL import Image  # 可选依赖：把整页截图缩到报告能随手转发的体积
    except ImportError:
        return "data:image/png;base64," + base64.b64encode(raw).decode()
    img = Image.open(io.BytesIO(raw))
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, max(1, round(img.height * ratio))), Image.LANCZOS)
    # 整页截图是不透明的大幅版面图，PNG 无损会让单文件报告涨到几十 MB；JPEG 在这个尺寸下文字仍清晰。
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=82, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def image_size(path: pathlib.Path):
    """读截图像素尺寸：先解析 PNG IHDR（无依赖），失败再用 Pillow，都没有返回 None。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(33)
        if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
            return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    except OSError:
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def esc(v) -> str:
    return html.escape("" if v is None else str(v))


def box_pct(finding, img_path, fid, problems):
    """把红框坐标换算成 left/top/width/height 百分比；无效输入记入 problems 并返回 None，不猜坐标。"""
    raw = finding.get("boxPct")
    if raw is None and finding.get("box") is not None:
        size = image_size(pathlib.Path(img_path)) if img_path else None
        if not size:
            problems.append(f"finding {fid}: box 坐标需要 {img_path} 的像素尺寸，但无法读取（无 Pillow 且非 PNG），红框已省略")
            return None
        try:
            x, y, w, h = (float(v) for v in finding["box"])
        except (TypeError, ValueError):
            problems.append(f"finding {fid}: box 必须是 [x,y,w,h] 数字，红框已省略")
            return None
        raw = [x / size[0] * 100, y / size[1] * 100, w / size[0] * 100, h / size[1] * 100]
    if raw is None:
        return None
    try:
        left, top, width, height = (float(v) for v in raw)
    except (TypeError, ValueError):
        problems.append(f"finding {fid}: boxPct 必须是 [l,t,w,h] 数字，红框已省略")
        return None
    # 先钳制到画布内，再检查尺寸：超界框钳制后可能变成零尺寸，同样视为无效。
    left, top = max(0.0, min(left, 100.0)), max(0.0, min(top, 100.0))
    width, height = min(width, 100.0 - left), min(height, 100.0 - top)
    if width <= 0 or height <= 0:
        problems.append(f"finding {fid}: 红框必须在截图内且宽高大于 0，红框已省略")
        return None
    return left, top, width, height


# 对照滑块：图框内竖条切换改前/改后；直接拖图内竖条或下方滑杆都能移动分界。
COMPARE = Template("""
  <div class="controls">
    $rulerControl
    <label><input type="checkbox" class="side"> 并排</label>
    <span class="hint">拖动图内竖条或下方滑杆：左侧改前 / 右侧改后</span>
  </div>
  <div class="compare">
    <div class="wipe">
      <img class="img-before" src="$before" alt="$pid 改前">
      <div class="after-clip"><img class="img-after" src="$after" alt="$pid 改后"></div>
      <span class="tag l">改前</span><span class="tag r">改后</span>
      <div class="handle"></div>
    </div>
    <input type="range" class="slider" aria-label="$pid 改前改后分界" min="0" max="100" value="50">
  </div>
  <div class="sbs">
    <figure><img class="img-before" src="$before" alt="$pid 改前"><figcaption>改前</figcaption></figure>
    <figure><img class="img-after" src="$after" alt="$pid 改后"><figcaption>改后</figcaption></figure>
  </div>
  $rulers
""")

FINDING_BLOCK = Template("""
<details class="fold finding" data-sev="$sev">
  <summary><span class="sev" style="background:$color">$sevLabel</span>
    <code class="fid">$fid</code> <span class="fpage mono">$fpage</span>
    <span class="ftitle">$title</span>
    <span class="res res-$res">$resLabel</span></summary>
  <div class="fbody">
    $annotated
    $short
    $compare
    <details class="detail"><summary>完整分析与处理记录</summary>
      <p class="why">$why</p>
      $delta
      <p class="fixline"><b>建议 / 实际改动：</b>$fix</p>
      <p class="mono">$where</p>
      <p>处理状态：$resText$reason</p>
    </details>
  </div>
</details>
""")

PAGE_BLOCK = Template("""
<details class="fold page" data-page="$pid">
  <summary><span class="pid mono">$pid</span> $title <span class="pmeta">$meta</span></summary>
  <div class="fbody">
    $review
    $content
  </div>
</details>
""")

DOC = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PPT 版式视觉验收 · $targetName</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --line:#e4e6eb; --text:#1a1d21; --muted:#6b7280; --ok:#059669; --red:#d92d20; }
  * { box-sizing: border-box; }
  body { margin:0; padding:32px 20px 80px; background:var(--bg); color:var(--text);
         font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
  main { max-width: 1180px; margin: 0 auto; }
  h1 { font-size:24px; margin:0 0 6px; }
  h2 { font-size:18px; margin:40px 0 14px; padding-bottom:8px; border-bottom:1px solid var(--line); }
  .sub { color:var(--muted); font-size:13px; margin:0 0 24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin-bottom:14px; }
  .status { display:inline-block; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:700; color:#fff; background:var(--ok); }
  dl.kv { display:grid; grid-template-columns:150px 1fr; gap:8px 16px; margin:0; }
  dl.kv dt { color:var(--muted); font-size:13px; }
  dl.kv dd { margin:0; }
  code, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }
  .sev { display:inline-block; min-width:38px; padding:2px 8px; border-radius:4px; color:#fff; font-size:12px; font-weight:700; text-align:center; }
  .delta { white-space:nowrap; }
  .delta b { color:var(--ok); }
  /* 折叠块：默认收起；summary 是唯一展开入口。 */
  details.fold { background:var(--card); border:1px solid var(--line); border-radius:10px; margin-bottom:12px; }
  details.fold > summary { cursor:pointer; list-style:none; display:flex; gap:10px; align-items:center;
                           padding:12px 16px; font-size:14.5px; }
  details.fold > summary::-webkit-details-marker { display:none; }
  details.fold > summary::before { content:"\\25B8"; color:var(--muted); transition:transform .15s; flex:none; }
  details.fold[open] > summary::before { transform:rotate(90deg); }
  details.fold > summary:hover { background:#fafbfc; }
  details.fold > .fbody { padding:2px 16px 16px; border-top:1px solid var(--line); }
  .ftitle { flex:1; }
  .fpage { color:var(--muted); flex:none; }
  .res { flex:none; font-size:12px; padding:2px 8px; border-radius:12px; font-weight:700; }
  .res-open { background:#fdecea; color:var(--red); }
  .res-fixed { background:#e7f6ef; color:var(--ok); }
  .res-kept { background:#eef1f4; color:var(--muted); }
  .toolbar { display:flex; gap:10px; margin:0 0 14px; }
  .toolbar button { border:1px solid var(--line); background:#fff; border-radius:8px; padding:6px 14px;
                    font-size:13px; cursor:pointer; }
  .toolbar button:hover { background:#f2f4f7; }
  /* 红框标注：框住问题位置，短标签说明，不用大段文字。 */
  .annotated { position:relative; margin:0 0 10px; line-height:0; border:1px solid var(--line); }
  .annotated img { width:100%; display:block; }
  .rbox { position:absolute; border:3px solid var(--red); border-radius:4px;
          box-shadow:0 0 0 1px rgba(255,255,255,.65); pointer-events:none; }
  .rlabel { position:absolute; left:-3px; top:-28px; background:var(--red); color:#fff; font-size:12.5px;
            font-weight:700; line-height:1.5; padding:2px 9px; border-radius:4px; white-space:nowrap; }
  .rbox.below .rlabel { top:auto; bottom:-28px; }
  .short { margin:0 0 10px; font-size:14px; }
  .short .mk { color:var(--red); font-weight:700; }
  details.detail { border:1px solid var(--line); border-radius:8px; margin:0 0 12px; background:#fafbfc; }
  details.detail > summary { cursor:pointer; padding:8px 12px; font-size:13px; color:var(--muted); }
  details.detail[open] > summary { border-bottom:1px solid var(--line); }
  details.detail > p { padding:0 12px; margin:10px 0; font-size:13.5px; }
  .why { white-space:pre-wrap; color:#3f4753; }
  .fixline { white-space:pre-wrap; }
  .controls { display:flex; gap:18px; align-items:center; margin-bottom:10px; font-size:13px; color:var(--muted); flex-wrap:wrap; }
  .controls label { display:inline-flex; gap:6px; align-items:center; cursor:pointer; }
  .compare { margin-top:6px; }
  .wipe { position:relative; overflow:hidden; border:1px solid var(--line); background:#fff; line-height:0;
          touch-action:none; cursor:col-resize; }
  .wipe img { width:100%; display:block; user-select:none; -webkit-user-drag:none; }
  /* 整图保持同位，只裁去左侧；百分比布局在隐藏、恢复和 resize 后仍由浏览器求值。 */
  .after-clip { position:absolute; inset:0; clip-path:inset(0 0 0 var(--split, 50%)); }
  .after-clip img { height:100%; }
  .handle { position:absolute; top:0; bottom:0; left:50%; width:2px; background:#d61f69; }
  .handle::after { content:""; position:absolute; top:50%; left:-9px; width:20px; height:20px; transform:translateY(-50%);
                   border-radius:50%; background:#d61f69; border:2px solid #fff; box-shadow:0 1px 4px rgba(0,0,0,.3); }
  .tag { position:absolute; top:8px; padding:2px 8px; background:rgba(26,29,33,.82); color:#fff; font-size:11px; font-weight:700; line-height:16px; }
  .tag.l { left:8px; } .tag.r { right:8px; }
  .slider { width:100%; margin:10px 0 0; }
  .sbs { display:none; grid-template-columns:1fr 1fr; gap:12px; }
  .sbs figure { margin:0; }
  .sbs img { width:100%; display:block; border:1px solid var(--line); }
  .sbs figcaption { color:var(--muted); font-size:12px; padding-top:6px; }
  .is-side .compare { display:none; }
  .is-side .sbs { display:grid; }
  .rulers { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }
  .rulers[hidden] { display:none; }   /* display:grid 会盖掉 hidden，标尺图默认要收起 */
  .rulers img { width:100%; display:block; border:1px solid var(--line); }
  .current { margin:0; }
  .current img { width:100%; display:block; }
  .current figcaption, .annotated figcaption { color:var(--muted); font-size:12px; padding-top:6px; line-height:1.5; }
  .review { white-space:pre-wrap; color:var(--muted); font-size:13px; margin:0 0 10px; }
  .pmeta { color:var(--muted); font-size:12.5px; flex:none; }
  .status.incomplete, .status.reviewed { background:#9a6700; }
  ul.plain { margin:0; padding-left:18px; }
  ul.plain li { margin-bottom:6px; }
</style>
</head>
<body>
<main>
  <h1>PPT 版式视觉验收 · $targetName</h1>
  <p class="sub"><span class="status $status">$statusText</span> &nbsp;$modeText &nbsp;·&nbsp; 被审文件 <code>$target</code> &nbsp;·&nbsp; 展示 $pageCount 页 &nbsp;·&nbsp; $generated</p>

  $summary
  <div class="toolbar">
    <button type="button" id="expand-all">全部展开</button>
    <button type="button" id="collapse-all">全部收起</button>
  </div>
  $contract
  <h2>问题与修复</h2>
  $findings
  <h2>逐页覆盖记录</h2>
  $pages
  $kept
  $pending
  $commands
  $limits
</main>
<script>
  const setSplit = (cmp, value) => {
    const pct = Math.max(0, Math.min(100, Number(value) || 0));
    cmp.style.setProperty('--split', pct + '%');
    const handle = cmp.querySelector('.handle');
    if (handle) handle.style.left = pct + '%';
    const left = cmp.querySelector('.tag.l'), right = cmp.querySelector('.tag.r');
    if (left) left.hidden = pct <= 0;
    if (right) right.hidden = pct >= 100;
  };
  for (const cmp of document.querySelectorAll('.cmp')) {
    const slider = cmp.querySelector('.slider');
    if (!slider) continue;
    slider.addEventListener('input', () => setSplit(cmp, slider.value));
    const wipe = cmp.querySelector('.wipe');
    if (wipe) {
      // 图框内直接拖动竖条；同时保留下方滑杆的键盘可达操作。
      let dragging = false;
      const move = (event) => {
        const rect = wipe.getBoundingClientRect();
        const pct = (event.clientX - rect.left) / rect.width * 100;
        slider.value = Math.round(Math.max(0, Math.min(100, pct)));
        setSplit(cmp, slider.value);
      };
      wipe.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        dragging = true;
        try { wipe.setPointerCapture(event.pointerId); } catch {}
        move(event);
      });
      wipe.addEventListener('pointermove', (event) => { if (dragging) move(event); });
      for (const type of ['pointerup', 'pointercancel']) {
        wipe.addEventListener(type, () => { dragging = false; });
      }
    }
    setSplit(cmp, slider.value);
  }
  for (const card of document.querySelectorAll('.fold')) {
    card.querySelector('.side')?.addEventListener('change', (e) => card.classList.toggle('is-side', e.target.checked));
    card.querySelector('.ruler')?.addEventListener('change', (e) => {
      const rulers = card.querySelector('.rulers');
      if (rulers) rulers.hidden = !e.target.checked;
    });
  }
  document.getElementById('expand-all')?.addEventListener('click', () => {
    document.querySelectorAll('details').forEach((d) => { d.open = true; });
  });
  document.getElementById('collapse-all')?.addEventListener('click', () => {
    document.querySelectorAll('details').forEach((d) => { d.open = false; });
  });
</script>
</body>
</html>
""")


def review_summary(data: dict) -> dict:
    pages = data.get("pages")
    if not data.get("target") or not isinstance(pages, list) or not pages:
        raise ValueError("target 和非空 pages 必填")
    ids = [p.get("id") for p in pages]
    if any(not isinstance(pid, str) or not pid.strip() for pid in ids) or len(set(ids)) != len(ids):
        raise ValueError("每页必须有唯一的非空 id")
    requested = data.get("status")
    if requested not in (None, "reviewed", "fixed", "clean", "incomplete"):
        raise ValueError("status 必须是 reviewed/fixed/clean/incomplete")
    mode = data.get("mode", "fix" if requested == "fixed" else "review")
    if mode not in ("review", "fix") or (requested == "fixed" and mode != "fix"):
        raise ValueError("mode 必须是 review/fix；status=fixed 需要 mode=fix")
    limits = list(data.get("limits", []))
    expected = data.get("pageCount")
    if type(expected) is not int or expected < 1 or expected != len(pages):
        limits.append(f"实际总页数未核对：pageCount={expected}，已提供 {len(pages)} 页")
    examined = 0
    for p in pages:
        review = p.get("review", {})
        needed = ["before", "interaction"] + (["after"] if mode == "fix" else [])
        missing = [key for key in needed if not isinstance(review.get(key), str) or not review[key].strip()]
        if mode == "fix" and not p.get("after"):
            missing.append("after 截图")
        if missing:
            limits.append(f"{p['id']} 未完成视觉复核：{', '.join(missing)}")
        else:
            examined += 1
    findings = data.get("findings", [])
    unresolved = 0
    for f in findings:
        if f.get("severity") not in SEV:
            raise ValueError(f"finding {f.get('id')}: severity 必须是 blocking/should/optional")
        resolution = f.get("resolution", "open")
        if resolution not in ("open", "fixed", "kept"):
            raise ValueError(f"finding {f.get('id')}: resolution 必须是 open/fixed/kept")
        resolved = ((resolution == "fixed" and mode == "fix" and bool(f.get("fix"))) or
                    (resolution == "kept" and bool(f.get("resolutionReason"))))
        unresolved += not resolved
    if limits or requested == "incomplete":
        status = "incomplete"
    elif unresolved or data.get("pending") or requested == "reviewed":
        status = "reviewed"
    elif mode == "fix" and any(f.get("resolution") == "fixed" and f.get("fix") for f in findings):
        status = "fixed"
    else:
        status = "clean"
    return {"mode": mode, "status": status, "pages": len(pages), "expectedPages": expected,
            "examinedPages": examined, "findings": len(findings), "unresolved": unresolved,
            "pending": len(data.get("pending", [])), "limits": limits}


def build(data: dict, max_width: int) -> str:
    audit = review_summary(data)
    target = pathlib.Path(str(data.get("target", "")))
    missing = []
    problems = []
    uri_cache = {}

    def img(p, label, required=False):
        if not p:
            if required:
                missing.append(f"{label}: 未提供图片")
            return ""
        path = pathlib.Path(p)
        if not path.is_file():
            missing.append(f"{label}: {p}")
            return ""
        key = str(path)
        if key not in uri_cache:
            try:
                uri_cache[key] = data_uri(path, max_width)
            except (OSError, ValueError) as error:
                missing.append(f"{label}: 图片读取失败 ({error})")
                return ""
        return uri_cache[key]

    def page_by_id(pid):
        for p in data.get("pages", []):
            if p.get("id") == pid:
                return p
        return None

    def rulers_of(pg, pid):
        ruler_b = img(pg.get("beforeRuler"), f"{pid} beforeRuler")
        ruler_a = img(pg.get("afterRuler"), f"{pid} afterRuler")
        has_after = bool(pg.get("after"))
        figures = "".join(
            f'<figure><img src="{src}" alt="{pid} {label}"><figcaption>{label}</figcaption></figure>'
            for src, label in [(ruler_b, "改前标尺" if has_after else "现状标尺"), (ruler_a, "改后标尺")]
            if src)
        if not figures:
            return "", ""
        return (f'<div class="rulers" hidden>{figures}</div>',
                '<label><input type="checkbox" class="ruler"> 标尺图</label>')

    def annotated_figure(finding):
        """问题卡上半部：红框标注截图。无图时降级为空；坐标无效时省略红框并记入 limits，不猜坐标。"""
        fid = str(finding.get("id"))
        img_path = finding.get("img")
        if not img_path:
            page = page_by_id(str(finding.get("page", "")).split(",")[0].strip())
            img_path = page.get("before") if page else None
        if not img_path:
            return ""
        uri = img(img_path, f"finding {fid} img")
        if not uri:
            return ""
        has_coords = finding.get("box") is not None or finding.get("boxPct") is not None
        geo = box_pct(finding, img_path, fid, problems) if has_coords else None
        if geo is not None:
            left, top, width, height = geo
            label = esc(finding.get("label") or fid or "问题")
            below = " below" if top < 8 else ""
            box_html = (f'<div class="rbox{below}" style="left:{left:.2f}%;top:{top:.2f}%;'
                        f'width:{width:.2f}%;height:{height:.2f}%">'
                        f'<span class="rlabel">{label}</span></div>')
            where = f" · {esc(finding['where'])}" if finding.get("where") else ""
            caption = f"红框 = 问题位置{where}"
            alt = f"{esc(fid)} 问题位置"
        elif has_coords:
            box_html, caption, alt = "", "红框坐标无效，已省略红框（见覆盖范围限制）", f"{esc(fid)} 所在页截图"
        else:
            box_html, caption, alt = "", "未提供红框坐标，仅显示所在页截图", f"{esc(fid)} 所在页截图"
        return (f'<figure class="annotated"><img src="{uri}" alt="{alt}">{box_html}'
                f'<figcaption>{caption}</figcaption></figure>')

    def compare_block(cid, before_uri, after_uri, ruler_html="", ruler_control=""):
        body = COMPARE.substitute(pid=cid, before=before_uri, after=after_uri,
                                  rulerControl=ruler_control, rulers=ruler_html)
        return f'<div class="cmp">{body}</div>'

    # ---- 问题与修复（主结构）----
    findings = data.get("findings", [])
    findings_html = ""
    if findings:
        cards = []
        ordered = [(sev, f) for sev in SEV for f in findings if f.get("severity") == sev]
        for sev, f in ordered:
            sev_label, color = SEV[sev]
            fid = str(f.get("id"))
            esc_fid = esc(fid)
            resolution = f.get("resolution", "open")
            page = page_by_id(str(f.get("page", "")).split(",")[0].strip())
            annotated = annotated_figure(f)
            short = f.get("short") or ""
            short_html = (f'<p class="short"><span class="mk">问题：</span>{esc(short)}</p>'
                          if short and short != f.get("title") else "")
            # 对照图：finding 级 beforeImg/afterImg 优先，缺省回落页级；两图齐全才渲染。
            fb = f.get("beforeImg") or (page.get("before") if page else None)
            fa = f.get("afterImg") or (page.get("after") if page else None)
            fb_uri = img(fb, f"{fid} beforeImg") if fb else ""
            fa_uri = img(fa, f"{fid} afterImg") if fa else ""
            compare = ""
            if fb_uri and fa_uri:
                compare = compare_block(esc_fid, fb_uri, fa_uri)
            elif fa or f.get("afterImg"):
                problems.append(f"finding {esc_fid}: 对照图需要改前改后两张真实截图，当前缺少其一，仅显示红框现状")
            delta = ""
            if f.get("before") or f.get("after"):
                delta = (f"<p class='mono delta'>现状 → 复验结果：{esc(f.get('before'))} → "
                         f"<b>{esc(f.get('after'))}</b></p>")
            reason = f"（{esc(f['resolutionReason'])}）" if f.get("resolutionReason") else ""
            cards.append(FINDING_BLOCK.substitute(
                sev=esc(sev), color=color, sevLabel=sev_label,
                fid=esc_fid, fpage=esc(f.get("page", "")), title=esc(f.get("title")),
                res=esc(resolution), resLabel=RES[resolution],
                annotated=annotated, short=short_html, compare=compare,
                why=esc(f.get("why")), delta=delta, fix=esc(f.get("fix")),
                where=esc(f.get("where")), resText=RES[resolution], reason=reason,
            ))
        findings_html = "".join(cards)
    else:
        findings_html = '<div class="card">本轮无 finding。</div>'

    # ---- 逐页覆盖记录 ----
    pages_html = []
    for pg in data.get("pages", []):
        pid = esc(pg.get("id", "?"))
        before = img(pg.get("before"), f"{pid} before", required=True)
        after = img(pg.get("after"), f"{pid} after")
        review = '<p class="review">' + esc("\n".join(f"{k}: {v}" for k, v in pg.get("review", {}).items())) + '</p>'
        ruler_html, ruler_control = rulers_of(pg, pid)
        if after:
            content = compare_block(pid, before, after, ruler_html, ruler_control)
        else:
            caption = "现状 · 未提供改后图" if audit["mode"] == "review" else "改前 · 未提供改后图，未复验"
            content = (f'{ruler_control}<figure class="current"><img src="{before}" alt="{pid} 现状">'
                       f'<figcaption>{caption}</figcaption></figure>{ruler_html}')
        bits = []
        if pg.get("after"):
            bits.append("已提供改后图")
        if pg.get("beforeRuler") or pg.get("afterRuler"):
            bits.append("含标尺图")
        pages_html.append(PAGE_BLOCK.substitute(
            pid=pid, title=esc(pg.get("title") or pid),
            meta=" · ".join(bits) if bits else "现状截图",
            review=review, content=content,
        ))

    if missing:
        raise ValueError("报告图片不完整：\n  " + "\n  ".join(missing))
    if problems:
        audit["limits"] = list(audit["limits"]) + [f"渲染降级：{p}" for p in problems]

    contract = ""
    if data.get("contract"):
        rows = "".join(f"<dt>{esc(k)}</dt><dd class='mono'>{esc(v)}</dd>" for k, v in data["contract"].items())
        contract = (f"<details class='fold'><summary>版面契约</summary>"
                    f"<div class='fbody'><dl class='kv'>{rows}</dl></div></details>")

    summary = ""
    if findings:
        counts = {k: sum(1 for f in findings if f.get("severity") == k) for k in SEV}
        chips = " &nbsp; ".join(
            f"<span class='sev' style='background:{SEV[k][1]}'>{SEV[k][0]}</span> {counts[k]} 条"
            for k in SEV if counts[k]
        )
        summary = f"<div class='card'>{chips}</div>"

    def listing(title, items, render):
        if not items:
            return ""
        lis = "".join(f"<li>{render(i)}</li>" for i in items)
        return (f"<details class='fold'><summary>{title}（{len(items)}）</summary>"
                f"<div class='fbody'><ul class='plain'>{lis}</ul></div></details>")

    kept = listing("保留项", data.get("kept", []),
                   lambda i: f"<b>{esc(i.get('what'))}</b> — {esc(i.get('why'))}")
    pending = listing("待确认", data.get("pending", []), esc)
    commands = listing("本轮验收命令", data.get("commands", []),
                       lambda i: f"<code>{esc(i.get('cmd'))}</code><br>{esc(i.get('result'))}")
    limits = listing("覆盖范围限制", audit["limits"], esc)

    status_text = {"clean": "clean · 覆盖范围内无待修项", "fixed": "已修改 · 已复验",
                   "reviewed": "有待修项 · 尚未全部处理", "incomplete": "未完成验收 · 覆盖不足"}
    return DOC.substitute(
        targetName=esc(target.name or target),
        statusText=status_text[audit["status"]], status=audit["status"],
        modeText="只读审查 · 本轮未修改被审文件" if audit["mode"] == "review" else "布局修复模式",
        target=esc(target), pageCount=len(data.get("pages", [])),
        generated=esc(data.get("generated", "")),
        summary=summary, contract=contract,
        findings=findings_html, pages="".join(pages_html),
        kept=kept, pending=pending, commands=commands, limits=limits,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, help="审查记录 JSON")
    ap.add_argument("--out", help="输出单文件 HTML；--check 时不写文件")
    ap.add_argument("--check", action="store_true", help="只读校验，stdout 输出覆盖和状态聚合")
    ap.add_argument("--max-width", type=int, default=1600, help="内嵌图片最大宽度，默认 1600")
    a = ap.parse_args()

    if a.max_width < 1 or (not a.check and not a.out):
        ap.error("--max-width 必须大于 0；生成报告需要 --out")
    try:
        data = json.loads(pathlib.Path(a.data).read_text(encoding="utf-8"))
        report = build(data, a.max_width)
        summary = review_summary(data)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 3
    if a.check:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return 0
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(json.dumps({
        "report": str(out), "bytes": out.stat().st_size,
        **summary,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    sys.exit(main())