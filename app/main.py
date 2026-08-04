from __future__ import annotations

import math
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .video_gen import (
    clip_unit_seconds,
    concat_video_files,
    extract_audio_segment,
    extract_last_frame,
    generate_clip,
    probe_duration,
    xai_chain_mode,
    xai_max_single_seconds,
    xfade_seconds,
)
from .digest import digest_audio, segment_features
from .emotion import emotion_keywords
from .mapping import build_constraints, compose_video_prompt
from .paths import ROOT, STATIC
from . import storage
from . import craft
from . import taste as taste_mod
from .program_export import build_program_mp4

# Load project .env (FAL_KEY, VIDEO_PROVIDER, …). Does not override already-set env.
load_dotenv(ROOT / ".env", override=False)

app = FastAPI(title="Xochipilli", version="0.1.0-d1")

# Desktop shell uses pywebview load_html → document origin is often "null" / about:blank
# while API is http://127.0.0.1:PORT. Without CORS, fetch() fails silently in WK and
# the UI never lists projects (e.g. Bonji Story) or completes import.
# Local-only tool: open to any Origin including null.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Prevent double-submit races (same segment generate twice)
_GEN_LOCKS: set[str] = set()


class WorldBody(BaseModel):
    world: Optional[str] = None
    title: Optional[str] = None
    lyrics: Optional[str] = None
    bar_mode: Optional[str] = None
    style: Optional[str] = None
    negative_prompt: Optional[str] = None
    apply_taste: Optional[bool] = None


class ProjectRestoreBody(BaseModel):
    """Full editable snapshot restore for client undo/redo."""
    segments: list[Any] = Field(default_factory=list)
    open_pin: Optional[float] = None
    world: str = ""
    style: str = ""
    negative_prompt: str = ""
    apply_taste: Optional[bool] = None
    lyrics: Optional[str] = None
    bar_mode: Optional[str] = None
    program: Optional[dict[str, Any]] = None


class PinBody(BaseModel):
    t: float


class SegmentPromptBody(BaseModel):
    prompt: str = ""


class CameraLockBody(BaseModel):
    camera_lock: bool = False


class SegmentTimesBody(BaseModel):
    t0: float
    t1: float


class UnmatchBody(BaseModel):
    editor_note: str = ""
    editor_keywords: list[str] = Field(default_factory=list)


def _proj(pid: str, *, with_series: bool = False) -> dict[str, Any]:
    try:
        return storage.load_project(pid, with_series=with_series)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")


def _normalize_resolution(raw: str | None) -> str:
    r = (raw or "720p").strip().lower()
    if r in {"480", "480p"}:
        return "480p"
    if r in {"720", "720p"}:
        return "720p"
    if r in {"1080", "1080p", "fhd", "fullhd"}:
        return "1080p"
    return "720p"


def _provider_name() -> str:
    provider = (os.environ.get("VIDEO_PROVIDER") or "mock").lower().strip()
    if provider in {"grok", "grok-imagine", "xai-oauth", "imagine"}:
        return "xai"
    return provider


