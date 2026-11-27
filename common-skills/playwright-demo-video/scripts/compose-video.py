#!/usr/bin/env python3
"""
Compose a narrated, subtitled, auto-trimmed 1280x720 HD MP4 from Playwright recordings + timeline.json.

Usage:
  compose-video.py <timeline.json> <output.mp4> [--verify-dir <dir>]

Environment variables:
  DEMO_TTS_VOICE   edge-tts voice name (default: zh-TW-HsiaoChenNeural)
  DEMO_TTS_RATE    edge-tts speech rate (default: +12%)
  DEMO_FONT_NAME   ASS subtitle font family (default: Noto Sans CJK TC)
"""
import argparse
import asyncio
import json
import math
import os
import re
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import edge_tts
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
VOICE = os.environ.get("DEMO_TTS_VOICE", "zh-TW-HsiaoChenNeural")
VOICE_RATE = os.environ.get("DEMO_TTS_RATE", "+12%")
ASS_FONT = os.environ.get("DEMO_FONT_NAME", "Noto Sans CJK TC")
W, H, FPS = 1280, 720, 30

FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
FONT_CANDIDATES_REG = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def load_font(size: int, bold: bool = True):
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REG
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def run_ffmpeg(args: list[str], desc: str = ""):
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *args]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({desc}):\nCMD: {' '.join(cmd)}\nSTDERR:\n{res.stderr}")


def media_duration(path: Path) -> float:
    res = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
    if not m:
        raise RuntimeError(f"Cannot parse duration for {path}:\n{res.stderr[:400]}")
    hh, mm, ss = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return hh * 3600 + mm * 60 + ss


async def synth_tts(text: str, out_mp3: Path):
    communicate = edge_tts.Communicate(text, VOICE, rate=VOICE_RATE)
    await communicate.save(str(out_mp3))


def wrap_subtitle_lines(text: str, max_chars: int = 26) -> list[str]:
    parts = re.split(r"([。！？；，、])", text.strip())
    clauses = []
    buf = ""
    for p in parts:
        if not p:
            continue
        buf += p
        if p in "。！？；":
            clauses.append(buf.strip())
            buf = ""
        elif p in "，、" and len(buf) >= 14:
            clauses.append(buf.strip())
            buf = ""
    if buf.strip():
        clauses.append(buf.strip())

    final = []
    for c in clauses:
        while len(c) > max_chars + 4:
            final.append(c[:max_chars])
            c = c[max_chars:]
        if c:
            final.append(c)
    return final


def fmt_ass_time(sec: float) -> str:
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - math.floor(sec)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def write_ass_subtitle(out_ass: Path, text: str, audio_dur: float, start_offset: float = 0.20):
    chunks = wrap_subtitle_lines(text, max_chars=26)
    total_chars = sum(max(1, len(c)) for c in chunks)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{ASS_FONT},28,&H00FFFFFF,&H000000FF,&H300F172A,&HC80F172A,1,0,0,0,100,100,0.5,0,3,8,0,2,48,48,26,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    t = start_offset
    usable = max(0.5, audio_dur - 0.1)
    for c in chunks:
        dur = usable * (max(1, len(c)) / total_chars)
        t_end = t + dur
        safe = c.replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{fmt_ass_time(t)},{fmt_ass_time(t_end)},Default,,0,0,0,,{safe}")
        t = t_end
    out_ass.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_title_card_png(out_png: Path, step_label: str, main_title: str, subtitle: str, footer: str):
    img = Image.new("RGB", (W, H), "#0f172a")
    draw = ImageDraw.Draw(img)
    for y in range(H):
        r = int(15 + (y / H) * 15)
        g = int(23 + (y / H) * 18)
        b = int(42 + (y / H) * 26)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    draw.rounded_rectangle([(120, 235), (132, 470)], radius=6, fill="#f97316")
    draw.rounded_rectangle([(164, 238), (460, 286)], radius=24, fill="#1e293b", outline="#f97316", width=2)
    draw.text((190, 246), step_label, fill="#fb923c", font=load_font(24, True))
    draw.text((164, 312), main_title, fill="#f8fafc", font=load_font(54, True))
    draw.text((164, 404), subtitle, fill="#94a3b8", font=load_font(28, False))
    if footer:
        draw.text((164, 620), footer, fill="#475569", font=load_font(20, False))
    img.save(out_png)


