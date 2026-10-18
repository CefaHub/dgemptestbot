"""Regression tests for the safe photo release builder.

Generated gradients and geometric patterns here are TEST FIXTURES ONLY.
No synthetic test imagery is ever committed as collectible idol portraits.
"""
import json
import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from tools import photo_release_pipeline as pipe


def test_cdn_proxy_normalization_preserves_original_photo_identity():
    original = "https://upload.wikimedia.org/wikipedia/commons/7/77/Giselle_at_Mise-en-Scene_event_on_19022026_%282%29.png"
    proxy = "https://wsrv.nl/?url=upload.wikimedia.org%2Fwikipedia%2Fcommons%2F7%2F77%2FGiselle_at_Mise-en-Scene_event_on_19022026_%282%29.png"
    assert pipe.canonical(original) == pipe.canonical(proxy)
    assert pipe.canonical(proxy) != pipe.canonical(
        "https://wsrv.nl/?url=upload.wikimedia.org%2Fwikipedia%2Fcommons%2F6%2F66%2FAnother_Portrait.png"
    )


def test_release_plan_contains_exactly_100_unique_slots():
    slots = pipe.plan_slots()
    assert len(slots) == 100
    assert len({slot["card_id"] for slot in slots}) == 100
    assert sum(slot["status"] == "already_published" for slot in slots) >= 9
    assert sum(slot["status"] == "needs_unique_photo" for slot in slots) <= 91
    for group in pipe.PLAN["groups"]:
        for tier in pipe.PLAN["tiers"]:
            entries = [c for c in slots if c["group"] == group["name"] and c["rarity"] == tier["rarity"]]
            assert len(entries) == len(group["members"])


@pytest.fixture
def photo_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(pipe, "ROOT", tmp_path)
    monkeypatch.setattr(pipe, "OUT", tmp_path / "output/photo_release_batch")
    for directory in ("dolce_empire", "tools", "data", "assets/collections", "photos/inbox"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    (tmp_path / "dolce_empire/_catalog.json").write_text("[]", encoding="utf-8")
    (tmp_path / "tools/photo_sources.json").write_text('{"cards":[]}', encoding="utf-8")
    (tmp_path / "assets/collections/verified_sets.json").write_text('{"sets":[]}', encoding="utf-8")
    members = ["KARINA", "WINTER", "GISELLE", "NINGNING"]
    records = []
    for index, member in enumerate(members):
        # Wide 1600x1000 sources ensure crop-to-3:4 is actually exercised.
        img = Image.new("RGB", (1600, 1000), (40 + index * 40, 80, 130))
        draw = ImageDraw.Draw(img)
        rnd = random.Random(12000 + index)
        for k in range(80):
            x, y = rnd.randint(0, 1500), rnd.randint(0, 900)
            color = (rnd.randint(20, 245), rnd.randint(20, 245), rnd.randint(20, 245))
            draw.ellipse((x, y, x + 30 + index * 2, y + 45), fill=color)
        local = tmp_path / f"photos/inbox/{member.lower()}.jpg"
        img.save(local, quality=95)
        records.append({
            "member": member, "local_path": f"photos/inbox/{member.lower()}.jpg",
            "source_page": f"https://example.test/aespa/{member.lower()}",
            "photographer": "Test fixture", "license": "CC0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "license_status": "verified",
            "focus_x": 0.5, "focus_y": 0.35,
        })
    manifest = {
        "sets": [{
            "group": "aespa", "era": "AURA", "rarity": "rare",
            "source_collection": "Test editorial selection (not an official album)",
            "source_mode": "curated", "cards": records,
        }]
    }
    (tmp_path / "tools/photo_releases.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path, manifest


def test_pipeline_generates_four_real_source_crops_and_one_wide_banner(photo_sandbox):
    root, manifest = photo_sandbox
    package = pipe.generate("tools/photo_releases.json")
    assert len(package["cards"]) == 4
    assert len(package["sets"]) == 1
    assert len(package["sources"]) == 4
    assert len({s["source_sha256"] for s in package["sources"]}) == 4
    for item in package["cards"]:
        exported = pipe.OUT / item["image_path"]
        with Image.open(exported) as image:
            assert image.size == (900, 1200)
    banner = pipe.OUT / package["sets"][0]["banner_path"]
    with Image.open(banner) as image:
        assert image.size == (1600, 900)
    # Build is preview-only; no live game files or metadata modified.
    assert json.loads((root / "dolce_empire/_catalog.json").read_text()) == []


def test_release_must_have_complete_group(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"].pop()
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="all 4 unique group members"):
        pipe.generate("tools/photo_releases.json")




def test_non_solo_original_cannot_publish_without_human_crop_approval(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][0]["solo_region"] = [0.05, 0.02, 0.72, 1.0]
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unapproved solo crop"):
        pipe.generate("tools/photo_releases.json")



def test_optional_solo_region_preserves_quality_and_source_provenance(photo_sandbox):
    root, manifest = photo_sandbox
    # Source-wide crop is larger than a portrait; a centered subject-only
    # selection must still leave at least 600x800 physical pixels.
    row = manifest["sets"][0]["cards"][0]
    row["solo_region"] = [0.05, 0.02, 0.72, 1.0]
    row["solo_review_status"] = "approved"
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    release = pipe.generate("tools/photo_releases.json")
    assert release["sources"][0]["solo_region"] == [0.05, 0.02, 0.72, 1.0]
    raw, full = pipe.original_image(row)
    assert pipe.solo_region(full, row["solo_region"]).size[0] >= 600
    path = pipe.OUT / release["cards"][0]["image_path"]
    with Image.open(path) as img:
        assert img.size == (900, 1200)


@pytest.mark.parametrize("region", [
    [0.1, 0.2, 0.1, 1.0],
    [0.8, 0.0, 0.2, 0.9],
    [-0.1, 0.0, 0.9, 1.0],
    [0, 0, 2, 1],
    [0, 0, 1],
    [0, "oops", 0.5, 1],
    [0, 0, True, 1],
])
def test_invalid_solo_region_fails_closed(photo_sandbox, region):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][0]["solo_region"] = region
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="solo_region"):
        pipe.generate("tools/photo_releases.json")


