"""Never select incomplete photo sessions for the preview job."""
import json

from tools.preview_ci import eligible_manifests
from tools.photo_candidate_previews import GROUPS


def _write(directory, name, set_id, status="research_preview_only_not_published",
           complete=True):
    members = [x[0] for x in GROUPS["ITZY"]["members"]]
    active = members if complete else members[:-1]
    session = "new_itzy_photoshoot"
    payload = {
        "set_id": set_id,
        "status": status,
        "group": "ITZY",
        "photo_session_id": session,
        "missing_members": [] if complete else [members[-1]],
        "cards": [{
            "member": member, "photo_session_id": session,
            "photo_url": f"https://example.invalid/photos/{member}",
            "source_page": f"https://example.invalid/rights/{member}",
            "photographer": "QA photographer",
            "license": "CC BY 4.0",
            "license_url": "https://creativecommons.org/licenses/by/4.0/",
            "license_status": "verified",
        } for member in active]
    }
    path = directory / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_published_collection_never_reprocessed(tmp_path):
    old = _write(tmp_path, "old_candidates.json", "coll_itzy_aura_rare")
    assert eligible_manifests([old], {"coll_itzy_aura_rare"}, research=tmp_path) == []


def test_complete_unpublished_manifest_only(tmp_path):
    good = _write(tmp_path, "good_candidates.json", "coll_itzy_aura_rare")
    assert eligible_manifests([good], set(), research=tmp_path) == [good]


def test_incomplete_manifest_is_never_previewed(tmp_path):
    partial = _write(tmp_path, "partial_candidates.json", "coll_itzy_aura_rare", complete=False)
    assert eligible_manifests([partial], set(), research=tmp_path) == []


def test_other_status_and_outside_manifest_are_ignored(tmp_path):
    draft = _write(tmp_path, "draft_candidates.json", "draft", status="publish")
    wrong_name = _write(tmp_path, "not_a_candidate.json", "set")
    outside = tmp_path.parent / "outside_candidates.json"
    assert eligible_manifests([draft, wrong_name, outside], set(), research=tmp_path) == []


def test_same_manifest_deduplicated(tmp_path):
    new = _write(tmp_path, "new_candidates.json", "new")
    assert eligible_manifests([new, new], set(), research=tmp_path) == [new]


def test_missing_photo_rights_not_selected(tmp_path):
    path = _write(tmp_path, "new_candidates.json", "new")
    spec = json.loads(path.read_text())
    spec["cards"][2]["license_status"] = "pending"
    path.write_text(json.dumps(spec))
    assert eligible_manifests([path], set(), research=tmp_path) == []



def test_ci_drops_complete_but_reused_photo_pack(tmp_path):
    """Even 5/5 fails immediately if an older rarity already uses one picture."""
    from tools.preview_ci import SOURCES
    row = json.loads(SOURCES.read_text(encoding="utf-8"))["cards"][0]
    manifest = _write(tmp_path, "new_candidates.json", "coll_itzy_aura_rare")
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    spec["cards"][3]["source_page"] = row["page"]
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    assert eligible_manifests([manifest], set(), research=tmp_path) == []


def test_ci_drops_all_members_if_any_photo_resolution_is_invalid(tmp_path):
    manifest = _write(tmp_path, "new_candidates.json", "coll_itzy_aura_rare")
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    spec["cards"][1]["native_dimensions"] = [599, 1200]
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    assert eligible_manifests([manifest], set(), research=tmp_path) == []
