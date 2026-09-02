#!/usr/bin/env python3
"""把 finding 的位置标注到真实截图上，裁出带上下文的局部图，供报告内嵌。

输入 boxes JSON（数组），每项：
  {"id": "F1", "png": "/tmp/spec-leak-shots/login.png",
   "x": 40, "y": 320, "w": 360, "h": 28, "note": "可选，写进 figcaption"}
`x/y/w/h` 是 CSS 文档坐标，capture-surface.js 清单里的字段可直接用。
用户直接给截图、没有清单时，从图上量出坐标填进来即可。

截图像素宽可能是 CSS 宽的整数倍（devicePixelRatio > 1），坐标要按比例换算。
比例按此顺序确定，正常情况无需手填：

1. `scale`：直接指定倍率。
2. `cssWidth`：该截图对应的 CSS 视口宽，倍率 = 图片像素宽 / cssWidth。
3. 自动：读同目录下 `<png 同名>.json` 的 `viewport.width`（capture-surface.js 的产物）。
4. 兜底 1.0，并打印一行提示——高分屏下这会让红框偏移，此时补 1 或 2。

用法：
  annotate-shot.py --boxes boxes.json --out <目录> [--pad 120] [--max-width 900]
                   [--overview <png> ...] [--inject <报告.html>]

产物：
  <out>/<id>.png            标注后的局部图
  <out>/overview-<名字>.png  等比缩小的全景图
  <out>/embed.json          {id: "data:image/png;base64,..."} 供内嵌单文件报告
  可选 --inject             就地把报告里的 `__EMBED_<id>__` 占位符替换成 data URI，
                            全景图占位符为 `__EMBED_overview:<名字>__`；
                            替换后校验无残留占位符，有缺失则报错退出。
"""

import argparse
import base64
import json
import pathlib
import re
import sys

from PIL import Image, ImageDraw

MARK = (217, 45, 32)  # 与报告里「阻断」同色，视觉上和严重度对齐


def data_uri(path: pathlib.Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def fit(img: Image.Image, max_width: int) -> Image.Image:
    if img.width <= max_width:
        return img
    ratio = max_width / img.width
    return img.resize((max_width, max(1, round(img.height * ratio))), Image.LANCZOS)


def resolve_scale(box: dict, img: Image.Image) -> float:
    """确定 CSS 坐标到图片像素的倍率。见模块 docstring 的四级顺序。"""
    scale = box.get("scale")
    if scale is not None:
        return float(scale)

    css_width = box.get("cssWidth")
    if css_width:
        return img.width / float(css_width)

    # capture-surface.js 会把 viewport 写进同名 JSON，优先自动读，
    # 免得调用方漏填 cssWidth 时在高分屏上静默画错位置。
    sidecar = pathlib.Path(box["png"]).with_suffix(".json")
    if sidecar.exists():
        try:
            width = json.loads(sidecar.read_text(encoding="utf-8"))["viewport"]["width"]
            if width:
                return img.width / float(width)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass

    if img.width > 2000:
        print(f"  {box['id']}: 未取到 CSS 视口宽，按 1.0 处理；"
              f"图片宽 {img.width}px 疑似高分屏，红框可能偏移，请补 cssWidth 或 scale")
    return 1.0


def annotate(box: dict, out_dir: pathlib.Path, pad: int, max_width: int) -> pathlib.Path:
    src = pathlib.Path(box["png"])
    img = Image.open(src).convert("RGB")
    scale = resolve_scale(box, img)

    x, y = box["x"] * scale, box["y"] * scale
    w, h = box["w"] * scale, box["h"] * scale

    left = max(0, int(x - pad))
    top = max(0, int(y - pad))
    right = min(img.width, int(x + w + pad))
    bottom = min(img.height, int(y + h + pad))
    if right <= left or bottom <= top:
        raise SystemExit(f"{box['id']}: 裁剪区域超出截图范围，检查坐标是否来自同一张图")

    crop = img.crop((left, top, right, bottom))
    draw = ImageDraw.Draw(crop)
    rx0, ry0 = x - left, y - top
    rx1, ry1 = rx0 + w, ry0 + h
    for i in range(3):  # 加粗到 3px，缩放后仍然看得清
        draw.rectangle((rx0 - i, ry0 - i, rx1 + i, ry1 + i), outline=MARK)

    crop = fit(crop, max_width)
    dst = out_dir / f"{box['id']}.png"
    crop.save(dst)
    return dst


PLACEHOLDER = re.compile(r"__EMBED_(.+?)__")


def inject(report: pathlib.Path, embed: dict[str, str]) -> int:
    """把报告里的 `__EMBED_<id>__` 就地换成 data URI，并校验没有漏的。"""
    html = report.read_text(encoding="utf-8")
    wanted = set(PLACEHOLDER.findall(html))
    missing = sorted(wanted - embed.keys())
    for key in wanted & embed.keys():
        html = html.replace(f"__EMBED_{key}__", embed[key])
    report.write_text(html, encoding="utf-8")

    left = PLACEHOLDER.findall(html)
    print(f"注入 {report}：占位符 {len(wanted)} 个，已替换 {len(wanted) - len(missing)} 个，"
          f"内嵌图片 {html.count('data:image/png;base64,')} 张，"
          f"报告 {report.stat().st_size // 1024} KB")
    unused = sorted(embed.keys() - wanted)
    if unused:
        print(f"  提示：produced 但报告未引用: {', '.join(unused)}")
    if missing or left:
        print(f"  缺失图片: {', '.join(missing) or '无'}；残留占位符: {', '.join(sorted(set(left))) or '无'}")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boxes", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad", type=int, default=120)
    ap.add_argument("--max-width", type=int, default=900)
    ap.add_argument("--overview", action="append", default=[])
    ap.add_argument("--inject", help="报告 HTML 路径，就地替换 __EMBED_<id>__ 占位符")
    a = ap.parse_args()

    out_dir = pathlib.Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    boxes = json.loads(pathlib.Path(a.boxes).read_text(encoding="utf-8"))

    embed: dict[str, str] = {}

    for box in boxes:
        dst = annotate(box, out_dir, a.pad, a.max_width)
        embed[box["id"]] = data_uri(dst)
        print(f"{box['id']} -> {dst} ({dst.stat().st_size // 1024} KB)")

    for ov in a.overview:
        src = pathlib.Path(ov)
        img = fit(Image.open(src).convert("RGB"), a.max_width)
        dst = out_dir / f"overview-{src.stem}.png"
        img.save(dst)
        key = f"overview:{src.stem}"
        embed[key] = data_uri(dst)
        print(f"{key} -> {dst} ({dst.stat().st_size // 1024} KB)")

    (out_dir / "embed.json").write_text(json.dumps(embed, indent=1), encoding="utf-8")
    total = sum(len(v) for v in embed.values()) // 1024
    print(f"embed.json 写入 {len(embed)} 张，内嵌后约 {total} KB")

    if a.inject:
        return inject(pathlib.Path(a.inject), embed)

    return 0


if __name__ == "__main__":
    sys.exit(main())
