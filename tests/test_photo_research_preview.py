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
    released = {entry["set_id"] for entry in catalog["sets"]}
    if candidate["set_id"] in released:
        pytest.skip("The formerly researched set is now officially published and validated")
    _, _, members = preview.validate_candidate(
        candidate, released
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
    credits = (output / "SOURCE_CREDITS_DRAFT.md").read_text(encoding="utf-8")
    assert "CC BY 4.0" in credits
    assert "David Lee" in credits
    assert "not approved for game release" in credits
    assert credits.count("Photo license:") == 5
    assert credits.count("Original photo page:") == 5
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


def test_itzy_gshock_partial_research_is_explicitly_unpublished():
    data = json.loads(
        (pipe.ROOT / "tools/research/itzy_aura_rare_gshock_2024_candidates.json")
        .read_text(encoding="utf-8")
    )
    assert data["set_id"] == "coll_itzy_aura_rare"
    assert data["collection_review_status"] == "pending"
    with pytest.raises(ValueError, match="complete, non-duplicated"):
        preview.validate_candidate(data, set())
    group, tier, lineup = preview.validate_candidate(
        data, set(), allow_incomplete=True
    )
    assert group["name"] == "ITZY" and tier["rarity"] == "rare"
    assert lineup == ["YEJI", "LIA", "RYUJIN", "CHAERYEONG", "YUNA"]
    assert data["missing_members"] == ["YEJI"]
    assert len(data["cards"]) == 4
    assert len({row["source_page"] for row in data["cards"]}) == 4
    assert all(
        row["photo_session_id"] == data["photo_session_id"]
        and row["license_status"] == "verified"
        for row in data["cards"]
    )


def test_partial_research_can_never_skip_declaring_missing_members():
    data = json.loads(
        (pipe.ROOT / "tools/research/itzy_aura_rare_gshock_2024_candidates.json")
        .read_text(encoding="utf-8")
    )
    data["missing_members"] = []
    with pytest.raises(ValueError, match="explicitly identify missing"):
        preview.validate_candidate(data, set(), allow_incomplete=True)


def test_itzy_partial_preview_renders_only_four_actual_sources(tmp_path, monkeypatch):
    data = json.loads(
        (pipe.ROOT / "tools/research/itzy_aura_rare_gshock_2024_candidates.json")
        .read_text(encoding="utf-8")
    )
    (tmp_path / "assets/collections").mkdir(parents=True)
    (tmp_path / "assets/collections/verified_sets.json").write_text('{"sets":[]}')
    path = tmp_path / "itzy_candidate.json"
    path.write_text(json.dumps(data))
    output = tmp_path / "output/itzy_preview"
    monkeypatch.setattr(preview, "ROOT", tmp_path)
    monkeypatch.setattr(preview, "checked_sources", lambda: (set(), set(), set(), []))
    order = [name for name, _ in pipe.GROUPS["ITZY"]["members"]]
    def fake_original(row):
        i = order.index(row["member"])
        return f"fixture {i}".encode(), Image.new("RGB", (1200, 1600), (70+i*29, 90, 140))
    monkeypatch.setattr(pipe, "original_image", fake_original)
    fingerprint = iter([0x1111111111111111 * (n + 1) for n in range(4)])
    monkeypatch.setattr(pipe, "perceptual_hash", lambda image: next(fingerprint))
    report = preview.preview(path, output, allow_incomplete=True)
    assert report["published"] is False
    assert report["previewed"] == 4
    assert report["missing"] == 1 and report["missing_members"] == ["YEJI"]
    assert report["failed"] == 0
    assert len(list(output.glob("*_DRAFT.png"))) == 4
    assert not (output / "banner_DRAFT.png").exists()
    assert (output / "contact_sheet_DRAFT.jpg").is_file()
    assert (output / "review_report.json").is_file()
    assert (output / "SOURCE_CREDITS_DRAFT.md").is_file()
    credits = (output / "SOURCE_CREDITS_DRAFT.md").read_text(encoding="utf-8")
    assert credits.count("- Photo license:") == 4
    assert "No verified original photograph" in credits