@app.get("/api/health")
def health():
    provider = _provider_name()
    fal_set = bool(os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY"))
    fal_flag_key = "fal_" + "key_configured"
    xai_res = _normalize_resolution(os.environ.get("XAI_VIDEO_RESOLUTION"))
    xai_aspect = (os.environ.get("XAI_VIDEO_ASPECT") or "16:9").strip()
    xai_model = os.environ.get("XAI_VIDEO_MODEL", "grok-imagine-video")
    xai_model_i2v = (
        os.environ.get("XAI_VIDEO_I2V_MODEL")
        or os.environ.get("XAI_VIDEO_MODEL_I2V")
        or "grok-imagine-video-1.5"
    )
    unit = clip_unit_seconds()
    out: dict[str, Any] = {
        "ok": True,
        "stage": "D1",
        "product": "Xochipilli",
        "root": str(ROOT),
        "video_provider": provider,
        fal_flag_key: fal_set if provider == "fal" else None,
        "fal_model": os.environ.get("FAL_VIDEO_MODEL") if provider == "fal" else None,
        "xai_model": xai_model if provider == "xai" else None,
        "xai_model_i2v": xai_model_i2v if provider == "xai" else None,
        "xai_resolution": xai_res if provider == "xai" else None,
        "xai_aspect": xai_aspect if provider == "xai" else None,
        "xai_resolution_choices": ["480p", "720p", "1080p"],
        "clip_unit_seconds": unit,
        "xai_chain_mode": xai_chain_mode() if provider == "xai" else None,
        "xfade_seconds": xfade_seconds(),
    }
    if provider == "xai":
        out["video_model"] = out["xai_model"]
        out["video_resolution"] = xai_res
        try:
            from .xai_auth import credentials_status

            out["xai_auth"] = credentials_status()
        except Exception as e:
            out["xai_auth"] = {"ok": False, "error": str(e)}
    elif provider == "fal":
        out["video_model"] = out["fal_model"] or "fal"
    else:
        out["video_model"] = "mock"
    try:
        from . import canva as canva_mod

        out["canva"] = canva_mod.status()
    except Exception as e:
        out["canva"] = {"ok": False, "error": str(e)}
    return out


@app.get("/api/projects")
def api_list_projects():
    return {"projects": storage.list_projects()}


@app.post("/api/projects")
def api_create_project(title: str = Form("Untitled")):
    return storage.new_project(title=title or "Untitled")


@app.get("/api/projects/{pid}")
def api_get_project(pid: str):
    return storage.public_project(_proj(pid))


@app.patch("/api/projects/{pid}")
def api_patch_project(pid: str, body: WorldBody):
    p = _proj(pid)
    if body.world is not None:
        p["world"] = body.world
    if body.title is not None:
        title = str(body.title).strip()
        if not title:
            raise HTTPException(400, "title empty")
        if len(title) > 200:
            raise HTTPException(400, "title too long")
        p["title"] = title
    if body.lyrics is not None:
        p["lyrics"] = body.lyrics
    if body.bar_mode is not None:
        if body.bar_mode not in ("waveform", "lyrics", "both"):
            raise HTTPException(400, "bar_mode must be waveform|lyrics|both")
        p["bar_mode"] = body.bar_mode
    if body.style is not None:
        p["style"] = str(body.style)[:4000]
    if body.negative_prompt is not None:
        p["negative_prompt"] = str(body.negative_prompt)[:4000]
    if body.apply_taste is not None:
        p["apply_taste"] = bool(body.apply_taste)
    return storage.public_project(storage.save_project(p))


@app.delete("/api/projects/{pid}")
def api_delete_project(pid: str):
    safe = Path(str(pid)).name
    if safe != pid or ".." in pid or "/" in pid or "\\" in pid:
        raise HTTPException(400, "invalid project id")
    try:
        storage.load_project(pid)
    except FileNotFoundError:
        raise HTTPException(404, "project not found")
    storage.delete_project(pid)
    return {"ok": True, "deleted": pid}


@app.post("/api/projects/{pid}/reveal")
def api_reveal_project(pid: str):
    import subprocess
    import sys

    safe = Path(str(pid)).name
    if safe != pid or ".." in pid or "/" in pid or "\\" in pid:
        raise HTTPException(400, "invalid project path")
    d = storage.project_dir(safe)
    try:
        d.resolve().relative_to(storage.PROJECTS.resolve())
    except ValueError:
        raise HTTPException(400, "invalid project path")
    if not d.is_dir():
        raise HTTPException(404, "project folder not found")
    try:
        if sys.platform == "darwin":
            subprocess.run(["/usr/bin/open", str(d)], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(d)], check=False)
        elif sys.platform == "win32":
            subprocess.run(["explorer", str(d)], check=False)
        else:
            raise HTTPException(500, f"unsupported platform {sys.platform}")
    except Exception as e:
        raise HTTPException(500, f"reveal failed: {e}") from e
    return {"ok": True, "path": str(d)}


@app.put("/api/projects/{pid}/restore")
def api_restore_project(pid: str, body: ProjectRestoreBody):
    p = _proj(pid)
    segs = body.segments if isinstance(body.segments, list) else []
    clean = []
    for s in segs:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        clean.append(s)
    p["segments"] = clean
    p["open_pin"] = body.open_pin
    p["world"] = body.world or ""
    p["style"] = body.style or ""
    p["negative_prompt"] = body.negative_prompt or ""
    if body.apply_taste is not None:
        p["apply_taste"] = bool(body.apply_taste)
    if body.lyrics is not None:
        p["lyrics"] = body.lyrics
    if body.bar_mode is not None:
        if body.bar_mode in ("waveform", "lyrics", "both"):
            p["bar_mode"] = body.bar_mode
    p["program"] = body.program
    return storage.public_project(storage.save_project(p))


@app.post("/api/projects/{pid}/import")
async def api_import(pid: str, file: UploadFile = File(...)):
    p = _proj(pid)
    pdir = storage.project_dir(pid)
    pdir.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    if suffix.lower() == ".aiff":
        suffix = ".aiff"
    raw_path = pdir / f"source{suffix}"
    with raw_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    for old in pdir.glob("source*"):
        if old.is_file() and old.resolve() != raw_path.resolve():
            try:
                old.unlink()
            except OSError:
                pass

    storage.clear_project_media(pid)
    p["program"] = None

    digest = digest_audio(raw_path, pdir)
    stem = Path(file.filename or "track").stem.strip() or "track"
    if not p.get("title") or str(p.get("title")).strip() in {"", "Untitled"}:
        p["title"] = stem
    p["source_audio"] = raw_path.name
    storage.write_digest_file(pid, digest)
    p["digest"] = {
        "theory_id": digest["theory_id"],
        "global": digest["global"],
        "waveform_peaks": digest["waveform_peaks"],
        "analysis_wav": digest["analysis_wav"],
        "series_file": "digest.json",
    }
    p["segments"] = []
    p["open_pin"] = None
    storage.save_project(p)
    return storage.public_project(p)


@app.get("/api/projects/{pid}/audio")
def api_audio(pid: str):
    p = _proj(pid)
    name = p.get("source_audio")
    if not name:
        raise HTTPException(404, "no audio")
    path = storage.project_dir(pid) / name
    if not path.exists():
        aw = storage.project_dir(pid) / "analysis.wav"
        if aw.exists():
            return FileResponse(aw, media_type="audio/wav")
        raise HTTPException(404, "audio missing")
    return FileResponse(path)


