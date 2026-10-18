"""Protect the GitHub photo gallery against incomplete and stale collections."""
import json

import pytest

from tools.generate_gallery import ROOT, GALLERY, generate_gallery


def test_committed_gallery_matches_complete_playable_catalog():
    produced = generate_gallery()
    assert GALLERY.read_text(encoding="utf-8") == produced
    catalog = json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))
    published = json.loads(
        (ROOT / "assets/collections/verified_sets.json").read_text(encoding="utf-8")
    )["sets"]
    assert produced.count('<img src="assets/cards/') == len(catalog)
    assert produced.count('id="coll_') == len(published)
    assert all(f"]({item['image_path']})" in produced for item in catalog)
    assert "tools/research/" not in produced


def test_unpublished_preview_is_not_visible_in_gallery():
    text = generate_gallery()
    assert "itzy_aura_rare_yeji_PREVIEW" not in text
    assert 'coll_itzy_aura_rare"></a>' not in text


def _fixture_root(tmp_path, duplicate=False, missing_photo=False):
    (tmp_path / "data").mkdir()
    (tmp_path / "assets/collections").mkdir(parents=True)
    (tmp_path / "assets/cards/itzy").mkdir(parents=True)
    (tmp_path / "assets/banners/itzy").mkdir(parents=True)
    cards = []
    for n, idol in enumerate(("YEJI", "LIA"), 1):
        photo = f"assets/cards/itzy/itzy_preview_{idol.lower()}.png"
        if not (missing_photo and n == 2):
            (tmp_path / photo).write_bytes(b"test-photo")
        cards.append(dict(
            id=f"card_{n}", idol=idol, group="ITZY", era="AURA",
            rarity="rare", set_id="coll_itzy_aura_rare",
            card_number=n, image_path=cards[0]["image_path"] if duplicate and n == 2 else photo,
        ))
    (tmp_path / "assets/banners/itzy/aura.png").write_bytes(b"test-banner")
    manifest = {"sets": [dict(
        set_id="coll_itzy_aura_rare", expected_members=["YEJI", "LIA"],
        group="ITZY", era="AURA", rarity="rare",
        banner_path="assets/banners/itzy/aura.png",
        source_collection="Test photo session",
    )]}
    (tmp_path / "data/catalog.json").write_text(json.dumps(cards), encoding="utf-8")
    (tmp_path / "assets/collections/verified_sets.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return tmp_path


def test_duplicate_file_path_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="Duplicate card image paths"):
        generate_gallery(_fixture_root(tmp_path, duplicate=True))


def test_missing_artwork_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="Published photo not found"):
        generate_gallery(_fixture_root(tmp_path, missing_photo=True))


def test_incomplete_set_fails_closed(tmp_path):
    root = _fixture_root(tmp_path)
    path = root / "data/catalog.json"
    cards = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(cards[:1]), encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete published set"):
        generate_gallery(root)
