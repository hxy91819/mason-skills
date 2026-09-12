#!/usr/bin/env python3
"""把一轮 PPT 版式验收渲染成单文件 HTML 报告：逐页改前改后对比 + 按严重度分组的 findings。

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
         "why": "before-p1.png 右上角的验收表是判断能否发布的唯一证据，但字段名与状态都不可辨；观众无法据此核对标题结论。放大原图可读不能补足演示画面的缺口。",
         "before": "验收表显示宽度 240px；投影视口 1920x1080",
         "fix": "建议扩大现有验收表的显示尺寸，利用主区空间呈现结果列；复验时在同一投影视口能直接辨认字段名和放行状态。本轮只读，尚未执行。",
         "where": "deck.html:191 .acceptance-shot", "resolution": "open"}
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
图片按路径读取并内嵌成 data URI；
装了 Pillow 时缩到 `--max-width` 并转 JPEG（单文件报告控制在几 MB），没装就原样内嵌 PNG。
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
  $review
  <div class="controls">
    $rulerControl
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
    <input type="range" class="slider" aria-label="$pid 改前改后分界" min="0" max="100" value="50">
  </div>
  <div class="sbs">
    <figure><img class="img-before" src="$before" alt="$pid 改前"><figcaption>改前</figcaption></figure>
    <figure><img class="img-after" src="$after" alt="$pid 改后"><figcaption>改后</figcaption></figure>
  </div>
  $rulers
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
  /* 整图保持同位，只裁去左侧；百分比布局在隐藏、恢复和 resize 后仍由浏览器求值。 */
  .after-clip { position:absolute; inset:0; clip-path:inset(0 0 0 var(--split, 50%)); }
  .after-clip img { height:100%; }
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
  .current { margin:0; }
  .current img { width:100%; display:block; }
  .review { white-space:pre-wrap; color:var(--muted); font-size:13px; }
  .status.incomplete, .status.reviewed { background:#9a6700; }
  ul.plain { margin:0; padding-left:18px; }
  ul.plain li { margin-bottom:6px; }
</style>
</head>
<body>
<main>
  <h1>PPT 版式视觉验收 · $targetName</h1>
  <p class="sub"><span class="status $status">$statusText</span> &nbsp;$modeText &nbsp;·&nbsp; 被审文件 <code>$target</code> &nbsp;·&nbsp; 展示 $pageCount 页 &nbsp;·&nbsp; $generated</p>

  $contract
  $summary
  <h2>逐页视觉证据</h2>
  $pages
  $findings
  $kept
  $pending
  $commands
  $limits
</main>
<script>
  for (const page of document.querySelectorAll('.page')) {
    const slider = page.querySelector('.slider');
    if (slider) {
      const move = () => {
        page.querySelector('.wipe').style.setProperty('--split', slider.value + '%');
        page.querySelector('.handle').style.left = slider.value + '%';
        page.querySelector('.tag.l').hidden = slider.value === '0';
        page.querySelector('.tag.r').hidden = slider.value === '100';
      };
      slider.addEventListener('input', move);
      page.querySelector('.side').addEventListener('change', (e) => page.classList.toggle('is-side', e.target.checked));
      move();
    }
    page.querySelector('.ruler')?.addEventListener('change', (e) => {
      page.querySelector('.rulers').hidden = !e.target.checked;
    });
  }
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

    def img(p, label, required=False):
        if not p:
            if required:
                missing.append(f"{label}: 未提供图片")
            return ""
        path = pathlib.Path(p)
        if not path.is_file():
            missing.append(f"{label}: {p}")
            return ""
        try:
            return data_uri(path, max_width)
        except (OSError, ValueError) as error:
            missing.append(f"{label}: 图片读取失败 ({error})")
            return ""

    pages_html = []
    for pg in data.get("pages", []):
        pid = esc(pg.get("id", "?"))
        ruler_b = img(pg.get("beforeRuler"), f"{pid} beforeRuler")
        ruler_a = img(pg.get("afterRuler"), f"{pid} afterRuler")
        before = img(pg.get("before"), f"{pid} before", required=True)
        after = img(pg.get("after"), f"{pid} after")
        rulers = "".join(f'<figure><img src="{src}" alt="{pid} {label}"><figcaption>{label}</figcaption></figure>'
                         for src, label in [(ruler_b, "改前标尺" if after else "现状标尺"), (ruler_a, "改后标尺")]
                         if src)
        ruler_control = '<label><input type="checkbox" class="ruler"> 标尺图</label>' if rulers else ''
        rulers = f'<div class="rulers" hidden>{rulers}</div>' if rulers else ''
        review = '<p class="review">' + esc("\n".join(f"{k}: {v}" for k, v in pg.get("review", {}).items())) + '</p>'
        if not after:
            caption = "现状 · 未提供改后图" if audit["mode"] == "review" else "改前 · 未提供改后图，未复验"
            pages_html.append(f'<section class="page" data-page="{pid}"><h3>{esc(pg.get("title") or pid)}</h3>'
                              f'{review}{ruler_control}<figure class="current"><img src="{before}" alt="{pid} 现状">'
                              f'<figcaption>{caption}</figcaption></figure>{rulers}</section>')
            continue
        pages_html.append(PAGE_BLOCK.substitute(
            pid=pid,
            title=esc(pg.get("title") or pid),
            before=before, after=after, review=review,
            rulerControl=ruler_control, rulers=rulers,
        ))

    if missing:
        raise ValueError("报告图片不完整：\n  " + "\n  ".join(missing))

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
                    f"<td>{esc(f.get('fix'))}<br><code>{esc(f.get('where'))}</code>"
                    f"<br>{esc(f.get('resolution', 'open'))} {esc(f.get('resolutionReason'))}</td>"
                    "</tr>"
                )
            blocks.append(
                "<table><thead><tr><th>级别</th><th>ID</th><th>页</th><th>类型</th>"
                "<th>问题与读者感受</th><th>现状 → 复验结果</th><th>建议 / 实际改动与处理状态</th></tr></thead>"
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
    pending = listing("待确认", data.get("pending", []), esc)
    commands = listing("本轮验收命令", data.get("commands", []),
                       lambda i: f"<code>{esc(i.get('cmd'))}</code><br>{esc(i.get('result'))}")
    limits = listing("覆盖范围限制", audit["limits"], esc)

    status_text = {"clean": "clean · 覆盖范围内无待修项", "fixed": "已修改 · 已复验",
                   "reviewed": "有待修项 · 尚未全部处理", "incomplete": "未完成验收 · 覆盖不足"}
    return DOC.substitute(
        target=esc(target), targetName=esc(target.name or target),
        statusText=status_text[audit["status"]], status=audit["status"],
        modeText="只读审查 · 本轮未修改被审文件" if audit["mode"] == "review" else "布局修复模式",
        pageCount=len(data.get("pages", [])),
        generated=esc(data.get("generated", "")),
        contract=contract, summary=summary,
        pages="".join(pages_html), findings=findings_html,
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
