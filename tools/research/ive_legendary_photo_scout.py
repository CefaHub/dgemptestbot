"""Visual source audit of genuinely distinct IVE Amsterdam 2024 photographs.

This is PHOTO RESEARCH, not a gacha release. Never label unknown subjects as
particular members before manual review of source portraits.
"""
import hashlib
import io
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "assets/previews/ive_velvet_light_legendary_source_research"
SHOOT = "20240613 IVE Amsterdam concert"
CANDIDATES = [
    ("REI SOLO CROP POSSIBILITY", "24"),
    ("YUJIN TWO-PERSON CROP POSSIBILITY", "36 Wonyoung and Yujin"),
]


def url_for(filename, width=960):
    slug = filename.replace(" ", "_")
    enc = urllib.parse.quote(slug)
    d = hashlib.md5(slug.encode("utf-8")).hexdigest()
    return (
        f"https://upload.wikimedia.org/wikipedia/commons/thumb/{d[0]}/{d[:2]}/"
        f"{enc}/{width}px-{enc}"
    )


def inspect():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    width, height, cols = 340, 370, 4
    total_rows = (len(CANDIDATES) + cols - 1) // cols
    sheet = Image.new("RGB", (width*cols, height*total_rows+46), (12, 17, 33))
    d = ImageDraw.Draw(sheet)
    normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    d.text((15, 12), "IVE / 2024 AMSTERDAM / REAL PHOTO SOURCE REVIEW", font=bold, fill="white")
    report=[]
    for idx,(subject,description) in enumerate(CANDIDATES):
        file = f"{SHOOT} {description}.jpg"
        x=(idx%cols)*width
        y=46+(idx//cols)*height
        url=url_for(file)
        page="https://commons.wikimedia.org/wiki/File:"+urllib.parse.quote(file.replace(" ","_"))
        entry={"label":subject,"filename":file,"source_page":page,"thumbnail":url,"status":"pending"}
        for attempt in range(2):
            try:
                request=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 (DOLCE Empire real-photo review)"})
                with urllib.request.urlopen(request,timeout=35) as res:
                    payload=res.read(12000000)
                with Image.open(io.BytesIO(payload)) as src:
                    src.load()
                    entry["image_dimensions"]=list(src.size)
                    img=ImageOps.contain(src.convert("RGB"),(315,305),Image.Resampling.LANCZOS)
                sheet.paste(img,(x+(width-img.width)//2,y+(307-img.height)//2))
                entry["status"]="loaded_needs_identity_and_crop_review"
                break
            except Exception as e:
                entry["error"]=str(e)[:250]
                if attempt<1:time.sleep(2.5)
        if entry["status"]=="pending":
            d.text((x+14,y+120),"SOURCE UNAVAILABLE",font=normal,fill=(255,110,130))
        d.text((x+10,y+316),subject,font=normal,fill="white")
        d.text((x+10,y+336),description[:31],font=normal,fill=(180,200,250))
        report.append(entry)
        print(subject,entry["status"],entry.get("error",""),flush=True)
    sheet.save(OUTPUT/"ALL_SOURCE_OPTIONS.jpg",quality=88,optimize=True)
    (OUTPUT/"SOURCE_AUDIT.json").write_text(json.dumps({
        "status":"research_only_not_published",
        "source_collection":"IVE Show What I Have World Tour, Amsterdam 13 June 2024",
        "author":"Robbie Klinkenberg / Redalert2fan",
        "license":"CC BY-SA 4.0",
        "expected_members":["YUJIN","GAEUL","REI","WONYOUNG","LIZ","LEESEO"],
        "next_step":"Human visual identity/quality check, reject photos reused in RARE and EPIC, crop only real single subjects with minimum 600x800 source pixels.",
        "candidates":report,
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Sourced {sum(r['status'].startswith('loaded') for r in report)}/{len(report)} reference photographs")


if __name__=="__main__":
    inspect()
