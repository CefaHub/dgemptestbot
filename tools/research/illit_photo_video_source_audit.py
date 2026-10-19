#!/usr/bin/env python3
"""Research ONLY: sample real 1080p frames from CC-BY ILLIT group photocall.
Source: K-POPIT 'ILLIT Canada Goose PhotoCall', 11 December 2024.
Commons verified its YouTube Creative Commons BY 3.0 licensing:
https://commons.wikimedia.org/wiki/File:250221_ILLIT.png
No frames are approved for gameplay automatically, no faces generated.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"assets/previews/illit_aura_rare_video_research"
VIDEO="https://www.youtube.com/watch?v=rQYc_Zn9cIc"


def shell(args, timeout):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report={
      "video":VIDEO,
      "date":"2024-12-11",
      "artist":"K-POPIT 케이팝잇",
      "commons_license_reference":"https://commons.wikimedia.org/wiki/File:250221_ILLIT.png",
      "license":"CC BY 3.0",
      "status":"research_only_not_in_gacha",
      "expected":["YUNAH","MINJU","MOKA","WONHEE","IROHA"],
      "minimum_individual_native_crop":[600,800],
      "source_note":"YouTube video may not be available to datacenter IPs; if blocked no images may be substituted.",
    }
    try:
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)
            options=["yt-dlp","--no-playlist","--force-ipv4","--no-progress",
                     "--retries","2","--fragment-retries","2",
                     "-f","bv*[height<=1080]+ba/b[height<=1080]",
                     "-o",str(dest/"illit.%(ext)s"),VIDEO]
            attempt=shell(options,170)
            if attempt.returncode:
                report["status"]="blocked_video_original_unavailable"
                report["error"]=attempt.stderr[-1300:]
            else:
                files=[x for x in dest.glob("illit.*") if x.is_file()]
                if not files:
                    raise ValueError("yt-dlp reported success but no real video")
                path=max(files,key=lambda x:x.stat().st_size)
                report["download_bytes"]=path.stat().st_size
                frames=dest/"frames"
                frames.mkdir()
                grab=shell(["ffmpeg","-hide_banner","-loglevel","error",
                            "-i",str(path),"-vf","fps=1/5,scale=640:-1",
                            "-frames:v","90",str(frames/"f_%03d.jpg")],120)
                if grab.returncode:
                    raise RuntimeError(grab.stderr[-600:])
                pics=sorted(frames.glob("*.jpg"))
                report["sampled_frames"]=len(pics)
                if pics:
                    tw,th=160,138
                    sheet=Image.new("RGB",(tw*10,th*((len(pics)+9)//10)+45),(12,15,31))
                    draw=ImageDraw.Draw(sheet)
                    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",12)
                    header=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",19)
                    draw.text((10,12),"ILLIT CANADA GOOSE 2024 — REAL CC BY 3.0 VIDEO FRAMES",font=header,fill="white")
                    for i,pic in enumerate(pics):
                        x=i%10*tw;y=(i//10)*th+45
                        with Image.open(pic) as im:
                            thumb=ImageOps.contain(im.convert("RGB"),(154,106))
                        sheet.paste(thumb,(x+(tw-thumb.width)//2,y+2))
                        draw.text((x+7,y+110),f"t={i*5}s (research only)",font=font,fill=(212,213,234))
                    sheet.save(OUT/"FRAME_CONTACT_SHEET.jpg",quality=82,optimize=True)
                    report["status"]="video_frames_sampled_need_individual_manual_review"
                else:
                    report["status"]="video_no_frames"
    except Exception as exc:
        report["status"]="blocked_source_video_error"
        report["error"]=str(exc)[:1200]
    (OUT/"VIDEO_SOURCE_AUDIT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    # Research failure does not create playable cards.


if __name__=="__main__":
    main()
