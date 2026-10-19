#!/usr/bin/env python3
"""Licensed ITZY/G-SHOCK (Oct 23 2024) source-video contact-sheet research.

Never releases game cards. Extracts real camera frames ONLY after downloading
the exact Wikimedia-confirmed CC BY 3.0 source video xRIHgC2ZVoM.
Requires human visual selection of one distinct sharp solo frame per member.
"""
from pathlib import Path
import json, math, subprocess, shutil
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets/previews/itzy_aura_rare_gshock_video"
SRC = "https://www.youtube.com/watch?v=xRIHgC2ZVoM"
LICENSE = "https://creativecommons.org/licenses/by/3.0/"
MEMBERS = ["YEJI","LIA","RYUJIN","CHAERYEONG","YUNA"]


def video_probe(file):
    p = subprocess.run(
        ["ffprobe","-v","error","-show_entries","format=duration",
         "-of","default=noprint_wrappers=1:nokey=1",str(file)],
        capture_output=True,text=True,check=True)
    return float(p.stdout.strip())


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    tmp=Path("/tmp/dolce-itzy-cc-source.mp4")
    record = {
        "status":"research_pending_licensed_video_capture",
        "purpose":"Identify five UNIQUE solo 3:4 high quality frames from ONE group appearance",
        "group":"ITZY","members":MEMBERS,
        "event":"ITZY x G-SHOCK launch, Starfield Suwon, 23 Oct 2024",
        "video":SRC,"author":"K-POPIT 케이팝잇",
        "license":"CC BY 3.0","license_url":LICENSE,
        "license_evidence":"https://commons.wikimedia.org/wiki/File:241023_ITZY_Chaeryeong.jpg",
        "published_set":"none; must visually inspect and approve five different frames",
    }
    # yt-dlp is run without an account or cookies; do not circumvent access controls.
    cmd = ["yt-dlp","--no-playlist","--socket-timeout","15",
           "--retries","1","--fragment-retries","1",
           "--max-filesize","250M",
           "-f","best[height<=1080]/best",
           "-o",str(tmp),SRC]
    proc=subprocess.run(cmd,capture_output=True,text=True,timeout=240)
    if proc.returncode or not tmp.exists():
        record.update(status="BLOCKED_video_not_available_without_signin",
                      blocking_reason=(proc.stderr or proc.stdout)[-1400:])
        (OUT/"SOURCE_REVIEW.json").write_text(
            json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("BLOCKED: unable to retrieve source video without account",flush=True)
        return
    try:
        duration=video_probe(tmp)
        record.update(source_duration_seconds=duration,
                      video_file_size=tmp.stat().st_size)
        sample_dir=Path("/tmp/dolce-itzy-frames")
        sample_dir.mkdir(exist_ok=True)
        # Keep 3-minute timeline review: 2 sec per frame, cap at 90 real frames.
        # Frame selection is NOT final credit attribution.
        secs=min(duration,180)
        subprocess.run([
            "ffmpeg","-v","error","-i",str(tmp),"-t",str(secs),
            "-vf","fps=1/2,scale=520:-1",
            "-q:v","4","-frames:v","90",str(sample_dir/"sample_%03d.jpg")
        ],check=True,timeout=120)
        frames=sorted(sample_dir.glob("sample_*.jpg"))
        if not frames:
            raise RuntimeError("Video downloaded but no film frames produced")
        cols=8
        w,h=260,212
        rows=math.ceil(len(frames)/cols)
        sheet=Image.new("RGB",(cols*w,54+rows*h),(11,16,34))
        draw=ImageDraw.Draw(sheet)
        font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",16)
        draw.text((12,12),"ITZY G-SHOCK / LICENSED REAL VIDEO / 2-SECOND SOLO-FRAME SCOUT",
                  fill=(243,247,255),font=font)
        for k,path in enumerate(frames):
            im=Image.open(path).convert("RGB")
            thumb=ImageOps.contain(im,(w-10,h-38))
            x=(k%cols)*w+(w-thumb.width)//2
            y=54+(k//cols)*h+5
            sheet.paste(thumb,(x,y))
            draw.text((k%cols*w+7,y+h-29),f"t={2*k:03d}s   frame {k+1:03d}",
                      font=font,fill=(186,215,255))
        sheet.save(OUT/"CONTACT_SHEET.jpg",quality=90,optimize=True)
        record.update(status="research_video_contact_sheet_generated",
                      sampled_frame_count=len(frames),
                      instruction="Identify and confirm each solo subject, then extract true native-resolution distinct frames for full five-member set; do not publish from thumbnail sheet.")
    except Exception as exc:
        record.update(status="BLOCKED_video_sample_extraction",blocking_reason=str(exc))
    finally:
        (OUT/"SOURCE_REVIEW.json").write_text(
            json.dumps(record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        if tmp.exists():tmp.unlink()
    print(record["status"],record.get("sampled_frame_count",0),flush=True)


if __name__=="__main__":
    main()
