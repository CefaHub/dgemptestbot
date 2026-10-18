#!/usr/bin/env python3
"""PREVIEW ONLY: real-photo contact sheet, duplicate audit and source quality report.

No database, gameplay catalog, published cards, or release queues are modified.
The five-person research set stays pending until final solo and stylistic review.

Usage:
    python tools/research/preview_photo_candidate.py \
        --candidate tools/research/lesserafim_aura_rare_v2_candidates.json \
        --output output/research_preview/lesserafim_aura_rare
"""
import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageDraw, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import photo_release_pipeline as pipe  # noqa: E402

THUMB_SIZE = (270, 360)
SESSION_WARN_SATURATION = 9.0


def validate_candidate(data, previously_released, allow_incomplete=False):
    """Require full sets by default; optionally inspect unpublished partial research."""
    if data.get("status") != "research_preview_only_not_published":
        raise ValueError("Research candidates must remain explicitly unpublished")
    group = pipe.GROUPS.get(data.get("group"))
    tier = pipe.TIERS.get((data.get("era"), data.get("rarity")))
    if not group or not tier:
        raise ValueError("Unknown group or album rarity")
    expected_set_id = (
        f'coll_{group["slug"]}_{tier["era"].lower().replace(" ", "_")}_{tier["rarity"]}'
    )
    if data.get("set_id") != expected_set_id or expected_set_id in previously_released:
        raise ValueError("Set ID is wrong or already published")
    session = data.get("photo_session_id", "")
    if not isinstance(session, str) or len(session.strip()) < 10:
        raise ValueError("A real shared photo session ID is required")
    expected_members = [member for member, _ in group["members"]]
    candidate_cards = data.get("cards")
    if not isinstance(candidate_cards, list) or not all(
        isinstance(row, dict) and isinstance(row.get("member"), str)
        for row in candidate_cards
    ):
        raise ValueError("A complete, non-duplicated member lineup is required")
    candidates = [row["member"] for row in candidate_cards]
    missing_members = sorted(set(expected_members) - set(candidates))
    if (len(candidates) != len(set(candidates))
            or not set(candidates).issubset(expected_members)
            or (missing_members and not allow_incomplete)):
        raise ValueError("A complete, non-duplicated member lineup is required")
    if missing_members and (
        not allow_incomplete
        or sorted(data.get("missing_members", [])) != missing_members
    ):
        raise ValueError("Partial preview must explicitly identify missing group members")
    if allow_incomplete and not candidate_cards:
        raise ValueError("Cannot preview a set without any real sourced photo")
    if data.get("collection_review_status") == "approved":
        raise ValueError("Research preview should not pre-approve an unreleased set")
    if not str(data.get("source_collection", "")).strip():
        raise ValueError("Photo series description is missing")
    for row in candidate_cards:
        if row.get("photo_session_id") != session:
            raise ValueError("Every original must belong to the same source photo session")
        if row.get("license_status") != "verified":
            raise ValueError(f"Unverified photo license: {row['member']}")
        for key in ("source_page", "photographer", "license", "license_url"):
            if not str(row.get(key, "")).strip():
                raise ValueError(f"Missing {key}: {row['member']}")
        if not row.get("photo_url") and not row.get("local_path"):
            raise ValueError(f"Missing original image: {row['member']}")
        if row.get("solo_region") and row.get("solo_review_status") != "pending":
            raise ValueError("Research preview cannot auto-approve a cropped group image")
    return group, tier, expected_members


def checked_sources():
    """Published pictures, not merely planned names, are the duplicate baseline."""
    data = pipe.load_json(ROOT / "tools/photo_sources.json")
    sources = data["cards"]
    return (
        {pipe.canonical(s["photo"]) for s in sources},
        {pipe.canonical(s["page"]) for s in sources},
        {s["source_sha256"] for s in sources if s.get("source_sha256")},
        [(int(s["source_dhash"], 16), s["id"]) for s in sources if s.get("source_dhash")],
    )


