"""One canonical DOLCE EMPIRE photo-card layout for every rarity and album.

This renderer only composites pre-existing, credited REAL portraits. It never
synthesizes a face, changes a card's photo identity, or modifies source ledgers.
A legacy PNG already has graphics baked in; opaque frame/footer/header zones
cover those *only*, while the central portrait remains pixel-identical.
"""
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps

CARD_SIZE = (900, 1200)
ACCENTS = {
    "rare": "#74c7ff",
    "epic": "#dca8ff",
    "legendary": "#ffe5a3",
    "mythic": "#ff91dc",
}
INK = (8, 13, 31)
MARGIN = (8, 12, 32)
PORTRAIT_REGION = (370, 175, 530, 860)


def font(size):
    for name in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def render_master(photo, *, name, group, era, rarity, number, total,
                  legacy=False, focus=(0.5, 0.35)):
    """Composites same 900x1200 UI in fixed geometry for all members/sets."""
    if rarity not in ACCENTS:
        raise ValueError("Unknown rarity " + rarity)
    if not (1 <= number <= total):
        raise ValueError("Invalid card index")
    if legacy:
        # The playable PNG already contains the original photograph.
        # Do NOT attempt to AI-inpaint or resynthesize obscured photo pixels.
        if photo.size != CARD_SIZE:
            raise ValueError("Legacy collectible must be 900x1200")
        background = photo.convert("RGB")
    else:
        # For all FUTURE releases: use the real unframed original photo.
        background = ImageOps.fit(
            photo.convert("RGB"), CARD_SIZE,
            method=Image.Resampling.LANCZOS, centering=focus
        )
        background = ImageEnhance.Contrast(background).enhance(1.025)
    base = background.convert("RGBA")
    wipe = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(wipe, "RGBA")
    # A consistent dark-card perimeter hides incompatible old frame shapes.
    # Existing photo remains intact in the central region.
    d.rectangle((0, 0, 58, 1200), fill=MARGIN + (255,))
    d.rectangle((842, 0, 900, 1200), fill=MARGIN + (255,))
    d.rectangle((0, 0, 900, 32), fill=MARGIN + (255,))
    d.rectangle((0, 1166, 900, 1200), fill=MARGIN + (255,))
    if legacy:
        # Old SPOTLIGHT and AURA templates had different pill geometries.
        d.rounded_rectangle((58, 54, 350, 127), radius=13, fill=INK + (255,))
        d.rounded_rectangle((607, 54, 844, 144), radius=13, fill=INK + (255,))
    # Universal dark fade fully erases old series numbering and name.
    for y in range(870, 1167):
        amount = max(0.0, min(1.0, (y - 870) / 117.0))
        d.line((59, y, 841, y),
               fill=INK + (round(255 * amount ** 1.65),), width=1)
    base = Image.alpha_composite(base, wipe)

    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    accent = tuple(bytes.fromhex(ACCENTS[rarity].lstrip("#")))
    # The following coordinates are intentionally fixed for EVERY card.
    draw.rounded_rectangle((22, 23, 877, 1177),
                           radius=36, outline=accent + (255,), width=8)
    draw.rounded_rectangle((40, 40, 859, 1160),
                           radius=28, outline=(250, 250, 255, 205), width=2)
    draw.rounded_rectangle((65, 62, 340, 114),
                           radius=12, fill=INK + (255,))
    draw.rounded_rectangle((637, 62, 835, 114),
                           radius=12, fill=INK + (255,))
    draw.text((82, 87), "DOLCE EMPIRE",
              font=font(20), anchor="lm", fill=(255, 255, 255, 255))
    draw.text((735, 87), rarity.upper(),
              font=font(24), anchor="mm", fill=accent + (255,))

    label = name.upper()
    label_size = 69
    while label_size > 34 and draw.textbbox(
        (0, 0), label, font=font(label_size)
    )[2] > 750:
        label_size -= 2
    draw.text((450, 1024), label, anchor="mm", font=font(label_size),
              fill=(255, 255, 255, 255), stroke_width=2,
              stroke_fill=(4, 5, 16, 255))
    draw.text((450, 1091), f"{group}  /  {era}",
              anchor="mm", font=font(26), fill=accent + (255,))
    draw.text((450, 1138), f"{number:02d}/{total:02d}   •   {rarity.upper()}",
              anchor="mm", font=font(21), fill=(245, 246, 255, 255))
    return Image.alpha_composite(base, overlay).convert("RGB")
