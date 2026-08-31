#!/usr/bin/env python3
"""把一轮 PPT 版式验收渲染成单文件 HTML 报告：逐页改前改后对比 + 按严重度分组的 findings。

输入 `--data <json>`：

    {
      "target": "/abs/deck.html",
      "status": "fixed",                       // fixed | clean
      "contract": {"页画布": "1920x1080", "页边距": "82px", "区块间隔": "28px"},
      "commands": [{"cmd": "node measure-deck.js ...", "result": "flags 25 -> 3"}],
      "pages": [
        {"id": "p1", "title": "方案共识",
         "before": "/tmp/x/before-p1.png", "after": "/tmp/x/after-p1.png",
         "beforeRuler": "/tmp/x/before-p1-ruler.png", "afterRuler": "/tmp/x/after-p1-ruler.png"}
      ],
      "findings": [
        {"id": "V2", "severity": "blocking", "kind": "slack", "page": "p2",
         "title": "主区底部空出 68px",
         "why": "读者看到这页没排满，和 P1、P3 的收尾位置不在一条线上",
         "before": "68.4px", "after": "0px",
         "fix": "主区 bottom 定位统一到 66px 并让列表随内容收敛",
         "where": "deck.html:191 .main"}
      ],
      "kept": [{"what": "kpi 卡片 ±0.3deg 旋转带来的 5px 错位", "why": "设计意图，非排版失误"}],
      "limits": ["..."]
    }

除 `target` 与 `pages` 外的字段都可省略。图片按路径读取并内嵌成 data URI；
装了 Pillow 时缩到 `--max-width` 并转 JPEG（单文件报告控制在几 MB），没装就原样内嵌 PNG。
引用的图片缺失时以非零码退出——报告里不留空图。

用法：
  build-report.py --data findings.json --out /tmp/ppt-visual-review/report.html [--max-width 1600]
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
KIND = {
    "rhythm": "节奏",
    "cross-page": "跨页一致",
    "slack": "留白",
    "symmetry": "对称",
    "scale": "档位",
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


def esc(v) -> str:
    return html.escape("" if v is None else str(v))


PAGE_BLOCK = Template("""
<section class="page" data-page="$pid">
  <h3>$title</h3>
  <div class="controls">
    <label><input type="checkbox" class="ruler"> 标尺图</label>
    <label><input type="checkbox" class="side"> 并排</label>
    <span class="hint">拖动滑块：左侧改前 / 右侧改后</span>
  </div>
  <div class="compare">
    <div class="wipe">
      <img class="img-before" src="$before" alt="$pid 改前">
      <div class="after-clip"><img class="img-after" src="$after" alt="$pid 改后"></div>
      <span class="tag l">改前</span><span class="tag r">改后</span>
      <div class="handle"></div>
    </div>
    <input type="range" class="slider" min="0" max="100" value="50">
  </div>
  <div class="sbs">
    <figure><img class="img-before" src="$before" alt="$pid 改前"><figcaption>改前</figcaption></figure>
    <figure><img class="img-after" src="$after" alt="$pid 改后"><figcaption>改后</figcaption></figure>
  </div>
  <div class="rulers" hidden>
    <img class="r-before" src="$beforeRuler" alt="$pid 改前标尺"><img class="r-after" src="$afterRuler" alt="$pid 改后标尺">
  </div>
