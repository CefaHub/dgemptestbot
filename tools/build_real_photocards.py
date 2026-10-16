#!/usr/bin/env python3
"""Original-photos-only image compositing. No AI-generated faces or image synthesis."""
import json
import math
import os
import random
import time
import urllib.request
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

BASE = Path(__file__).resolve().parent
MANIFEST = json.loads((BASE / "photo_sources.json").read_text(encoding="utf-8"))
OUT = BASE.parent / "output"
SRC = OUT / "original_photos"
CARDS = OUT / "cards_3x4"
BANNERS = OUT / "banners_16x9"
CACHE = os.getenv("DOLCE_TEST_LOCAL_PHOTOS")
UA = "DolceEmpireCardCreator/1.0 (github: CefaHub/dgemptestbot; offline rendering and Wikimedia attribution)"
W,H = 900,1200
BW,BH = 1600,900
COLORS = {
    "illit": {"base": (18,19,38),"deep":(28,26,55),"highlight":(242,206,252),"accent":(181,156,250),"faint":(240,233,255),"bg":(47,35,74)},
    "aespa": {"base": (8,14,30),"deep":(10,28,51),"highlight":(137,225,255),"accent":(97,153,239),"faint":(224,247,255),"bg":(15,36,57)}
}
RARITY_COLOR={"RARE":(113,185,246),"EPIC":(192,132,252),"LEGENDARY":(255,204,112),"MYTHIC":(235,115,202)}

def font(size=48,bold=False):
    choices = (["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf","/usr/share/fonts/truetype/lato/Lato-Bold.ttf"] if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf","/usr/share/fonts/truetype/lato/Lato-Regular.ttf"])
    for p in choices:
        if Path(p).is_file():return ImageFont.truetype(p,size)
    return ImageFont.load_default()


def fetch_photo(row):
    url = row['photo']
    local = SRC / (row['id'] + ('.png' if url.endswith('.png') else '.jpg'))
    if local.exists():
        return Image.open(local).convert('RGB')
    if CACHE:
        p=Path(CACHE)/ (row['id']+'.png')
        if not p.is_file(): raise RuntimeError(f"Missing explicit test image: {p}")
        return Image.open(p).convert('RGB')
    # Prefer Commons cached thumbnail rather than rate-limited original.
    from urllib.parse import urlsplit
    url_path = urlsplit(url).path
    if url_path.startswith('/wikipedia/commons/'):
        name = url_path.rsplit('/', 1)[-1]
        thumb_root = 'https://thumb.wikimedia.org' + url_path.replace('/wikipedia/commons/', '/wikipedia/commons/thumb/', 1)
        candidates = [thumb_root + '/500px-' + name, url]
    else:
        candidates = [url]
    errors = []
    for candidate in candidates:
        req = urllib.request.Request(candidate, headers={'User-Agent': UA, 'Accept': 'image/png,image/jpeg,image/*;q=0.9'})
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=25) as response:
                    buf = response.read(24_000_000)
                check = Image.open(BytesIO(buf))
                check.verify()
                local.write_bytes(buf)
                return Image.open(local).convert('RGB')
            except Exception as exc:
                errors.append(str(exc))
                if attempt == 0:
                    time.sleep(2)
    raise RuntimeError('Unable to fetch real photograph ' + row['id'] + ': ' + '; '.join(errors))


def rounded_photo(c,photo,xy,radius=24,zoom=1,shift_y=0):
    x,y,w,h=xy
    out=ImageOps.fit(photo,(w,h),method=Image.Resampling.LANCZOS,centering=(.5,max(.0,min(1.0,.5+shift_y))))
    m=Image.new('L',(w,h));ImageDraw.Draw(m).rounded_rectangle((0,0,w-1,h-1),radius=radius,fill=255)
    c.paste(out,(x,y),m)


def gradient_overlay(width,height,color,alpha_top=0,alpha_bottom=190):
    o=Image.new('RGBA',(width,height),(0,0,0,0)); pix=o.load()
    for y in range(height):
        t=y/max(1,height-1);alpha=int(alpha_top+(alpha_bottom-alpha_top)*t*t)
        for x in range(width):pix[x,y]=(*color,alpha)
    return o


def sparkle(draw,x,y,col,s=8):
    draw.line((x-s,y,x+s,y),fill=(*col,220),width=max(1,int(s/6)))
    draw.line((x,y-s*1.3,x,y+s*1.3),fill=(*col,220),width=max(1,int(s/6)))
    draw.ellipse((x-2,y-2,x+2,y+2),fill=(255,255,255,250))


def right_text(draw,xy,text,fill,fontobj):
    box=draw.textbbox((0,0),text,font=fontobj)
    draw.text((xy[0]-(box[2]-box[0]),xy[1]),text,font=fontobj,fill=fill)


