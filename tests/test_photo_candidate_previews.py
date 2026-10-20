"""Proof that partial real-photo reviews cannot mutate the playable album catalog."""
import json
from pathlib import Path

import pytest
from PIL import Image

from tools import photo_candidate_previews as previews


@pytest.fixture
def preview_input(tmp_path, monkeypatch):
    original = json.loads(
        (previews.ROOT / "tools/research/lesserafim_aura_rare_candidates.json").read_text(encoding="utf-8")
    )
    def fake_original(row):
        index = {"CHAEWON": 1, "SAKURA": 2, "KAZUHA": 3, "EUNCHAE": 4}[row["member"]]
        picture = Image.new("RGB", (1200, 1600), (index, 100, 150))
        return (row["member"] + "-unique-source").encode(), picture

    distinct_hash = {1: 0x0000000000000000, 2: 0xFFFFFFFFFFFFFFFF,
                     3: 0xAAAAAAAAAAAAAAAA, 4: 0x5555555555555555}
    monkeypatch.setattr(previews, "original_image", fake_original)
    monkeypatch.setattr(
        previews, "perceptual_hash",
        lambda picture: distinct_hash[picture.getpixel((0, 0))[0]]
    )

    def write_manifest(item):
        destination = tmp_path / "candidates.json"
        destination.write_text(json.dumps(item, ensure_ascii=False), encoding="utf-8")
        return destination

    return original, write_manifest, tmp_path / "previews"


def test_four_real_candidates_preview_without_publishing(preview_input):
    source, write, output = preview_input
    # This historical four-photo mock preview is superseded by a complete
    # five-member set once an approved release is queued or published.
    # Preserve duplicate protection in the renderer; do not require old
    # source URLs to remain unissued forever.
    pending = json.loads((previews.ROOT / "tools/photo_releases.json").read_text(encoding="utf-8"))["sets"]
    published = json.loads((previews.ROOT / "assets/collections/verified_sets.json").read_text(encoding="utf-8"))["sets"]
    if any(item.get("set_id") == "coll_lesserafim_aura_rare" or
           (item.get("group"), item.get("era"), item.get("rarity")) ==
           ("LE SSERAFIM", "AURA", "rare") for item in pending + published):
        pytest.skip("Superseded four-card mock; full unique five-card release is queued or published")
    live_catalog = previews.ROOT / "dolce_empire/_catalog.json"
    live_sets = previews.ROOT / "assets/collections/verified_sets.json"
    before = (live_catalog.read_bytes(), live_sets.read_bytes())
    result = previews.prepare_candidates(write(source), output_dir=output)
    assert result["members_missing"] == ["YUNJIN"]
    assert len(result["cards"]) == 4
    assert "BLOCKED" in result["publication"]
    for row in result["cards"]:
        with Image.open(output / row["file"]) as image:
            assert image.size == (900, 1200)
    assert (output / "PREVIEW_REPORT.json").is_file()
    assert result["contact_sheet"] == "CONTACT_SHEET.png"
    with Image.open(output / result["contact_sheet"]) as sheet:
        assert sheet.size[0] >= 1250
        assert sheet.size[1] == 720
        # YUNJIN is member 3/5: inspect a blank area in the THIRD card slot.
        # The other source cards remain genuine photographs, never copied into it.
        margin = (sheet.width - (5 * 280 + 4 * 24)) // 2
        third_slot_x = margin + 2 * (280 + 24)
        assert sheet.getpixel((third_slot_x + 30, 500)) == (39, 47, 68)
    assert (live_catalog.read_bytes(), live_sets.read_bytes()) == before


def test_reused_photo_between_candidates_is_rejected(preview_input):
    source, write, output = preview_input
    source["cards"][1]["photo_url"] = source["cards"][0]["photo_url"]
    with pytest.raises(ValueError, match="Previously published photograph"):
        previews.prepare_candidates(write(source), output_dir=output)


def test_unverified_rights_are_rejected(preview_input):
    source, write, output = preview_input
    source["cards"][0]["license_status"] = "pending"
    with pytest.raises(ValueError, match="Unverified photo rights"):
        previews.prepare_candidates(write(source), output_dir=output)


def test_incomplete_group_coverage_is_reported_not_filled(preview_input):
    source, write, output = preview_input
    source["missing_members"] = []
    with pytest.raises(ValueError, match="partition the full group"):
        previews.prepare_candidates(write(source), output_dir=output)


def test_candidate_manifest_status_must_prevent_publication(preview_input):
    source, write, output = preview_input
    source["status"] = "publish"
    with pytest.raises(ValueError, match="preview-only"):
        previews.prepare_candidates(write(source), output_dir=output)