def preview(candidate, target, allow_incomplete=False):
    """Build real-photo contact sheet; missing members are blank, never faked."""
    candidate = Path(candidate)
    target = Path(target)
    data = json.loads(candidate.read_text(encoding="utf-8"))
    existing = pipe.load_json(ROOT / "assets/collections/verified_sets.json")["sets"]
    group, tier, members = validate_candidate(
        data, {entry["set_id"] for entry in existing},
        allow_incomplete=allow_incomplete,
    )
    source_urls, source_pages, raw_hashes, visual_hashes = checked_sources()

    target.mkdir(parents=True, exist_ok=True)
    tiles, results, banner_images = [], [], []
    cards = {row["member"]: row for row in data["cards"]}
    for idx, member in enumerate(members, 1):
        if member not in cards:
            info = {
                "member": member,
                "source_page": None,
                "photo_session_id": data["photo_session_id"],
                "status": "missing_source",
                "warnings": ["No verified image available; member remains unreleased."],
            }
            results.append(info)
            tiles.append((member, None, info))
            continue
        row = cards[member]
        info = {
            "member": member,
            "source_page": row["source_page"],
            "license": row["license"],
            "photo_session_id": data["photo_session_id"],
            "status": "pending_review",
            "warnings": [],
        }
        results.append(info)
        source_url = row.get("photo_url") or row.get("local_path")
        try:
            if pipe.canonical(source_url) in source_urls:
                raise ValueError("Original URL reused in another rarity/collection")
            if pipe.canonical(row["source_page"]) in source_pages:
                raise ValueError("Original source page reused in another rarity/collection")
            source_urls.add(pipe.canonical(source_url))
            source_pages.add(pipe.canonical(row["source_page"]))
            raw, full = pipe.original_image(row)
            sha = hashlib.sha256(raw).hexdigest()
            if sha in raw_hashes:
                raise ValueError("Original photo hash already published")
            raw_hashes.add(sha)
            solo = pipe.solo_region(full, row.get("solo_region"))
            p_hash = pipe.perceptual_hash(solo)
            for earlier, card_id in visual_hashes:
                if (p_hash ^ earlier).bit_count() <= 3:
                    raise ValueError(f"Visually repeated real photo: {card_id}")
            visual_hashes.append((p_hash, member))
            focus = (float(row.get("focus_x", 0.5)), float(row.get("focus_y", 0.35)))
            final = pipe.zoomed_photo(solo, row.get("zoom", 1), focus)
            artwork = pipe.card_art(
                final, group, tier, member, idx, len(members), focus
            )
            artwork.save(target / f"{idx:02d}_{member.lower()}_DRAFT.png", format="PNG")
            thumbnail = ImageOps.fit(
                final, (150, 200), method=Image.Resampling.LANCZOS
            )
            saturation = round(ImageStat.Stat(thumbnail.convert("HSV")).mean[1], 1)
            info.update(
                original_dimensions=list(full.size),
                cropped_dimensions=list(solo.size),
                final_crop_dimensions=list(final.size),
                preview_dimensions=list(artwork.size),
                source_sha256=sha,
                source_dhash=f"{p_hash:016x}",
                mean_saturation=saturation,
            )
            if row.get("solo_region"):
                info["warnings"].append(
                    "Cropped image originates from multiple subjects; "
                    "must visually confirm a single face and no neighboring body."
                )
            if row.get("solo_review_status") != "approved":
                info["warnings"].append("Solo portrait is not approved for publishing")
            tiles.append((member, artwork, info))
            banner_images.append((member, final, focus))
        except Exception as exc:
            info["status"] = "error"
            info["error"] = f"{type(exc).__name__}: {exc}"
            # Do not add substitute faces/artwork. Leave an explicit empty slot.
            tiles.append((member, None, info))

    saturation_values = [
        info["mean_saturation"] for info in results if "mean_saturation" in info
    ]
    if len(saturation_values) > 1:
        median = statistics.median(saturation_values)
        for info in results:
            value = info.get("mean_saturation")
            if value is not None and value < SESSION_WARN_SATURATION and median > 24:
                info["warnings"].append(
                    f"Image appears monochrome versus a color collection (median saturation {median}); "
                    "requires whole-album aesthetic review"
                )

    margin, header_h, footer_h = 20, 84, 84
    width = len(members) * (THUMB_SIZE[0] + margin) + margin
    height = THUMB_SIZE[1] + header_h + footer_h + 2 * margin
    sheet = Image.new("RGB", (width, height), "#141520")
    dr = ImageDraw.Draw(sheet)
    dr.text((25, 12), f'DOLCE EMPIRE / {data["group"]} / {data["era"]}', fill="white", font=pipe.font(27, True))
    dr.text((25, 49), "PRIVATE RESEARCH PREVIEW / NOT IN GACHA", fill="#ffbb72", font=pipe.font(18))
    for pos, (member, image, info) in enumerate(tiles):
        x, y = margin + pos * (THUMB_SIZE[0] + margin), header_h
        if image is not None:
            sheet.paste(ImageOps.fit(image, THUMB_SIZE), (x, y))
        else:
            dr.rectangle((x, y, x + THUMB_SIZE[0], y + THUMB_SIZE[1]), fill="#302e3b")
            label = "AWAITING PHOTO" if info["status"] == "missing_source" else "IMAGE FAILED QC"
            dr.text((x + 10, y + 160), label, fill="#ff938b", font=pipe.font(17, True))
        dr.text((x + 4, y + THUMB_SIZE[1] + 7), member, fill="white", font=pipe.font(21, True))
        badge = ("ERROR" if info["status"] == "error"
                 else "NOT SOURCED" if info["status"] == "missing_source"
                 else "REVIEW NEEDED")
        dr.text((x + 4, y + THUMB_SIZE[1] + 37), badge, fill="#ffba74", font=pipe.font(17))
    sheet.save(target / "contact_sheet_DRAFT.jpg", quality=92, subsampling=0)
    if len(banner_images) == len(members):
        # Banner derives from exactly the five individual approved-for-preview
        # crops; it is never a fresh unrelated photo source or synthetic face.
        pipe.banner_art(
            [(member, photo) for member, photo, _ in banner_images],
            group, tier,
            {member: focus for member, _, focus in banner_images},
        ).save(target / "banner_DRAFT.png", format="PNG")
    failures = sum(item["status"] == "error" for item in results)
    missing = sum(item["status"] == "missing_source" for item in results)
    report = {
        "set_id": data["set_id"],
        "photo_session_id": data["photo_session_id"],
        "published": False,
        "review_status": "pending",
        "members_expected": len(members),
        "previewed": len(members) - failures - missing,
        "failed": failures,
        "missing": missing,
        "missing_members": [item["member"] for item in results if item["status"] == "missing_source"],
        "user_approval_required": True,
        "records": results,
    }
    (target / "review_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    credits = [
        "# DOLCE EMPIRE — unpublished real-photo preview",
        "",
        "RESEARCH ONLY — NOT RELEASED IN THE GAME.",
        "",
        "These are genuine photographs, not AI-generated idol faces.",
        "Photos are cropped, color-adjusted where appropriate, framed,",
        "and captioned into draft 3:4 cards and a matching 16:9 banner.",
        "Licensing of the photographs does not imply artist endorsement.",
        "Do not publish or redistribute artwork without required credits.",
        "",
    ]
    for member in members:
        if member not in cards:
            credits.extend(["## " + member, "- No verified original photograph has been selected.", ""])
            continue
        row = cards[member]
        credits.extend([
            "## " + member,
            "- Photographer: " + str(row["photographer"]),
            "- Original photo page: " + str(row["source_page"]),
            "- Original provider page: " + str(row.get("original_source", row["source_page"])),
            "- Photo license: " + str(row["license"]),
            "- License URL: " + str(row["license_url"]),
            "- Adaptations: solo crop where specified, 3:4 crop, adjustments, card frame and typography",
            "- Quality review: pending; not approved for game release",
            "",
        ])
    (target / "SOURCE_CREDITS_DRAFT.md").write_text(
        "\n".join(credits) + "\n", encoding="utf-8"
    )
    print(
        f"Research preview: {report['previewed']}/{len(members)} images prepared, "
        f"{failures} failed, {missing} missing, "
        f"{sum(bool(r['warnings']) for r in results)} need review; "
        "zero game cards published."
    )
    for item in results:
        warnings = "; ".join(item.get("warnings", []))
        print(f" - {item['member']}: {item['status']}; {warnings or 'no automatic warning'}")
        if "error" in item:
            print("   ERROR:", item["error"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", default="tools/research/lesserafim_aura_rare_v2_candidates.json")
    parser.add_argument("--output", default="output/research_preview/lesserafim_aura_rare")
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="Preview incomplete researched sets with blank slots, NEVER publish")
    args = parser.parse_args()
    candidate = ROOT / args.candidate
    output = ROOT / args.output
    if not candidate.resolve().is_relative_to((ROOT / "tools/research").resolve()):
        parser.error("Research candidates must be under tools/research")
    if not output.resolve().is_relative_to((ROOT / "output").resolve()):
        parser.error("Preview images must stay inside output/")
    report = preview(candidate, output, allow_incomplete=args.allow_incomplete)
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
