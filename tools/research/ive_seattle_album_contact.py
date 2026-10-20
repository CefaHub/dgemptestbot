#!/usr/bin/env python3
"""Visual INVENTORY of a whole REAL-photography IVE concert shoot (not cards).

Never labels a specific idol or approves a card, does not touch game catalog.
Only after checking ALL six members across distinct source images may the
separate preflight/preview pipeline be considered. Source rights are audited
at the page level, and each JPEG here remains research-only.
"""
import base64
import hashlib
import io
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

from PIL import Image, ImageOps, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tools/research/ive_seattle_2026_full_album_inventory.json"
OUT = ROOT / "output/ive_seattle_2026_source_inventory"


def _font(size=22):
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                      "C:/Windows/Fonts/arialbd.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default()


def source_preflight(manifest):
    """Check a whole-event source inventory before any network action."""
    if manifest.get("mode") != "research_full_album_only_no_cards":
        raise ValueError("This process cannot build or publish cards")
    expected = ["YUJIN", "GAEUL", "REI", "WONYOUNG", "LIZ", "LEESEO"]
    if manifest.get("expected_members") != expected:
        raise ValueError("Six-person IVE roster required in research inventory")
    rows = manifest.get("photos", [])
    if len(rows) < 6 or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("Source inventory must not contain duplicate or too few originals")
    for row in rows:
        if row.get("license_status") != "source_page_cc_by_4_confirmed":
            raise ValueError("Each indexed original requires verified source page")
        if row.get("license") != "CC BY 4.0" or row.get("source_date") != "August 7, 2026":
            raise ValueError("Source rows are not from one licensed shoot")
        if row.get("source_page") != f"https://www.flickr.com/photos/davidjlee/{row['id']}/":
            raise ValueError("Incorrect Flickr original page link")
        if not row.get("image_url", "").startswith(
            f"https://live.staticflickr.com/65535/{row['id']}_"
        ):
            raise ValueError("Image URL does not match unique original page")
    return rows


def fetch_sample(url, timeout=20):
    request = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; DolceEmpirePhotoResearch/1.0)",
        "Accept": "image/jpeg,image/png,image/webp",
    })
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(7_000_001)
    if not 1000 < len(raw) <= 7_000_000:
        raise ValueError("Downloaded thumbnail too small or oversized")
    with Image.open(io.BytesIO(raw)) as probe:
        probe.verify()
    with Image.open(io.BytesIO(raw)) as im:
        picture = ImageOps.exif_transpose(im).convert("RGB")
    return picture, hashlib.sha256(raw).hexdigest()


def render_sheet(rows, thumbs, output):
    # A visual inventory of every indexed original, no card frames or member tags.
    cell_w, cell_h = 215, 280
    pad, header = 10, 85
    cols = 5
    nrows = (len(rows) + cols - 1) // cols
    canvas = Image.new("RGB",
                       (cols * (cell_w + pad) + pad, header + nrows * (cell_h + pad) + 12),
                       (15, 20, 36))
    d = ImageDraw.Draw(canvas)
    d.text((15, 10), "IVE SEATTLE 2026 / FULL PHOTO SESSION INVENTORY",
           fill="white", font=_font(22))
    d.text((15, 46), "NO CARD RENDERS / NO MEMBER SELECTION / SOURCE REVIEW ONLY",
           fill=(255, 159, 170), font=_font(16))
    for index, row in enumerate(rows):
        x = pad + (index % cols) * (cell_w + pad)
        y = header + (index // cols) * (cell_h + pad)
        im = thumbs.get(row["id"])
        if im:
            picture = ImageOps.contain(im, (cell_w, cell_h - 37))
            px = x + (cell_w - picture.width) // 2
            py = y + (cell_h - 37 - picture.height) // 2
            canvas.paste(picture, (px, py))
            d.text((x + 5, y + cell_h - 29), f"#{index+1:02d} FLICKR {row['id']}",
                   font=_font(13), fill=(234, 246, 252))
        else:
            d.rectangle((x, y, x+cell_w-1, y+cell_h-37), fill=(42, 48, 65))
            d.text((x+5, y+cell_h-45), f"#{index+1:02d} UNAVAILABLE",
                   font=_font(13), fill=(255, 176, 183))
    canvas.save(output, "JPEG", quality=76, optimize=True)
    return canvas.size


def research(manifest, output=OUT, fetch=fetch_sample):
    rows = source_preflight(manifest)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for previous in output.glob("CONTACT_SHEET*"):
        previous.unlink()
    images, audit = {}, []
    for index, row in enumerate(rows):
        try:
            picture, sha = fetch(row["image_url"])
            images[row["id"]] = picture
            audit.append({"index": index+1, "id": row["id"], "source_page": row["source_page"],
                          "sha256_sample": sha, "sample_dimensions": list(picture.size),
                          "status": "downloaded_source_thumbnail_not_member_approved"})
            print(f"Source {index+1}/{len(rows)}: Flickr {row['id']} {picture.size}", flush=True)
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            audit.append({"index": index+1, "id": row["id"], "source_page": row["source_page"],
                          "status": "source_unavailable", "error": str(exc)[:180]})
            print(f"Source {index+1}/{len(rows)} unavailable: {exc}", flush=True)
    sheet_path = output / "CONTACT_SHEET_FULL_INDEX.jpg"
    dimensions = render_sheet(rows, images, sheet_path)
    report = {
        "source_album": manifest["album_url"],
        "claimed_total_album_photos": manifest["claimed_total_album_photos"],
        "number_of_indexed_sources": len(rows),
        "source_thumbnails_downloaded": len(images),
        "source_photographer": manifest["photographer"],
        "photographed_on": manifest["taken_on"],
        "qa_status": "awaiting_visual_all_six_member_check",
        "full_group_members_approved": 0,
        "cards_created": 0,
        "game_catalog_modified": False,
        "contact_sheet": sheet_path.name,
        "sheet_dimensions": dimensions,
        "audit": audit,
    }
    (output / "AUDIT_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return report


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    report = research(manifest)
    print("FULL_SOURCE_AUDIT_DONE:", report["source_thumbnails_downloaded"], "/",
          report["number_of_indexed_sources"], flush=True)
    if "--display-small-contact" in sys.argv:
        # Used only in GitHub CI logs for curator-side visual source QA.
        # NOT a playable image or render and never committed into the game.
        with Image.open(OUT / report["contact_sheet"]) as img:
            img.thumbnail((920, 1250))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=56)
        block = base64.b64encode(buf.getvalue()).decode("ascii")
        print("DOLCE_IVE_CONTACT_BASE64_BEGIN", flush=True)
        for i in range(0, len(block), 256):
            print("DOLCE64 " + block[i:i+256], flush=True)
        print("DOLCE_IVE_CONTACT_BASE64_END", flush=True)


if __name__ == "__main__":
    main()
