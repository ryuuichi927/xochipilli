"""Uvicorn entry that registers craft/taste routes on the FastAPI app."""
from __future__ import annotations

import os
import threading

from .main import app
from . import archive
from . import craft_routes

# Register mode / structured Unmatch / regen-subclips / /api/taste
craft_routes.register(app)

#: Give the UI time to open its last project first — that bumps opened_at, so the project
#: Ryuichi is looking at right now is never mistaken for cold.
_ARCHIVE_DELAY_SEC = float(os.environ.get("XOCHIPILLI_ARCHIVE_DELAY", "90"))


@app.on_event("startup")
def _schedule_archive_sweep() -> None:
    if os.environ.get("XOCHIPILLI_NO_ARCHIVE"):
        return

    def sweep() -> None:
        archive.run_once()

    timer = threading.Timer(_ARCHIVE_DELAY_SEC, sweep)
    timer.daemon = True  # a pending sweep must never hold up shutdown
    timer.start()


__all__ = ["app"]
