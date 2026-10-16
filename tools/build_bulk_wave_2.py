#!/usr/bin/env python3
"""Generate collectible cards from credited REAL photos. Never synthesizes people."""
import argparse
import hashlib
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "tools/bulk_wave_2.json").read_text(encoding="utf-8"))
OUT = ROOT / "output" / "bulk_wave_2"
W, H = 900, 1200
BW, BH = 1600, 900
COLORS = {
    "illit": (202, 158, 252),
    "aespa": (133, 203, 254),
    "ive": (238, 171, 231),
    "itzy": (255, 120, 157),
    "lesserafim": (255, 172, 190),
}
TIER = {
    "rare": (78, 160, 249),
    "legendary": (255, 204, 107),
    "mythic": (209, 144, 255),
}
UA = "DolceEmpireKpopPhotoEdition/2.0 (CefaHub/dgemptestbot; credited Wikimedia-Commons photography)"


def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).is_file():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def weighted(c1, c2, t):
    return tuple(max(0, min(255, int(a * (1-t) + b*t))) for a,b in zip(c1,c2))


def portrait_from_bytes(data):
    with Image.open(BytesIO(data)) as src:
        src.verify()
    with Image.open(BytesIO(data)) as src:
        img = ImageOps.exif_transpose(src).convert("RGB")
    if min(img.size) < 320:
        raise RuntimeError(f"Photo too small for a 3:4 card: {img.size}")
    return img


def image_urls(row):
    if row.get("photo"):
        original = row["photo"]
    else:
        filename = row["file_title"].replace(" ", "_")
        digest = hashlib.md5(filename.encode("utf-8")).hexdigest()
        original = (
            "https://upload.wikimedia.org/wikipedia/commons/"
            + digest[0] + "/" + digest[:2] + "/" + urllib.parse.quote(filename, safe="()_'")
        )
    path = urllib.parse.urlsplit(original).path
    name = path.rsplit("/", 1)[-1]
    thumb = "https://upload.wikimedia.org" + path.replace("/wikipedia/commons/", "/wikipedia/commons/thumb/", 1)
    # Thumbnails lower Wikimedia bandwidth and normally avoid the 429 limit on originals.
    return [thumb + "/640px-" + name, thumb + "/500px-" + name, original]


