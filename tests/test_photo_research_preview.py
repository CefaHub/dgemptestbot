"""Review previews may stage real photos, but never publish fake or incomplete sets.

Synthetic images in this module are TEST FIXTURES only; no such art is
included in production packages, gameplay catalogs, or research manifests.
"""
import copy
import json
from pathlib import Path

import pytest
from PIL import Image

from tools import photo_release_pipeline as pipe
from tools.research import preview_photo_candidate as preview


def test_research_candidate_is_a_complete_unpublished_five_member_set():
    candidate = json.loads(
        (pipe.ROOT / "tools/research/lesserafim_aura_rare_v2_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    catalog = json.loads((pipe.ROOT / "assets/collections/verified_sets.json").read_text())
    _, _, members = preview.validate_candidate(
        candidate, {entry["set_id"] for entry in catalog["sets"]}
    )
    assert set(members) == {entry["member"] for entry in candidate["cards"]}
    assert len(members) == 5
    assert candidate["collection_review_status"] == "pending"
    assert "coll_lesserafim_aura_rare" not in {
        s["set_id"] for s in catalog["sets"]
    }


def test_shoot_mismatch_and_missing_members_are_rejected():
    candidate = json.loads(
        (pipe.ROOT / "tools/research/lesserafim_aura_rare_v2_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    mismatched = copy.deepcopy(candidate)
    mismatched["cards"][0]["photo_session_id"] = "wrong_date_event"
    with pytest.raises(ValueError, match="same source photo session"):
        preview.validate_candidate(mismatched, set())

    incomplete = copy.deepcopy(candidate)
    incomplete["cards"].pop()
    with pytest.raises(ValueError, match="complete, non-duplicated"):
        preview.validate_candidate(incomplete, set())


def test_preview_does_not_accept_preapproved_research_or_existing_set():
    candidate = json.loads(
        (pipe.ROOT / "tools/research/lesserafim_aura_rare_v2_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    already = {candidate["set_id"]}
    with pytest.raises(ValueError, match="already published"):
        preview.validate_candidate(candidate, already)
    preapproved = copy.deepcopy(candidate)
    preapproved["collection_review_status"] = "approved"
    with pytest.raises(ValueError, match="should not pre-approve"):
        preview.validate_candidate(preapproved, set())


@pytest.fixture
def fake_preview_env(tmp_path, monkeypatch):
    """Local pixel TEST FIXTURES; never downloaded or published as artist photos."""
    candidate = json.loads(
        (pipe.ROOT / "tools/research/lesserafim_aura_rare_v2_candidates.json").read_text(
            encoding="utf-8"
        )
    )
    (tmp_path / "assets/collections").mkdir(parents=True)
    (tmp_path / "assets/collections/verified_sets.json").write_text('{"sets":[]}')
    output = tmp_path / "output/preview"
    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(json.dumps(candidate))
    monkeypatch.setattr(preview, "ROOT", tmp_path)
    monkeypatch.setattr(preview, "checked_sources", lambda: (set(), set(), set(), []))

    def fake_original(row):
        order = [member for member, _ in pipe.GROUPS["LE SSERAFIM"]["members"]]
        index = order.index(row["member"])
        if index == 2:
            # Keep one black-and-white test photo to exercise palette warnings.
            rgb = (55, 55, 55)
        else:
            rgb = (40 + index * 20, 100, 170)
        return f"TEST IMAGE DATA {index}".encode(), Image.new("RGB", (1600, 2000), rgb)

    monkeypatch.setattr(pipe, "original_image", fake_original)
    hashes = iter([(index + 1) * 0x1111111111111111 for index in range(5)])
    monkeypatch.setattr(pipe, "perceptual_hash", lambda image: next(hashes))
    return candidate_file, output, tmp_path


def test_research_preview_produces_five_card_images_and_banner_without_publishing(fake_preview_env):
    candidate_file, output, root = fake_preview_env
    before = sorted(str(p) for p in root.rglob("*") if p.is_file())
    result = preview.preview(candidate_file, output)
    assert result["published"] is False
    assert result["review_status"] == "pending"
    assert result["previewed"] == 5
    assert result["failed"] == 0
    assert len(list(output.glob("*_DRAFT.png"))) == 6
    assert (output / "contact_sheet_DRAFT.jpg").is_file()
    assert (output / "review_report.json").is_file()
    with Image.open(output / "banner_DRAFT.png") as banner:
        assert banner.size == pipe.BANNER_SIZE
    for image in output.glob("0*_DRAFT.png"):
        with Image.open(image) as card:
            assert card.size == pipe.CARD_SIZE
    # The script cannot write to the live catalog or published source lists.
    after = sorted(str(p) for p in root.rglob("*") if p.is_file())
    assert all("/output/" in path for path in set(after) - set(before))
    assert any(
        "Cropped image originates" in warning
        for member in result["records"] for warning in member["warnings"]
    )
