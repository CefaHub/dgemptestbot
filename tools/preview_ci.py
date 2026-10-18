#!/usr/bin/env python3
"""Run previews for changed, unpublished research candidates only.

Never replay already-published photos: duplicate-image protection remains strict.
CI push events render only candidate manifests changed by the triggering push.
Manual dispatch can explicitly name a manifest or review all unpublished files.
"""
import argparse
import json
import os
import subprocess
from pathlib import Path

from tools.photo_candidate_previews import ROOT, prepare_candidates

RESEARCH = ROOT / "tools" / "research"
PUBLISHED = ROOT / "assets" / "collections" / "verified_sets.json"


def released_ids(path=PUBLISHED):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {entry["set_id"] for entry in data["sets"]}


def eligible_manifests(paths, published, research=RESEARCH):
    """Only explicitly marked unpublished previews in the approved directory."""
    folder = Path(research).resolve()
    chosen = []
    for value in paths:
        path = Path(value)
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if path.parent != folder or not path.name.endswith("_candidates.json"):
            continue
        if not path.is_file():
            continue
        spec = json.loads(path.read_text(encoding="utf-8"))
        if spec.get("status") != "research_preview_only_not_published":
            print(f"Skip non-preview manifest: {path.name}")
            continue
        if spec.get("set_id") in published:
            print(f"Skip previously released collection: {spec['set_id']}")
            continue
        chosen.append(path)
    return sorted(set(chosen))


def changed_in_push():
    """Use the actual push range (including pushes with several commits)."""
    before = os.getenv("GITHUB_EVENT_BEFORE", "")
    if not before or before == "0" * 40:
        raise RuntimeError("GitHub push base commit missing; not guessing changes")
    names = subprocess.check_output(
        ["git", "diff", "--name-only", before, "HEAD", "--", "tools/research"],
        cwd=ROOT, text=True,
    ).splitlines()
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", help="Explicit research candidate JSON (manual review)")
    args = parser.parse_args()
    if args.manifest:
        paths = [args.manifest]
    elif os.getenv("GITHUB_EVENT_NAME") == "push":
        paths = changed_in_push()
    else:
        paths = [str(p) for p in RESEARCH.glob("*_candidates.json")]
    candidates = eligible_manifests(paths, released_ids())
    if not candidates:
        print("No new eligible unpublished candidate manifests; no photo reprocessing.")
        return
    for index, path in enumerate(candidates, start=1):
        output = ROOT / "output" / "photo_candidate_previews" / path.stem
        report = prepare_candidates(path, output_dir=output, archive_originals=True)
        print(f"PREVIEW ONLY: {path.name}: {len(report['cards'])} source-backed candidates; "
              f"missing {len(report['members_missing'])}; stored at {output}")


if __name__ == "__main__":
    main()
