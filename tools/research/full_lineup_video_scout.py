#!/usr/bin/env python3
"""Research a WHOLE group from one Creative-Commons video; ZERO card rendering.

This is a source inventory/contact-sheet tool, not a card builder. Even when
frames download correctly, NONE are accepted as member portraits until a
separate full-5/5 visual, originality, crop, and rights review is complete.

Usage:
  python tools/research/full_lineup_video_scout.py \\
    tools/research/itzy_2019_dispatch_full_event_video_scout.json
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont

from tools.photo_release_pipeline import GROUPS, ROOT

DEFAULT_OUT = ROOT / "output" / "full_lineup_video_scout"


def validate_spec(spec):
    if spec.get("status") != "full_lineup_video_source_research_no_card_selection":
        raise ValueError("Scouting can never use a publish/release manifest")
    group = GROUPS.get(spec.get("group"))
    if group is None:
        raise ValueError("Unknown group in scout")
    expected = [name for name, _ in group["members"]]
    if spec.get("full_group_members") != expected:
        raise ValueError("Full group lineup must match release plan EXACTLY")
    if not spec.get("session_id") or not spec.get("source_page"):
        raise ValueError("Event and source page are required")
    if spec.get("license") not in ("CC BY 3.0", "CC BY 4.0", "CC BY-SA 4.0"):
        raise ValueError("Research needs documented attribution/permitted reuse")
    url = spec.get("video_url", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org" or not parsed.path.endswith(".webm"):
        raise ValueError("Video scouting accepts only exact Wikimedia Commons HTTPS WEBM files")
    if spec.get("qa_status") != "video_not_yet_inspected":
        raise ValueError("Do not call a video reviewed or approved without inspecting all frames")
    step = spec.get("sampling_period_seconds")
    if not isinstance(step, int) or step < 1 or step > 15:
        raise ValueError("Frame sample step must be a reasonable positive integer")
    cap = spec.get("network_max_bytes")
    if not isinstance(cap, int) or not 1_000_000 <= cap <= 150_000_000:
        raise ValueError("Strict source download limit required")
    return expected


def retrieve_video(spec, destination):
    request = Request(spec["video_url"], headers={
        "User-Agent": "DolceEmpireLicensedPhotoResearch/1.0 (attributed)",
        "Accept": "video/webm,application/octet-stream",
    })
    digest = hashlib.sha256()
    total = 0
    with urlopen(request, timeout=75) as response, destination.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > spec["network_max_bytes"]:
                raise ValueError("Full video exceeds allowed download size")
            digest.update(chunk)
            out.write(chunk)
    if total < 100_000:
        raise ValueError("Downloaded source is not a substantive video file")
    return {"source_sha256": digest.hexdigest(), "source_bytes": total}


def _font(size):
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf"
    ):
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def frame_sheet(files, output_path, *, page):
    cell_w, cell_h, gap = 320, 180, 14
    columns, rows = 5, 4
    margin_top, side = 112, 28
    sheet = Image.new("RGB", (side * 2 + columns * cell_w + 4 * gap,
                              margin_top + rows * (cell_h + 35) + 30),
                      (15, 20, 36))
    d = ImageDraw.Draw(sheet)
    d.text((side, 18), "ITZY / FULL EVENT VIDEO SOURCE SCOUT", font=_font(27), fill="white")
    d.text((side, 64), "RESEARCH FRAMES ONLY / NO MEMBER APPROVAL / NO GAME CARDS", font=_font(17),
           fill=(245, 177, 178))
    for i, file in enumerate(files):
        col, row = i % columns, i // columns
        if row >= rows:
            break
        x = side + col * (cell_w + gap)
        y = margin_top + row * (cell_h + 35)
        with Image.open(file) as im:
            thumbnail = im.convert("RGB").resize((cell_w, cell_h), Image.Resampling.LANCZOS)
        sheet.paste(thumbnail, (x, y))
        d.text((x + 2, y + cell_h + 6), f"SAMPLE {page * columns * rows + i + 1:02d} / {file.stem}",
               font=_font(14), fill=(235, 240, 248))
    sheet.save(output_path, "JPEG", quality=87, optimize=True)


def scout(spec, output_dir=DEFAULT_OUT, download_fn=retrieve_video, run_fn=subprocess.run):
    expected = validate_spec(spec)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Scout must never mistake stale results for source-backed frames.
    for file in output_dir.rglob("*"):
        if file.is_file():
            file.unlink()
    report = {
        "kind": "WHOLE_EVENT_VIDEO_RESEARCH_ONLY",
        "set_id": spec["set_id"],
        "group": spec["group"],
        "expected_members": expected,
        "source_page": spec["source_page"],
        "source_url": spec["video_url"],
        "rights": {"creator": spec["creator"], "license": spec["license"],
                   "license_url": spec["license_url"]},
        "status": "not_inspected",
        "all_five_member_portraits_verified": False,
        "cards_created": 0,
        "catalog_updated": False,
        "requires_review": "Every one of five distinct solo frames at >=600x800 native, no duplicates, visual inspection, publicity rights",
    }
    report_file = output_dir / "SCOUT_REPORT.json"
    if not shutil.which("ffmpeg"):
        report["status"] = "ffmpeg_unavailable"
    else:
        try:
            with tempfile.TemporaryDirectory(prefix="dolce-video-scout_") as td:
                original = Path(td) / "source.webm"
                download_info = download_fn(spec, original)
                report.update(download_info)
                command = [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(original),
                    "-vf", f"fps=1/{spec['sampling_period_seconds']}",
                    "-q:v", "3", "-frames:v", "60",
                    str(output_dir / "frame_%03d.jpg")
                ]
                run_fn(command, check=True, capture_output=True, text=True, timeout=300)
                images = sorted(output_dir.glob("frame_*.jpg"))
                report["frames_sampled"] = len(images)
                if not images:
                    report["status"] = "no_frames_from_video"
                else:
                    with Image.open(images[0]) as first:
                        report["original_frame_pixels"] = list(first.size)
                    for page, index in enumerate(range(0, len(images), 20)):
                        frame_sheet(images[index:index + 20],
                                    output_dir / f"CONTACT_SHEET_{page+1:02d}.jpg", page=page)
                    report["status"] = "whole_event_sampled_waiting_all_five_solo_qa"
        except Exception as exc:
            report["status"] = "video_source_unavailable_or_decoder_error"
            report["error"] = f"{type(exc).__name__}: {str(exc)[:260]}"
            # No empty/garbled old preview artifacts survive on failure.
            for f in output_dir.glob("frame_*.jpg"):
                f.unlink()
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    spec = json.loads((ROOT / args.manifest).read_text(encoding="utf-8"))
    result = scout(spec, output_dir=args.output)
    print(json.dumps({k: result.get(k) for k in (
        "status", "frames_sampled", "original_frame_pixels",
        "all_five_member_portraits_verified", "cards_created", "error")},
        ensure_ascii=False))


if __name__ == "__main__":
    main()
