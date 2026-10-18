"""Prevent CI from re-rendering or republishing released photo sources."""
import json
from pathlib import Path

from tools.preview_ci import eligible_manifests


def _write(directory, name, set_id, status="research_preview_only_not_published"):
    path = directory / name
    path.write_text(json.dumps({"set_id": set_id, "status": status}), encoding="utf-8")
    return path


def test_published_photo_collection_never_reprocessed(tmp_path):
    old = _write(tmp_path, "old_candidates.json", "coll_lesserafim_aura_rare")
    assert eligible_manifests([old], {"coll_lesserafim_aura_rare"}, research=tmp_path) == []


def test_new_unpublished_manifest_is_selected(tmp_path):
    new = _write(tmp_path, "new_candidates.json", "coll_itzy_aura_rare")
    assert eligible_manifests([new], {"coll_lesserafim_aura_rare"}, research=tmp_path) == [new]


def test_other_status_and_outside_manifest_are_ignored(tmp_path):
    draft = _write(tmp_path, "draft_candidates.json", "draft", status="publish")
    wrong_name = _write(tmp_path, "not_a_candidate.json", "set")
    outside = tmp_path.parent / "outside_candidates.json"
    assert eligible_manifests([draft, wrong_name, outside], set(), research=tmp_path) == []


def test_same_manifest_deduplicated(tmp_path):
    new = _write(tmp_path, "new_candidates.json", "new")
    assert eligible_manifests([new, new], set(), research=tmp_path) == [new]
