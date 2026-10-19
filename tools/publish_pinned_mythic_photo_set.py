#!/usr/bin/env python3
"""Publish ONE visually signed-off 5/5 real-photo set from pinned GitHub previews.

The source originals were previously downloaded and checked by the real-photo
research CI, which produced PREVIEW_REPORT.json with source SHA256 and dHash.
This offline promotion never generates, swaps, or fetches photographic subjects.
It verifies immutable Git blob hashes of the exact archived card PNGs and report,
and preserves the report's actual *fetched* source identity in the credit ledger.
Only the explicitly reviewed LE SSERAFIM ROYAL HAZE MYTHIC set is eligible.
"""
import hashlib
import json
import re
import subprocess
from pathlib import Path
from PIL import Image

from tools.photo_release_pipeline import (
    ROOT, GROUPS, TIERS, BANNER_SIZE, banner_art,
    check_complete_release, canonical,
)
from tools.generate_gallery import generate_gallery

SET_ID = "coll_lesserafim_royal_haze_mythic"
PREVIEW = Path("assets/previews/lesserafim_royal_haze_mythic")
REPORT_BLOB = "15406bb009ab95d4723bad64ac543ef8835023fc"
ART_BLOBS = {
    "CHAEWON": "7b4fedeb3cd6948fcd0cc0464efb9167185b5b5b",
    "SAKURA": "b794bbdec4c752c54db5861a0eeb084965afdcc3",
    "YUNJIN": "caaf6bf67c275b7e5b5dcb9e44ee6a38db170cca",
    "KAZUHA": "26adcbd1f42c275b6ee7da1135e02246297a84d4",
    "EUNCHAE": "5ea515eef27454f17b729977b9d35e012d9272cf",
}
RESEARCH = Path("tools/research/lesserafim_royal_haze_mythic_candidates.json")
QUEUE = Path("tools/photo_releases.json")


def read(path, root=ROOT):
    return json.loads((root / path).read_text(encoding="utf-8"))


def git_blob(path):
    return subprocess.check_output(
        ["git", "hash-object", str(path)], text=True,
    ).strip()