@app.post("/api/projects/{pid}/pin")
def api_pin(pid: str, body: PinBody):
    p = _proj(pid, with_series=True)
    if not p.get("digest"):
        raise HTTPException(400, "import audio first")
    t = float(body.t)
    dur = float((p["digest"].get("global") or {}).get("duration_sec") or 0)
    t = max(0.0, min(t, dur if dur > 0 else t))

    if p.get("open_pin") is None:
        p["open_pin"] = round(t, 3)
        storage.save_project(p)
        return {
            "status": "opened",
            "open_pin": p["open_pin"],
            "project": storage.public_project(p),
        }

    t0 = float(p["open_pin"])
    t1 = t
    if abs(t1 - t0) < 0.05:
        raise HTTPException(400, "segment too short")
    if t1 < t0:
        t0, t1 = t1, t0

    feat = segment_features(p["digest"], t0, t1)
    kws = emotion_keywords(feat)
    constraints = build_constraints(feat)
    seg_id = uuid.uuid4().hex[:10]
    seg = {
        "id": seg_id,
        "t0": round(t0, 3),
        "t1": round(t1, 3),
        "features": feat,
        "emotion_keywords": kws,
        "constraints": constraints,
        "prompt": "",
        "video": None,
        "unmatched": False,
    }
    craft.enrich_new_segment(seg)
    p["segments"].append(seg)
    p["open_pin"] = None
    storage.save_project(p)
    return {
        "status": "closed",
        "segment": seg,
        "project": storage.public_project(p),
    }


@app.post("/api/projects/{pid}/pin/cancel")
def api_pin_cancel(pid: str):
    p = _proj(pid)
    p["open_pin"] = None
    return storage.public_project(storage.save_project(p))


@app.put("/api/projects/{pid}/segments/{sid}/prompt")
def api_seg_prompt(pid: str, sid: str, body: SegmentPromptBody):
    p = _proj(pid)
    for s in p["segments"]:
        if s["id"] == sid:
            s["prompt"] = body.prompt
            storage.save_project(p)
            return s
    raise HTTPException(404, "segment not found")


@app.put("/api/projects/{pid}/segments/{sid}/camera-lock")
def api_seg_camera_lock(pid: str, sid: str, body: CameraLockBody):
    p = _proj(pid)
    for s in p["segments"]:
        if s["id"] == sid:
            s["camera_lock"] = bool(body.camera_lock)
            storage.save_project(p)
            return s
    raise HTTPException(404, "segment not found")


@app.post("/api/projects/{pid}/segments/{sid}/ref-image")
async def api_seg_ref_image(pid: str, sid: str, file: UploadFile = File(...)):
    p = _proj(pid)
    seg = next((s for s in p["segments"] if s["id"] == sid), None)
    if not seg:
        raise HTTPException(404, "segment not found")
    raw_name = file.filename or "ref.jpg"
    ext = Path(raw_name).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        ct = (file.content_type or "").lower()
        if "png" in ct:
            ext = ".png"
        elif "webp" in ct:
            ext = ".webp"
        elif "gif" in ct:
            ext = ".gif"
        else:
            ext = ".jpg"
    data = await file.read()
    if len(data) < 32:
        raise HTTPException(400, "empty image")
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "image too large (max 20MB)")
    refs = storage.project_dir(pid) / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    old = seg.get("ref_image")
    if old:
        prev = refs / Path(str(old)).name
        if prev.is_file():
            try:
                prev.unlink()
            except OSError:
                pass
    fname = f"{sid}-ref{ext}"
    path = refs / fname
    path.write_bytes(data)
    seg["ref_image"] = fname
    storage.save_project(p)
    return {"segment": seg, "ref_image": fname}


@app.delete("/api/projects/{pid}/segments/{sid}/ref-image")
def api_seg_ref_image_delete(pid: str, sid: str):
    p = _proj(pid)
    seg = next((s for s in p["segments"] if s["id"] == sid), None)
    if not seg:
        raise HTTPException(404, "segment not found")
    refs = storage.project_dir(pid) / "refs"
    old = seg.get("ref_image")
    if old:
        prev = refs / Path(str(old)).name
        if prev.is_file():
            try:
                prev.unlink()
            except OSError:
                pass
    seg["ref_image"] = None
    storage.save_project(p)
    return {"segment": seg}


@app.get("/api/projects/{pid}/refs/{name}")
def api_ref_file(pid: str, name: str):
    safe = Path(name).name
    path = storage.project_dir(pid) / "refs" / safe
    if not path.exists():
        raise HTTPException(404, "ref not found")
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media)


@app.put("/api/projects/{pid}/segments/{sid}/times")
def api_seg_times(pid: str, sid: str, body: SegmentTimesBody):
    p = _proj(pid, with_series=True)
    dig = p.get("digest") or {}
    dur = float((dig.get("global") or {}).get("duration_sec") or 0)
    t0 = float(body.t0)
    t1 = float(body.t1)
    if t1 < t0:
        t0, t1 = t1, t0
    if t1 - t0 < 0.08:
        t1 = t0 + 0.08
    if dur > 0:
        t0 = max(0.0, min(t0, dur - 0.08))
        t1 = max(t0 + 0.08, min(t1, dur))
    for s in p["segments"]:
        if s["id"] == sid:
            s["t0"] = round(t0, 4)
            s["t1"] = round(t1, 4)
            try:
                feat = (
                    segment_features(dig, s["t0"], s["t1"])
                    if dig
                    else {"duration_sec": s["t1"] - s["t0"], "t0": s["t0"], "t1": s["t1"]}
                )
            except Exception:
                feat = {
                    "duration_sec": round(s["t1"] - s["t0"], 3),
                    "t0": s["t0"],
                    "t1": s["t1"],
                }
            s["features"] = feat
            s["constraints"] = build_constraints(feat)
            s["emotion_keywords"] = emotion_keywords(feat)
            storage.save_project(p)
            return s
    raise HTTPException(404, "segment not found")