def test_network_blocked_source_leaves_empty_slot_not_fake_card(preview_input, monkeypatch):
    """A transient Commons 429 must not erase verified previews or synthesize art."""
    from urllib.error import HTTPError
    source, write, output = preview_input
    # Explicitly use unique unissued test pages to exercise networking recovery.
    for row in source["cards"]:
        row["photo_url"] = f"https://example.invalid/unique/{row['member']}.jpg"
        row["source_page"] = f"https://example.invalid/attribution/{row['member']}.html"
    existing = previews.original_image

    def blocked_sakura(row):
        if row["member"] == "SAKURA":
            raise HTTPError(row["photo_url"], 429, "Wikimedia quota", {}, None)
        return existing(row)

    monkeypatch.setattr(previews, "original_image", blocked_sakura)
    # Simulate older successful research artifacts in the same folder.
    # An unavailable source MUST NOT leave a stale "ready" card in the ZIP.
    output.mkdir(parents=True, exist_ok=True)
    old_png = output / "lesserafim_aura_rare_sakura_PREVIEW.png"
    old_png.write_bytes(b"stale-card-from-previous-run")
    old_original_dir = output / "source_originals"
    old_original_dir.mkdir()
    (old_original_dir / "sakura.bin").write_bytes(b"stale-source")
    (output / "PREVIEW_REPORT.json").write_text('{"old": true}')
    result = previews.prepare_candidates(write(source), output_dir=output)
    assert {row["member"] for row in result["cards"]} == {"CHAEWON", "KAZUHA", "EUNCHAE"}
    assert set(result["members_missing"]) == {"SAKURA", "YUNJIN"}
    assert result["members_source_unavailable"][0]["member"] == "SAKURA"
    assert result["members_source_unavailable"][0]["status"] == "download_unavailable_not_verified"
    assert (output / "CONTACT_SHEET.png").is_file()
    assert not old_png.exists()
    assert not (old_original_dir / "sakura.bin").exists()
    assert json.loads((output / "PREVIEW_REPORT.json").read_text())["members_missing"]
    assert "BLOCKED" in result["publication"]


def test_photo_source_cache_reuses_only_exact_verified_image_bytes(preview_input, monkeypatch, tmp_path):
    """A rate-limited second run may reuse a real earlier source, never a fake image."""
    from io import BytesIO
    source, write, output = preview_input
    for row in source["cards"]:
        row["photo_url"] = f"https://example.invalid/cache/{row['member']}.png"
        row["source_page"] = f"https://example.invalid/credits/{row['member']}"
    monkeypatch.setattr(previews, "SOURCE_CACHE", tmp_path / "sources")
    member_color = {"CHAEWON": 1, "SAKURA": 2, "KAZUHA": 3, "EUNCHAE": 4}

    def valid_source(row):
        img = Image.new("RGB", (1200, 1600), (member_color[row["member"]], 100, 150))
        buffer = BytesIO()
        img.save(buffer, "PNG")
        return buffer.getvalue(), img

    monkeypatch.setattr(previews, "original_image", valid_source)
    first = previews.prepare_candidates(write(source), output_dir=output, archive_originals=True)
    assert len(first["cards"]) == 4

    def unexpected_network(_row):
        raise AssertionError("Same source must be restored from verified local cache")

    monkeypatch.setattr(previews, "original_image", unexpected_network)
    second = previews.prepare_candidates(write(source), output_dir=output, archive_originals=True)
    assert len(second["cards"]) == 4
    assert {r["member"]: r["source_sha256"] for r in second["cards"]} == {
        r["member"]: r["source_sha256"] for r in first["cards"]
    }
    assert all((output / "source_originals" / f"{name.lower()}.bin").is_file()
               for name in member_color)


def test_tampered_source_cache_refetches_real_image(preview_input, monkeypatch, tmp_path):
    """Never treat tampered PNG or mismatched SHA as an approved source."""
    from io import BytesIO
    source, write, output = preview_input
    for row in source["cards"]:
        row["photo_url"] = f"https://example.invalid/fresh/{row['member']}.png"
        row["source_page"] = f"https://example.invalid/rights/{row['member']}"
    monkeypatch.setattr(previews, "SOURCE_CACHE", tmp_path / "sources")
    member_color = {"CHAEWON": 1, "SAKURA": 2, "KAZUHA": 3, "EUNCHAE": 4}
    fetched = []

    def network(row):
        fetched.append(row["member"])
        im = Image.new("RGB", (1200, 1600), (member_color[row["member"]], 100, 150))
        b = BytesIO()
        im.save(b, "PNG")
        return b.getvalue(), im

    monkeypatch.setattr(previews, "original_image", network)
    original = previews.prepare_candidates(write(source), output_dir=output, archive_originals=True)
    assert len(original["cards"]) == 4
    cached = next((tmp_path / "sources").glob("*.bin"))
    cached.write_bytes(b"fake-photo-not-same-sha")
    fetched.clear()
    again = previews.prepare_candidates(write(source), output_dir=output, archive_originals=True)
    assert len(again["cards"]) == 4
    assert len(fetched) == 1, "Only corrupted source must be reacquired"