def verify_inputs(root=ROOT):
    root = Path(root)
    queued = read(QUEUE, root)
    specs = queued.get("sets", [])
    if len(specs) != 1:
        raise ValueError("Expected exactly one approved complete set")
    spec = specs[0]
    current = read(Path("data/catalog.json"), root)
    released = read(Path("assets/collections/verified_sets.json"), root)
    old_sources = read(Path("tools/photo_sources.json"), root)
    old_ids = {s["set_id"] for s in released["sets"]}
    group, tier, new_id = check_complete_release(spec, old_ids)
    if new_id != SET_ID or spec.get("group") != "LE SSERAFIM":
        raise ValueError("This locked publisher only releases LE SSERAFIM MYTHIC")
    if spec.get("collection_review_status") != "approved":
        raise ValueError("No visual collection sign-off")
    if old_ids & {SET_ID} or any(c["set_id"] == SET_ID for c in current):
        raise ValueError("Set is already published, never replay it")
    if current != read(Path("dolce_empire/_catalog.json"), root):
        raise ValueError("The two game catalogs differ")

    report_path = root / PREVIEW / "PREVIEW_REPORT.json"
    if git_blob(report_path) != REPORT_BLOB:
        raise ValueError("Pinned source report was modified")
    report = read(PREVIEW / "PREVIEW_REPORT.json", root)
    research = read(RESEARCH, root)
    expected = [name for name, _ in group["members"]]
    rows = {row["member"]: row for row in report["cards"]}
    original = {row["member"]: row for row in research["cards"]}
    queued_cards = {row["member"]: row for row in spec["cards"]}
    if (set(rows) != set(expected) or set(original) != set(expected) or
        set(queued_cards) != set(expected) or report["members_missing"] or
        (report["group"], report["era"], report["rarity"]) !=
        ("LE SSERAFIM", "ROYAL HAZE", "mythic")):
        raise ValueError("Preview is not the complete verified 5/5 collection")

    existing_sha = {s.get("source_sha256") for s in old_sources["cards"]}
    existing_pages = {canonical(s.get("page", "")) for s in old_sources["cards"]}
    existing_urls = {canonical(s.get("photo", "")) for s in old_sources["cards"]}
    previous_dhash = [
        int(s["source_dhash"], 16)
        for s in old_sources["cards"] if s.get("source_dhash")
    ]
    source_sha, source_page, source_url, rendered_sha = set(), set(), set(), set()
    planned = []
    for index, (name, translation) in enumerate(group["members"], 1):
        record, spec_card, candidate = rows[name], queued_cards[name], original[name]
        preview_path = root / PREVIEW / record["file"]
        if not record["file"].endswith(f"_{name.lower()}_PREVIEW.png"):
            raise ValueError(f"Wrong member preview mapping for {name}")
        if git_blob(preview_path) != ART_BLOBS[name]:
            raise ValueError(f"Archived visual-approved {name} artwork changed")
        if (record["source_page"] != spec_card["source_page"] or
            record["source_page"] != candidate["source_page"] or
            spec_card["original_source"] != candidate["original_source"] or
            candidate["photo_session_id"] != spec["photo_session_id"] or
            candidate["license_status"] != "verified" or
            spec_card["visual_review_status"] != "approved" or
            spec_card["license"] != "CC BY 4.0"):
            raise ValueError(f"Source provenance / review mismatch for {name}")
        orig_id = re.search(r"(\d{11})", candidate["original_source"])
        if not orig_id or orig_id.group(1) not in candidate["source_page"]:
            raise ValueError(f"Flickr ID does not match the Wikimedia source page for {name}")
        raw_sha, dhash = record["source_sha256"], record["source_dhash"]
        if not re.fullmatch(r"[a-f0-9]{64}", raw_sha) or not re.fullmatch(r"[a-f0-9]{16}", dhash):
            raise ValueError(f"Source fingerprints missing for {name}")
        key_page, key_url = canonical(record["source_page"]), canonical(candidate["photo_url"])
        if (raw_sha in existing_sha | source_sha or
            key_page in existing_pages | source_page or
            key_url in existing_urls | source_url):
            raise ValueError(f"Source original already used for {name}")
        visual = int(dhash, 16)
        if any((visual ^ other).bit_count() <= 3 for other in previous_dhash):
            raise ValueError(f"Same or near-identical source portrait: {name}")
        source_sha.add(raw_sha); source_page.add(key_page)
        source_url.add(key_url); previous_dhash.append(visual)
        with Image.open(preview_path) as img:
            img.verify()
        with Image.open(preview_path) as img:
            if img.size != (900, 1200) or img.format != "PNG":
                raise ValueError(f"Wrong real-photo artwork properties: {name}")
        digest = hashlib.sha256(preview_path.read_bytes()).hexdigest()
        if digest in rendered_sha:
            raise ValueError("Duplicate artwork not allowed")
        rendered_sha.add(digest)
        stem = f"lesserafim_royal_haze_mythic_{name.lower()}_{index:02d}"
        planned.append({
            "name": name, "translation": translation,
            "stem": stem,
            "path": preview_path,
            "destination": f"assets/cards/lesserafim/{stem}.png",
            "report": record, "source": candidate,
        })
    return queued, spec, group, tier, current, released, old_sources, planned