@app.post("/api/projects/{pid}/segments/{sid}/unmatch")
def api_unmatch(pid: str, sid: str, body: UnmatchBody):
    p = _proj(pid)
    for s in p["segments"]:
        if s["id"] == sid:
            entry = {
                "at": storage._now(),
                "segment_id": sid,
                "t0": s["t0"],
                "t1": s["t1"],
                "ai_keywords": list(s.get("emotion_keywords") or []),
                "editor_note": body.editor_note,
                "editor_keywords": body.editor_keywords,
                "features": s.get("features"),
            }
            p.setdefault("unmatch_log", []).append(entry)
            s["unmatched"] = True
            storage.save_project(p)
            return {"ok": True, "entry": entry}
    raise HTTPException(404, "segment not found")


@app.post("/api/projects/{pid}/segments/{sid}/generate")
async def api_generate(pid: str, sid: str):
    lock_key = f"{pid}:{sid}"
    if lock_key in _GEN_LOCKS:
        raise HTTPException(409, "この区間はすでに生成中です（二重送信をブロック）")
    _GEN_LOCKS.add(lock_key)
    try:
        return await _api_generate_inner(pid, sid)
    finally:
        _GEN_LOCKS.discard(lock_key)


async def _api_generate_inner(pid: str, sid: str):
    p = _proj(pid)
    seg = next((s for s in p["segments"] if s["id"] == sid), None)
    if not seg:
        raise HTTPException(404, "segment not found")
    if not (seg.get("prompt") or "").strip():
        raise HTTPException(400, "prompt required")

    feat = seg.get("features") or {}
    if not feat.get("duration_sec"):
        feat = {**feat, "duration_sec": float(seg["t1"]) - float(seg["t0"])}

    pdir = storage.project_dir(pid)
    clips_dir = pdir / "clips"
    refs_dir = pdir / "refs"
    clips_dir.mkdir(exist_ok=True)
    refs_dir.mkdir(exist_ok=True)

    start_image: Path | None = None
    chain = False
    user_ref = False
    ref_name = seg.get("ref_image")
    if ref_name:
        cand = refs_dir / Path(str(ref_name)).name
        if cand.is_file() and cand.stat().st_size > 32:
            start_image = cand
            user_ref = True

    prev = None
    if not start_image:
        segs_sorted = sorted(p.get("segments") or [], key=lambda s: float(s.get("t0") or 0))
        for s in segs_sorted:
            if s.get("id") == sid:
                break
            prev = s
        if prev:
            prev_clip = None
            clips = prev.get("clips") or []
            aid = prev.get("active_clip_id")
            if aid:
                prev_clip = next((c for c in clips if c.get("id") == aid), None)
            if not prev_clip and prev.get("video", {}).get("file"):
                prev_clip = prev.get("video")
            if not prev_clip and clips:
                prev_clip = clips[-1]
            if prev_clip and prev_clip.get("file"):
                src_vid = clips_dir / prev_clip["file"]
                if src_vid.is_file() and src_vid.stat().st_size > 1000:
                    frame_path = clips_dir / f"{sid}-from-{prev.get('id')}-last.jpg"
                    try:
                        extract_last_frame(src_vid, frame_path)
                        start_image = frame_path
                        chain = True
                    except Exception:
                        start_image = None
                        chain = False

    # Craft mode: hold / shift / motion → chain + lock policy
    if not seg.get("mode"):
        craft.enrich_new_segment(seg)
    cam_lock = bool(seg.get("camera_lock"))
    start_image, chain, cam_lock, seg_mode = craft.apply_segment_mode(
        seg,
        start_image=start_image,
        chain=chain,
        cam_lock=cam_lock,
        user_ref=user_ref,
    )

    tags = list((seg.get("constraints") or {}).get("soft_tags") or [])
    tags = tags + list(seg.get("emotion_keywords") or [])
    dur = float(feat.get("duration_sec") or (seg["t1"] - seg["t0"]))
    provider = _provider_name()
    unit = clip_unit_seconds()
    # xAI can do up to ~15s in one request. Splitting 6–10s into 5s parts was
    # leaving orphan p00 files when part1 extension failed — UI showed no take.
    if provider == "xai" and dur <= xai_max_single_seconds() + 0.05:
        n_parts = 1
        unit = max(unit, min(dur, xai_max_single_seconds()))
    else:
        n_parts = max(1, int(math.ceil(dur / unit)))
        if dur <= unit + 0.35:
            n_parts = 1

    # Internal multi-part may still use Extension; prev-segment chain already
    # cleared by apply_segment_mode when mode=shift.
    want_extension = (
        provider == "xai" and n_parts > 1 and xai_chain_mode() == "extension"
    )

    clip_id = "c_" + uuid.uuid4().hex[:8]
    out = clips_dir / f"{sid}-{clip_id[2:]}.mp4"

    analysis = pdir / ((p.get("digest") or {}).get("analysis_wav") or "analysis.wav")
    audio_seg = clips_dir / f"{sid}-audio.wav"
    try:
        if analysis.exists():
            extract_audio_segment(analysis, float(seg["t0"]), float(seg["t1"]), audio_seg)
        else:
            audio_seg = None
    except Exception:
        audio_seg = None

    # i2v parts to hard/xfade-concat; extension keeps a growing full clip in `accum`
    i2v_parts: list[Path] = []
    subclips: list[dict[str, Any]] = []
    last_meta: dict[str, Any] = {}
    cur_start = start_image
    composed_first = ""
    accum: Path | None = None
    modes_used: list[str] = []
    partial_error: str | None = None

    for i in range(n_parts):
        part_dur = unit if i < n_parts - 1 else max(1.0, dur - unit * (n_parts - 1))
        if n_parts == 1:
            # Single-shot: use full segment duration (capped by provider unit above).
            part_dur = max(1.0, min(dur, unit if provider == "xai" else dur))
        if n_parts > 1 and i == n_parts - 1 and part_dur < 2.0 and dur >= 2.0:
            part_dur = max(2.0, dur - unit * (n_parts - 1))

        chain_here = bool(cur_start) and (chain or user_ref or i > 0)
        # shift/motion never lock; hold uses user camera_lock only
        lock_here = craft.lock_for_part(cam_lock=cam_lock, mode=seg_mode)

        apply_taste = p.get("apply_taste")
        if apply_taste is None:
            apply_taste = True
        st, neg = taste_mod.merge_prompt_fields(
            style=p.get("style") or "",
            negative_prompt=p.get("negative_prompt") or "",
            apply_taste=bool(apply_taste),
        )
        composed = compose_video_prompt(
            seg["prompt"],
            {**feat, "duration_sec": part_dur},
            world=p.get("world") or "",
            chain_from_prev=chain_here and not (user_ref and i == 0),
            user_ref_image=bool(user_ref and i == 0),
            camera_lock=lock_here,
            style=st,
            negative_prompt=neg,
            valence=craft._clamp(seg.get("valence"), -1.0, 1.0),
            arousal=craft._clamp(seg.get("arousal"), 0.0, 1.0),
        )
        if i == 0:
            composed_first = composed

        part_path = clips_dir / f"{sid}-{clip_id[2:]}-p{i:02d}.mp4"

        # Prefer native extension when we already have a growing video ≤14.5s
        try_ext = (
            want_extension
            and i > 0
            and accum is not None
            and accum.is_file()
            and 1.8 <= probe_duration(accum) <= 14.5
        )

        meta: dict[str, Any]
        mode = "i2v"
        try:
            if try_ext:
                try:
                    meta = await generate_clip(
                        out_path=part_path,
                        duration=part_dur,
                        user_prompt=seg["prompt"],
                        composed_prompt=composed,
                        tags=tags,
                        audio_segment=None,
                        start_image=None,
                        source_video=accum,
                    )
                    mode = "extension"
                except Exception as ext_err:
                    # Fall back to last-frame I2V for this part
                    frame_path = clips_dir / f"{sid}-{clip_id[2:]}-p{i:02d}-fb.jpg"
                    try:
                        extract_last_frame(accum, frame_path)
                        cur_start = frame_path
                    except Exception:
                        pass
                    meta = await generate_clip(
                        out_path=part_path,
                        duration=part_dur,
                        user_prompt=seg["prompt"],
                        composed_prompt=composed,
                        tags=tags,
                        audio_segment=None,
                        start_image=cur_start,
                    )
                    mode = "i2v-fallback"
                    last_meta_note = f"extension failed, used i2v: {ext_err}"
                    meta["note"] = last_meta_note
            else:
                meta = await generate_clip(
                    out_path=part_path,
                    duration=part_dur,
                    user_prompt=seg["prompt"],
                    composed_prompt=composed,
                    tags=tags,
                    audio_segment=None,
                    start_image=cur_start,
                )
                mode = str(meta.get("mode") or ("i2v" if cur_start else "t2v"))
        except Exception as e:
            # Keep completed parts as a partial take instead of discarding orphan p00.
            if subclips or (part_path.is_file() and part_path.stat().st_size > 1000):
                partial_error = f"part {i + 1}/{n_parts}: {e}"
                break
            raise HTTPException(
                502,
                f"映像生成に失敗しました (part {i + 1}/{n_parts}): {e}",
            ) from e

        if meta.get("is_mock") and provider not in {"mock", ""}:
            if subclips:
                partial_error = f"unexpected mock under real provider (part {i + 1}/{n_parts})"
                break
            raise HTTPException(
                502, f"unexpected mock under real provider (part {i + 1}/{n_parts})"
            )

        last_meta = meta
        modes_used.append(mode)
        subclips.append(
            {
                "index": i,
                "file": part_path.name,
                "duration": part_dur,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "mode": mode,
                "chained": bool(meta.get("chained") or chain_here or mode.startswith("extension")),
                "chain_frame": Path(cur_start).name if cur_start and mode != "extension" else None,
                "is_mock": bool(meta.get("is_mock")),
            }
        )

        if mode == "extension":
            # API returned original+extension already stitched
            accum = part_path
            # Seed I2V fallback / next frame from the growing clip
            if i < n_parts - 1:
                frame_path = clips_dir / f"{sid}-{clip_id[2:]}-p{i:02d}-last.jpg"
                try:
                    extract_last_frame(part_path, frame_path)
                    cur_start = frame_path
                except Exception:
                    cur_start = None
        else:
            # Independent part (t2v / i2v). If we had an extension accum before
            # this is the first i2v after extension, keep accum as head.
            if accum is not None and not i2v_parts and mode.startswith("i2v"):
                # Head is the extension result; this part continues after it
                i2v_parts.append(accum)
                accum = None
            i2v_parts.append(part_path)
            if i < n_parts - 1 and part_path.is_file():
                frame_path = clips_dir / f"{sid}-{clip_id[2:]}-p{i:02d}-last.jpg"
                try:
                    extract_last_frame(part_path, frame_path)
                    cur_start = frame_path
                except Exception:
                    cur_start = None
            # Pure extension path keeps only accum; track first part as accum seed
            if i == 0 and want_extension:
                accum = part_path

    if not subclips and not i2v_parts and accum is None:
        raise HTTPException(500, "生成結果が空です" + (f" ({partial_error})" if partial_error else ""))

    # Assemble final output
    pure_extension = bool(accum) and not i2v_parts
    if pure_extension and accum is not None:
        if accum.resolve() != out.resolve():
            out.write_bytes(accum.read_bytes())
    elif len(i2v_parts) == 1:
        if i2v_parts[0].resolve() != out.resolve():
            out.write_bytes(i2v_parts[0].read_bytes())
    elif len(i2v_parts) > 1:
        try:
            concat_video_files(i2v_parts, out, xfade=xfade_seconds())
        except Exception as e:
            # Fall back to first completed part rather than losing everything
            if i2v_parts and i2v_parts[0].is_file():
                out.write_bytes(i2v_parts[0].read_bytes())
                partial_error = (partial_error or "") + f"; concat failed: {e}"
            else:
                raise HTTPException(500, f"クリップ連結に失敗しました: {e}") from e
    elif accum is not None:
        if accum.resolve() != out.resolve():
            out.write_bytes(accum.read_bytes())
    else:
        raise HTTPException(500, "生成結果が空です")

    # Optional: mux segment audio onto final (best-effort)
    if audio_seg and Path(audio_seg).exists() and out.is_file():
        tmp_mux = out.with_suffix(".mux.mp4")
        import subprocess

        r = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(out),
                "-i",
                str(audio_seg),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(tmp_mux),
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and tmp_mux.is_file():
            tmp_mux.replace(out)

    primary_mode = (
        "extension"
        if pure_extension
        else (
            "hybrid"
            if "extension" in modes_used and any(m.startswith("i2v") for m in modes_used)
            else (modes_used[-1] if modes_used else "t2v")
        )
    )

    take_n = len(seg.get("clips") or []) + 1
    note_bits = []
    if last_meta.get("note"):
        note_bits.append(str(last_meta.get("note")))
    if partial_error:
        note_bits.append(f"partial take — later parts failed: {partial_error}")
    entry = {
        "id": clip_id,
        "file": out.name,
        "provider": last_meta.get("provider"),
        "composed_prompt": composed_first,
        "note": " · ".join(note_bits) if note_bits else last_meta.get("note"),
        "created_at": storage._now(),
        "label": f"take {take_n}" + (" (partial)" if partial_error else ""),
        "auth_source": last_meta.get("auth_source"),
        "model": last_meta.get("model"),
        "resolution": last_meta.get("resolution"),
        "chained": bool(
            last_meta.get("chained") or chain or user_ref or n_parts > 1
        ),
        "chain_from_segment": (prev.get("id") if chain and prev and not user_ref else None),
        "chain_frame": start_image.name if start_image else None,
        "user_ref_image": bool(user_ref),
        "ref_image": seg.get("ref_image") if user_ref else None,
        "camera_lock": bool(cam_lock),
        "segment_mode": seg_mode,
        "clip_unit_seconds": unit,
        "subclip_count": len(subclips) or n_parts,
        "subclips": subclips,
        "duration_requested": dur,
        "is_mock": bool(last_meta.get("is_mock")),
        "chain_mode": primary_mode,
        "xfade_seconds": xfade_seconds() if primary_mode in {"i2v", "hybrid", "i2v-fallback"} else 0,
        "partial": bool(partial_error),
    }
    seg.setdefault("clips", []).append(entry)
    seg["active_clip_id"] = clip_id
    seg["video"] = dict(entry)
    storage.save_project(p)
    return {"segment": seg, "meta": last_meta, "clip": entry, "partial": bool(partial_error)}


