"""The whole-event source audit is NOT permitted to generate any cards."""
import json
from pathlib import Path

import pytest
from PIL import Image

from tools.research.full_lineup_video_scout import scout, validate_spec, ROOT


@pytest.fixture
def base():
    return json.loads(
        (ROOT / "tools/research/itzy_2019_dispatch_full_event_video_scout.json").read_text("utf-8")
    )


def test_no_missing_group_members_may_be_scanned(base):
    base["full_group_members"].pop()
    with pytest.raises(ValueError, match="Full group lineup"):
        validate_spec(base)


def test_no_unlicensed_source_may_be_scanned(base):
    base["license"] = "no license"
    with pytest.raises(ValueError, match="documented attribution"):
        validate_spec(base)


def test_never_marks_five_stills_approved_or_renders_cards(base, tmp_path, monkeypatch):
    # Fake a source video and extraction; assertions focus on safe project state.
    import tools.research.full_lineup_video_scout as module
    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    def fake_downloader(_spec, target):
        target.write_bytes(b"placeholder-for-test-only")
        return {"source_sha256": "a" * 64, "source_bytes": 23}
    def fake_decoder(_argv, **_kwargs):
        for number in range(1, 6):
            Image.new("RGB", (1920, 1080), (number * 25, 110, 140)).save(
                tmp_path / f"frame_{number:03d}.jpg"
            )
    live_catalog = (ROOT / "data/catalog.json").read_bytes()
    result = scout(base, output_dir=tmp_path,
                   download_fn=fake_downloader, run_fn=fake_decoder)
    assert result["frames_sampled"] == 5
    assert result["status"] == "whole_event_sampled_waiting_all_five_solo_qa"
    assert result["cards_created"] == 0
    assert result["catalog_updated"] is False
    assert result["all_five_member_portraits_verified"] is False
    assert list(tmp_path.glob("CONTACT_SHEET_*.jpg"))
    assert not list(tmp_path.glob("*_PREVIEW.png"))
    assert (ROOT / "data/catalog.json").read_bytes() == live_catalog


def test_video_download_failure_does_not_fake_images(base, tmp_path, monkeypatch):
    import tools.research.full_lineup_video_scout as module
    monkeypatch.setattr(module.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    def failed_fetch(_spec, _target):
        raise ConnectionError("Wikimedia CDN 429")
    result = scout(base, output_dir=tmp_path, download_fn=failed_fetch)
    assert result["status"] == "video_source_unavailable_or_decoder_error"
    assert not list(tmp_path.glob("frame_*"))
    assert not list(tmp_path.glob("*_PREVIEW.png"))
    assert json.loads((tmp_path / "SCOUT_REPORT.json").read_text())["cards_created"] == 0
