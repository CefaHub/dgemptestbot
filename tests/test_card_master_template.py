"""Every photo-card collection uses the same coordinate-locked master UI."""
from pathlib import Path

import pytest
from PIL import Image

from tools.card_master_template import CARD_SIZE, PORTRAIT_REGION, ACCENTS, render_master
from tools.unify_card_designs import normalize


@pytest.mark.parametrize("rarity", ["rare", "epic", "legendary", "mythic"])
def test_unified_template_preserves_original_real_portrait(rarity):
    # An artificial test RGB field is NOT a published card or portrait.
    image = Image.new("RGB", CARD_SIZE, (32, 91, 180))
    before = image.crop(PORTRAIT_REGION).tobytes()
    new = render_master(
        image, name="MEMBER", group="TEST", era="AURA",
        rarity=rarity, number=1, total=5, legacy=True
    )
    assert new.size == CARD_SIZE
    assert new.crop(PORTRAIT_REGION).tobytes() == before
    assert new.getpixel((12, 600)) == (8, 12, 32)
    assert new.getpixel((24, 600)) == tuple(bytes.fromhex(ACCENTS[rarity][1:]))


def test_same_collection_has_identical_frame_and_label_geometry():
    photo_a = Image.new("RGB", CARD_SIZE, (180, 70, 22))
    photo_b = Image.new("RGB", CARD_SIZE, (0, 100, 230))
    first = render_master(
        photo_a, name="GISELLE", group="aespa", era="AURA",
        rarity="rare", number=3, total=4, legacy=True
    )
    other = render_master(
        photo_b, name="NINGNING", group="aespa", era="AURA",
        rarity="rare", number=4, total=4, legacy=True
    )
    for p in ((12, 500), (24, 500), (42, 500), (65, 80), (639, 80),
              (24, 820), (24, 1120), (12, 1120)):
        assert first.getpixel(p) == other.getpixel(p)


def test_released_artwork_is_not_a_second_time_reframed():
    record = Path(__file__).resolve().parents[1] / "assets/collections/card_design_v1.json"
    if not record.exists():
        pytest.skip("Full catalogue normalization only runs on release workflow")
    import json
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(record.read_text(encoding="utf-8"))
    cards = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    assert manifest["member_count"] == len(cards)
    assert manifest["set_count"] > 0
    assert len(manifest["images"]) == len(cards)
    assert normalize(root) == 0