class ClipSelectBody(BaseModel):
    clip_id: str


@app.post("/api/projects/{pid}/segments/{sid}/clips/select")
def api_select_clip(pid: str, sid: str, body: ClipSelectBody):
    p = _proj(pid)
    seg = next((s for s in p["segments"] if s["id"] == sid), None)
    if not seg:
        raise HTTPException(404, "segment not found")
    clips = seg.get("clips") or []
    hit = next((c for c in clips if c.get("id") == body.clip_id), None)
    if not hit:
        raise HTTPException(404, "clip not found")
    craft.assert_adoptable(hit, _provider_name())
    seg["active_clip_id"] = hit["id"]
    seg["video"] = dict(hit)
    storage.save_project(p)
    return {"segment": seg, "clip": hit}


@app.delete("/api/projects/{pid}/segments/{sid}/clips/{clip_id}")
def api_delete_clip(pid: str, sid: str, clip_id: str):
    p = _proj(pid)
    seg = next((s for s in p["segments"] if s["id"] == sid), None)
    if not seg:
        raise HTTPException(404, "segment not found")
    clips = list(seg.get("clips") or [])
    hit = next((c for c in clips if c.get("id") == clip_id), None)
    if not hit:
        raise HTTPException(404, "clip not found")
    seg["clips"] = [c for c in clips if c.get("id") != clip_id]
    clips_dir = storage.project_dir(pid) / "clips"

    def _unused(name: str | None, field: str = "file") -> bool:
        if not name:
            return False
        return not any(
            (c.get(field) == name)
            for s2 in p.get("segments") or []
            for c in (s2.get("clips") or [])
        )

    for field in ("file", "chain_frame"):
        fname = hit.get(field)
        if fname and _unused(fname, field if field == "file" else "chain_frame"):
            still = any(
                (c.get("file") == fname or c.get("chain_frame") == fname)
                for s2 in p.get("segments") or []
                for c in (s2.get("clips") or [])
            )
            if not still:
                fpath = clips_dir / Path(str(fname)).name
                try:
                    if fpath.is_file():
                        fpath.unlink()
                except OSError:
                    pass

    for sc in hit.get("subclips") or []:
        fname = sc.get("file")
        if fname:
            fpath = clips_dir / Path(str(fname)).name
            try:
                if fpath.is_file():
                    fpath.unlink()
            except OSError:
                pass

    if seg.get("active_clip_id") == clip_id:
        if seg["clips"]:
            act = seg["clips"][-1]
            seg["active_clip_id"] = act.get("id")
            seg["video"] = dict(act)
        else:
            seg["active_clip_id"] = None
            seg["video"] = None
            audio_side = clips_dir / f"{sid}-audio.wav"
            try:
                if audio_side.is_file():
                    audio_side.unlink()
            except OSError:
                pass
    storage.save_project(p)
    return {"segment": seg}