def test_too_small_solo_crop_is_not_upscaled(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][0]["solo_region"] = [0.03, 0, 0.2, 0.30]
    manifest["sets"][0]["cards"][0]["solo_review_status"] = "approved"
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="too small"):
        pipe.generate("tools/photo_releases.json")


def test_release_duplicate_original_is_rejected(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][1]["local_path"] = manifest["sets"][0]["cards"][0]["local_path"]
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Original photo reused"):
        pipe.generate("tools/photo_releases.json")


def test_unapproved_license_blocks_publishing(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][0]["license_status"] = "pending"
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Rights not verified"):
        pipe.generate("tools/photo_releases.json")


def test_existing_rarity_cannot_be_recycled(photo_sandbox):
    root, manifest = photo_sandbox
    (root / "assets/collections/verified_sets.json").write_text(
        json.dumps({"sets": [{"set_id": "coll_aespa_aura_rare"}]})
    )
    with pytest.raises(ValueError, match="already released"):
        pipe.generate("tools/photo_releases.json")


def test_tiny_source_is_rejected(photo_sandbox):
    root, manifest = photo_sandbox
    image = Image.new("RGB", (200, 250), "red")
    image.save(root / "photos/inbox/karina.jpg")
    with pytest.raises(ValueError, match="too small"):
        pipe.generate("tools/photo_releases.json")


def test_reencoded_photo_cannot_reappear_as_higher_rarity(photo_sandbox):
    root, manifest = photo_sandbox
    first = manifest["sets"][0]["cards"][0]
    raw, photo = pipe.original_image(first)
    old_hash = pipe.perceptual_hash(photo)
    old_source = {
        "cards": [{
            "id": "previous_rare_member",
            "photo": "https://example.test/different-old-file.jpg",
            "page": "https://example.test/old-source-page",
            "source_dhash": f"{old_hash:016x}",
        }]
    }
    (root / "tools/photo_sources.json").write_text(json.dumps(old_source))
    with pytest.raises(ValueError, match="near-identical"):
        pipe.generate("tools/photo_releases.json")
