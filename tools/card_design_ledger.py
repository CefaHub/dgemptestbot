"""Append verified new-release cards to the immutable master-design audit ledger.

Historical re-framed PNGs are hash-locked. Future real-photo card releases
are created directly with card_master_template.render_master(), and can only be
added after checking that they have the same coordinates and dimensions.
"""
import hashlib
import json
from pathlib import Path

from PIL import Image

from .card_master_template import ACCENTS, CARD_SIZE, MARGIN


def extend_record(root):
    root = Path(root)
    p = root / "assets/collections/card_design_v1.json"
    if not p.is_file():
        # Lightweight package fixtures can publish to a scratch sandbox
        # without the historical image-ledger. Production repo has this file.
        return 0
    record = json.loads(p.read_text(encoding="utf-8"))
    cards = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    sets = json.loads(
        (root / "assets/collections/verified_sets.json").read_text(encoding="utf-8")
    )["sets"]
    if record.get("schema") != "dolce_master_card_design_v1":
        raise ValueError("Unknown master design record schema")
    old_images = record["images"]
    paths = {card["image_path"] for card in cards}
    if not set(old_images) <= paths:
        raise ValueError("An audited card vanished from the catalog")
    for path, details in old_images.items():
        current = hashlib.sha256((root / path).read_bytes()).hexdigest()
        if current != details["after_sha256"]:
            raise ValueError("An already-verified card was modified: " + path)
    additions = 0
    for card in cards:
        path = card["image_path"]
        if path in old_images:
            continue
        file = root / path
        if not file.is_file():
            raise ValueError("No artwork for newly released card: " + path)
        with Image.open(file) as photo:
            if photo.size != CARD_SIZE or photo.format != "PNG":
                raise ValueError("New card must be a complete 900x1200 PNG: " + path)
            photo = photo.convert("RGB")
            accent = tuple(bytes.fromhex(ACCENTS[card["rarity"]][1:]))
            if photo.getpixel((12, 600)) != MARGIN or photo.getpixel((24, 600)) != accent:
                raise ValueError("New card does not use the universal frame: " + path)
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        old_images[path] = {
            "before_sha256": None,
            "after_sha256": digest,
            "id": card["id"], "group": card["group"],
            "era": card["era"], "rarity": card["rarity"],
            "member": card["idol"],
            "template_native": True,
        }
        additions += 1
    if len(old_images) != len(cards):
        raise ValueError("Template ledger doesn't cover the published catalog")
    record["member_count"] = len(cards)
    record["set_count"] = len(sets)
    if additions:
        p.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
    return additions