@app.get("/api/projects/{pid}/clips/{name}")
def api_clip(pid: str, name: str):
    safe = Path(name).name
    path = storage.project_dir(pid) / "clips" / safe
    if not path.exists():
        raise HTTPException(404, "clip not found")
    suffix = path.suffix.lower()
    media = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
    }.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media)


@app.post("/api/projects/{pid}/program/export")
def api_program_export(pid: str):
    p = _proj(pid)
    pdir = storage.project_dir(pid)
    clips_dir = pdir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    out = clips_dir / "program.mp4"
    try:
        meta = build_program_mp4(p, clips_dir, out, include_gaps=True)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"program export failed: {e}") from e

    if not out.is_file() or out.stat().st_size < 32:
        raise HTTPException(500, "program export produced empty file")

    p["program"] = {
        "file": "program.mp4",
        "id": meta["id"],
        "created_at": storage._now(),
        "duration_sec": meta["duration_sec"],
        "t0": meta["t0"],
        "t1": meta["t1"],
        "clip_count": meta["clip_count"],
        "gap_count": meta["gap_count"],
        "bytes": meta.get("bytes") or out.stat().st_size,
        "manifest": meta["manifest"],
    }
    storage.save_project(p)
    return {
        "ok": True,
        "program": p["program"],
        "project": storage.public_project(p),
    }


