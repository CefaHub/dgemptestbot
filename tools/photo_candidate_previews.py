#!/usr/bin/env python3
"""Render real-photo candidate previews only; NEVER modify the released game catalog.

Usage:
    python tools/photo_candidate_previews.py tools/research/lesserafim_aura_rare_candidates.json

This intentionally accepts incomplete sets for internal review, unlike the public
photo-release builder. Publication still requires all group members to have
unique, attribution-verified original photographs and a successful full-set build.
"""
import hashlib
import json
import sys
from pathlib import Path
from urllib.error import URLError

from PIL import Image, ImageDraw

try:
    from .photo_release_pipeline import (
        ROOT, GROUPS, TIERS, CARD_SIZE, canonical, original_image,
        perceptual_hash, zoomed_photo, solo_region, card_art, load_json, font,
    )
except ImportError:  # Direct CLI invocation from tools/ as a script.
    from photo_release_pipeline import (
        ROOT, GROUPS, TIERS, CARD_SIZE, canonical, original_image,
        perceptual_hash, zoomed_photo, solo_region, card_art, load_json, font,
    )

PREVIEW_DIR = ROOT / "output" / "photo_candidate_previews"


def write_review_sheet(output_dir, group, tier, member_ids, entries, missing):
    """Visual review shows only sourced photographs; unknown slots remain empty."""
    slot_w, slot_h, gap = 280, 374, 24
    margin = 54
    canvas_width = max(1250, margin * 2 + len(member_ids) * slot_w + (len(member_ids) - 1) * gap)
    board = Image.new("RGB", (canvas_width, 720), (14, 19, 36))
    d = ImageDraw.Draw(board)
    d.text((margin, 37), "DOLCE EMPIRE  /  PHOTO RELEASE REVIEW",
           font=font(31, True), fill=(248, 248, 255))
    d.text((margin, 89), f"{group['name']}  /  {tier['era']}  /  {tier['rarity'].upper()}",
           font=font(26, True), fill=(180, 203, 242))
    d.text((margin, 135), f"{len(entries)} / {len(member_ids)} original photographs verified",
           font=font(21), fill=(220, 228, 245))
    first_x = (canvas_width - (len(member_ids) * slot_w + (len(member_ids) - 1) * gap)) // 2
    files_by_member = {row["member"]: row["file"] for row in entries}
    for index, member in enumerate(member_ids):
        x, y = first_x + index * (slot_w + gap), 194
        d.rounded_rectangle((x, y, x + slot_w, y + slot_h), radius=12,
                            fill=(39, 47, 68), outline=(91, 103, 137), width=3)
        if member in files_by_member:
            card_path = output_dir / files_by_member[member]
            with Image.open(card_path) as photo:
                thumb = photo.convert("RGB").resize((slot_w - 8, slot_h - 8), Image.Resampling.LANCZOS)
                board.paste(thumb, (x + 4, y + 4))
        else:
            # Do NOT invent or replicate a portrait to fill a missing place.
            d.text((x + slot_w // 2, y + 140), "NO VERIFIED PHOTO",
                   anchor="mm", font=font(18, True), fill=(255, 163, 170))
            d.text((x + slot_w // 2, y + 184), member,
                   anchor="mm", font=font(26, True), fill=(251, 243, 245))
            d.text((x + slot_w // 2, y + 230), "NOT RELEASED",
                   anchor="mm", font=font(17), fill=(210, 216, 232))
        d.text((x + slot_w // 2, y + slot_h + 24), member,
               anchor="mm", font=font(21, True), fill=(250, 250, 255))
    d.text((margin, 665),
           "RESEARCH ONLY  /  NOT IN GACHA  /  NO AI IMAGES  /  NO REUSED PORTRAITS",
           font=font(20, True), fill=(255, 170, 184))
    target = output_dir / "CONTACT_SHEET.png"
    board.save(target, format="PNG", optimize=True)
    return target


def prepare_candidates(manifest_path, output_dir=PREVIEW_DIR, archive_originals=False):
    manifest_path = Path(manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    spec = load_json(manifest_path)
    if spec.get("status") != "research_preview_only_not_published":
        raise ValueError("Candidate manifests must be preview-only, not publishable.")
    group = GROUPS.get(spec.get("group"))
    tier = TIERS.get((spec.get("era"), spec.get("rarity")))
    if not group or not tier:
        raise ValueError("Unknown group, era, or rarity.")
    if not spec.get("source_collection", "").strip():
        raise ValueError("Shared source collection is required.")
    members = [x[0] for x in group["members"]]
    cards = spec.get("cards", [])
    if not cards:
        raise ValueError("No real-photo candidates in the preview.")
    member_ids = [row.get("member") for row in cards]
    missing = spec.get("missing_members", [])
    if (len(set(member_ids)) != len(member_ids)
            or len(set(missing)) != len(missing)
            or set(member_ids) & set(missing)
            or set(member_ids) | set(missing) != set(members)):
        raise ValueError("Candidate coverage must partition the full group exactly.")

    existing = load_json(ROOT / "tools/photo_sources.json")["cards"]
    previous_urls = {canonical(x["photo"]) for x in existing if x.get("photo")}
    previous_pages = {canonical(x["page"]) for x in existing if x.get("page")}
    previous_sha = {x["source_sha256"] for x in existing if x.get("source_sha256")}
    previous_hashes = [(int(x["source_dhash"], 16), x["id"]) for x in existing if x.get("source_dhash")]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    preview = []
    unavailable = []

    for row in cards:
        member = row["member"]
        for key in ("source_page", "photographer", "license", "license_url", "photo_url"):
            if not str(row.get(key, "")).strip():
                raise ValueError(f"Missing {key} for {member}")
        if row.get("license_status") != "verified":
            raise ValueError(f"Unverified photo rights for {member}")
        photo_url = row["photo_url"]
        source_page = row["source_page"]
        if canonical(photo_url) in previous_urls or canonical(source_page) in previous_pages:
            raise ValueError(f"Previously published photograph cannot be reused: {member}")
        previous_urls.add(canonical(photo_url))
        previous_pages.add(canonical(source_page))
        try:
            raw, original = original_image(row)
        except (URLError, TimeoutError) as exc:
            # Wikimedia often blocks GitHub runners (429), and third-party
            # image proxies can return 404. Keep genuine completed previews
            # instead of aborting the entire RESEARCH report. This exception
            # is intentionally not used by the PUBLISH pipeline.
            unavailable.append({
                "member": member,
                "source_page": source_page,
                "error": str(exc)[:250],
                "status": "download_unavailable_not_verified",
            })
            print(f"PREVIEW SOURCE UNAVAILABLE: {member}: {exc}", flush=True)
            continue
        if archive_originals:
            # Preserve the exact licensed source bytes *inside the CI artifact*.
            # Avoid changing source identity if Wikimedia later rate-limits release CI.
            originals = output_dir / "source_originals"
            originals.mkdir(parents=True, exist_ok=True)
            (originals / f"{member.lower()}.bin").write_bytes(raw)
        image = solo_region(original, row.get("solo_region"))
        sha = hashlib.sha256(raw).hexdigest()
        if sha in previous_sha:
            raise ValueError(f"Duplicate original file bytes: {member}")
        previous_sha.add(sha)
        visual = perceptual_hash(image)
        for seen, label in previous_hashes:
            if (seen ^ visual).bit_count() <= 3:
                raise ValueError(f"Repeated or near-identical photograph: {member} / {label}")
        previous_hashes.append((visual, member))
        focus = (float(row.get("focus_x", 0.5)), float(row.get("focus_y", 0.35)))
        if not all(0 <= value <= 1 for value in focus):
            raise ValueError(f"Invalid focus for {member}")
        index = members.index(member) + 1
        artwork = card_art(
            zoomed_photo(image, row.get("zoom", 1.0), focus),
            group, tier, member, index, len(members), focus,
        )
        output_name = f"{group['slug']}_{tier['era'].lower().replace(' ', '_')}_{tier['rarity']}_{member.lower()}_PREVIEW.png"
        destination = output_dir / output_name
        artwork.save(destination, "PNG", optimize=True)
        preview.append({
            "member": member, "file": destination.name,
            "source_page": source_page, "source_sha256": sha,
            "source_dhash": f"{visual:016x}", "original_pixels": list(original.size),
            "solo_region": row.get("solo_region"), "crop_pixels": list(image.size),
            "preview_pixels": list(CARD_SIZE),
            "archived_source": f"source_originals/{member.lower()}.bin" if archive_originals else None,
        })
        print(f"Prepared candidate card: {member} from real source image.")

    unfilled = missing + [row["member"] for row in unavailable]
    contact_sheet = write_review_sheet(output_dir, group, tier, members, preview, unfilled)
    report = {
        "publication": "BLOCKED: preview-only; explicit visual review required before game catalog release",
        "contact_sheet": contact_sheet.name,
        "group": group["name"], "era": tier["era"], "rarity": tier["rarity"],
        "members_missing": unfilled,
        "members_declared_missing": missing,
        "members_source_unavailable": unavailable,
        "cards": preview,
        "note": "Check image sharpness and solo crop manually; never release a missing-member set. Unavailable downloads are NOT verified cards and must not be published.",
    }
    (output_dir / "PREVIEW_REPORT.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/photo_candidate_previews.py RESEARCH_MANIFEST.json")
    report = prepare_candidates(sys.argv[1])
    print(f"Generated {len(report['cards'])} REAL photo-card previews; NOT published to game.")


if __name__ == "__main__":
    main()
