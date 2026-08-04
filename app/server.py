"""Uvicorn entry that registers craft/taste routes on the FastAPI app."""
from __future__ import annotations

from .main import app
from . import craft_routes

# Register mode / structured Unmatch / regen-subclips / /api/taste
craft_routes.register(app)

__all__ = ["app"]