def frame_rect(d,xy,col,width=2,r=30):
    d.rounded_rectangle(xy,radius=r,outline=col,width=width)


def render_card(row,photo):
    cc=COLORS[row['palette']];name=row['member'];rarity=row['rarity'];rcol=RARITY_COLOR.get(rarity,cc['highlight'])
    image=Image.new('RGB',(W,H),cc['base']); draw=ImageDraw.Draw(image)
    for y in range(H):
        t=y/H;draw.line((0,y,W,y),fill=tuple(int(cc['deep'][k]*(1-t)+cc['bg'][k]*t) for k in range(3)))
    # reflective backing and authentic photograph
    draw.rounded_rectangle((32,32,868,1168),radius=32,fill=(226,213,251) if row['palette']=='illit' else (104,160,196))
    draw.rounded_rectangle((42,42,858,1158),radius=26,fill=cc['base'])
    rounded_photo(image,photo,(57,69,786,951),radius=22,shift_y=-0.04)
    shade=gradient_overlay(786,951,cc['base'],0,210)
    mask=Image.new('L',(786,951));ImageDraw.Draw(mask).rounded_rectangle((0,0,785,950),radius=22,fill=255)
    shade.putalpha(Image.composite(shade.getchannel('A'),Image.new('L',(786,951)),mask))
    image.paste(Image.alpha_composite(image.crop((57,69,843,1020)).convert('RGBA'),shade).convert('RGB'),(57,69))
    d=ImageDraw.Draw(image,'RGBA')
    # hairline frame, corners, small technical labels
    d.rounded_rectangle((29,29,870,1170),radius=35,outline=(*cc['faint'],220),width=3)
    d.rounded_rectangle((51,63,849,1027),radius=24,outline=(*cc['highlight'],160),width=3)
    d.rounded_rectangle((74,81,301,127),radius=12,fill=(*cc['base'],205),outline=(*cc['highlight'],180),width=2)
    d.text((90,92),'DOLCE  EMPIRE',font=font(17,True),fill=cc['faint'])
    d.rounded_rectangle((618,82,824,136),radius=15,fill=(*cc['base'],227),outline=(*rcol,240),width=3)
    d.text((645,96),rarity,font=font(24,True),fill=(*rcol,255))
    for x,y,s in [(72,38,10),(817,35,15),(40,610,8),(862,438,7),(795,1096,9),(115,1060,7)]: sparkle(d,x,y,cc['highlight'],s)
    d.line((110,1032,789,1032),fill=(*cc['highlight'],200),width=2)
    label_font=font(72 if len(name)<=6 else 63,True)
    # central name with shadow
    bbox=d.textbbox((0,0),name,font=label_font,stroke_width=1);tw=bbox[2]-bbox[0]
    x=(W-tw)//2
    d.text((x+3,1028+5),name,font=label_font,fill=(0,0,0,180))
    d.text((x,1028),name,font=label_font,fill=cc['faint'],stroke_width=1,stroke_fill=cc['base'])
    d.text((W//2,1140),row['group'].upper()+'   /   001',font=font(20,True),anchor='mm',fill=(*cc['highlight'],240))
    d.line((126,1124,275,1124),fill=(*cc['highlight'],150),width=2)
    d.line((625,1124,774,1124),fill=(*cc['highlight'],150),width=2)
    path=CARDS/(row['id']+'.png');image.save(path,optimize=True)
    return path


def collage_from_card_photos(group):
    """Compose four authentic member photos; no new requests or AI faces."""
    members = [row for row in MANIFEST['cards'] if row['group'].lower() == group.lower()]
    if len(members) < 4:
        raise ValueError('Expected four real source portraits for ' + group)
    result = Image.new('RGB', (BW, BH), (20, 20, 35))
    band = BW // 4
    for idx, row in enumerate(members[:4]):
        src = SRC / (row['id'] + ('.png' if row['photo'].endswith('.png') else '.jpg'))
        with Image.open(src) as ph:
            portrait = ImageOps.fit(ph.convert('RGB'), (band, BH),
                                    method=Image.Resampling.LANCZOS,
                                    centering=(.5, .35))
        result.paste(portrait, (idx * band, 0))
    d = ImageDraw.Draw(result, 'RGBA')
    for x in (band, 2 * band, 3 * band):
        d.line((x, 0, x, BH), fill=(245, 228, 255, 145), width=3)
    return result


def gradient_transparent(width,height,color,gradient='left'):
    g=Image.new('RGBA',(width,height),(0,0,0,0));pix=g.load()
    for y in range(height):
        for x in range(width):
            t=x/width if gradient=='left' else y/height
            a=round(245*(1-t)**2) if gradient=='left' else round(230*t)
            pix[x,y]=(*color,a)
    return g


def render_banner(row,photo):
    cc=COLORS[row['palette']]
    image=ImageOps.fit(photo,(BW,BH),method=Image.Resampling.LANCZOS,centering=(.5,.52)).convert('RGBA')
    image=Image.alpha_composite(image,gradient_transparent(BW,BH,cc['base']))
    image=Image.alpha_composite(image,gradient_transparent(BW,BH,cc['deep'],'bottom'))
    d=ImageDraw.Draw(image,'RGBA')
    d.rounded_rectangle((23,23,BW-23,BH-23),radius=28,outline=(*cc['highlight'],190),width=5)
    d.rounded_rectangle((36,36,BW-36,BH-36),radius=23,outline=(*cc['faint'],100),width=2)
    d.rounded_rectangle((82,67,405,126),radius=12,fill=(*cc['base'],225),outline=(*cc['highlight'],190),width=2)
    d.text((101,84),'DOLCE  EMPIRE',font=font(27,True),fill=cc['faint'])
    d.text((86,200),row['group'].upper()+'  /  NEW DROP',font=font(28,True),fill=cc['highlight'])
    title=row['title'].split(' ')[0]
    d.text((80,284),title,font=font(130,True),fill=cc['faint'],stroke_width=2,stroke_fill=cc['base'])
    d.text((84,444),'SPOTLIGHT',font=font(75,True),fill=cc['highlight'])
    d.line((90,565,730,565),fill=(*cc['highlight'],160),width=3)
    d.text((91,595),row['subtitle'],font=font(27,True),fill=cc['faint'])
    d.text((91,755),'LIMITED COLLECTION    •    K-POP TYCOON',font=font(22,True),fill=cc['faint'])
    for x,y,s in [(1480,78,12),(700,82,9),(1456,772,18),(51,601,8),(1301,69,11)]:sparkle(d,x,y,cc['highlight'],s)
    path=BANNERS/(row['id']+'.png');image.convert('RGB').save(path,optimize=True)
    return path


def credits():
    entries=MANIFEST['cards']+MANIFEST['banners']
    lines=['# Original photo credits / Источники реальных фотографий','','Images on these cards and banners are original REAL photographs, **not AI-generated**. Cards/banners are modified (cropping, frames, typography, colors).','Each entry preserves author, file link and license as required under Creative Commons attribution.','**Important:** public image license does not waive artists\' publicity/personality rights; verify permitted use before deploying widely.','']
    cards_by_id = {c['id']: c for c in MANIFEST['cards']}
    for e in entries:
        lines += ['## ' + e['id']]
        if e.get('source_card_ids'):
            lines += ['- Composite banner from REAL member photos; no AI portraits.']
            for card_id in e['source_card_ids']:
                c = cards_by_id[card_id]
                lines += ['- ' + c['member'] + ': ' + c['author'] + ' — ' + c['page'] + ' — ' + c['license'] + ' (' + c['license_url'] + ')']
        else:
            lines += ['- Author / Автор: ' + e['author'],
                      '- Original / Оригинал: ' + e['page'],
                      '- License / Лицензия: ' + e['license'] + ' — ' + e['license_url']]
            if e['license_review'] == 'pending':
                lines += ['- WARNING: License review pending on Commons; verify before public distribution.']
        lines += ['- Modification: real photographs cropped and composited into fan-made card or banner.', '']
    (OUT/'PHOTO_CREDITS.md').write_text('\n'.join(lines),encoding='utf-8')


def main():
    for folder in [OUT,SRC,CARDS,BANNERS]: folder.mkdir(parents=True,exist_ok=True)
    for row in MANIFEST['cards']:
        print('CARD',row['id'],flush=True);render_card(row,fetch_photo(row))
    for row in MANIFEST['banners']:
        print('BANNER COLLAGE', row['id'], flush=True)
        render_banner(row, collage_from_card_photos(row['group']))
    credits()
    (OUT/'MANIFEST.json').write_text(json.dumps(MANIFEST,ensure_ascii=False,indent=2),encoding='utf-8')
    import zipfile
    with zipfile.ZipFile(OUT/'DolceEmpire_REAL_PHOTOS_8_CARDS_2_BANNERS.zip','w',zipfile.ZIP_DEFLATED) as z:
        for folder in [CARDS,BANNERS]:
            for f in folder.glob('*.png'): z.write(f, f.relative_to(OUT))
        for f in [OUT/'PHOTO_CREDITS.md',OUT/'MANIFEST.json']:z.write(f,f.name)
    print('SUCCESS:',OUT/'DolceEmpire_REAL_PHOTOS_8_CARDS_2_BANNERS.zip')

if __name__=='__main__':main()
