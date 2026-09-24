#!/usr/bin/env python3
"""统一审查报告渲染器：问题卡、文字建议对照、真实修复滑块和反馈复制。

输入契约及 PPT/spec-leak 映射见本 Skill references/report-data.md。
用法：build-report.py --data findings.json --out report.html [--max-width 1600]
      build-report.py --data findings.json --check
--check 只校验并汇总数据与图片，不写 HTML；不能替代实际审查或视觉复验。
图片以内嵌 data URI 输出；Pillow 可选（压缩图片），纯文本不依赖 Pillow/浏览器。
返回码：成功 0，参数错误 2，输入或图片错误 3（保留已有报告）。
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
CATEGORIES = {"visual": "视觉与交互问题", "content": "内容与证据建议"}


def finding_category(finding):
    category = finding.get("category", "visual")
    if category not in CATEGORIES:
        raise ValueError(f"finding {finding.get('id')}: category 必须是 visual/content")
    return category


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


def verify_image(path: pathlib.Path):
    """未嵌入的本地截图也必须可读；校验无需压缩或生成 data URI。"""
    try:
        from PIL import Image
    except ImportError:
        size = image_size(path)
        if not size or min(size) <= 0:
            raise ValueError("无法读取图片尺寸；非 PNG 图片需要 Pillow")
    else:
        with Image.open(path) as image:
            image.verify()


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
""")

FINDING_BLOCK = Template("""
<details class="fold finding" data-sev="$sev" data-finding-id="$fid">
  <summary><span class="sev" style="background:$color">$sevLabel</span>
    <code class="fid">$fid</code> <span class="fpage mono">$fpage</span>
    <span class="ftitle">$title</span>
    <span class="res res-$res">$resLabel</span></summary>
  <div class="fbody">
    $annotated
    $short
    $compare
    $textCompare
    <details class="detail"><summary>完整分析与处理记录</summary>
      <p class="why">$why</p>
      $delta
      <p class="fixline"><b>建议 / 实际改动：</b>$fix</p>
      <p class="mono">$where</p>
      <p>处理状态：$resText$reason</p>
    </details>
    $feedback
  </div>
</details>
""")

