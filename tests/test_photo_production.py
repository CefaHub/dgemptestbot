"""Production list never invents source images or publishes incomplete albums."""
import copy
import json
from pathlib import Path

import pytest

from tools import photo_production as production
from tools import photo_release_pipeline as pipeline


def test_exact_100_photo_slots_and_all_distinct_ids():
    sets = production.build_plan(production.load_json(production.ROOT, production.PLAN_PATH))
    assert len(sets) == 20
    assert len({set_id for set_id in sets}) == 20
    slots = [card for album in sets.values() for card in album["cards"]]
    assert len(slots) == 100
    assert len({slot["card_id"] for slot in slots}) == 100
    assert len({slot["image_path"] for slot in slots}) == 100
    assert {len(album["cards"]) for album in sets.values()} == {4, 5, 6}
    assert all([card["card_number"] for card in album["cards"]]
               == list(range(1, len(album["cards"])+1)) for album in sets.values())


def test_live_release_queue_is_complete_and_monotonic():
    report = production.read_status()
    published = json.loads((production.ROOT / production.CATALOG_PATH).read_text())
    assert report["target_cards"] == 100
    assert report["published_cards"] == len(published)
    assert report["published_cards"] + report["remaining_cards"] == 100
    assert report["remaining_sets"] + report["published_sets"] == 20
    assert all(set(row) >= {"set_id", "cards", "banner_path", "priority"}
               for row in report["queue"])
    assert all(row["size"] == len(row["cards"]) for row in report["queue"])
    assert all(len({c["member"] for c in row["cards"]}) == row["size"]
               for row in report["queue"])
    assert all(row["priority"] >= 1 for row in report["queue"])


def sandbox_copy(tmp_path):
    for path in (
        production.PLAN_PATH, production.SCHEDULE_PATH,
        production.CATALOG_PATH, production.MIRROR_PATH,
        production.SETS_PATH,
    ):
        dest = tmp_path / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((production.ROOT / path).read_bytes())
    return tmp_path


def test_approximate_goal_can_expand_by_whole_member_sets(tmp_path):
    """100 is not a card-count cap: 116 cards across 24 complete sets is valid."""
    root = sandbox_copy(tmp_path)
    plan_path = root / production.PLAN_PATH
    schedule_path = root / production.SCHEDULE_PATH
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    schedule = json.loads(schedule_path.read_text(encoding="utf-8"))
    extra = copy.deepcopy(next(g for g in plan["groups"] if g["slug"] == "aespa"))
    extra["slug"] = "newcomers"
    extra["name"] = "NEWCOMERS"
    plan["groups"].append(extra)
    for tier in plan["tiers"]:
        era = tier["era"].lower().replace(" ", "_")
        schedule["queue"].append({
            "priority": len(schedule["queue"]) + 1,
            "set_id": f'coll_newcomers_{era}_{tier["rarity"]}',
            "note": "New full 4-member collection; not a partial quota filler",
        })
    schedule["target_catalog_cards"] = 116
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    schedule_path.write_text(json.dumps(schedule), encoding="utf-8")
    report = production.read_status(root)
    assert report["target_cards"] == 116
    assert report["published_cards"] + report["remaining_cards"] == 116
    assert report["remaining_sets"] + report["published_sets"] == 24
    extra_sets = [item for item in report["queue"] if item["group"] == "NEWCOMERS"]
    assert len(extra_sets) == 4
    assert all(len(x["cards"]) == 4 and x["size"] == 4 for x in extra_sets)


def test_partial_release_is_never_treated_as_published(tmp_path):
    root = sandbox_copy(tmp_path)
    status = production.read_status(root)
    pending_card = status["queue"][0]["cards"][0]
    for file_path in (production.CATALOG_PATH, production.MIRROR_PATH):
        path = root / file_path
        catalog = json.loads(path.read_text())
        catalog.append({
            "id": pending_card["card_id"],
            "image_path": pending_card["image_path"],
            "set_id": pending_card["set_id"],
        })
        path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(production.ProductionError, match="manifest disagree"):
        production.read_status(root)


def test_catalog_mirror_drift_fails_closed(tmp_path):
    root = sandbox_copy(tmp_path)
    path = root / production.MIRROR_PATH
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(production.ProductionError, match="mirror catalogs differ"):
        production.read_status(root)


def test_duplicate_queue_priority_is_rejected(tmp_path):
    root = sandbox_copy(tmp_path)
    path = root / production.SCHEDULE_PATH
    schedule = json.loads(path.read_text())
    schedule["queue"][1]["priority"] = schedule["queue"][0]["priority"]
    path.write_text(json.dumps(schedule), encoding="utf-8")
    with pytest.raises(production.ProductionError, match="unique IDs"):
        production.read_status(root)


def test_unplanned_queue_album_is_rejected(tmp_path):
    root = sandbox_copy(tmp_path)
    path = root / production.SCHEDULE_PATH
    schedule = json.loads(path.read_text())
    schedule["queue"].append({"priority":len(schedule["queue"])+1, "set_id": "coll_fake"})
    path.write_text(json.dumps(schedule), encoding="utf-8")
    with pytest.raises(production.ProductionError, match="unknown album"):
        production.read_status(root)


def test_safe_draft_is_not_publishable():
    report = production.read_status()
    if not report["queue"]:
        pytest.skip("All 100 albums have already been released")
    entry = report["queue"][0]
    draft = production.release_template(entry["set_id"])
    assert draft["sets"][0]["group"] == entry["group"]
    assert len(draft["sets"][0]["cards"]) == entry["size"]
    assert draft["sets"][0]["collection_review_status"] == "pending"
    assert not draft["sets"][0]["source_collection"]
    assert all(not item["photo_url"] and item["license_status"] == "pending"
               for item in draft["sets"][0]["cards"])
    with pytest.raises(ValueError):
        pipeline.check_complete_release(draft["sets"][0], set())


def test_published_album_cannot_be_drafted_as_new_release():
    published = production.load_json(production.ROOT, production.SETS_PATH)["sets"]
    with pytest.raises(production.ProductionError, match="already published"):
        production.release_template(published[0]["set_id"])
