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

try:
    from .photo_release_pipeline import (
        ROOT, GROUPS, TIERS, CARD_SIZE, canonical, original_image,
        perceptual_hash, zoomed_photo, card_art, load_json,
    )
except ImportError:  # Direct CLI invocation from tools/ as a script.
    from photo_release_pipeline import (
        ROOT, GROUPS, TIERS, CARD_SIZE, canonical, original_image,
        perceptual_hash, zoomed_photo, card_art, load_json,
    )

PREVIEW_DIR = ROOT / "output" / "photo_candidate_previews"


def prepare_candidates(manifest_path, output_dir=PREVIEW_DIR):
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
        raw, image = original_image(row)
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
            "source_dhash": f"{visual:016x}", "original_pixels": list(image.size),
            "preview_pixels": list(CARD_SIZE),
        })
        print(f"Prepared candidate card: {member} from real source image.")

    report = {
        "publication": "BLOCKED: incomplete research-only candidates; game catalog unchanged",
        "group": group["name"], "era": tier["era"], "rarity": tier["rarity"],
        "members_missing": missing,
        "cards": preview,
        "note": "Check image sharpness and solo crop manually; never release a missing-member set.",
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
