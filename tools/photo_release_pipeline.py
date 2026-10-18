#!/usr/bin/env python3
"""Curated DOLCE EMPIRE K-pop photo release pipeline.

Usage:
  python tools/photo_release_pipeline.py plan
  python tools/photo_release_pipeline.py build --manifest tools/photo_releases.json
  python tools/photo_release_pipeline.py build --manifest tools/photo_releases.json --publish

A release needs its full member lineup, attributable permission-cleared REAL
photographs, and distinct original images across all rarities. No AI faces.
"""
import argparse
import hashlib
import json
import shutil
import urllib.request
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlsplit, parse_qs

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT / "tools/photo_release_plan.json").read_text("utf-8"))
OUT = ROOT / "output/photo_release_batch"
CARD_SIZE = (900, 1200)
BANNER_SIZE = (1600, 900)
TIER_COLORS = {t["rarity"]: t["color"] for t in PLAN["tiers"]}
GROUPS = {g["name"]: g for g in PLAN["groups"]}
TIERS = {(t["era"], t["rarity"]): t for t in PLAN["tiers"]}
USER_AGENT = "DolceEmpirePhotoCurator/1.0 (public attribution, contact CefaHub)"


def canonical(url):
    """Normalize source identity; CDN proxy queries contain the ORIGINAL photo path."""
    parsed = urlsplit(url.strip())
    host = parsed.netloc.lower()
    if host in {"wsrv.nl", "images.weserv.nl"}:
        origin = parse_qs(parsed.query).get("url", [""])[0]
        if origin:
            if "://" not in origin:
                origin = "https://" + origin.lstrip("/")
            return canonical(origin)
    return host + unquote(parsed.path).replace("_", " ").casefold().rstrip("/")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def font(size, heavy=False):
    choices = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if heavy else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if heavy else "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in choices:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def original_image(row):
    """Fetch only explicit real-image URLs; never scrape, hallucinate or substitute."""
    if row.get("local_path"):
        p = (ROOT / row["local_path"]).resolve()
        inbox = (ROOT / "photos/inbox").resolve()
        if not p.is_relative_to(inbox):
            raise ValueError("Local originals must be inside photos/inbox")
        raw = p.read_bytes()
    else:
        url = row.get("photo_url", "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("A direct HTTPS original photo URL is required")
        request = urllib.request.Request(
            url, headers={"User-Agent": USER_AGENT, "Accept": "image/jpeg,image/png,image/webp"}
        )
        with urllib.request.urlopen(request, timeout=35) as response:
            if response.headers.get("Content-Length") and int(response.headers["Content-Length"]) > 20_000_000:
                raise ValueError("Original image exceeds 20 MB")
            raw = response.read(20_000_001)
    if len(raw) > 20_000_000:
        raise ValueError("Original image exceeds 20 MB")
    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as loaded:
            photo = ImageOps.exif_transpose(loaded).convert("RGB")
    except (OSError, ValueError) as error:
        raise ValueError("Source is not a valid real photograph file") from error
    width, height = photo.size
    # Test the actual area available after cropping to 3:4. No stretching.
    crop_width = min(width, int(height * 3 / 4))
    crop_height = min(height, int(width * 4 / 3))
    if crop_width < 600 or crop_height < 800:
        raise ValueError(f"Source too small for a quality 3:4 crop: {photo.size}")
    return raw, photo


def perceptual_hash(photo):
    """dHash on a standardized 3:4 photo crop; detects re-encoded/resized duplicates."""
    thumb = ImageOps.fit(photo, (90, 120), method=Image.Resampling.LANCZOS)
    thumb = thumb.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = list(thumb.getdata())
    bits = 0
    for y in range(8):
        for x in range(8):
            bits = (bits << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return bits


def color(hexvalue):
    return tuple(bytes.fromhex(hexvalue.lstrip("#")))


def solo_region(photo, region):
    """Strict optional source crop for an actual one-person portrait.

    The cutout must still have at least 600x800 usable pixels for 3:4.
    Keep attribution and source SHA for the *whole original photograph*,
    while visual duplicate checks apply to the final person-only region.
    """
    if region is None:
        return photo
    if (not isinstance(region, (list, tuple)) or len(region) != 4
            or any(isinstance(value, bool) or not isinstance(value, (float, int))
                   for value in region)):
        raise ValueError("solo_region must be [left, top, right, bottom] fractions")
    left, top, right, bottom = map(float, region)
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("solo_region must be ordered coordinates from 0 to 1")
    w, h = photo.size
    crop = photo.crop((
        round(left * w), round(top * h), round(right * w), round(bottom * h)
    ))
    usable_w = min(crop.width, int(crop.height * 3/4))
    usable_h = min(crop.height, int(crop.width * 4/3))
    if usable_w < 600 or usable_h < 800:
        raise ValueError(f"Solo region is too small for 3:4 photo quality: {crop.size}")
    return crop


def zoomed_photo(photo, zoom, focus):
    """Crop away unwanted neighbors while keeping the idol centered."""
    zoom = float(zoom)
    if not 1 <= zoom <= 1.6:
        raise ValueError("Photo zoom must be between 1.0 and 1.6")
    if zoom == 1:
        return photo
    w, h = photo.size
    cw, ch = int(w / zoom), int(h / zoom)
    x = max(0, min(w - cw, round(focus[0] * w - cw / 2)))
    y = max(0, min(h - ch, round(focus[1] * h - ch / 2)))
    return photo.crop((x, y, x + cw, y + ch))


def card_art(photo, group, tier, member, number, total, focus=(0.5, 0.35)):
    """Actual photo fills 3:4; fades only at bottom—no opaque stripe over the face."""
    frame = ImageOps.fit(photo, CARD_SIZE, method=Image.Resampling.LANCZOS, centering=focus)
    frame = ImageEnhance.Contrast(frame).enhance(1.025)
    frame = frame.convert("RGBA")
    accent = color(tier["color"])
    shade = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    pixels = ImageDraw.Draw(shade, "RGBA")
    for y in range(810, 1200):
        alpha = int(238 * ((y - 810) / 390) ** 1.30)
        pixels.line((0, y, 899, y), fill=(9, 11, 29, alpha))
    pixels.rounded_rectangle((22, 22, 877, 1177), radius=30, outline=accent + (255,), width=7)
    pixels.rounded_rectangle((37, 37, 861, 1161), radius=27, outline=(255, 255, 255, 160), width=2)
    pixels.rounded_rectangle((61, 62, 310, 108), radius=12, fill=(12, 12, 31, 200))
    pixels.text((79, 75), "DOLCE EMPIRE", fill=(255, 255, 255, 255), font=font(20, True))
    pixels.rounded_rectangle((635, 62, 829, 108), radius=12, fill=(12, 12, 31, 215))
    pixels.text((731, 86), tier["rarity"].upper(), anchor="mm",
                font=font(23, True), fill=accent + (255,))
    label = member.upper()
    size = min(73, int(720 / max(1, len(label)) * 1.4))
    pixels.text((450, 1033), label, anchor="mm", font=font(size, True),
                fill=(255, 255, 255, 255), stroke_width=1, stroke_fill=(13, 12, 28, 255))
    pixels.text((450, 1100), f"{group['name']}  /  {tier['era']}", anchor="mm",
                font=font(26, True), fill=accent + (255,))
    pixels.text((450, 1141), f"{number:02d}/{total:02d}   •   {tier['rarity'].upper()}", anchor="mm",
                font=font(22, True), fill=(245, 245, 255, 255))
    return Image.alpha_composite(frame, shade).convert("RGB")


def banner_art(photos, group, tier, focuses):
    """Wide promotional artwork composed only of member photos from THIS set."""
    output = Image.new("RGB", BANNER_SIZE, (14, 19, 39))
    accent = color(tier["color"])
    left = 520
    usable = 1040
    cell_w = usable // len(photos)
    for i, (member, photo) in enumerate(photos):
        cropped = ImageOps.fit(photo, (cell_w - 8, 760),
                               method=Image.Resampling.LANCZOS, centering=focuses[member])
        output.paste(cropped, (left + i * cell_w + 4, 69))
    overlay = Image.new("RGBA", BANNER_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    draw.rectangle((25, 25, left, 875), fill=(12, 16, 32, 245))
    draw.rounded_rectangle((20, 20, 1580, 880), radius=22, outline=accent + (255,), width=5)
    draw.text((67, 95), "DOLCE EMPIRE", font=font(31, True), fill=(255, 255, 255))
    group_font = 55 if len(group["name"]) < 10 else 42
    draw.text((67, 315), group["name"].upper(), font=font(group_font, True), fill=(255, 255, 255))
    draw.text((67, 407), tier["era"], font=font(41, True), fill=accent)
    draw.text((67, 495), tier["rarity"].upper() + "  /  COMPLETE SET",
              font=font(23, True), fill=(242, 241, 248))
    draw.text((67, 765), f"{len(photos)} UNIQUE PHOTOGRAPHS", font=font(21), fill=(250, 250, 255))
    return Image.alpha_composite(output.convert("RGBA"), overlay).convert("RGB")


def plan_slots():
    existing = load_json(ROOT / "dolce_empire/_catalog.json")
    existing_ids = {c["id"] for c in existing}
    records = []
    for group in PLAN["groups"]:
        for tier in PLAN["tiers"]:
            slug = tier["era"].lower().replace(" ", "_")
            for idx, (member, translation) in enumerate(group["members"], 1):
                stem = f"{group['slug']}_{slug}_{tier['rarity']}_{member.lower()}_{idx:02d}"
                cid = "card_" + stem
                records.append({
                    "card_id": cid, "group": group["name"], "member": member,
                    "member_ru": translation, "era": tier["era"], "rarity": tier["rarity"],
                    "set_id": f"coll_{group['slug']}_{slug}_{tier['rarity']}",
                    "status": "already_published" if cid in existing_ids else "needs_unique_photo",
                })
    target = ROOT / "output/photo_release_plan.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    done = sum(x["status"] == "already_published" for x in records)
    print(f"Planned {len(records)} distinct photo slots; already published {done}, need photos {len(records)-done}.")
    return records


def check_complete_release(spec, existing_sets):
    group = GROUPS.get(spec.get("group"))
    tier = TIERS.get((spec.get("era"), spec.get("rarity")))
    if not group or not tier:
        raise ValueError("Unknown group / era / rarity: " + str(spec))
    slug = tier["era"].lower().replace(" ", "_")
    set_id = f"coll_{group['slug']}_{slug}_{tier['rarity']}"
    if set_id in existing_sets:
        raise ValueError(f"Collection already released; do not recycle cards: {set_id}")
    cards = spec.get("cards", [])
    expected = [m[0] for m in group["members"]]
    if len(cards) != len(expected) or sorted(c.get("member") for c in cards) != sorted(expected):
        raise ValueError(f"{set_id} must contain all {len(expected)} unique group members")
    if not spec.get("source_collection", "").strip():
        raise ValueError("Document a shared visual collection/concept for the whole set")
    if spec.get("source_mode", "curated") != "curated":
        raise ValueError("This pipeline publishes curated mixed-source concepts only")
    for row in cards:
        for field in ("source_page", "photographer", "license", "license_url"):
            if not str(row.get(field, "")).strip():
                raise ValueError(f"Missing {field} for {row['member']}")
        if row.get("license_status") != "verified":
            raise ValueError(f"Rights not verified for {row['member']}; cannot publish")
        if not row.get("photo_url") and not row.get("local_path"):
            raise ValueError(f"Missing real photo for {row['member']}")
        for name in ("focus_x", "focus_y"):
            if not 0 <= float(row.get(name, 0.5)) <= 1:
                raise ValueError(f"Invalid {name} for {row['member']}")
        # Fail early on malformed cutouts: full-image cropping is the default.
        region = row.get("solo_region")
        if region is not None and (
            not isinstance(region, list) or len(region) != 4 or
            any(isinstance(value, bool) or not isinstance(value, (int, float))
                for value in region) or
            not (0 <= region[0] < region[2] <= 1 and
                 0 <= region[1] < region[3] <= 1)
        ):
            raise ValueError(f"Invalid solo_region for {row['member']}")
        # Multi-person originals cannot be promoted from research to gacha
        # before checking the final portrait shows exactly one subject.
        if region is not None and row.get("solo_review_status") != "approved":
            raise ValueError(f"Unapproved solo crop for {row['member']}; preview and review before release")
    return group, tier, set_id


def generate(manifest_path, publish=False):
    manifest = load_json(ROOT / manifest_path)
    batches = manifest.get("sets", [])
    if not batches:
        raise ValueError("No sourced releases. Add REAL photos for a full set before building.")
    current = load_json(ROOT / "dolce_empire/_catalog.json")
    already_sets = load_json(ROOT / "assets/collections/verified_sets.json")["sets"]
    previous_sources = load_json(ROOT / "tools/photo_sources.json")
    urls = {canonical(s.get("photo", "")) for s in previous_sources["cards"] if s.get("photo")}
    pages = {canonical(s.get("page", "")) for s in previous_sources["cards"] if s.get("page")}
    original_hashes = {s.get("source_sha256") for s in previous_sources["cards"] if s.get("source_sha256")}
    # Compare against *earlier releases*, not just candidates in this batch.
    # Prevent the same original being re-encoded and republished as Mythic.
    photo_hashes = [
        (int(s["source_dhash"], 16), s.get("id", "older release"))
        for s in previous_sources["cards"] if s.get("source_dhash")
    ]
    set_ids = {s["set_id"] for s in already_sets}
    pending_cards, pending_sets, pending_sources = [], [], []
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for spec in batches:
        group, tier, set_id = check_complete_release(spec, set_ids)
        set_ids.add(set_id)
        slug = tier["era"].lower().replace(" ", "_")
        staged = {}
        members = [name for name, _ in group["members"]]
        by_member = {item["member"]: item for item in spec["cards"]}
        # Original Wikimedia files are often rate-limited after several thumbnail
        # downloads on the same CI runner. Fetch large originals FIRST, while
        # keeping final card numbers in the canonical group lineup order.
        prefetched_originals = {}
        for member in members:
            item = by_member[member]
            if urlsplit(item.get("photo_url", "")).netloc.lower() == "upload.wikimedia.org":
                prefetched_originals[member] = original_image(item)
        for index, (member, translated) in enumerate(group["members"], 1):
            item = by_member[member]
            source_url = item.get("photo_url") or item.get("local_path")
            page = item["source_page"]
            if canonical(source_url) in urls or canonical(page) in pages:
                raise ValueError(f"Original photo reused across releases: {member}")
            urls.add(canonical(source_url))
            pages.add(canonical(page))
            print(f'Fetching {member}: {source_url}',flush=True)
            raw, original = prefetched_originals.pop(member, None) or original_image(item)
            photo = solo_region(original, item.get("solo_region"))
            digest = hashlib.sha256(raw).hexdigest()
            if digest in original_hashes:
                raise ValueError(f"Duplicate original image bytes reused for {member}")
            original_hashes.add(digest)
            visual = perceptual_hash(photo)
            for prior, who in photo_hashes:
                if (visual ^ prior).bit_count() <= 3:
                    raise ValueError(f"Possible photo duplicate or near-identical frame: {member} / {who}")
            photo_hashes.append((visual, member))
            focus = (float(item.get("focus_x", 0.5)), float(item.get("focus_y", 0.35)))
            stem = f"{group['slug']}_{slug}_{tier['rarity']}_{member.lower()}_{index:02d}"
            card_id = "card_" + stem
            image_path = f"assets/cards/{group['slug']}/{stem}.png"
            exported = OUT / image_path
            exported.parent.mkdir(parents=True, exist_ok=True)
            framed_photo = zoomed_photo(photo, item.get("zoom", 1.0), focus)
            card_art(framed_photo, group, tier, member, index, len(members), focus).save(
                exported, "PNG", optimize=True
            )
            staged[member] = (photo, focus)
            pending_cards.append({
                "id": card_id, "group": group["name"], "idol": member.title(),
                "era": tier["era"], "rarity": tier["rarity"],
                "base_income": tier["base_income"], "aliases": [translated, member.lower()],
                "collection_id": set_id, "set_id": set_id, "source_collection": spec["source_collection"],
                "series": tier["era"], "card_number": index, "card_total": len(members),
                "image_path": image_path,
            })
            pending_sources.append({
                "id": stem, "group": group["name"], "member": member,
                "photo": source_url, "page": page,
                "original_source": item.get("original_source", page),
                "author": item["photographer"],
                "license": item["license"], "license_url": item["license_url"],
                "license_review": "confirmed", "source_sha256": digest,
                "source_dhash": f"{visual:016x}", "rarity": tier["rarity"],
                "series": tier["era"], "number": index, "total": len(members),
                "solo_region": item.get("solo_region"),
            })
        banner_path = f"assets/banners/{group['slug']}/{group['slug']}_{slug}_{tier['rarity']}_banner.png"
        banner_file = OUT / banner_path
        banner_file.parent.mkdir(parents=True, exist_ok=True)
        banner_art([(name, staged[name][0]) for name in members], group, tier,
                   {name: staged[name][1] for name in members}).save(banner_file, "PNG", optimize=True)
        pending_sets.append({
            "set_id": set_id, "group": group["name"], "era": tier["era"],
            "rarity": tier["rarity"], "source_collection": spec["source_collection"],
            "source_mode": "curated", "expected_members": members,
            "banner_path": banner_path,
        })
    additions = {"cards": pending_cards, "sets": pending_sets, "sources": pending_sources}
    (OUT / "release_metadata.json").write_text(
        json.dumps(additions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    credit_lines = [
        "# DOLCE EMPIRE — photo source credits",
        "",
        "The original photographs are NOT AI-generated.",
        "Every image below has been cropped, color-adjusted, framed and captioned.",
        "The photo and derived card/banner art retain the source license shown for each image.",
        "CC BY-SA requires author attribution, a license link, and compatible share-alike",
        "licensing for adapted artworks. Permission to use a photograph does not imply",
        "the photographer or depicted artist endorses DOLCE EMPIRE.",
        "",
    ]
    for source in pending_sources:
        credit_lines += [
            "## " + source["group"] + " / " + source["member"] + " / " + source["series"],
            "- Photo author: " + source["author"],
            "- Wikimedia page: " + source["page"],
            "- Original source: " + source["original_source"],
            "- Source license: " + source["license"],
            "- License URL: " + source["license_url"],
            "- Modifications: image crop, contrast, card frame, text and banner composition",
            "",
        ]
    credit_text = "\n".join(credit_lines)
    (OUT / "PHOTO_CREDITS_NEW_RELEASES.md").write_text(credit_text, encoding="utf-8")
    if publish:
        credits = ROOT / "assets/PHOTO_CREDITS_NEW_RELEASES.md"
        existing = credits.read_text(encoding="utf-8") if credits.exists() else ""
        credits.write_text(existing + ("\n\n" if existing else "") + credit_text,
                           encoding="utf-8")
        for image in (OUT / "assets").rglob("*.png"):
            destination = ROOT / image.relative_to(OUT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(image.read_bytes())
        current.extend(pending_cards)
        mirror = ROOT / "data/catalog.json"
        (ROOT / "dolce_empire/_catalog.json").write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        mirror.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        previous_sources["cards"].extend(pending_sources)
        (ROOT / "tools/photo_sources.json").write_text(
            json.dumps(previous_sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        saved = load_json(ROOT / "assets/collections/verified_sets.json")
        saved["sets"].extend(pending_sets)
        (ROOT / "assets/collections/verified_sets.json").write_text(
            json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        # When invoked as 'python tools/script.py', Python only puts tools/
        # on sys.path. Importing the bot package requires the repo root.
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from dolce_empire.set_validation import validate_photo_sets
        assert validate_photo_sets(current) == len(current)
        # Consume the release queue ONLY after all assets and catalog checks pass.
        # Future curators can add fresh sets without recycling previously shipped ones.
        manifest["last_published_set_ids"] = [x["set_id"] for x in pending_sets]
        manifest["sets"] = []
        (ROOT / manifest_path).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
    print(f"Built {len(pending_cards)} unique real-photo 3:4 cards and {len(pending_sets)} 16:9 banners.")
    print("Published to the game catalog." if publish else "Preview only; no live game files changed.")
    return additions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["plan", "build"])
    parser.add_argument("--manifest", default="tools/photo_releases.json")
    parser.add_argument("--publish", action="store_true",
                        help="Explicit opt-in, after source rights and assets are verified")
    args = parser.parse_args()
    if args.action == "plan":
        plan_slots()
    else:
        generate(args.manifest, publish=args.publish)


if __name__ == "__main__":
    main()