def make_mobile_backdrop_png(out_png: Path, badge: str, title: str, info_lines: list[str]):
    img = Image.new("RGB", (W, H), "#0f172a")
    draw = ImageDraw.Draw(img)
    for y in range(H):
        r = int(15 + (y / H) * 14)
        g = int(23 + (y / H) * 18)
        b = int(42 + (y / H) * 24)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    px, py, pw, ph = 180, 22, 326, 676
    draw.rounded_rectangle(
        [(px - 10, py - 10), (px + pw + 10, py + ph + 10)],
        radius=36,
        fill="#1e293b",
        outline="#475569",
        width=3,
    )

    rx = 590
    if badge:
        f_b = load_font(22, True)
        bbox = draw.textbbox((0, 0), badge, font=f_b)
        bw = max(180, (bbox[2] - bbox[0]) + 48)
        draw.rounded_rectangle([(rx, 150), (rx + bw, 198)], radius=24, fill="#1e293b", outline="#38bdf8", width=2)
        draw.text((rx + 24, 159), badge, fill="#38bdf8", font=f_b)
    draw.text((rx, 228), title, fill="#f8fafc", font=load_font(40, True))

    y_cur = 304
    for idx, line in enumerate(info_lines[:5]):
        color = "#cbd5e1" if idx < 2 else "#94a3b8"
        draw.text((rx, y_cur), line, fill=color, font=load_font(23, False))
        y_cur += 42
    img.save(out_png)


def make_desktop_badge_png(out_png: Path, badge: str):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if badge:
        draw = ImageDraw.Draw(img)
        f = load_font(18, True)
        bbox = draw.textbbox((0, 0), badge, font=f)
        tw = bbox[2] - bbox[0]
        pad_x = 18
        bx2 = W - 18
        bx1 = bx2 - tw - pad_x * 2
        by1, by2 = 14, 50
        draw.rounded_rectangle(
            [(bx1, by1), (bx2, by2)],
            radius=18,
            fill=(15, 23, 42, 215),
            outline=(249, 115, 22, 230),
            width=2,
        )
        draw.text((bx1 + pad_x, by1 + 6), badge, fill=(248, 250, 252, 255), font=f)
    img.save(out_png)


def render_title_card_clip(png_path: Path, out_mp4: Path, dur: float = 1.8):
    run_ffmpeg([
        "-loop", "1", "-t", f"{dur:.3f}", "-i", str(png_path),
        "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", f"fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.3,fade=t=out:st={max(0.1, dur-0.3):.3f}:d=0.3",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest",
        str(out_mp4),
    ], f"title card {png_path.name}")