def publish():
    from dolce_empire import set_validation
    from tools.photo_production import read_status
    queued, spec, group, tier, cards, sets, sources, planned = verify_inputs()
    banner_path = "assets/banners/lesserafim/lesserafim_royal_haze_mythic_banner.png"
    photos = []
    focuses = {}
    for row in planned:
        name, source, report = row["name"], row["source"], row["report"]
        target = ROOT / row["destination"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row["path"].read_bytes())  # Exact pinned real-photo artwork
        with Image.open(target) as card:
            # Crop only the photo-bearing area of the already-approved artwork,
            # without downloading, hallucinating or changing idol identities.
            photos.append((name, card.convert("RGB").crop((55, 125, 845, 940))))
        focuses[name] = (0.5, 0.28)
        idx = planned.index(row) + 1
        cards.append({
            "id": "card_" + row["stem"], "group": group["name"],
            "idol": name.title(), "era": tier["era"], "rarity": tier["rarity"],
            "base_income": tier["base_income"], "aliases": [row["translation"], name.lower()],
            "collection_id": SET_ID, "set_id": SET_ID,
            "source_collection": spec["source_collection"],
            "series": tier["era"], "card_number": idx,
            "card_total": len(planned), "image_path": row["destination"],
        })
        sources["cards"].append({
            "id": row["stem"], "group": group["name"], "member": name,
            # These URLs refer to the EXACT source image bytes used by preview CI,
            # not the different full-resolution Flickr URL attempted later.
            "photo": source["photo_url"], "page": report["source_page"],
            "original_source": source["original_source"],
            "author": source["photographer"], "license": source["license"],
            "license_url": source["license_url"], "license_review": "confirmed",
            "source_sha256": report["source_sha256"],
            "source_dhash": report["source_dhash"], "rarity": tier["rarity"],
            "series": tier["era"], "number": idx, "total": len(planned),
            "solo_region": source.get("solo_region"),
            "photo_session_id": spec["photo_session_id"],
            "source_fingerprint_provenance": "pinned PREVIEW_REPORT.json generated from downloaded original",
            "rendered_artwork_provenance": "pinned reviewed CI preview PNG promoted unchanged",
        })
    banner = banner_art(photos, group, tier, focuses)
    out_banner = ROOT / banner_path
    out_banner.parent.mkdir(parents=True, exist_ok=True)
    banner.save(out_banner, "PNG", optimize=True)
    with Image.open(out_banner) as img:
        if img.size != BANNER_SIZE:
            raise ValueError("Wrong 16:9 released banner")
    sets["sets"].append({
        "set_id": SET_ID, "group": group["name"], "era": tier["era"],
        "rarity": tier["rarity"], "source_collection": spec["source_collection"],
        "source_mode": "curated",
        "expected_members": [r["name"] for r in planned],
        "photo_session_id": spec["photo_session_id"],
        "banner_path": banner_path,
    })
    (ROOT / "data/catalog.json").write_text(
        json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "dolce_empire/_catalog.json").write_text(
        json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "tools/photo_sources.json").write_text(
        json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "assets/collections/verified_sets.json").write_text(
        json.dumps(sets, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    credits_path = ROOT / "assets/PHOTO_CREDITS_NEW_RELEASES.md"
    with credits_path.open("a", encoding="utf-8") as dest:
        dest.write("\n\n## LE SSERAFIM / ROYAL HAZE / MYTHIC (5 photos)\n\n")
        dest.write("Photographer: David Lee, Seattle 17 September 2025, **CC BY 4.0**. "
                   "Individual source photos were verified from Wikimedia Commons and Flickr. "
                   "Real-photo crops, frames, captions and a banner have been created. "
                   "No endorsement is implied. This release promotes five previously "
                   "rendered, visually approved and **Git-SHA-pinned** photo PNGs "
                   "unchanged because public image CDNs return HTTP 429 to CI. "
                   "The recorded original photo SHA256/dHash come from the immutable "
                   "research preview report, not a second download.\n\n")
        for row in planned:
            src = row["source"]
            dest.write(f"- {row['name']}: {src['source_page']} | original {src['original_source']} "
                       f"| {src['license']} ({src['license_url']}); modifications: "
                       "card crop, framing, lettering and banner composition.\n")
    queued["last_published_set_ids"] = [SET_ID]
    queued["sets"] = []
    queued["description"] = "LE SSERAFIM ROYAL HAZE MYTHIC: complete 5/5, published from Git-pinned reviewed real photo PNGs."
    (ROOT / QUEUE).write_text(json.dumps(queued, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if set_validation.validate_photo_sets(cards) != len(cards):
        raise ValueError("Final game source ledger validation failed")
    if read_status()["published_cards"] != len(cards):
        raise ValueError("Production schedule mismatch after release")
    (ROOT / "GALLERY.md").write_text(generate_gallery(ROOT), encoding="utf-8")
    print(f"REAL PHOTO RELEASE: {SET_ID}; 5 fully credited member cards, 1 banner; catalog now {len(cards)}")


if __name__ == "__main__":
    publish()
