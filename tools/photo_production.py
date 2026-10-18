#!/usr/bin/env python3
"""Auditable production schedule for 100 distinct DOLCE EMPIRE photo slots.

This tool NEVER fabricates photographs, grants image rights, or writes game data.
It reads the LIVE published catalog and works only on unpublished *complete*
member sets. Planned cards are not playable until real photos are approved.

  python tools/photo_production.py status
  python tools/photo_production.py status --json
  python tools/photo_production.py validate
  python tools/photo_production.py template --set coll_itzy_aura_rare
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = "tools/photo_release_plan.json"
SCHEDULE_PATH = "tools/photo_production_schedule.json"
CATALOG_PATH = "dolce_empire/_catalog.json"
MIRROR_PATH = "data/catalog.json"
SETS_PATH = "assets/collections/verified_sets.json"
CARD_SIZE = (900, 1200)
BANNER_SIZE = (1600, 900)


class ProductionError(ValueError):
    """Photo production data is inconsistent with the published catalog."""


def load_json(root, path):
    return json.loads((Path(root) / path).read_text(encoding="utf-8"))


def build_plan(plan):
    """Deterministic card, member, set, and artwork names in canonical order."""
    sets, all_card_ids, all_art_paths = {}, set(), set()
    for group in plan["groups"]:
        for tier in plan["tiers"]:
            era_slug = tier["era"].lower().replace(" ", "_")
            stem = f'{group["slug"]}_{era_slug}_{tier["rarity"]}'
            set_id = "coll_" + stem
            if set_id in sets:
                raise ProductionError(f"Repeated planned set: {set_id}")
            cards = []
            for number, (member, member_ru) in enumerate(group["members"], 1):
                photo_stem = f"{stem}_{member.lower()}_{number:02d}"
                card_id = "card_" + photo_stem
                image_path = f'assets/cards/{group["slug"]}/{photo_stem}.png'
                if card_id in all_card_ids or image_path in all_art_paths:
                    raise ProductionError(f"Repeated card ID or photo output: {card_id}")
                all_card_ids.add(card_id)
                all_art_paths.add(image_path)
                cards.append({
                    "card_id": card_id,
                    "set_id": set_id,
                    "member": member,
                    "member_ru": member_ru,
                    "card_number": number,
                    "image_path": image_path,
                })
            sets[set_id] = {
                "set_id": set_id,
                "group": group["name"],
                "era": tier["era"],
                "rarity": tier["rarity"],
                "banner_path": f'assets/banners/{group["slug"]}/{stem}_banner.png',
                "cards": cards,
            }
    return sets


def read_status(root=ROOT):
    """Fail closed on catalog drift; never mistake half a set for a release."""
    root = Path(root)
    schedule = load_json(root, SCHEDULE_PATH)
    plan = load_json(root, PLAN_PATH)
    published_cards = load_json(root, CATALOG_PATH)
    mirror = load_json(root, MIRROR_PATH)
    manifest = load_json(root, SETS_PATH)["sets"]

    planned = build_plan(plan)
    target_count = sum(len(s["cards"]) for s in planned.values())
    if target_count != schedule.get("target_catalog_cards") or target_count != 100:
        raise ProductionError(f"Slot count must be exactly 100, got {target_count}")
    if published_cards != mirror:
        raise ProductionError("The deployed and mirror catalogs differ; fix before planning")
    if len({row["id"] for row in published_cards}) != len(published_cards):
        raise ProductionError("Duplicate photo card IDs in live catalog")
    if len({row["image_path"] for row in published_cards}) != len(published_cards):
        raise ProductionError("Photo artwork reused in the live catalog")

    published_set_ids = [row["set_id"] for row in manifest]
    if len(set(published_set_ids)) != len(manifest):
        raise ProductionError("Duplicate published collection IDs")

    published_by_set = {}
    for row in published_cards:
        if row["id"] not in {x["card_id"] for x in planned.get(row["set_id"], {}).get("cards", [])}:
            raise ProductionError(f"Live card outside canonical 100 slots: {row['id']}")
        published_by_set.setdefault(row["set_id"], []).append(row)
    if set(published_by_set) != set(published_set_ids):
        raise ProductionError("Live catalog and verified release manifest disagree")

    for entry in manifest:
        expected = planned.get(entry["set_id"])
        if expected is None:
            raise ProductionError(f"Unplanned published set: {entry['set_id']}")
        for field in ("group", "era", "rarity", "banner_path"):
            if expected[field] != entry.get(field):
                raise ProductionError(f"Incorrect published {field}: {entry['set_id']}")
        actual = published_by_set[entry["set_id"]]
        if {c["id"] for c in actual} != {c["card_id"] for c in expected["cards"]}:
            raise ProductionError(f"Incomplete or incorrect released set: {entry['set_id']}")
        if {c["image_path"] for c in actual} != {c["image_path"] for c in expected["cards"]}:
            raise ProductionError(f"Wrong image output paths: {entry['set_id']}")
        if [member["member"] for member in expected["cards"]] != entry["expected_members"]:
            raise ProductionError(f"Wrong released member list: {entry['set_id']}")

    queue = schedule.get("queue")
    if not isinstance(queue, list):
        raise ProductionError("Photo production schedule has no queue")
    queued_ids = [item["set_id"] for item in queue]
    if (len(queued_ids) != len(set(queued_ids))
            or len({item["priority"] for item in queue}) != len(queue)
            or [x["priority"] for x in queue] != list(range(1, len(queue)+1))):
        raise ProductionError("Queue must have unique IDs and consecutive priorities")
    if set(queued_ids) - set(planned):
        raise ProductionError("Queue references an unknown album")
    missing = set(planned) - set(published_set_ids)
    if not missing.issubset(set(queued_ids)):
        raise ProductionError("Unpublished sets are absent from production queue")
    pending = []
    for entry in queue:
        set_id = entry["set_id"]
        if set_id in published_set_ids:
            continue
        release = planned[set_id]
        pending.append({
            "priority": entry["priority"],
            "set_id": set_id,
            "group": release["group"],
            "era": release["era"],
            "rarity": release["rarity"],
            "size": len(release["cards"]),
            "note": entry.get("note", ""),
            "cards": release["cards"],
            "banner_path": release["banner_path"],
        })
    return {
        "target_cards": target_count,
        "published_cards": len(published_cards),
        "remaining_cards": sum(item["size"] for item in pending),
        "published_sets": len(published_set_ids),
        "remaining_sets": len(pending),
        "queue": pending,
    }


def release_template(set_id, root=ROOT):
    """Draft for curators ONLY: deliberately absent photos and unverified rights."""
    status = read_status(root)
    entry = next((row for row in status["queue"] if row["set_id"] == set_id), None)
    if entry is None:
        raise ProductionError("Set is already published or absent from the queue")
    return {
        "version": 1,
        "description": "PRIVATE DRAFT: incomplete sources; cannot publish.",
        "sets": [{
            "group": entry["group"],
            "era": entry["era"],
            "rarity": entry["rarity"],
            "source_collection": "",
            "photo_session_id": "",
            "source_mode": "curated",
            "collection_review_status": "pending",
            "cards": [
                {
                    "member": card["member"],
                    "photo_session_id": "",
                    "photo_url": "",
                    "source_page": "",
                    "photographer": "",
                    "license": "",
                    "license_url": "",
                    "license_status": "pending",
                    "solo_review_status": "pending",
                    "focus_x": 0.5,
                    "focus_y": 0.35,
                }
                for card in entry["cards"]
            ],
        }],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Show published and missing real photos")
    status.add_argument("--json", action="store_true", help="Print machine-readable release queue")
    sub.add_parser("validate", help="Fail on incomplete, duplicated, or drifting catalogs")
    template = sub.add_parser("template", help="Write a NON-PUBLISHABLE source review draft")
    template.add_argument("--set", dest="set_id", required=True)
    template.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            content = release_template(args.set_id)
            path = args.output or ROOT / "output" / f"draft_{args.set_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
            print(f"Unverified source-review draft written to {path}; NOT published.")
            return
        report = read_status()
    except (ProductionError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Invalid photo production state: {exc}\n")
    if args.command == "validate":
        print("DOLCE EMPIRE: 100 unique slots / complete published sets / queue OK")
        return
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f'DOLCE EMPIRE: {report["published_cards"]}/{report["target_cards"]} '
            f'photo cards published in {report["published_sets"]} sets; '
            f'{report["remaining_cards"]} photos in {report["remaining_sets"]} sets to source.'
        )
        for entry in report["queue"]:
            print(f'{entry["priority"]:02d}. {entry["group"]} / {entry["era"]} '
                  f'/ {entry["rarity"].upper()} — {entry["size"]} unique photos '
                  f'[{entry["set_id"]}]')


if __name__ == "__main__":
    main()