</section>
""")

DOC = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PPT 版式视觉验收 · $targetName</title>
<style>
  :root { --bg:#f6f7f9; --card:#fff; --line:#e4e6eb; --text:#1a1d21; --muted:#6b7280; --ok:#059669; }
  * { box-sizing: border-box; }
  body { margin:0; padding:32px 20px 80px; background:var(--bg); color:var(--text);
         font:15px/1.65 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
  main { max-width: 1180px; margin: 0 auto; }
  h1 { font-size:24px; margin:0 0 6px; }
  h2 { font-size:18px; margin:40px 0 14px; padding-bottom:8px; border-bottom:1px solid var(--line); }
  h3 { font-size:16px; margin:0 0 10px; }
  .sub { color:var(--muted); font-size:13px; margin:0 0 24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px 20px; margin-bottom:14px; }
  .status { display:inline-block; padding:3px 10px; border-radius:20px; font-size:12px; font-weight:700; color:#fff; background:var(--ok); }
  dl.kv { display:grid; grid-template-columns:150px 1fr; gap:8px 16px; margin:0; }
  dl.kv dt { color:var(--muted); font-size:13px; }
  dl.kv dd { margin:0; }
  table { width:100%; border-collapse:collapse; font-size:13.5px; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--muted); font-weight:600; font-size:12.5px; }
  code, .mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }
  .sev { display:inline-block; min-width:38px; padding:2px 8px; border-radius:4px; color:#fff; font-size:12px; font-weight:700; text-align:center; }
  .delta { white-space:nowrap; }
  .delta b { color:var(--ok); }
  .page { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px 18px; margin-bottom:18px; }
  .controls { display:flex; gap:18px; align-items:center; margin-bottom:10px; font-size:13px; color:var(--muted); }
  .controls label { display:inline-flex; gap:6px; align-items:center; cursor:pointer; }
  .wipe { position:relative; overflow:hidden; border:1px solid var(--line); background:#fff; line-height:0; }
  .wipe img { width:100%; display:block; }
  .after-clip { position:absolute; inset:0; overflow:hidden; width:50%; }
  .after-clip img { position:absolute; top:0; left:0; height:100%; width:auto; max-width:none; }
  .handle { position:absolute; top:0; bottom:0; left:50%; width:2px; background:#d61f69; }
  .tag { position:absolute; top:8px; padding:2px 8px; background:rgba(26,29,33,.82); color:#fff; font-size:11px; font-weight:700; line-height:16px; }
  .tag.l { left:8px; } .tag.r { right:8px; }
  .slider { width:100%; margin:10px 0 0; }
  .sbs { display:none; grid-template-columns:1fr 1fr; gap:12px; }
  .sbs figure { margin:0; }
  .sbs img { width:100%; display:block; border:1px solid var(--line); }
  .sbs figcaption { color:var(--muted); font-size:12px; padding-top:6px; }
  .page.is-side .compare { display:none; }
  .page.is-side .sbs { display:grid; }
  .rulers { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }
  .rulers[hidden] { display:none; }   /* display:grid 会盖掉 hidden，标尺图默认要收起 */
  .rulers img { width:100%; display:block; border:1px solid var(--line); }
  ul.plain { margin:0; padding-left:18px; }
  ul.plain li { margin-bottom:6px; }
</style>
</head>
<body>
<main>
  <h1>PPT 版式视觉验收 · $targetName</h1>
  <p class="sub"><span class="status">$statusText</span> &nbsp;被审文件 <code>$target</code> &nbsp;·&nbsp; $pageCount 页 &nbsp;·&nbsp; $generated</p>

  $contract
  $summary
  <h2>逐页改前改后</h2>
  $pages
  $findings
  $kept
  $commands
  $limits
</main>
<script>
  for (const page of document.querySelectorAll('.page')) {
    const slider = page.querySelector('.slider');
    const clip = page.querySelector('.after-clip');
    const handle = page.querySelector('.handle');
    const afterImg = page.querySelector('.after-clip img');
    const wipe = page.querySelector('.wipe');
    // 右侧改后图按整幅宽度定位，滑块只切裁剪宽度，两幅图才严格同位可比。
    const fit = () => { afterImg.style.width = wipe.clientWidth + 'px'; };
    const move = () => {
      clip.style.width = slider.value + '%';
      handle.style.left = slider.value + '%';
    };
    slider.addEventListener('input', move);
    addEventListener('resize', fit);
    page.querySelector('.side').addEventListener('change', (e) => page.classList.toggle('is-side', e.target.checked));
    page.querySelector('.ruler').addEventListener('change', (e) => {
      page.querySelector('.rulers').hidden = !e.target.checked;
    });
    fit(); move();
  }
</script>
</body>
</html>
""")


