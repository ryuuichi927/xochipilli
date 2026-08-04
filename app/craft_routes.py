"""Craft/taste API routes. Import side-effect registers on `app`."""
from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import craft
from . import storage
from . import taste as taste_mod


class UnmatchBodyV2(BaseModel):
    reason: str = "other"
    editor_note: str = ""
    editor_keywords: list[str] = Field(default_factory=list)


class ModeBody(BaseModel):
    mode: str = "hold"  # hold | shift | motion


class RegenSubclipsBody(BaseModel):
    indices: list[int] = Field(default_factory=list)


def _provider_name() -> str:
    provider = (os.environ.get("VIDEO_PROVIDER") or "mock").lower().strip()
    if provider in {"grok", "grok-imagine", "xai-oauth", "imagine"}:
        return "xai"
    return provider


def register(app) -> None:
    """Call once from main after app = FastAPI(...)."""

    @app.get("/api/taste")
    def api_taste():
        return taste_mod.public_taste()

    @app.put("/api/projects/{pid}/segments/{sid}/mode")
    def api_seg_mode(pid: str, sid: str, body: ModeBody):
        try:
            p = storage.load_project(pid)
        except FileNotFoundError:
            raise HTTPException(404, "project not found")
        for s in p["segments"]:
            if s["id"] == sid:
                s["mode"] = taste_mod.normalize_mode(body.mode)
                if s["mode"] in ("shift", "motion"):
                    s["camera_lock"] = False
                storage.save_project(p)
                return s
        raise HTTPException(404, "segment not found")

    @app.post("/api/projects/{pid}/segments/{sid}/unmatch-v2")
    def api_unmatch_v2(pid: str, sid: str, body: UnmatchBodyV2):
        """Structured Unmatch with reason → taste.json. Prefer this over legacy /unmatch."""
        try:
            p = storage.load_project(pid)
        except FileNotFoundError:
            raise HTTPException(404, "project not found")
        for s in p["segments"]:
            if s["id"] == sid:
                return craft.handle_unmatch(
                    p,
                    s,
                    reason=body.reason,
                    editor_note=body.editor_note,
                    editor_keywords=body.editor_keywords,
                )
        raise HTTPException(404, "segment not found")

    @app.post("/api/projects/{pid}/segments/{sid}/clips/{clip_id}/regen-subclips")
    async def api_regen_subclips(
        pid: str, sid: str, clip_id: str, body: RegenSubclipsBody
    ):
        try:
            p = storage.load_project(pid)
        except FileNotFoundError:
            raise HTTPException(404, "project not found")
        seg = next((s for s in p["segments"] if s["id"] == sid), None)
        if not seg:
            raise HTTPException(404, "segment not found")
        clips = seg.get("clips") or []
        clip = next((c for c in clips if c.get("id") == clip_id), None)
        if not clip:
            raise HTTPException(404, "clip not found")
        updated = await craft.regen_subclips(
            pid=pid,
            seg=seg,
            clip=clip,
            indices=body.indices,
            world=p.get("world") or "",
            provider=_provider_name(),
            style=p.get("style") or "",
            negative_prompt=p.get("negative_prompt") or "",
        )
        for i, c in enumerate(seg.get("clips") or []):
            if c.get("id") == clip_id:
                seg["clips"][i] = updated
                if seg.get("active_clip_id") == clip_id:
                    seg["video"] = dict(updated)
                break
        storage.save_project(p)
        return {"ok": True, "clip": updated, "segment": seg}
