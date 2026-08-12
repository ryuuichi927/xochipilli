#!/usr/bin/env python3
"""Move works out of the repo into the data home (see app/paths.py).

Projects used to sit in `<repo>/data`, so updating or re-cloning the code put finished
work in the blast radius. This moves projects, taste and Canva tokens to
`~/Documents/Xochipilli` (or $XOCHIPILLI_DATA) and never overwrites an existing target.

    .venv/bin/python tools/migrate_data.py [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.paths import DATA, LEGACY_DATA  # noqa: E402


def _dir_summary(d: Path) -> str:
    files = [f for f in d.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    return f"{len(files)} files, {total / 1e6:.1f} MB"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if DATA.resolve() == LEGACY_DATA.resolve():
        print(f"data home is still the repo ({DATA}) — nothing to migrate")
        return 0
    if not LEGACY_DATA.is_dir():
        print(f"no legacy data at {LEGACY_DATA}")
        return 0

    print(f"from: {LEGACY_DATA}")
    print(f"to  : {DATA}")
    moves: list[tuple[Path, Path]] = []

    legacy_projects = LEGACY_DATA / "projects"
    if legacy_projects.is_dir():
        for src in sorted(legacy_projects.iterdir()):
            if not src.is_dir() or not (src / "project.json").is_file():
                continue
            moves.append((src, DATA / "projects" / src.name))

    for name in ("user", "canva_tokens.json", "canva_pkce.json"):
        src = LEGACY_DATA / name
        if src.exists():
            moves.append((src, DATA / name))

    if not moves:
        print("nothing to move")
        return 0

    done = 0
    for src, dst in moves:
        label = _dir_summary(src) if src.is_dir() else f"{src.stat().st_size / 1e6:.1f} MB"
        if dst.exists():
            print(f"skip (target exists) {src.name}  [{label}]")
            continue
        print(f"{'would move' if args.dry_run else 'move'} {src.name}  [{label}]")
        if args.dry_run:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        done += 1

    if not args.dry_run:
        print(f"moved {done} item(s)")
        left = [p for p in (LEGACY_DATA / "projects").glob("*/project.json")] if legacy_projects.is_dir() else []
        if left:
            print(f"WARNING: {len(left)} project(s) still in the repo — resolve by hand")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