def build(data: dict, max_width: int) -> str:
    target = pathlib.Path(str(data.get("target", "")))
    missing = []

    def img(p, label):
        if not p:
            return ""
        path = pathlib.Path(p)
        if not path.exists():
            missing.append(f"{label}: {p}")
            return ""
        return data_uri(path, max_width)

    pages_html = []
    for pg in data.get("pages", []):
        pid = esc(pg.get("id", "?"))
        ruler_b = img(pg.get("beforeRuler"), f"{pid} beforeRuler")
        ruler_a = img(pg.get("afterRuler"), f"{pid} afterRuler")
        pages_html.append(PAGE_BLOCK.substitute(
            pid=pid,
            title=esc(pg.get("title") or pid),
            before=img(pg.get("before"), f"{pid} before"),
            after=img(pg.get("after"), f"{pid} after") or img(pg.get("before"), f"{pid} before"),
            beforeRuler=ruler_b or ruler_a,
            afterRuler=ruler_a or ruler_b,
        ))

    if missing:
        print("FAIL 报告引用的图片不存在：\n  " + "\n  ".join(missing), file=sys.stderr)
        sys.exit(3)

    contract = ""
    if data.get("contract"):
        rows = "".join(f"<dt>{esc(k)}</dt><dd class='mono'>{esc(v)}</dd>" for k, v in data["contract"].items())
        contract = f"<h2>版面契约</h2><div class='card'><dl class='kv'>{rows}</dl></div>"

    findings = data.get("findings", [])
    summary = ""
    if findings:
        counts = {k: sum(1 for f in findings if f.get("severity") == k) for k in SEV}
        chips = " &nbsp; ".join(
            f"<span class='sev' style='background:{SEV[k][1]}'>{SEV[k][0]}</span> {counts[k]} 条"
            for k in SEV if counts[k]
        )
        summary = f"<div class='card'>{chips}</div>"

    findings_html = ""
    if findings:
        blocks = []
        for sev, (label, color) in SEV.items():
            group = [f for f in findings if f.get("severity") == sev]
            if not group:
                continue
            rows = []
            for f in group:
                delta = ""
                if f.get("before") or f.get("after"):
                    delta = f"<span class='mono delta'>{esc(f.get('before'))} → <b>{esc(f.get('after'))}</b></span>"
                rows.append(
                    "<tr>"
                    f"<td><span class='sev' style='background:{color}'>{label}</span></td>"
                    f"<td class='mono'>{esc(f.get('id'))}</td>"
                    f"<td>{esc(f.get('page'))}</td>"
                    f"<td>{esc(KIND.get(f.get('kind'), f.get('kind')))}</td>"
                    f"<td><b>{esc(f.get('title'))}</b><br>{esc(f.get('why'))}</td>"
                    f"<td>{delta}</td>"
                    f"<td>{esc(f.get('fix'))}<br><code>{esc(f.get('where'))}</code></td>"
                    "</tr>"
                )
            blocks.append(
                "<table><thead><tr><th>级别</th><th>ID</th><th>页</th><th>类型</th>"
                "<th>问题与读者感受</th><th>改前 → 改后</th><th>改动</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
        findings_html = "<h2>findings</h2><div class='card'>" + "".join(blocks) + "</div>"

    def listing(title, items, render):
        if not items:
            return ""
        lis = "".join(f"<li>{render(i)}</li>" for i in items)
        return f"<h2>{title}</h2><div class='card'><ul class='plain'>{lis}</ul></div>"

    kept = listing("保留项", data.get("kept", []),
                   lambda i: f"<b>{esc(i.get('what'))}</b> — {esc(i.get('why'))}")
    commands = listing("本轮验收命令", data.get("commands", []),
                       lambda i: f"<code>{esc(i.get('cmd'))}</code><br>{esc(i.get('result'))}")
    limits = listing("覆盖范围限制", data.get("limits", []), esc)

    status = data.get("status", "fixed")
    return DOC.substitute(
        target=esc(target), targetName=esc(target.name or target),
        statusText="clean · 无版式问题" if status == "clean" else "已修改 · 附改前改后对比",
        pageCount=len(data.get("pages", [])),
        generated=esc(data.get("generated", "")),
        contract=contract, summary=summary,
        pages="".join(pages_html), findings=findings_html,
        kept=kept, commands=commands, limits=limits,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-width", type=int, default=1600)
    a = ap.parse_args()

    data = json.loads(pathlib.Path(a.data).read_text(encoding="utf-8"))
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data, a.max_width), encoding="utf-8")
    print(json.dumps({
        "report": str(out), "bytes": out.stat().st_size,
        "pages": len(data.get("pages", [])), "findings": len(data.get("findings", [])),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
