from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import PROJECTS


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_projects() -> list[dict[str, Any]]:
    items = []
    for p in PROJECTS.glob("*/project.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            items.append(
                {
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "updated_at": data.get("updated_at"),
                    "created_at": data.get("created_at"),
                    "duration_sec": (data.get("digest") or {}).get("global", {}).get("duration_sec"),
                    "segment_count": len(data.get("segments") or []),
                    "dir": p.parent.name,
                }
            )
        except Exception:
            continue
    items.sort(key=lambda x: x.get("updated_at") or x.get("id") or "", reverse=True)
    return items



def project_dir(pid: str) -> Path:
    return PROJECTS / pid


def digest_path(pid: str) -> Path:
    return project_dir(pid) / "digest.json"


def _strip_series_from_digest(digest: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of digest without heavy series (UI does not need it)."""
    if not isinstance(digest, dict):
        return digest
    out = {k: v for k, v in digest.items() if k != "series"}
    out["series_file"] = "digest.json"
    return out


def write_digest_file(pid: str, digest: dict[str, Any]) -> None:
    """Persist full digest (including series) beside project.json."""
    if not isinstance(digest, dict):
        return
    d = project_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    path = digest_path(pid)
    path.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")


def load_digest_file(pid: str) -> dict[str, Any] | None:
    path = digest_path(pid)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def attach_series(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure data['digest']['series'] is available for segment feature calc."""
    dig = data.get("digest")
    if not isinstance(dig, dict):
        return data
    series = dig.get("series")
    if isinstance(series, dict) and series.get("times"):
        return data
    pid = str(data.get("id") or "")
    file_dig = load_digest_file(pid) if pid else None
    if file_dig and isinstance(file_dig.get("series"), dict):
        # mutate a shallow copy of digest so callers can use series without saving it
        dig2 = dict(dig)
        dig2["series"] = file_dig["series"]
        # fill missing light fields from file if needed
        for k in ("global", "waveform_peaks", "theory_id", "analysis_wav"):
            if dig2.get(k) is None and file_dig.get(k) is not None:
                dig2[k] = file_dig[k]
        data = dict(data)
        data["digest"] = dig2
    return data


def public_project(data: dict[str, Any]) -> dict[str, Any]:
    """API-facing project: never ship multi-MB series arrays to the browser."""
    out = dict(data)
    dig = out.get("digest")
    if isinstance(dig, dict) and "series" in dig:
        dig2 = dict(dig)
        dig2.pop("series", None)
        dig2["series_file"] = "digest.json"
        out["digest"] = dig2
    return out


def load_project(pid: str, *, with_series: bool = False) -> dict[str, Any]:
    path = project_dir(pid) / "project.json"
    if not path.exists():
        raise FileNotFoundError(pid)
    data = json.loads(path.read_text(encoding="utf-8"))
    data = migrate_project(data)
    if with_series:
        data = attach_series(data)
    return data


def migrate_project(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize segment clip lists + peel series out of project.json."""
    changed = False
    pid = str(data.get("id") or "")
    dig = data.get("digest")
    if isinstance(dig, dict) and isinstance(dig.get("series"), dict) and dig["series"].get("times"):
        # Ensure digest.json has the heavy payload; slim project.json
        file_dig = load_digest_file(pid) if pid else None
        if not file_dig or not (file_dig.get("series") or {}).get("times"):
            write_digest_file(pid, dig)
        slim = _strip_series_from_digest(dig)
        if data.get("digest") != slim:
            data["digest"] = slim
            changed = True
    elif isinstance(dig, dict) and dig.get("series") is None and "series_file" not in dig:
        # already without series — mark pointer for clarity
        dig = dict(dig)
        dig["series_file"] = "digest.json"
        data["digest"] = dig
        # don't force rewrite unless other changes

    for seg in data.get("segments") or []:
        if not isinstance(seg, dict):
            continue
        clips = seg.get("clips")
        if not isinstance(clips, list):
            clips = []
            seg["clips"] = clips
            changed = True
        # lift legacy single video into clips
        legacy = seg.get("video")
        if isinstance(legacy, dict) and legacy.get("file"):
            if not any(c.get("file") == legacy.get("file") for c in clips if isinstance(c, dict)):
                cid = legacy.get("id") or ("c_" + uuid.uuid4().hex[:8])
                entry = {
                    "id": cid,
                    "file": legacy["file"],
                    "provider": legacy.get("provider"),
                    "composed_prompt": legacy.get("composed_prompt"),
                    "note": legacy.get("note"),
                    "fal_error": legacy.get("fal_error"),
                    "xai_error": legacy.get("xai_error"),
                    "created_at": legacy.get("created_at") or _now(),
                    "label": legacy.get("label") or f"take {len(clips) + 1}",
                }
                clips.append(entry)
                seg["active_clip_id"] = cid
                changed = True
        # ensure active points at something
        active = seg.get("active_clip_id")
        if clips and (not active or not any(c.get("id") == active for c in clips)):
            seg["active_clip_id"] = clips[-1].get("id")
            changed = True
        # mirror active → video for backward-compatible clients
        if clips:
            act = next((c for c in clips if c.get("id") == seg.get("active_clip_id")), clips[-1])
            if seg.get("video") != act:
                seg["video"] = dict(act)
                changed = True
        elif "video" in seg and not clips:
            # empty
            pass
    if changed:
        try:
            save_project(data)
        except Exception:
            pass
    return data


def save_project(data: dict[str, Any]) -> dict[str, Any]:
    """Write project.json without series. Full digest stays in digest.json if provided."""
    pid = data["id"]
    data = dict(data)
    data["updated_at"] = _now()
    dig = data.get("digest")
    if isinstance(dig, dict) and isinstance(dig.get("series"), dict) and dig["series"].get("times"):
        # persist full then strip for project.json
        write_digest_file(pid, dig)
        data["digest"] = _strip_series_from_digest(dig)
    elif isinstance(dig, dict) and "series" in dig:
        # empty/partial series — drop it
        data["digest"] = _strip_series_from_digest(dig)
    d = project_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "project.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def new_project(title: str = "Untitled") -> dict[str, Any]:
    pid = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    data = {
        "id": pid,
        "title": title,
        "created_at": _now(),
        "updated_at": _now(),
        "world": "",
        "style": "",
        "negative_prompt": "",
        "apply_taste": True,
        "lyrics": "",
        "bar_mode": "waveform",  # waveform | lyrics | both
        "source_audio": None,
        "digest": None,
        "open_pin": None,
        "segments": [],
        "unmatch_log": [],
    }
    return save_project(data)


def delete_project(pid: str) -> None:
    """Remove entire project directory (project.json, audio, clips, refs)."""
    safe = Path(str(pid)).name
    if safe != pid:
        raise ValueError("invalid project id")
    d = project_dir(safe)
    # must stay under PROJECTS
    try:
        d.resolve().relative_to(PROJECTS.resolve())
    except ValueError as e:
        raise ValueError("project path escapes projects root") from e
    if d.exists() and d.is_dir():
        shutil.rmtree(d)


def _safe_unlink(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def clear_project_media(pid: str) -> None:
    """Wipe clips/ and refs/ under a project (used on re-import)."""
    d = project_dir(Path(str(pid)).name)
    for sub in ("clips", "refs"):
        p = d / sub
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        p.mkdir(parents=True, exist_ok=True)


def remove_program_file(pid: str) -> None:
    clips = project_dir(Path(str(pid)).name) / "clips"
    _safe_unlink(clips / "program.mp4")


def remove_segment_media(
    pid: str,
    seg: dict[str, Any],
    remaining_segments: list[dict[str, Any]] | None = None,
) -> None:
    """Delete on-disk media owned by one segment if nothing remaining still points at it."""
    remaining = remaining_segments if remaining_segments is not None else []
    d = project_dir(Path(str(pid)).name)
    clips_dir = d / "clips"
    refs_dir = d / "refs"
    sid = str(seg.get("id") or "")

    def still_used(name: str | None) -> bool:
        if not name:
            return False
        for s2 in remaining:
            if (s2.get("ref_image") and Path(str(s2["ref_image"])).name == name):
                return True
            for c in s2.get("clips") or []:
                if not isinstance(c, dict):
                    continue
                for k in ("file", "chain_frame"):
                    v = c.get(k)
                    if v and Path(str(v)).name == name:
                        return True
            video = s2.get("video") or {}
            if isinstance(video, dict) and video.get("file"):
                if Path(str(video["file"])).name == name:
                    return True
        return False

    names: set[str] = set()
    for c in seg.get("clips") or []:
        if not isinstance(c, dict):
            continue
        for k in ("file", "chain_frame"):
            v = c.get(k)
            if v:
                names.add(Path(str(v)).name)
    video = seg.get("video") or {}
    if isinstance(video, dict) and video.get("file"):
        names.add(Path(str(video["file"])).name)
    if sid:
        names.add(f"{sid}-audio.wav")
        # leftover takes / frames for this segment id prefix
        if clips_dir.is_dir():
            for f in clips_dir.glob(f"{sid}-*"):
                if f.is_file():
                    names.add(f.name)

    for name in names:
        if still_used(name):
            continue
        _safe_unlink(clips_dir / name)

    ref = seg.get("ref_image")
    if ref:
        rname = Path(str(ref)).name
        if not still_used(rname):
            _safe_unlink(refs_dir / rname)


def gc_unreferenced_clips(pid: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Remove clip files not referenced by project.json (orphaned takes / test frames)."""
    p = data if data is not None else load_project(pid)
    d = project_dir(Path(str(pid)).name)
    clips_dir = d / "clips"
    if not clips_dir.is_dir():
        return {"removed": [], "kept": 0}

    keep: set[str] = set()
    prog = (p.get("program") or {}).get("file")
    if prog:
        keep.add(Path(str(prog)).name)
    else:
        # keep program.mp4 only if present in metadata; bare file without meta is orphan
        pass

    for seg in p.get("segments") or []:
        sid = str(seg.get("id") or "")
        if sid:
            keep.add(f"{sid}-audio.wav")
        if seg.get("ref_image"):
            # refs live under refs/, not clips/
            pass
        for c in seg.get("clips") or []:
            if not isinstance(c, dict):
                continue
            for k in ("file", "chain_frame"):
                v = c.get(k)
                if v:
                    keep.add(Path(str(v)).name)
        video = seg.get("video") or {}
        if isinstance(video, dict) and video.get("file"):
            keep.add(Path(str(video["file"])).name)

    removed: list[str] = []
    for f in list(clips_dir.iterdir()):
        if not f.is_file():
            continue
        if f.name in keep:
            continue
        # never delete while open name is program and still referenced
        _safe_unlink(f)
        removed.append(f.name)
    return {"removed": removed, "kept": len(keep)}
