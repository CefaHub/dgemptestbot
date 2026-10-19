"""Make one browsable visual QA sheet from ALL released game-card PNG files."""
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/previews/design_audit/ALL_RELEASED_CARD_DESIGNS.jpg"
THUMB = (148, 198)
CELL = (173, 244)
COLUMNS = 8


def contact_sheet():
    cards = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    rows = math.ceil(len(cards) / COLUMNS)
    overview = Image.new("RGB", (CELL[0] * COLUMNS, 60 + CELL[1] * rows),
                         (11, 14, 32))
    d = ImageDraw.Draw(overview)
    fontpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    boldpath = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    regular = ImageFont.truetype(fontpath, 12)
    bold = ImageFont.truetype(boldpath, 18)
    d.text((24, 18), f"DOLCE EMPIRE / {len(cards)} RELEASED PHOTO CARDS / UNIFIED DESIGN",
           fill=(248, 248, 255), font=bold)
    for idx, card in enumerate(cards):
        image_path = ROOT / card["image_path"]
        with Image.open(image_path) as original:
            if original.size != (900, 1200):
                raise ValueError(f"Unusual card shape: {image_path}")
            thumb = ImageOps.contain(
                original.convert("RGB"), THUMB, method=Image.Resampling.LANCZOS
            )
        left = idx % COLUMNS * CELL[0]
        top = 60 + idx // COLUMNS * CELL[1]
        overview.paste(thumb, (left + 10, top))
        d.text((left + 10, top + 201), card["idol"][:22],
               fill=(244, 244, 255), font=regular)
        d.text((left + 10, top + 219), f"{card['group']} / {card['rarity'].upper()}"[:27],
               fill=(171, 200, 234), font=regular)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    overview.save(OUT, "JPEG", quality=87, optimize=True, subsampling=0)
    print(f"Visual QA: {OUT}, {len(cards)} photo cards, {rows} rows")


if __name__ == "__main__":
    contact_sheet()
