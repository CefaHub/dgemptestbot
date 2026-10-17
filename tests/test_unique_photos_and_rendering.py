"""Never issue the same idol photograph as a new rarity or hide missing artwork."""
import copy
import json
from pathlib import Path

import pytest

from dolce_empire.catalog import all_cards
from dolce_empire import set_validation, art


@pytest.fixture
def source_patch(monkeypatch, tmp_path):
    original = json.loads(set_validation.SOURCES_FILE.read_text(encoding="utf-8"))
    def apply(source):
        path = tmp_path / "source_list.json"
        path.write_text(json.dumps(source), encoding="utf-8")
        monkeypatch.setattr(set_validation, "SOURCES_FILE", path)
    return original, apply


def test_real_unique_source_photographs_in_live_catalog():
    assert set_validation.validate_photo_sets(all_cards()) == len(all_cards())
    sources = json.loads(set_validation.SOURCES_FILE.read_text(encoding="utf-8"))["cards"]
    assert len({s["photo"] for s in sources}) == len(sources)
    assert len({s["page"] for s in sources}) == len(sources)
    assert "epic" in {c["rarity"] for c in all_cards()}
    assert sum(c["group"] == "ILLIT" and c["era"] == "SPOTLIGHT" for c in all_cards()) == 5


def test_same_original_photo_url_with_new_file_page_is_rejected(source_patch):
    sources, apply = source_patch
    altered = copy.deepcopy(sources)
    altered["cards"][1]["photo"] = altered["cards"][0]["photo"]
    apply(altered)
    with pytest.raises(ValueError, match="Reused source photograph"):
        set_validation.validate_photo_sets(all_cards())


def test_duplicate_original_file_hash_is_rejected_even_with_different_urls(source_patch):
    sources, apply = source_patch
    altered = copy.deepcopy(sources)
    altered["cards"][0]["source_sha256"] = "a" * 64
    altered["cards"][1]["source_sha256"] = "a" * 64
    apply(altered)
    with pytest.raises(ValueError, match="Reused photo binary"):
        set_validation.validate_photo_sets(all_cards())


def test_missing_real_photo_must_not_generate_a_placeholder(monkeypatch, tmp_path):
    art.render_card.cache_clear()
    monkeypatch.setattr(art, "ROOT", tmp_path)
    card_id = all_cards()[0]["id"]
    with pytest.raises(FileNotFoundError, match="Real-photo card missing"):
        art.render_card(card_id)
    art.render_card.cache_clear()


def test_old_bulk_rarity_generator_removed_and_no_readme():
    root = Path(__file__).resolve().parents[1]
    for file in (
        "README.md",
        "tools/build_bulk_wave_2.py",
        "tools/bulk_wave_2.json",
        "assets/collections/bulk_wave_2.json",
        ".github/workflows/bulk-wave-2.yml",
    ):
        assert not (root / file).exists(), file
