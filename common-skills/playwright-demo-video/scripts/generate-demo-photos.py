#!/usr/bin/env python3
"""Generate crisp labeled demo JPG images for file-upload slots in Playwright recordings."""
import argparse
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

FONT_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def load_font(size: int):
    for fp in FONT_PATHS:
        if os.path.exists(fp):
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def generate_photo(out_path: Path, tag: str, title: str, subtitle: str = "DEMO SAMPLE", bg: str = "#1e3a5f", accent: str = "#38bdf8"):
    img = Image.new("RGB", (800, 600), bg)
    draw = ImageDraw.Draw(img)
    for x in range(0, 800, 40):
        draw.line([(x, 0), (x, 600)], fill=(255, 255, 255), width=1)
    for y in range(0, 600, 40):
        draw.line([(0, y), (800, y)], fill=(255, 255, 255), width=1)
    # Blend subtle grid by overlaying dark tint
    overlay = Image.new("RGB", (800, 600), bg)
    img = Image.blend(img, overlay, 0.92)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(48, 48), (752, 552)], radius=24, outline=accent, width=4)
    draw.rounded_rectangle([(88, 96), (288, 152)], radius=28, fill=accent)
    draw.text((116, 108), tag, fill="#0f172a", font=load_font(28))
    draw.text((88, 220), title, fill="#f8fafc", font=load_font(48))
    draw.text((88, 320), subtitle, fill="#cbd5e1", font=load_font(26))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=90)


def main():
    parser = argparse.ArgumentParser(description="Generate labeled demo photos from a JSON spec.")
    parser.add_argument("spec", type=Path, help="JSON list of {filename, tag, title, subtitle?, bg?, accent?}")
    parser.add_argument("out_dir", type=Path, help="Output directory")
    args = parser.parse_args()

    items = json.loads(args.spec.read_text(encoding="utf-8"))
    for it in items:
        generate_photo(
            args.out_dir / it["filename"],
            it["tag"],
            it["title"],
            it.get("subtitle", "DEMO SAMPLE"),
            it.get("bg", "#1e3a5f"),
            it.get("accent", "#38bdf8"),
        )
    print(f"Generated {len(items)} demo photos in {args.out_dir}")


if __name__ == "__main__":
    main()