DOC = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$reportTitle · $targetName</title>
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
  .delta { white-space:pre-wrap; overflow-wrap:anywhere; }
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
  .annotation-image { position:relative; }
  .annotated { margin:0 0 10px; line-height:0; border:1px solid var(--line); }
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
  .annotated figcaption { color:var(--muted); font-size:12px; padding-top:6px; line-height:1.5; }
  .review { white-space:pre-wrap; color:var(--muted); font-size:13px; margin:0 0 10px; }
  .status.incomplete, .status.reviewed { background:#9a6700; }
  ul.plain { margin:0; padding-left:18px; }
  ul.plain li { margin-bottom:6px; }
  .text-compare { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:12px; margin:12px 0; }
  .text-compare pre, .draft { white-space:pre-wrap; overflow-wrap:anywhere; font:inherit; }
  .text-compare > div { padding:12px; border:1px solid var(--line); border-radius:8px; }
  .text-compare > div:first-child { background:#fff8f7; }
  .text-compare > div:last-child { background:#f4fbf7; }
  .feedback { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-top:12px; }
  #feedback-export { width:100%; min-height:160px; }
  .coverage { width:100%; border-collapse:collapse; }
  .coverage th, .coverage td { border-bottom:1px solid var(--line); padding:8px; text-align:left; overflow-wrap:anywhere; }
  @media (max-width:640px) {
    body { padding:16px 10px; }
    .text-compare { grid-template-columns:minmax(0,1fr); }
    details.fold > summary, .toolbar { flex-wrap:wrap; }
    dl.kv { grid-template-columns:1fr; gap:4px; }
  }
</style>
</head>
<body>
<main>
  <h1>$reportTitle · $targetName</h1>
  <p class="sub"><span class="status $status">$statusText</span> &nbsp;$modeText &nbsp;·&nbsp; 被审文件 <code>$target</code> &nbsp;·&nbsp; 覆盖记录 $pageCount 项 &nbsp;·&nbsp; $generated</p>

  $summary
  <div class="toolbar">
    <button type="button" id="expand-all">全部展开</button>
    <button type="button" id="collapse-all">全部收起</button>
    <button type="button" id="copy-all">复制全部反馈</button>
  </div>
  $contract
  $coverage
  $overview
  $findings
  $draft
  $limits
  <p id="feedback-status" role="status"></p>
  <textarea id="feedback-export" aria-label="可复制反馈" hidden></textarea>
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

  }
  document.getElementById('expand-all')?.addEventListener('click', () => {
    document.querySelectorAll('details').forEach((d) => { d.open = true; });
  });
  document.getElementById('collapse-all')?.addEventListener('click', () => {
    document.querySelectorAll('details').forEach((d) => { d.open = false; });
  });
  // 反馈是本次报告的审阅意见，不改变审查/修复状态，也不发送给外部服务。
  const feedbackText = (card) => '[' + card.dataset.findingId + ' ' +
    card.querySelector('.feedback-state').selectedOptions[0].textContent + '] ' +
    card.querySelector('.ftitle').textContent + '\\n' +
    (card.querySelector('.short')?.textContent || '');
  const copyFeedback = async (text) => {
    const output = document.getElementById('feedback-export');
    output.value = text;
    output.hidden = false;
    try {
      await navigator.clipboard.writeText(text);
      document.getElementById('feedback-status').textContent = '已复制反馈';
    } catch {
      output.focus(); output.select();
      document.getElementById('feedback-status').textContent = '请复制下方已选中的反馈';
    }
  };
  document.querySelectorAll('.finding').forEach(card => {
    card.querySelector('.copy-feedback').addEventListener('click', () => copyFeedback(feedbackText(card)));
  });
  document.getElementById('copy-all').addEventListener('click', () =>
    copyFeedback(Array.from(document.querySelectorAll('.finding'), feedbackText).join('\\n\\n')));
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
        evidence_mode = p.get("evidenceMode", data.get("evidenceMode", "visual"))
        if evidence_mode not in ("visual", "text"):
            raise ValueError("evidenceMode 必须是 visual/text")
        review = p.get("review", {})
        needed = ["before"] + (["interaction"] if evidence_mode == "visual" else []) + (["after"] if mode == "fix" else [])
        missing = [key for key in needed if not isinstance(review.get(key), str) or not review[key].strip()]
        if mode == "fix" and evidence_mode == "visual" and not p.get("after"):
            missing.append("after 截图")
        if missing:
            limits.append(f"{p['id']} 未完成复核：{', '.join(missing)}")
        else:
            examined += 1
    findings = data.get("findings", [])
    finding_ids = [f.get("id") for f in findings if f.get("id") is not None]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("finding id 必须唯一")
    unresolved = 0
    groups = {k: {"findings": 0, "fixed": 0, "unresolved": 0} for k in CATEGORIES}
    for f in findings:
        if f.get("severity") not in SEV:
            raise ValueError(f"finding {f.get('id')}: severity 必须是 blocking/should/optional")
        resolution = f.get("resolution", "open")
        if resolution not in ("open", "fixed", "kept"):
            raise ValueError(f"finding {f.get('id')}: resolution 必须是 open/fixed/kept")
        resolved = ((resolution == "fixed" and mode == "fix" and bool(f.get("fix"))) or
                    (resolution == "kept" and bool(f.get("resolutionReason"))))
        unresolved += not resolved
        group = groups[finding_category(f)]
        group["findings"] += 1
        group["fixed"] += resolution == "fixed" and resolved
        group["unresolved"] += not resolved
    if limits or requested == "incomplete":
        status = "incomplete"
    elif unresolved or data.get("pending") or requested == "reviewed":
        status = "reviewed"
    elif mode == "fix" and any(f.get("resolution") == "fixed" and f.get("fix") for f in findings):
        status = "fixed"
    else:
        status = "clean"
    for category, group in groups.items():
        group["status"] = ("incomplete" if limits or requested == "incomplete" else
                           "reviewed" if group["unresolved"] else
                           "fixed" if group["fixed"] else "clean")
    return {"mode": mode, "status": status, "groups": groups, "pages": len(pages), "expectedPages": expected,
            "examinedPages": examined, "findings": len(findings), "unresolved": unresolved,
            "pending": len(data.get("pending", [])), "limits": limits}


def build(data: dict, max_width: int) -> tuple[str, dict]:
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

    def annotated_figure(finding):
        """问题卡上半部：红框标注截图。无图时降级为空；坐标无效时省略红框并记入 limits，不猜坐标。"""
        fid = str(finding.get("id"))
        if finding.get("annotatedImg"):
            uri = img(finding["annotatedImg"], f"{fid} annotatedImg", required=True)
            return (f'<figure class="annotated"><img src="{uri}" alt="{esc(fid)} 标注证据">'
                    f'<figcaption>{esc(finding.get("where"))}</figcaption></figure>')
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
        return (f'<figure class="annotated"><div class="annotation-image"><img src="{uri}" alt="{alt}">{box_html}</div>'
                f'<figcaption>{caption}</figcaption></figure>')

    def compare_block(cid, before_uri, after_uri):
        body = COMPARE.substitute(pid=cid, before=before_uri, after=after_uri)
        return f'<div class="cmp">{body}</div>'

    # ---- 问题与修复（主结构）----
    findings = data.get("findings", [])
    findings_html = ""
    if findings:
        cards = {category: [] for category in CATEGORIES}
        ordered = [(sev, f) for sev in SEV for f in findings if f.get("severity") == sev]
        for sev, f in ordered:
            sev_label, color = SEV[sev]
            fid = str(f.get("id"))
            esc_fid = esc(fid)
            resolution = f.get("resolution", "open")
            page = page_by_id(str(f.get("page", "")).split(",")[0].strip())
            annotated = annotated_figure(f) if resolution == "fixed" or f.get("annotatedImg") else ""
            short = f.get("changeSummary") or f.get("short") or ""
            short_html = (f'<p class="short"><span class="mk">问题：</span>{esc(short)}</p>'
                          if short and short != f.get("title") else "")
            # 对照图：finding 级 beforeImg/afterImg 优先，缺省回落页级；两图齐全才渲染。
            fb = f.get("beforeImg") or (page.get("before") if page else None)
            fa = f.get("afterImg") or (page.get("after") if page else None)
            fb_uri = img(fb, f"{fid} beforeImg") if fb and resolution == "fixed" else ""
            fa_uri = img(fa, f"{fid} afterImg") if fa and resolution == "fixed" else ""
            compare = ""
            if fb_uri and fa_uri and resolution == "fixed" and fb_uri != fa_uri:
                compare = compare_block(esc_fid, fb_uri, fa_uri)
            elif resolution == "fixed" and (page or {}).get("evidenceMode", data.get("evidenceMode", "visual")) == "visual" and not (fb_uri and fa_uri):
                problems.append(f"finding {esc_fid}: 对照图需要改前改后两张真实截图，当前缺少其一，仅显示红框现状")
            delta = ""
            if f.get("before") or f.get("after"):
                delta = (f"<p class='mono delta'>现状 → 复验结果：{esc(f.get('before'))} → "
                         f"<b>{esc(f.get('after'))}</b></p>")
            text_compare = ""
            if f.get("textComparison"):
                text = f["textComparison"]
                repaired_text = resolution == "fixed" and audit["mode"] == "fix"
                if repaired_text and "after" not in text:
                    raise ValueError(f"finding {fid}: 已修文字对照缺少真实 after")
                label = "改后 · 已执行" if repaired_text else "建议 · 尚未执行"
                value = text.get("after") if repaired_text else text.get("suggested")
                text_compare = (
                    '<div class="text-compare"><div><b>原文</b><pre>' + esc(text.get("before")) +
                    '</pre></div><div><b>' + label + '</b><pre>' + esc(value) +
                    '</pre></div></div>')
            feedback = ('<div class="feedback"><label>审阅意见 <select class="feedback-state" '
                        'aria-label="' + esc_fid + ' 审阅意见">'
                        '<option value="pending">待定</option><option value="accept">采纳</option>'
                        '<option value="discuss">讨论</option><option value="reject">驳回</option>'
                        '</select></label><button type="button" class="copy-feedback">复制此项反馈</button></div>')
            reason = f"（{esc(f['resolutionReason'])}）" if f.get("resolutionReason") else ""
            cards[finding_category(f)].append(FINDING_BLOCK.substitute(
                sev=esc(sev), color=color, sevLabel=sev_label,
                fid=esc_fid, fpage=esc(f.get("page", "")), title=esc(f.get("title")),
                res=esc(resolution), resLabel=RES[resolution],
                annotated=annotated, short=short_html, compare=compare, textCompare=text_compare, feedback=feedback,
                why=esc("\n".join(str(f[k]) for k in ("kind", "action", "why", "audienceReason") if f.get(k))), delta=delta, fix=esc(f.get("fix")),
                where=esc(f.get("where")), resText=RES[resolution], reason=reason,
            ))
    else:
        cards = {category: [] for category in CATEGORIES}
    findings_html = "".join(
        f'<section id="{category}-findings"><h2>{title}</h2>'
        + ("".join(cards[category]) or '<p class="sub">本轮无此类记录。</p>') + '</section>'
        for category, title in CATEGORIES.items())

    # 核对本地证据，不将逐页记录加入报告。
    for pg in data.get("pages", []):
        pid = str(pg["id"])
        if pg.get("evidenceMode", data.get("evidenceMode", "visual")) == "text":
            continue
        for key in ("before", "after"):
            path = pg.get(key)
            if key == "before" or path:
                if not path:
                    missing.append(f"{pid} {key}: 未提供图片")
                    continue
                try:
                    verify_image(pathlib.Path(path))
                except (OSError, ValueError, SyntaxError) as error:
                    missing.append(f"{pid} {key}: 图片读取失败 ({error})")
    # ---- 整体前后对照：逐页真实 before/after，只展开有像素变化的页 ----
    overview = ""
    metrics = data.get("metrics") or []
    if metrics:
        if not isinstance(metrics, list) or any(not isinstance(m, dict) or not m.get("name") for m in metrics):
            raise ValueError("metrics 必须是含 name/before/after 的对象列表")
        rows = "".join(f"<tr><td>{esc(m['name'])}</td><td>{esc(m.get('before'))}</td><td><b>{esc(m.get('after'))}</b></td></tr>"
                       for m in metrics)
        overview += ('<table class="coverage metrics"><thead><tr><th>指标</th><th>改前</th><th>改后</th></tr></thead>'
                     f'<tbody>{rows}</tbody></table>')
    if data.get("pageCompare"):
        if audit["mode"] != "fix":
            raise ValueError("pageCompare 需要 mode=fix 且各页提供真实 after 截图")
        changed, unchanged = [], []
        for pg in data.get("pages", []):
            if pg.get("evidenceMode", data.get("evidenceMode", "visual")) == "text":
                continue
            pid = str(pg["id"])
            b_uri = img(pg.get("before"), f"{pid} before", required=True)
            a_uri = img(pg.get("after"), f"{pid} after", required=True)
            if not (b_uri and a_uri):
                continue
            if b_uri == a_uri:
                unchanged.append(pid)
                continue
            note = (pg.get("review") or {}).get("after", "")
            changed.append(
                f'<details class="fold pagecmp" data-page-id="{esc(pid)}"><summary><code>{esc(pid)}</code>'
                f'<span class="ftitle">{esc(pg.get("title", ""))}</span></summary><div class="fbody">'
                + (f'<p class="review">{esc(note)}</p>' if note else "")
                + compare_block(esc(pid), b_uri, a_uri) + '</div></details>')
        overview += (f'<p class="sub">{len(changed)} 页有变化'
                     + (f"，{len(unchanged)} 页无像素变化：{esc('、'.join(unchanged))}" if unchanged else "")
                     + '</p>' + "".join(changed))
    if overview:
        overview = f'<section id="overview"><h2>整体前后对照</h2>{overview}</section>'

    if missing:
        raise ValueError("报告图片不完整：\n  " + "\n  ".join(missing))
    if problems:
        audit["limits"] = list(audit["limits"]) + [f"渲染降级：{p}" for p in problems]
        audit["status"] = "incomplete"
        for group in audit["groups"].values():
            group["status"] = "incomplete"

    contract = ""
    context = {**data.get("context", {}), **data.get("contract", {})}
    if context:
        rows = "".join(f"<dt>{esc(k)}</dt><dd class='mono'>{esc(v)}</dd>" for k, v in context.items())
        contract = (f"<details class='fold'><summary>审查背景</summary>"
                    f"<div class='fbody'><dl class='kv'>{rows}</dl></div></details>")

    group_status = {"clean": "无待处理项", "fixed": "已修复并复验",
                    "reviewed": "有待处理项", "incomplete": "检查覆盖不足"}
    summary = "".join(
        f"<div class='card group-summary' data-category='{category}'><b>{CATEGORIES[category]}</b> · "
        f"{group_status[group['status']]} · {group['findings']} 项，"
        f"已修复 {group['fixed']} 项，待处理 {group['unresolved']} 项</div>"
        for category, group in audit["groups"].items())

    def listing(title, items, render):
        if not items:
            return ""
        lis = "".join(f"<li>{render(i)}</li>" for i in items)
        return (f"<details class='fold'><summary>{title}（{len(items)}）</summary>"
                f"<div class='fbody'><ul class='plain'>{lis}</ul></div></details>")

    limits = listing("覆盖范围限制", audit["limits"], esc)

    coverage = ""
    if data.get("showCoverage"):
        rows = "".join('<tr><td>' + esc(p["id"]) + '</td><td>' + esc(p.get("title", p.get("where", ""))) +
                       '</td><td>' + esc("\n".join(str(v) for v in p.get("review", {}).values())) + '</td></tr>'
                       for p in data["pages"])
        coverage = ('<details class="fold"><summary>证据与覆盖范围</summary><div class="fbody">'
                    '<table class="coverage"><thead><tr><th>页面／文件</th><th>位置／用途</th><th>观察与检查结果</th>'
                    '</tr></thead><tbody>' + rows + '</tbody></table></div></details>')
    draft = ('<details class="fold"><summary>建议稿 · 尚未执行</summary><div class="fbody"><pre class="draft">'
             + esc(data["suggestedCopy"]) + '</pre></div></details>') if data.get("suggestedCopy") else ""
    if data.get("fixedCopy") is not None:
        if audit["mode"] != "fix":
            raise ValueError("fixedCopy 需要 mode=fix")
        draft += ('<details class="fold"><summary>实际改后全文</summary><div class="fbody"><pre class="draft">'
                  + esc(data["fixedCopy"]) + '</pre></div></details>')
    status_text = {"clean": "clean · 覆盖范围内无待修项", "fixed": "已修改 · 已复验",
                   "reviewed": "分项结论见下方", "incomplete": "未完成验收 · 覆盖不足"}
    return DOC.substitute(
        reportTitle=esc(data.get("title", "审查报告")), targetName=esc(target.name or target),
        statusText=status_text[audit["status"]], status=audit["status"],
        modeText="只读审查 · 本轮未修改被审文件" if audit["mode"] == "review" else "修复复验",
        target=esc(target), pageCount=len(data.get("pages", [])),
        generated=esc(data.get("generated", "")),
        summary=summary, contract=contract, overview=overview,
        findings=findings_html, limits=limits, coverage=coverage, draft=draft,
    ), audit


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
        report, summary = build(data, a.max_width)
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
