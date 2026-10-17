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