@app.get("/api/projects/{pid}/program")
def api_program_file(pid: str):
    p = _proj(pid)
    name = (p.get("program") or {}).get("file") or "program.mp4"
    path = storage.project_dir(pid) / "clips" / Path(name).name
    if not path.is_file():
        raise HTTPException(404, "program not built yet — export first")
    return FileResponse(path, media_type="video/mp4", filename="program.mp4")


# --- Canva Connect (export polish) -------------------------------------------


class CanvaSendBody(BaseModel):
    """what: program | clip | segment_active | ref
    For clip: pass clip_file name under clips/.
    For segment_active / ref: pass segment_id.
    open_design: try create Canva design (images only).
    """

    what: str = "program"
    segment_id: Optional[str] = None
    clip_file: Optional[str] = None
    open_design: bool = True
    title: Optional[str] = None


@app.get("/api/canva/status")
def api_canva_status():
    from . import canva as canva_mod

    return canva_mod.status()


@app.get("/api/canva/authorize")
def api_canva_authorize():
    from . import canva as canva_mod

    try:
        return canva_mod.start_authorize()
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/canva/callback")
def api_canva_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    from . import canva as canva_mod

    if error:
        msg = error_description or error
        html = f"""<!doctype html><meta charset=utf-8>
<title>Canva</title><body style="font-family:system-ui;padding:2rem;background:#0c0e12;color:#eee">
<h1>Canva authorize failed</h1><p>{msg}</p>
<p><a href="/" style="color:#c9a227">Back to Xochipilli</a></p></body>"""
        return HTMLResponse(html, status_code=400)
    if not code:
        raise HTTPException(400, "missing code")
    try:
        canva_mod.finish_authorize(code, state)
    except Exception as e:
        html = f"""<!doctype html><meta charset=utf-8>
<title>Canva</title><body style="font-family:system-ui;padding:2rem;background:#0c0e12;color:#eee">
<h1>Token exchange failed</h1><p>{e}</p>
<p><a href="/" style="color:#c9a227">Back to Xochipilli</a></p></body>"""
        return HTMLResponse(html, status_code=400)
    html = """<!doctype html><meta charset=utf-8>
<title>Canva connected</title>
<body style="font-family:system-ui;padding:2rem;background:#0c0e12;color:#eee">
<h1 style="color:#c9a227">Canva connected</h1>
<p>You can close this tab and send clips from Xochipilli.</p>
<script>try{if(window.opener){window.opener.postMessage({type:'canva-connected'},'*');}}catch(e){}
setTimeout(function(){ location.href='/'; }, 1200);</script>
<p><a href="/" style="color:#c9a227">Back to Xochipilli</a></p></body>"""
    return HTMLResponse(html)


