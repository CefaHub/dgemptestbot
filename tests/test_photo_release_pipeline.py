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
            "photo_session_id": "test_aespa_single_photo_session",
            "source_page": f"https://example.test/aespa/{member.lower()}",
            "photographer": "Test fixture", "license": "CC0",
            "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "license_status": "verified",
            "focus_x": 0.5, "focus_y": 0.35,
        })
    manifest = {
        "sets": [{
            "group": "aespa", "era": "AURA", "rarity": "rare",
            "source_collection": "Test single-shoot collection (not an official album)",
            "photo_session_id": "test_aespa_single_photo_session",
            "collection_review_status": "approved",
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
    assert {s["photo_session_id"] for s in package["sources"]} == {"test_aespa_single_photo_session"}
    assert package["sets"][0]["photo_session_id"] == "test_aespa_single_photo_session"
    for item in package["cards"]:
        exported = pipe.OUT / item["image_path"]
        with Image.open(exported) as image:
            assert image.size == (900, 1200)
    banner = pipe.OUT / package["sets"][0]["banner_path"]
    with Image.open(banner) as image:
        assert image.size == (1600, 900)
    # Build is preview-only; no live game files or metadata modified.
    assert json.loads((root / "dolce_empire/_catalog.json").read_text()) == []


def test_publish_also_updates_gallery_in_the_same_release(photo_sandbox, monkeypatch):
    """One CI publish must commit the card assets, source ledger and updated index."""
    from dolce_empire import set_validation
    from tools.generate_gallery import generate_gallery

    root, manifest = photo_sandbox
    monkeypatch.setattr(set_validation, "ROOT", root)
    monkeypatch.setattr(
        set_validation, "SETS_FILE", root / "assets/collections/verified_sets.json"
    )
    monkeypatch.setattr(
        set_validation, "SOURCES_FILE", root / "tools/photo_sources.json"
    )
    package = pipe.generate("tools/photo_releases.json", publish=True)
    assert len(package["cards"]) == 4
    assert (root / "GALLERY.md").read_text(encoding="utf-8") == generate_gallery(root)
    assert (root / "GALLERY.md").read_text(encoding="utf-8").count('<img src="assets/cards/') == 4
    assert json.loads((root / "tools/photo_releases.json").read_text())["sets"] == []
    assert len(json.loads((root / "data/catalog.json").read_text())) == 4


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


def test_set_rejects_missing_shared_photo_session(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0].pop("photo_session_id")
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="photo_session_id"):
        pipe.generate("tools/photo_releases.json")


def test_set_rejects_mixed_member_photo_sessions(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][2]["photo_session_id"] = "different_photo_session"
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Mixed photo sessions"):
        pipe.generate("tools/photo_releases.json")


def test_set_rejects_unreviewed_shoot_even_with_verified_rights(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["collection_review_status"] = "pending"
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="review approval"):
        pipe.generate("tools/photo_releases.json")


def test_zoom_cannot_destroy_original_image_resolution(photo_sandbox):
    root, manifest = photo_sandbox
    manifest["sets"][0]["cards"][0]["zoom"] = 1.4
    (root / "tools/photo_releases.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Zoom leaves too few pixels"):
        pipe.generate("tools/photo_releases.json")



def test_wikimedia_429_uses_same_photo_cdn_proxy(monkeypatch):
    """429 on Wikimedia must never swap in another member's photograph."""
    from io import BytesIO
    from urllib.error import HTTPError
    from urllib.parse import urlsplit
    buffer = BytesIO()
    Image.new("RGB", (1200, 1600), (112, 78, 35)).save(buffer, "JPEG", quality=95)
    payload = buffer.getvalue()
    class FakeResponse(BytesIO):
        def __init__(self, data):
            super().__init__(data)
            self.headers = {"Content-Length": str(len(data))}
    calls = []
    def get(request, timeout):
        url = request.full_url
        calls.append(url)
        if len(calls) == 1:
            raise HTTPError(url, 429, "Too Many Requests", {}, None)
        assert urlsplit(url).hostname == "wsrv.nl"
        assert "upload.wikimedia.org" in url
        return FakeResponse(payload)
    monkeypatch.setattr(pipe.urllib.request, "urlopen", get)
    original = "https://upload.wikimedia.org/wikipedia/commons/1/17/Unique_Photo.jpg"
    raw, image = pipe.original_image({"photo_url": original})
    assert raw == payload and image.size == (1200, 1600)
    assert len(calls) == 2 and calls[0] == original


def test_unrelated_source_429_is_not_proxied(monkeypatch):
    from urllib.error import HTTPError
    calls = []
    def get(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
    monkeypatch.setattr(pipe.urllib.request, "urlopen", get)
    with pytest.raises(HTTPError):
        pipe.original_image({"photo_url": "https://photos.example.org/photo.jpg"})
    assert calls == ["https://photos.example.org/photo.jpg"]


def test_wikimedia_missing_photo_404_is_never_substituted(monkeypatch):
    from urllib.error import HTTPError
    calls = []
    def get(request, timeout):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 404, "Not found", {}, None)
    monkeypatch.setattr(pipe.urllib.request, "urlopen", get)
    with pytest.raises(HTTPError):
        pipe.original_image({
            "photo_url": "https://upload.wikimedia.org/wikipedia/commons/a/aa/missing.jpg"
        })
    assert len(calls) == 1
