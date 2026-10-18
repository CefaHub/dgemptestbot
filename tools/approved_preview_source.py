"""Pin inspected real-photo preview renders to their original-source audit metadata.

Used only after a human-readable contact sheet has been examined. We never
substitute photographs or fetch other images. A published preview bundle must
match explicit Git blob IDs in the approved release manifest.
"""
import hashlib
import json
import re
from pathlib import Path

from PIL import Image


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def verified_previews(spec, group, tier, members, root):
    """Return approved pre-rendered 900x1200 PNGs and source digests or fail closed."""
    root = Path(root).resolve()
    relative = spec["approved_preview_dir"]
    folder = (root / relative).resolve()
    if folder.parent != (root / "assets" / "previews").resolve():
        raise ValueError("Approved photo previews must be under assets/previews/SETNAME")
    if not folder.is_dir():
        raise ValueError("Approved preview directory missing")
    report_path = folder / "PREVIEW_REPORT.json"
    report_bytes = report_path.read_bytes()
    if git_blob_sha(report_bytes) != spec.get("approved_preview_report_blob"):
        raise ValueError("Approved preview report changed after visual sign-off")
    report = json.loads(report_bytes)
    if (report.get("group"), report.get("era"), report.get("rarity")) != (
        group["name"], tier["era"], tier["rarity"]
    ):
        raise ValueError("Approved preview is for a different group/rarity")
    if report.get("members_missing"):
        raise ValueError("Incomplete approved preview must never publish")
    entries = report.get("cards", [])
    if (not isinstance(entries, list) or len(entries) != len(members)
            or {r["member"] for r in entries} != set(members)):
        raise ValueError("Approved preview must contain every distinct group member")
    by_member = {r["member"]: r for r in entries}
    candidates = {r["member"]: r for r in spec["cards"]}
    hashes = spec.get("approved_preview_card_blobs")
    if not isinstance(hashes, dict) or set(hashes) != set(members):
        raise ValueError("Every preview card must have a pinned Git blob hash")

    output = {}
    for member in members:
        meta, row = by_member[member], candidates[member]
        if (meta.get("source_page") != row.get("source_page")
                or meta.get("solo_region") != row.get("solo_region")
                or meta.get("preview_pixels") != [900, 1200]):
            raise ValueError(f"Source/solo metadata changed after {member} preview approval")
        if (not re.fullmatch("[0-9a-f]{64}", str(meta.get("source_sha256", "")))
                or not re.fullmatch("[0-9a-f]{16}", str(meta.get("source_dhash", "")))):
            raise ValueError(f"Invalid cryptographic source audit for {member}")
        size = meta.get("crop_pixels", [])
        if (not isinstance(size, list) or len(size) != 2
                or min(size) < 600 or size[0] < 600 or size[1] < 800):
            raise ValueError(f"Native portrait crop insufficient for {member}")
        expected = (f"{group['slug']}_{tier['era'].lower().replace(' ', '_')}_"
                    f"{tier['rarity']}_{member.lower()}_PREVIEW.png")
        if meta.get("file") != expected:
            raise ValueError(f"Wrong filename for approved member {member}")
        photo_path = folder / expected
        raw = photo_path.read_bytes()
        if git_blob_sha(raw) != hashes[member]:
            raise ValueError(f"Approved portrait was changed or substituted: {member}")
        with Image.open(photo_path) as im:
            im.verify()
        with Image.open(photo_path) as im:
            if im.size != (900, 1200):
                raise ValueError(f"Wrong real-photocard resolution for {member}")
        output[member] = {
            "artwork": photo_path,
            "source_sha256": meta["source_sha256"],
            "source_dhash": meta["source_dhash"],
        }
    return output
