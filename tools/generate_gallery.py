#!/usr/bin/env python3
"""Generate the human-browsable GitHub gallery from released real-photo cards.

Never include research previews: only fully verified published collections.
Use --check in CI so a new release cannot silently leave this page stale.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "GALLERY.md"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def generate_gallery(root=ROOT):
    root = Path(root)
    cards = read_json(root / "data/catalog.json")
    manifest = read_json(root / "assets/collections/verified_sets.json")
    releases = manifest["sets"]
    if not releases:
        raise ValueError("Published collections list is empty")
    if len({c["id"] for c in cards}) != len(cards):
        raise ValueError("Duplicate card IDs in playable catalog")
    if len({c["image_path"] for c in cards}) != len(cards):
        raise ValueError("Duplicate card image paths")
    if len({s["set_id"] for s in releases}) != len(releases):
        raise ValueError("Duplicate published collection ID")

    lines = [
        "# DOLCE EMPIRE — галерея настоящих фотокарточек",
        "",
        "> Автоматически создано из **опубликованного** каталога игры. Исследовательские превью и незавершённые наборы сюда не попадают.",
        "",
        f"**Опубликовано: {len(cards)} карточек в {len(releases)} полных коллекциях.**",
        "",
        "Нажми на фотографию, чтобы открыть оригинальный PNG 900×1200. Баннеры каждого сета — 1600×900.",
        "",
        "## Быстрые ссылки",
        "",
    ]
    for section in releases:
        slug = section["set_id"]
        lines.append(
            f'- [{section["group"]} — {section["era"]} / {section["rarity"].upper()}](#{slug})'
        )
    lines.append("")

    used_ids = set()
    for section in releases:
        set_id = section["set_id"]
        items = sorted(
            (c for c in cards if c["set_id"] == set_id),
            key=lambda c: c["card_number"],
        )
        expected = section["expected_members"]
        if len(items) != len(expected):
            raise ValueError(f"Incomplete published set: {set_id}")
        if [c["idol"].upper() for c in items] != expected:
            raise ValueError(f"Wrong member order in {set_id}")
        if [c["card_number"] for c in items] != list(range(1, len(items) + 1)):
            raise ValueError(f"Wrong card numbering in {set_id}")
        if any(c["rarity"] != section["rarity"] or c["era"] != section["era"]
               or c["group"] != section["group"] for c in items):
            raise ValueError(f"Mixed metadata in {set_id}")
        if any(c["id"] in used_ids for c in items):
            raise ValueError(f"Card reused across collections: {set_id}")
        used_ids.update(c["id"] for c in items)

        banner = section["banner_path"]
        if not banner.startswith("assets/banners/") or not (root / banner).is_file():
            raise ValueError(f"Published banner missing: {banner}")
        lines.extend([
            f"## {section['group']} — {section['era']} · {section['rarity'].upper()}",
            "",
            f"<a id=\"{set_id}\"></a>",
            "",
            f"**{len(items)}/{len(expected)} участниц** · [Открыть баннер]({banner})",
            "",
            "| " + " | ".join([str(i+1) for i in range(len(items))]) + " |",
            "| " + " | ".join([":---:" for _ in items]) + " |",
        ])
        previews = []
        names = []
        for c in items:
            path = c["image_path"]
            if not path.startswith("assets/cards/") or not path.endswith(".png"):
                raise ValueError(f"Untrusted published card path: {path}")
            if not (root / path).is_file():
                raise ValueError(f"Published photo not found: {path}")
            # No generated/third-party image URLs: all thumbnails use committed PNGs.
            previews.append(
                f'[<img src="{path}" width="175" alt="{c["idol"]} {c["group"]} {c["rarity"]}">]({path})'
            )
            names.append(f'**{c["idol"]}**')
        lines.append("| " + " | ".join(previews) + " |")
        lines.append("| " + " | ".join(names) + " |")
        lines.extend(["", f"*Фотосерия: {section['source_collection']}.*", ""])

    if used_ids != {c["id"] for c in cards}:
        raise ValueError("The published catalog contains cards outside verified sets")
    lines.extend([
        "---",
        "",
        "Все фото принадлежат соответствующим авторам. Условия и ссылки на оригиналы:",
        "[Photo Credits](assets/PHOTO_CREDITS.md),",
        "[Bulk Credits](assets/PHOTO_CREDITS_BULK.md),",
        "[New Release Credits](assets/PHOTO_CREDITS_NEW_RELEASES.md).",
        "Лицензия исходного фото не означает, что участницы рекламируют проект.",
        "",
        "Галерея генерируется командой `python tools/generate_gallery.py`; проверяется через `--check` и CI.",
        "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Fail if committed gallery differs from published card catalog")
    args = parser.parse_args(argv)
    content = generate_gallery()
    if args.check:
        if not GALLERY.exists() or GALLERY.read_text(encoding="utf-8") != content:
            parser.exit(1, "GALLERY.md outdated: run python tools/generate_gallery.py\n")
        print("Published gallery is up to date")
    else:
        GALLERY.write_text(content, encoding="utf-8")
        print(f"Generated {GALLERY} from released photos")


if __name__ == "__main__":
    main()
