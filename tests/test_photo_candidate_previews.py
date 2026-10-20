"""Strict full-set-only photo candidate QA; incomplete groups produce ZERO cards."""
import json
from io import BytesIO
from urllib.error import HTTPError

import pytest
from PIL import Image

from tools import photo_candidate_previews as previews


@pytest.fixture
def preview_input(tmp_path, monkeypatch):
    # Fresh fictional ITZY photo URLs: NEVER reuse historical/published sources.
    members = [name for name, _ in previews.GROUPS["ITZY"]["members"]]
    assert len(members) == 5
    session = "itzy_one_unpublished_session"
    source = {
        "status": "research_preview_only_not_published",
        "set_id": "coll_itzy_aura_rare",
        "group": "ITZY",
        "era": "AURA",
        "rarity": "rare",
        "source_collection": "Fictional shared photo session for deterministic tests",
        "photo_session_id": session,
        "missing_members": [],
        "cards": [
            {
                "member": member,
                "photo_session_id": session,
                "photo_url": f"https://example.invalid/unique-itzy-photo/{member}.png",
                "source_page": f"https://example.invalid/attribution/itzy/{member}",
                "photographer": "Licensed photographer",
                "license": "CC BY 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "license_status": "verified",
                "focus_x": 0.5,
                "focus_y": 0.3,
            }
            for member in members
        ],
    }
    colors = {name: idx + 1 for idx, name in enumerate(members)}
    hash_values = [0, 0xffffffffffffffff, 0xaaaaaaaaaaaaaaaa,
                   0x5555555555555555, 0x0f0f0f0f0f0f0f0f]

    def fake_original(row):
        pixel = colors[row["member"]]
        picture = Image.new("RGB", (1200, 1600), (pixel, 100, 150))
        b = BytesIO()
        picture.save(b, "PNG")
        return b.getvalue(), picture

    monkeypatch.setattr(previews, "original_image", fake_original)
    monkeypatch.setattr(previews, "perceptual_hash",
                        lambda photo: hash_values[photo.getpixel((0, 0))[0] - 1])
    monkeypatch.setattr(previews, "SOURCE_CACHE", tmp_path / "cache")

    def write_manifest(spec):
        dst = tmp_path / "new_itzy_candidates.json"
        dst.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return dst

    return source, write_manifest, tmp_path / "renders", members


def test_full_five_member_set_preview_not_published(preview_input):
    source, write, out, members = preview_input
    game = previews.ROOT / "dolce_empire/_catalog.json"
    sets = previews.ROOT / "assets/collections/verified_sets.json"
    before = (game.read_bytes(), sets.read_bytes())
    report = previews.prepare_candidates(write(source), output_dir=out)
    assert {item["member"] for item in report["cards"]} == set(members)
    assert report["members_missing"] == []
    assert report["publication"].startswith("BLOCKED")
    assert (out / "CONTACT_SHEET.png").is_file()
    for item in report["cards"]:
        with Image.open(out / item["file"]) as image:
            assert image.size == (900, 1200)
    with Image.open(out / "CONTACT_SHEET.png") as image:
        assert image.width >= 1250
    assert (game.read_bytes(), sets.read_bytes()) == before


