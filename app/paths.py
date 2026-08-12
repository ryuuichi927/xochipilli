from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEORY = ROOT / "theory"
STATIC = ROOT / "static"

#: Works live outside the repo: updating, moving or re-cloning the code must never be able
#: to touch what the user made. Override with XOCHIPILLI_DATA.
DATA = Path(os.environ.get("XOCHIPILLI_DATA") or (Path.home() / "Documents" / "Xochipilli")).expanduser()
PROJECTS = DATA / "projects"

#: Cold storage for projects nobody opened in a while. iCloud Drive can evict the local
#: copy, which is the point — the disk gets its space back.
ARCHIVE = Path(
    os.environ.get("XOCHIPILLI_ARCHIVE")
    or (Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Xochipilli/Archive")
).expanduser()

#: Where projects used to live, before they moved out of the repo (see tools/migrate_data.py).
LEGACY_DATA = ROOT / "data"

PROJECTS.mkdir(parents=True, exist_ok=True)
