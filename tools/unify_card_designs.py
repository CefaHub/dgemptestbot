#!/usr/bin/env python3
"""Replace inconsistent baked card UI on ALL released real-photo card PNGs.

This is a one-time, fully-audited artwork update. No card IDs, game economy,
photos, origins, rarity, lineup or source catalog is changed. Original assets
remain retrievable from Git history. Existing faces/central portrait pixels
stay byte-for-byte identical. A second run is a no-op, not a second overlay.
"""
import hashlib
import json
import tempfile
from pathlib import Path

from PIL import Image

try:
    from .card_master_template import CARD_SIZE, PORTRAIT_REGION, render_master
except ImportError:
    from card_master_template import CARD_SIZE, PORTRAIT_REGION, render_master

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "assets/collections/card_design_v1.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalize(root=ROOT):
    root = Path(root)
    items = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    sets = json.loads(
        (root / "assets/collections/verified_sets.json").read_text(encoding="utf-8")
    )["sets"]
    assert items == json.loads(
        (root / "dolce_empire/_catalog.json").read_text(encoding="utf-8")
    ), "Catalog mirror mismatch"
    assert len({item["id"] for item in items}) == len(items)
    assert len({item["image_path"] for item in items}) == len(items)
    assert len({s["set_id"] for s in sets}) == len(sets)
    assert sum(len(s["expected_members"]) for s in sets) == len(items)
    if (root / "assets/collections/card_design_v1.json").exists():
        manifest = json.loads(
            (root / "assets/collections/card_design_v1.json").read_text(encoding="utf-8")
        )
        expected = manifest["images"]
        assert len(expected) == len(items), "New cards require regular master renderer"
        for card in items:
            name = card["image_path"]
            assert name in expected
            assert sha((root / name).read_bytes()) == expected[name]["after_sha256"], (
                "An already unified card was changed: " + name
            )
        print(f"Already standardized: {len(items)} cards; skipped without changes")
        return 0

    # Stage the whole catalogue before replacing anything. Atomic at Git level
    # (all files go into one commit); failures do not result in half a set.
    results = {}
    with tempfile.TemporaryDirectory(prefix="dolce-card-template-") as temp:
        temporary = Path(temp)
        for card in items:
            name = card["image_path"]
            filepath = root / name
            original = filepath.read_bytes()
            with Image.open(filepath) as im:
                im.load()
                assert im.size == CARD_SIZE and im.format == "PNG", name
                new_image = render_master(
                    im, name=card["idol"], group=card["group"],
                    era=card["era"], rarity=card["rarity"],
                    number=card["card_number"], total=card["card_total"],
                    legacy=True
                )
                assert new_image.size == CARD_SIZE
                assert new_image.crop(PORTRAIT_REGION).tobytes() == (
                    im.convert("RGB").crop(PORTRAIT_REGION).tobytes()
                ), "Portrait pixels modified: " + name
                target = temporary / name
                target.parent.mkdir(parents=True, exist_ok=True)
                new_image.save(target, "PNG", optimize=True)
            updated = target.read_bytes()
            assert sha(updated) != sha(original), "Artwork unexpectedly unchanged"
            results[name] = dict(
                before_sha256=sha(original),
                after_sha256=sha(updated),
                id=card["id"], group=card["group"], era=card["era"],
                rarity=card["rarity"], member=card["idol"],
            )
        assert len(results) == len(items)
        for name in results:
            (root / name).write_bytes((temporary / name).read_bytes())

    record = {
        "schema": "dolce_master_card_design_v1",
        "template": "tools/card_master_template.py",
        "original_assets": "available through the parent git revision",
        "member_count": len(items),
        "set_count": len(sets),
        "central_portrait_unchanged_pixels": list(PORTRAIT_REGION),
        "images": results,
    }
    path = root / "assets/collections/card_design_v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"Standardized {len(items)} existing real-photo cards / {len(sets)} entire sets")
    return len(items)


if __name__ == "__main__":
    normalize()