def render_scene_clip(
    scene: dict,
    raw_video: Path,
    video_scale: float,
    raw_dur: float,
    audio_mp3: Path,
    audio_dur: float,
    work_dir: Path,
    default_info_lines: list[str],
) -> Path:
    sid = scene["id"]
    track = scene.get("track", "desktop")
    segs = scene.get("segments", [])
    if not segs:
        raise RuntimeError(f"Scene {sid} has no recorded segments")

    seg_clips = []
    for idx, seg in enumerate(segs):
        st = max(0.0, seg["start"] * video_scale)
        en = min(raw_dur, seg["end"] * video_scale)
        if en - st < 0.08:
            continue
        spd = float(seg.get("speed", 1.0))
        seg_mp4 = work_dir / f"{sid}_seg{idx:02d}.mp4"
        vf = f"trim=start={st:.3f}:end={en:.3f},setpts=(PTS-STARTPTS)/{spd:.4f},fps={FPS},format=yuv420p"
        run_ffmpeg([
            "-i", str(raw_video),
            "-an",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg_mp4),
        ], f"{sid} seg {idx}")
        seg_clips.append(seg_mp4)

    concat_list = work_dir / f"{sid}_segs.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in seg_clips) + "\n", encoding="utf-8")
    raw_scene_mp4 = work_dir / f"{sid}_raw.mp4"
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy", str(raw_scene_mp4),
    ], f"{sid} concat segs")

    actual_vid_dur = media_duration(raw_scene_mp4)
    # Anti-freeze pacing: gently stretch video (up to 1.38x) when narration is slightly longer
    desired_vid_dur = max(actual_vid_dur, audio_dur - 0.6)
    stretch = min(1.38, desired_vid_dur / max(0.5, actual_vid_dur))
    stretched_vid_dur = actual_vid_dur * stretch
    target_dur = max(stretched_vid_dur + 0.35, audio_dur + 0.55)
    pad_sec = max(0.0, target_dur - stretched_vid_dur)

    ass_path = work_dir / f"{sid}.ass"
    write_ass_subtitle(ass_path, scene["narration"], audio_dur, start_offset=0.20)
    ass_escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")

    out_mp4 = work_dir / f"{sid}_final.mp4"
    pts_filter = f"setpts={stretch:.4f}*PTS," if stretch > 1.02 else ""
    if track == "mobile":
        backdrop_png = work_dir / f"{sid}_backdrop.png"
        info_lines = scene.get("infoLines") or default_info_lines
        make_mobile_backdrop_png(backdrop_png, scene.get("badge", ""), scene["title"], info_lines)
        fc = (
            f"[1:v]{pts_filter}scale=310:670:force_original_aspect_ratio=decrease,"
            f"tpad=stop_mode=clone:stop_duration={pad_sec:.3f},fps={FPS}[mob];"
            f"[0:v][mob]overlay=188:25:shortest=0,trim=duration={target_dur:.3f},setpts=PTS-STARTPTS,"
            f"ass='{ass_escaped}',fade=t=in:st=0:d=0.2,fade=t=out:st={max(0.1, target_dur-0.25):.3f}:d=0.25,"
            f"format=yuv420p[vout];"
            f"[2:a]adelay=200|200,apad=whole_dur={target_dur:.3f}[aout]"
        )
        run_ffmpeg([
            "-loop", "1", "-t", f"{target_dur:.3f}", "-i", str(backdrop_png),
            "-i", str(raw_scene_mp4),
            "-i", str(audio_mp3),
            "-filter_complex", fc,
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{target_dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            str(out_mp4),
        ], f"{sid} mobile composite")
    else:
        badge_png = work_dir / f"{sid}_badge.png"
        make_desktop_badge_png(badge_png, scene.get("badge", ""))
        fc = (
            f"[0:v]{pts_filter}scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=#0f172a,"
            f"tpad=stop_mode=clone:stop_duration={pad_sec:.3f},fps={FPS}[desk];"
            f"[desk][1:v]overlay=0:0,trim=duration={target_dur:.3f},setpts=PTS-STARTPTS,"
            f"ass='{ass_escaped}',fade=t=in:st=0:d=0.2,fade=t=out:st={max(0.1, target_dur-0.25):.3f}:d=0.25,"
            f"format=yuv420p[vout];"
            f"[2:a]adelay=200|200,apad=whole_dur={target_dur:.3f}[aout]"
        )
        run_ffmpeg([
            "-i", str(raw_scene_mp4),
            "-loop", "1", "-t", f"{target_dur:.3f}", "-i", str(badge_png),
            "-i", str(audio_mp3),
            "-filter_complex", fc,
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{target_dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
            str(out_mp4),
        ], f"{sid} desktop composite")

    warn = "  [WARN: freeze_pad > 2.0s, consider trimming narration]" if pad_sec > 2.0 else ""
    print(f"  [OK] {sid}: raw={actual_vid_dur:.2f}s stretch={stretch:.2f}x audio={audio_dur:.2f}s freeze_pad={pad_sec:.2f}s final={target_dur:.2f}s{warn}")
    return out_mp4


def extract_verify_frames(output_mp4: Path, verify_dir: Path, total_dur: float):
    verify_dir.mkdir(parents=True, exist_ok=True)
    # Print stream summary
    info = subprocess.run([FFMPEG, "-i", str(output_mp4)], capture_output=True, text=True).stderr
    for line in info.splitlines():
        if any(k in line for k in ["Duration:", "Stream #"]):
            print("  ", line.strip())
    # Sample 5 evenly-spaced frames across the output video
    fractions = [0.02, 0.20, 0.45, 0.72, 0.96]
    for idx, frac in enumerate(fractions, 1):
        ts = max(0.1, min(total_dur - 0.2, total_dur * frac))
        out_png = verify_dir / f"verify_{idx:02d}_{int(ts)}s.png"
        run_ffmpeg(["-ss", f"{ts:.2f}", "-i", str(output_mp4), "-frames:v", "1", str(out_png)], f"verify frame {idx}")
    print(f"Extracted {len(fractions)} verification frames to {verify_dir}")


async def main():
    parser = argparse.ArgumentParser(description="Compose narrated Playwright demo video.")
    parser.add_argument("timeline", type=Path, help="Path to timeline.json")
    parser.add_argument("output", type=Path, help="Output MP4 path")
    parser.add_argument("--verify-dir", type=Path, default=None, help="Optional directory to extract 5 verification frames")
    args = parser.parse_args()

    timeline_path = args.timeline.resolve()
    output_mp4 = args.output.resolve()
    work_dir = timeline_path.parent / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(timeline_path.read_text(encoding="utf-8"))
    meta = data.get("meta", {})
    scenes = data["scenes"]

    tracks = {}
    for key, wall_key, name in [
        ("desktopVideo", "desktopWallSec", "desktop"),
        ("mobileVideo", "mobileWallSec", "mobile"),
    ]:
        if meta.get(key):
            p = Path(meta[key])
            dur = media_duration(p)
            scale = dur / max(0.1, float(meta.get(wall_key, dur)))
            tracks[name] = (p, dur, scale)
            print(f"Raw {name}: {dur:.2f}s (scale={scale:.4f})")

    print(f"Synthesizing TTS narration ({VOICE}, rate={VOICE_RATE}, {len(scenes)} scenes)...")
    audio_files = {}
    tasks = []
    for s in scenes:
        mp3 = work_dir / f"{s['id']}.mp3"
        audio_files[s["id"]] = mp3
        tasks.append(synth_tts(s["narration"], mp3))
    await asyncio.gather(*tasks)

    footer = meta.get("footer", "Playwright 流程演示")
    default_info_lines = meta.get("mobileInfoLines") or [
        "行動端操作視角",
        "即時同步狀態與附件",
    ]

    final_parts = []
    for s in scenes:
        tc = s.get("titleCard")
        if tc:
            tc_png = work_dir / f"{s['id']}_card.png"
            tc_mp4 = work_dir / f"{s['id']}_card.mp4"
            make_title_card_png(tc_png, tc["step"], tc["title"], tc["subtitle"], footer)
            render_title_card_clip(tc_png, tc_mp4, dur=float(tc.get("dur", 1.8)))
            final_parts.append(tc_mp4)

        track = s.get("track", "desktop")
        if track not in tracks:
            raise RuntimeError(f"Scene {s['id']} references track '{track}', not found in meta")
        raw_vid, r_dur, v_scale = tracks[track]
        mp3 = audio_files[s["id"]]
        a_dur = media_duration(mp3)
        clip = render_scene_clip(s, raw_vid, v_scale, r_dur, mp3, a_dur, work_dir, default_info_lines)
        final_parts.append(clip)

    concat_all = work_dir / "final_concat.txt"
    concat_all.write_text("\n".join(f"file '{p.resolve()}'" for p in final_parts) + "\n", encoding="utf-8")
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_all),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(output_mp4),
    ], "final concat")

    final_dur = media_duration(output_mp4)
    size_mb = output_mp4.stat().st_size / (1024 * 1024)
    print(f"\nDONE! Output: {output_mp4} ({final_dur:.1f}s, {size_mb:.2f} MB)")
    if args.verify_dir:
        extract_verify_frames(output_mp4, args.verify_dir.resolve(), final_dur)


if __name__ == "__main__":
    asyncio.run(main())
