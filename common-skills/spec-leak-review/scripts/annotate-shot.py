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

用法：annotate-shot.py --boxes boxes.json --out <目录> [--pad 120] [--max-width 900]
输出 <out>/<id>.png 及 annotations.json（id 到标注图绝对路径的映射）。
HTML 报告由 review-html-report 消费这些路径并内嵌；本脚本只生成真实标注证据。
成功退出 0，缺图或无效输入退出 1，参数错误退出 2。
"""

import argparse
import json
import pathlib
import sys

from PIL import Image, ImageDraw

MARK = (217, 45, 32)  # 与报告里「阻断」同色，视觉上和严重度对齐


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boxes", required=True, help="带截图路径与 CSS 坐标的 JSON 数组")
    ap.add_argument("--out", required=True, help="标注 PNG 与 annotations.json 输出目录")
    ap.add_argument("--pad", type=int, default=120, help="局部图上下文像素，默认 120")
    ap.add_argument("--max-width", type=int, default=900, help="输出图片最大宽度，默认 900")
    a = ap.parse_args()
    if a.pad < 0 or a.max_width < 1:
        ap.error("--pad 必须非负，--max-width 必须大于 0")

    out_dir = pathlib.Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    boxes = json.loads(pathlib.Path(a.boxes).read_text(encoding="utf-8"))

    annotations: dict[str, str] = {}

    for box in boxes:
        dst = annotate(box, out_dir, a.pad, a.max_width)
        annotations[box["id"]] = str(dst.resolve())
        print(f"{box['id']} -> {dst} ({dst.stat().st_size // 1024} KB)")

    (out_dir / "annotations.json").write_text(json.dumps(annotations, indent=1), encoding="utf-8")
    print(f"annotations.json 写入 {len(annotations)} 个标注图路径")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        sys.exit(1)