@app.post("/api/canva/disconnect")
def api_canva_disconnect():
    from . import canva as canva_mod

    canva_mod.clear_tokens()
    return {"ok": True, **canva_mod.status()}


@app.post("/api/projects/{pid}/canva/send")
def api_canva_send(pid: str, body: CanvaSendBody):
    """Upload a clip / program / ref image into the user's Canva library."""
    from . import canva as canva_mod

    if not canva_mod.configured():
        raise HTTPException(
            400,
            "Canva not configured — set CANVA_CLIENT_ID / CANVA_CLIENT_SECRET in .env",
        )
    try:
        # ensure token (refresh if needed)
        canva_mod.access_token()
    except Exception as e:
        raise HTTPException(401, str(e)) from e

    p = _proj(pid)
    pdir = storage.project_dir(pid)
    clips_dir = pdir / "clips"
    refs_dir = pdir / "refs"
    what = (body.what or "program").lower().strip()
    path: Path | None = None
    display = body.title or p.get("title") or "Xochipilli"
    kind = "video"

    if what == "program":
        name = (p.get("program") or {}).get("file") or "program.mp4"
        path = clips_dir / Path(name).name
        if not path.is_file():
            raise HTTPException(404, "program.mp4 missing — run Export stitch first")
        display = f"{display}-program"[:50]
    elif what == "clip":
        if not body.clip_file:
            raise HTTPException(400, "clip_file required")
        path = clips_dir / Path(body.clip_file).name
        if not path.is_file():
            raise HTTPException(404, "clip file not found")
        display = f"{display}-{path.stem}"[:50]
    elif what in {"segment_active", "active"}:
        sid = body.segment_id
        seg = next((s for s in (p.get("segments") or []) if s.get("id") == sid), None)
        if not seg:
            raise HTTPException(404, "segment not found")
        clip = None
        aid = seg.get("active_clip_id")
        clips = seg.get("clips") or []
        if aid:
            clip = next((c for c in clips if c.get("id") == aid), None)
        if not clip and seg.get("video", {}).get("file"):
            clip = seg.get("video")
        if not clip and clips:
            clip = clips[-1]
        if not clip or not clip.get("file"):
            raise HTTPException(404, "segment has no clip")
        path = clips_dir / Path(clip["file"]).name
        display = f"{display}-{sid[:8]}"[:50]
    elif what == "ref":
        sid = body.segment_id
        seg = next((s for s in (p.get("segments") or []) if s.get("id") == sid), None)
        if not seg or not seg.get("ref_image"):
            raise HTTPException(404, "segment has no ref image")
        path = refs_dir / Path(seg["ref_image"]).name
        kind = "image"
        display = f"{display}-ref"[:50]
    else:
        raise HTTPException(400, f"unknown what={what}")

    if not path or not path.is_file():
        raise HTTPException(404, "file not found")

    try:
        up = canva_mod.upload_file(path, display_name=display)
    except Exception as e:
        raise HTTPException(502, f"Canva upload failed: {e}") from e

    result: dict[str, Any] = {
        "ok": True,
        "what": what,
        "local_file": path.name,
        "upload": up,
        "library_url": canva_mod.open_library_url(),
        "design": None,
        "note": None,
    }
    asset_id = up.get("asset_id")
    asset_type = (up.get("type") or "").lower()
    # Design-from-asset only supports images today
    if body.open_design and asset_id and asset_type == "image":
        try:
            result["design"] = canva_mod.create_design_from_image(
                asset_id, title=display
            )
        except Exception as e:
            result["note"] = f"uploaded OK; design create skipped: {e}"
    elif asset_type == "video":
        result["note"] = (
            "Video is in your Canva library (Projects). "
            "Open Canva → Projects to drop it on a design. "
            "API cannot auto-place video on a design yet."
        )
    return result


@app.delete("/api/projects/{pid}/segments/{sid}")
def api_del_seg(pid: str, sid: str):
    p = _proj(pid)
    doomed = next((s for s in p["segments"] if s["id"] == sid), None)
    p["segments"] = [s for s in p["segments"] if s["id"] != sid]
    if doomed:
        storage.remove_segment_media(pid, doomed, remaining_segments=p["segments"])
    if p.get("program"):
        storage.remove_program_file(pid)
        p["program"] = None
    return storage.public_project(storage.save_project(p))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