def load_source(row):
    cache = OUT / "source_cache" / (row["id"] + ".jpg")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        with Image.open(cache) as photo:
            return photo.convert("RGB")
    errors = []
    for url in image_urls(row):
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/jpeg,image/png,image/*"})
                with urllib.request.urlopen(req, timeout=30) as reply:
                    content = reply.read(16_000_000)
                photo = portrait_from_bytes(content)
                photo.save(cache, "JPEG", quality=94, optimize=True)
                print(f"SOURCE {row['id']} {photo.size} OK", flush=True)
                time.sleep(0.7)
                return photo
            except (OSError, urllib.error.URLError, RuntimeError) as exc:
                errors.append(str(exc))
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 429:
                    time.sleep(4 + attempt * 5)
                else:
                    time.sleep(1 + attempt)
    raise RuntimeError(f"Could not fetch real photo {row['id']} ({row['page']}): " + "; ".join(errors[-5:]))


def card_image(row, source):
    groupkey = row["image_path"].split("/")[2]
    groupcolor = COLORS[groupkey]
    tier = TIER[row["rarity"]]
    bg = (10, 15, 32) if row["rarity"] == "rare" else (27, 17, 35)
    if row["rarity"] == "mythic":
        bg = (21, 16, 47)
    im = Image.new("RGB", (W,H), bg)
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line((0,y,W,y), fill=weighted(bg,groupcolor,.14 + .22*(1-t)))
    # Framed real member photo; all effects are outside the photograph.
    d.rounded_rectangle((26,24,874,1176), radius=35, outline=groupcolor, width=6)
    d.rounded_rectangle((40,39,860,1162), radius=29, outline=tier, width=3)
    photo = ImageOps.fit(source, (760,866), method=Image.Resampling.LANCZOS, centering=(.5,.28))
    mask = Image.new("L",(760,866),0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,759,865),radius=24,fill=255)
    im.paste(photo,(70,124),mask)
    d=ImageDraw.Draw(im,"RGBA")
    d.rectangle((70,916,830,990),fill=(*bg,220))
    d.rounded_rectangle((70,70,350,113),radius=12,fill=(*bg,235),outline=(*groupcolor,250),width=2)
    d.text((85,79),"DOLCE  EMPIRE",font=font(20,True),fill=(245,245,250,255))
    d.rounded_rectangle((580,71,827,113),radius=12,fill=(*bg,238),outline=(*tier,255),width=2)
    d.text((700,92),row["rarity"].upper(),font=font(21,True),anchor="mm",fill=(*tier,255))
    for x,y in ((93,1020),(800,1097),(817,44),(55,620),(803,610)):
        d.line((x-10,y,x+10,y),fill=(*groupcolor,230),width=2)
        d.line((x,y-10,x,y+10),fill=(*groupcolor,230),width=2)
    name=row["member"].upper()
    size=58 if len(name)>7 else 73
    d.text((450,1016),name,font=font(size,True),anchor="mm",fill=(255,255,255,255))
    d.text((450,1081),row["group"]+"  /  "+row["series"],font=font(27,True),anchor="mm",fill=(*groupcolor,255))
    d.text((450,1130),f"{row['card_number']:02d}/{row['card_total']:02d}     •     {row['rarity'].upper()}",font=font(22,True),anchor="mm",fill=(*tier,255))
    return im


def banner_image(group, series, members, sources):
    key=group["slug"]
    col=COLORS[key]
    tier=TIER[series["rarity"]]
    im=Image.new("RGB",(BW,BH),(12,17,37))
    d=ImageDraw.Draw(im)
    for y in range(BH):
        d.line((0,y,BW,y),fill=weighted((12,17,37),col,.08 + .19*(1-y/BH)))
    # Compose *all* real portraits in a 2-row mosaic, with text safely left.
    startx=625
    rw=930
    top=85
    if len(members)<=4:
        columns=2
    else:
        columns=3
    upper=members[:columns]
    lower=members[columns:]
    for rowidx,chunk in enumerate((upper,lower)):
        if not chunk:continue
        width = rw//len(chunk)
        height=365
        for i,item in enumerate(chunk):
            shot=ImageOps.fit(sources[item["source_id"]],(width-10,height-10),centering=(.5,.22),method=Image.Resampling.LANCZOS)
            mask=Image.new("L",shot.size,0)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,shot.width-1,shot.height-1),radius=18,fill=255)
            x=startx+i*width+(width-shot.width)//2
            y=top+rowidx*height+5
            im.paste(shot,(x,y),mask)
    d=ImageDraw.Draw(im,"RGBA")
    d.rounded_rectangle((20,20,BW-20,BH-20),radius=24,outline=(*col,255),width=5)
    d.rounded_rectangle((35,35,BW-35,BH-35),radius=23,outline=(*tier,200),width=2)
    d.rounded_rectangle((55,62,420,128),radius=15,fill=(12,17,37,230),outline=(*col,220),width=2)
    d.text((73,79),"DOLCE  EMPIRE",font=font(31,True),fill=(245,245,255,255))
    group_name=group["group"].upper()
    label_size=76 if len(group_name)<=7 else 50
    d.text((66,274),group_name,font=font(label_size,True),fill=(250,250,255,255))
    d.text((66,384),series["name"],font=font(54,True),fill=(*col,255))
    d.text((70,484),series["rarity"].upper()+"  /  FULL SET",font=font(32,True),fill=(*tier,255))
    d.line((75,551,562,551),fill=(*tier,230),width=3)
    d.text((75,595),f"{len(members)} MEMBERS   •   REAL PHOTOS",font=font(21,True),fill=(237,237,247,255))
    d.text((75,773),"COLLECT THEM ALL",font=font(24,True),fill=(237,237,247,255))
    return im


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--group",required=True,choices=[g["slug"] for g in DATA["groups"]])
    parser.add_argument("--members",default="",help="Optional comma-separated split for rate-limited group")
    opts=parser.parse_args()
    g=next(x for x in DATA["groups"] if x["slug"]==opts.group)
    member_filter={v.strip().upper() for v in opts.members.split(",") if v.strip()}
    photo_rows=[x for x in DATA["photo_sources"] if x["group"] == g["group"]
                and (not member_filter or x["member"].upper() in member_filter)]
    if member_filter and {x["member"].upper() for x in photo_rows} != member_filter:
        raise ValueError('Unknown or duplicate member selected for split')
    sources={x["id"]:load_source(x) for x in photo_rows}
    member_rows=[c for c in DATA["cards"] if c["image_path"].split("/")[2]==g["slug"]
                 and c["photo_source_id"] in sources]
    tiers=DATA["series"]
    created=[]
    for row in member_rows:
        photo=sources[row["photo_source_id"]]
        out=OUT / row["image_path"]
        out.parent.mkdir(parents=True,exist_ok=True)
        card_image(row,photo).save(out,"PNG",optimize=True)
        created.append(out)
    if not member_filter:
        for tier in tiers:
            banner=next(b for b in DATA["banners"] if b["slug"]==g["slug"] and b["rarity"]==tier["rarity"])
            rows=[c for c in member_rows if c["rarity"]==tier["rarity"]]
            members=[{"source_id":r["photo_source_id"]} for r in rows]
            out=OUT / banner["image_path"]
            out.parent.mkdir(parents=True,exist_ok=True)
            banner_image(g,tier,members,sources).save(out,"PNG",optimize=True)
            created.append(out)
    # GitHub Actions artifacts include only finished game media, not source photographs.
    print(f"COMPLETE {g['group']}: {len(created)} png assets",flush=True)

if __name__=="__main__":
    main()