def test_even_one_missing_member_is_rejected_before_any_download(preview_input, monkeypatch):
    source, write, out, members = preview_input
    source["cards"].pop()

    def no_network(_):
        raise AssertionError("Do not acquire ANY photo for an incomplete group")

    monkeypatch.setattr(previews, "original_image", no_network)
    with pytest.raises(ValueError, match="Incomplete set rejected"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not out.exists()


def test_explicit_missing_member_is_rejected(preview_input):
    source, write, out, members = preview_input
    source["missing_members"] = [members[-1]]
    source["cards"].pop()
    with pytest.raises(ValueError, match="Incomplete set rejected"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not out.exists()


def test_same_session_required_for_all_members(preview_input):
    source, write, out, members = preview_input
    source["cards"][-1]["photo_session_id"] = "another_event"
    with pytest.raises(ValueError, match="one common verified photo session"):
        previews.prepare_candidates(write(source), output_dir=out)


def test_duplicate_source_url_rejected(preview_input):
    source, write, out, _ = preview_input
    source["cards"][-1]["photo_url"] = source["cards"][0]["photo_url"]
    with pytest.raises(ValueError, match="Previously published photograph"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not list(out.glob("*_PREVIEW.png"))


def test_unverified_license_rejected(preview_input):
    source, write, out, _ = preview_input
    source["cards"][0]["license_status"] = "pending"
    with pytest.raises(ValueError, match="Unverified photo rights"):
        previews.prepare_candidates(write(source), output_dir=out)


def test_nonpreview_manifest_rejected(preview_input):
    source, write, out, _ = preview_input
    source["status"] = "publish"
    with pytest.raises(ValueError, match="preview-only"):
        previews.prepare_candidates(write(source), output_dir=out)


def test_network_429_rolls_back_entire_set_and_old_artifacts(preview_input, monkeypatch):
    source, write, out, members = preview_input
    member_blocked = members[-1]  # Failure occurs AFTER first four valid originals.
    orig = previews.original_image

    def one_blocked(row):
        if row["member"] == member_blocked:
            raise HTTPError(row["photo_url"], 429, "Wikimedia throttled", {}, None)
        return orig(row)

    monkeypatch.setattr(previews, "original_image", one_blocked)
    out.mkdir()
    (out / "itzy_aura_rare_yeji_PREVIEW.png").write_bytes(b"obsolete")
    (out / "CONTACT_SHEET.png").write_bytes(b"old-sheet")
    with pytest.raises(ValueError, match="Full-set source unavailable"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not list(out.glob("*_PREVIEW.png")), "No 4/5, ever"
    assert not (out / "CONTACT_SHEET.png").exists()
    assert not (out / "PREVIEW_REPORT.json").exists()


def test_cached_exact_photo_bytes_reused_on_full_set(preview_input, monkeypatch):
    source, write, out, _ = preview_input
    first = previews.prepare_candidates(write(source), output_dir=out, archive_originals=True)
    assert len(first["cards"]) == 5

    def no_network(_):
        raise AssertionError("Verified cached photos should not be redownloaded")

    monkeypatch.setattr(previews, "original_image", no_network)
    second = previews.prepare_candidates(write(source), output_dir=out, archive_originals=True)
    assert len(second["cards"]) == 5
    assert {r["member"]: r["source_sha256"] for r in first["cards"]} == {
        r["member"]: r["source_sha256"] for r in second["cards"]
    }


def test_corrupted_cache_refetches_and_no_invented_card(preview_input, monkeypatch):
    source, write, out, _ = preview_input
    previews.prepare_candidates(write(source), output_dir=out, archive_originals=True)
    cached = next((out.parent / "cache").glob("*.bin"))
    cached.write_bytes(b"forged-source")
    fetched = []
    prev = previews.original_image

    def spy(row):
        fetched.append(row["member"])
        return prev(row)

    monkeypatch.setattr(previews, "original_image", spy)
    result = previews.prepare_candidates(write(source), output_dir=out, archive_originals=True)
    assert len(result["cards"]) == 5
    assert len(fetched) == 1



def test_fifth_member_render_error_rolls_back_all_previews(preview_input, monkeypatch):
    """Atomic output: even image rendering failure may not leak a 4/5 set."""
    source, write, out, members = preview_input
    real_art = previews.card_art
    calls = 0

    def last_render_fails(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == len(members):
            raise RuntimeError("Pillow render failure")
        return real_art(*args, **kwargs)

    monkeypatch.setattr(previews, "card_art", last_render_fails)
    with pytest.raises(RuntimeError, match="Pillow render failure"):
        previews.prepare_candidates(write(source), output_dir=out, archive_originals=True)
    assert calls == len(members)
    assert not list(out.rglob("*_PREVIEW.png"))
    assert not list(out.rglob("*.bin"))
    assert not (out / "CONTACT_SHEET.png").exists()
    assert not (out / "PREVIEW_REPORT.json").exists()



def test_duplicate_parent_original_rejects_every_card_before_network(preview_input, monkeypatch):
    """Five differently cropped Wikimedia pages of ONE group photo are not unique originals."""
    source, write, out, members = preview_input
    parent = "https://commons.wikimedia.org/wiki/File:ITZY_original_group_photo.jpg"
    source["cards"][0]["origin_photo_page"] = parent
    source["cards"][1]["origin_photo_page"] = parent
    monkeypatch.setattr(previews, "original_image",
                        lambda _row: (_ for _ in ()).throw(AssertionError("Must preflight first")))
    with pytest.raises(ValueError, match="photo family"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not out.exists()


def test_known_native_photo_too_small_rejects_entire_set(preview_input, monkeypatch):
    source, write, out, _ = preview_input
    source["cards"][3]["native_dimensions"] = [586, 732]
    monkeypatch.setattr(previews, "original_image",
                        lambda _row: (_ for _ in ()).throw(AssertionError("Must preflight first")))
    with pytest.raises(ValueError, match="undersized original"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not out.exists()


def test_solo_crop_declared_resolution_checked_before_network(preview_input, monkeypatch):
    source, write, out, _ = preview_input
    source["cards"][2]["native_dimensions"] = [1500, 2000]
    source["cards"][2]["solo_region"] = [0.0, 0.0, 0.38, 0.6]
    monkeypatch.setattr(previews, "original_image",
                        lambda _row: (_ for _ in ()).throw(AssertionError("Must preflight first")))
    with pytest.raises(ValueError, match="undersized original"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not out.exists()


def test_released_original_page_rejects_all_five_before_network(preview_input, monkeypatch):
    source, write, out, _ = preview_input
    first_existing = json.loads(
        (previews.ROOT / "tools/photo_sources.json").read_text(encoding="utf-8")
    )["cards"][0]
    source["cards"][-1]["origin_photo_page"] = first_existing["page"]
    monkeypatch.setattr(previews, "original_image",
                        lambda _row: (_ for _ in ()).throw(AssertionError("Must preflight first")))
    with pytest.raises(ValueError, match="photo family"):
        previews.prepare_candidates(write(source), output_dir=out)
    assert not out.exists()
