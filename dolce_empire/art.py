"""Procedural card graphics; optionally uses owner-supplied licensed image assets.
No idol photographs are redistributed in this repository.
"""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .catalog import ROOT, get_card

PALETTE = {
    'common': ('#536072','#1a2331','#cbd4df'),
    'rare': ('#1b75aa','#101a37','#72dbff'),
    'epic': ('#7041bb','#23143f','#cca5ff'),
    'legendary': ('#b4842b','#291d12','#ffda86'),
    'mythic': ('#138d90','#071c33','#9ffbff'),
    'secret': ('#ba235a','#230c22','#ff8dc4'),
}
FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
         '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
         'C:/Windows/Fonts/arial.ttf']


def font(size):
    for location in FONTS:
        if Path(location).exists():
            return ImageFont.truetype(location,size)
    return ImageFont.load_default()


def rgb(code):
    return tuple(bytes.fromhex(code.lstrip('#')))


def blend(a,b,t):
    return tuple(int(x*(1-t)+y*t) for x,y in zip(a,b))


def _asset(card_id):
    for suffix in ('.jpg','.jpeg','.png','.webp'):
        path=ROOT/'assets'/'idols'/f'{card_id}{suffix}'
        if path.is_file() and path.stat().st_size <= 12_000_000:
            return path
    return None


def _fit_font(text,max_px,starting):
    sz=starting
    while sz>18:
        f=font(sz)
        if ImageDraw.Draw(Image.new('RGB',(1,1))).textbbox((0,0),text,font=f)[2] <= max_px:
            return f
        sz-=2
    return font(sz)

@lru_cache(maxsize=96)
def render_card(definition_id, level=1, awakening=0, serial=0):
    c=get_card(definition_id)
    if c is None: raise ValueError('Unknown card')
    width,height=700,1000
    primary,dark,light=PALETTE[c['rarity']]
    p,d,l=rgb(primary),rgb(dark),rgb(light)
    image=Image.new('RGB',(width,height))
    dr=ImageDraw.Draw(image)
    for y in range(height):
        fraction=y/(height-1)
        dr.line([(0,y),(width,y)],fill=blend(p,d,min(.98, fraction**0.65)))
    # Geometry behind main figure; always yields meaningful illustration without photos.
    dr=ImageDraw.Draw(image,'RGBA')
    for radius in (260,215,150,90):
        dr.ellipse((350-radius,350-radius,350+radius,350+radius),outline=(*l,45),width=4)
    for i in range(14):
        x=35+i*47
        y=125+(i*71)%530
        dr.ellipse((x,y,x+4,y+4),fill=(*l,130))
    asset=_asset(definition_id)
    if asset:
        try:
            portrait=Image.open(asset).convert('RGB')
            box=(48,158,652,742)
            target_w,target_h=box[2]-box[0],box[3]-box[1]
            s=max(target_w/portrait.width,target_h/portrait.height)
            portrait=portrait.resize((round(portrait.width*s),round(portrait.height*s)),Image.Resampling.LANCZOS)
            left=(portrait.width-target_w)//2;top=(portrait.height-target_h)//2
            portrait=portrait.crop((left,top,left+target_w,top+target_h))
            overlay=Image.new('L',(target_w,target_h),220)
            image.paste(portrait,(box[0],box[1]),overlay)
        except Exception:
            pass
    else:
        # Distinct abstract cover without pretending this is an actual idol photo.
        dr.polygon([(118,590),(350,205),(580,590),(470,725),(225,725)],fill=(*l,48))
        dr.ellipse((232,255,470,490),outline=(*l,145),width=9)
        dr.line((340,227,340,590),fill=(*l,135),width=5)
        dr.text((350,455),c['idol'][0].upper(),font=font(186),anchor='mm',fill=(*l,180))
        dr.text((350,674),'ARTWORK SLOT',font=font(20),anchor='mm',fill=(*l,150))
    dr.rectangle((18,18,682,982),outline=(*l,245),width=7)
    dr.rectangle((30,30,670,970),outline=(*l,100),width=2)
    dr.rounded_rectangle((55,50,645,135),radius=20,fill=(*d,200))
    dr.text((350,92),'D O L C E   E M P I R E',font=font(31),anchor='mm',fill=(*l,255))
    dr.rounded_rectangle((45,747,655,955),radius=20,fill=(*d,242),outline=(*l,170),width=2)
    dr.text((350,795),c['idol'].upper(),font=_fit_font(c['idol'].upper(),550,59),anchor='mm',fill=(255,255,255,255))
    dr.text((350,853),f"{c['group']}  /  {c['era']}",font=_fit_font(c['group']+' '+c['era'],570,27),anchor='mm',fill=(*l,255))
    dr.text((65,911),c['rarity'].upper(),font=font(26),fill=(*l,255))
    dr.text((633,911),f'LV.{level}  AW.{awakening}',font=font(22),anchor='ra',fill=(*l,255))
    result=BytesIO();image.save(result,format='PNG',optimize=True)
    return result.getvalue()
