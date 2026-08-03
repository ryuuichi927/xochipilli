from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROJECTS = DATA / "projects"
THEORY = ROOT / "theory"
STATIC = ROOT / "static"

PROJECTS.mkdir(parents=True, exist_ok=True)
