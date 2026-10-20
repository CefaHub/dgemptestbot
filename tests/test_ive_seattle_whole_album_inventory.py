"""Researching an entire event is allowed; taking partial collectible cards is not."""
import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from tools.research import ive_seattle_album_contact as scout


@pytest.fixture
def full_manifest():
    return json.loads(scout.MANIFEST.read_text(encoding="utf-8"))


def test_all_sources_one_event_fully_licensed_or_reject(full_manifest):
    assert len(scout.source_preflight(full_manifest)) == 37
    assert len({r["id"] for r in full_manifest["photos"]}) == 37
    broken = copy.deepcopy(full_manifest)
    broken["photos"][2]["license_status"] = "pending"
    with pytest.raises(ValueError, match="verified source page"):
        scout.source_preflight(broken)


def test_mismatched_source_image_identity_rejected(full_manifest):
    broken = copy.deepcopy(full_manifest)
    broken["photos"][2]["image_url"] = broken["photos"][3]["image_url"]
    with pytest.raises(ValueError, match="does not match unique"):
        scout.source_preflight(broken)


def test_whole_shoot_source_contact_never_creates_cards(full_manifest, tmp_path):
    card_list = (scout.ROOT / "data/catalog.json").read_bytes()
    def synthetic_source_for_unit_test(url):
        return Image.new("RGB", (1000, 1500), (90, 160, 120)), "f" * 64
    result = scout.research(full_manifest, output=tmp_path, fetch=synthetic_source_for_unit_test)
    assert result["source_thumbnails_downloaded"] == 37
    assert result["cards_created"] == 0
    assert result["game_catalog_modified"] is False
    assert result["full_group_members_approved"] == 0
    assert (tmp_path / "CONTACT_SHEET_FULL_INDEX.jpg").is_file()
    assert not list(tmp_path.glob("*_PREVIEW.png"))
    assert (scout.ROOT / "data/catalog.json").read_bytes() == card_list


def test_network_failure_never_selects_partial_members(full_manifest, tmp_path):
    from urllib.error import URLError
    def offline(_):
        raise URLError("flickr timeout")
    result = scout.research(full_manifest, output=tmp_path, fetch=offline)
    assert result["source_thumbnails_downloaded"] == 0
    assert all(r["status"] == "source_unavailable" for r in result["audit"])
    assert result["cards_created"] == 0
    assert result["full_group_members_approved"] == 0
