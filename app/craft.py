"""Craft layer helpers: segment mode, unmatch/taste, adopt rules, subclip regen."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from . import storage
from . import taste as taste_mod
from .mapping import compose_video_prompt
from .video_gen import (
    clip_unit_seconds,
    concat_video_files,
    extract_last_frame,
    generate_clip,
    xfade_seconds,
)


def _clamp(v: Any, lo: float, hi: float) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, x))


def enrich_new_segment(seg: dict[str, Any]) -> dict[str, Any]:
    """Defaults for a newly pinned segment.

    Does NOT stamp Episode labels on the segment (Episode is Unmatch interpretation only).
    Optional local affect: valence (-1..1), arousal (0..1).
    """
    kws = list(seg.get("emotion_keywords") or [])
    seg["suggested_keywords"] = list(kws)
    seg["mode"] = taste_mod.normalize_mode(seg.get("mode") or "hold")
    seg["camera_lock"] = bool(seg.get("camera_lock", False))
    seg["unmatched"] = False
    seg["unmatch"] = None
    # local affect axes (optional; not Episode)
    if "valence" not in seg:
        seg["valence"] = None
    else:
        seg["valence"] = _clamp(seg.get("valence"), -1.0, 1.0)
    if "arousal" not in seg:
        seg["arousal"] = None
    else:
        seg["arousal"] = _clamp(seg.get("arousal"), 0.0, 1.0)
    return seg


def apply_segment_mode(
    seg: dict[str, Any],
    *,
    start_image: Optional[Path],
    chain: bool,
    cam_lock: bool,
    user_ref: bool,
) -> tuple[Optional[Path], bool, bool, str]:
    mode = taste_mod.normalize_mode(seg.get("mode"))
    if mode == "shift":
        if not user_ref:
            start_image = None
            chain = False
        cam_lock = False
    elif mode == "motion":
        cam_lock = False
    return start_image, chain, cam_lock, mode


def lock_for_part(*, cam_lock: bool, mode: str) -> bool:
    if mode in ("shift", "motion"):
        return False
    return bool(cam_lock)


def assert_adoptable(clip: dict[str, Any], provider: str) -> None:
    if clip.get("is_mock") and provider not in {"mock", ""}:
        raise HTTPException(
            400,
            "mock テイクは採用できません（本物プロバイダで再生成してください）",
        )
    if clip.get("error") or clip.get("failed"):
        raise HTTPException(400, "失敗テイクは採用できません")


def handle_unmatch(
    p: dict[str, Any],
    seg: dict[str, Any],
    *,
    reason: str,
    editor_note: str = "",
    editor_keywords: list[str] | None = None,
    valence: float | None = None,
    arousal: float | None = None,
) -> dict[str, Any]:
    reason_n = taste_mod.normalize_reason(reason)
    suggested = list(seg.get("suggested_keywords") or seg.get("emotion_keywords") or [])
    # prefer explicit affect from body; else segment fields
    val = _clamp(valence if valence is not None else seg.get("valence"), -1.0, 1.0)
    aro = _clamp(arousal if arousal is not None else seg.get("arousal"), 0.0, 1.0)

    entry = {
        "at": storage._now(),
        "segment_id": seg["id"],
        "t0": seg["t0"],
        "t1": seg["t1"],
        "reason": reason_n,
        "ai_keywords": list(seg.get("emotion_keywords") or []),
        "suggested_keywords": suggested,
        "editor_note": editor_note or "",
        "editor_keywords": list(editor_keywords or []),
        "mode": taste_mod.normalize_mode(seg.get("mode")),
        "valence": val,
        "arousal": aro,
        "features": seg.get("features"),
    }
    p.setdefault("unmatch_log", []).append(entry)
    seg["unmatched"] = True
    seg["unmatch"] = {
        "at": entry["at"],
        "reason": reason_n,
        "editor_note": entry["editor_note"],
        "suggested_keywords": suggested,
        "valence": val,
        "arousal": aro,
    }
    # keep last known local affect on segment when provided
    if val is not None:
        seg["valence"] = val
    if aro is not None:
        seg["arousal"] = aro
    storage.save_project(p)
    taste = taste_mod.record_unmatch(
        project_id=str(p.get("id") or ""),
        segment_id=str(seg["id"]),
        reason=reason_n,
        suggested_keywords=suggested,
        editor_note=editor_note or "",
        mode=seg.get("mode"),
        valence=val,
        arousal=aro,
    )
    return {
        "ok": True,
        "entry": entry,
        "taste_hints": taste.get("hints") or [],
        "valid_reasons": list(taste_mod.VALID_REASONS),
    }


async def regen_subclips(
    *,
    pid: str,
    seg: dict[str, Any],
    clip: dict[str, Any],
    indices: list[int],
    world: str = "",
    provider: str = "mock",
    style: str = "",
    negative_prompt: str = "",
    prompts: dict[str, str] | None = None,
) -> dict[str, Any]:
    subs = list(clip.get("subclips") or [])
    if not subs:
        raise HTTPException(400, "このテイクに subclips がありません")
    idx_set = sorted({int(i) for i in indices})
    if not idx_set:
        raise HTTPException(400, "indices が空です")
    for i in idx_set:
        if i < 0 or i >= len(subs):
            raise HTTPException(400, f"index {i} が範囲外 (0..{len(subs)-1})")

    clips_dir = storage.project_dir(pid) / "clips"
    clips_dir.mkdir(exist_ok=True)
    sid = str(seg["id"])
    feat = dict(seg.get("features") or {})
    unit = float(clip.get("clip_unit_seconds") or clip_unit_seconds())
    mode_seg = taste_mod.normalize_mode(seg.get("mode"))
    cam_lock = lock_for_part(cam_lock=bool(seg.get("camera_lock")), mode=mode_seg)
    tags = list((seg.get("constraints") or {}).get("soft_tags") or [])
    tags = tags + list(seg.get("emotion_keywords") or [])

    part_paths: list[Path] = [clips_dir / Path(str(sc["file"])).name for sc in subs]

    # Cumulative time windows for every subclip (for TIME WINDOW in compose).
    windows: list[tuple[float, float]] = []
    cum = 0.0
    for sc in subs:
        d = float(sc.get("duration") or unit)
        windows.append((cum, cum + d))
        cum += d
    sequence_duration = float(feat.get("duration_sec") or cum)
    total_parts = len(subs)
    base_prompt = seg.get("prompt") or ""

    for i in idx_set:
        part_dur = float(subs[i].get("duration") or unit)
        window_t0, window_t1 = windows[i]
        override = (prompts or {}).get(str(i), "").strip()
        user_prompt = override if override else base_prompt
        cur_start: Path | None = None
        if i > 0 and part_paths[i - 1].is_file():
            fp = clips_dir / f"{sid}-regen-{clip['id']}-p{i:02d}-start.jpg"
            try:
                extract_last_frame(part_paths[i - 1], fp)
                cur_start = fp
            except Exception:
                cur_start = None
        elif clip.get("chain_frame"):
            cand = clips_dir / Path(str(clip["chain_frame"])).name
            if cand.is_file():
                cur_start = cand

        feat_part = {**feat, "duration_sec": part_dur}
        composed = compose_video_prompt(
            user_prompt,
            feat_part,
            world=world or "",
            chain_from_prev=bool(cur_start),
            user_ref_image=False,
            camera_lock=cam_lock,
            style=style or "",
            negative_prompt=negative_prompt or "",
            valence=_clamp(seg.get("valence"), -1.0, 1.0),
            arousal=_clamp(seg.get("arousal"), 0.0, 1.0),
            part_index=i,
            total_parts=total_parts,
            window_t0=window_t0,
            window_t1=window_t1,
            sequence_duration=sequence_duration,
        )
        out_part = clips_dir / f"{sid}-{clip['id'][2:]}-p{i:02d}-r{uuid.uuid4().hex[:4]}.mp4"
        try:
            meta = await generate_clip(
                out_path=out_part,
                duration=part_dur,
                user_prompt=user_prompt,
                composed_prompt=composed,
                tags=tags,
                audio_segment=None,
                start_image=cur_start,
            )
        except Exception as e:
            raise HTTPException(502, f"subclip {i} 再生成失敗: {e}") from e
        if meta.get("is_mock") and provider not in {"mock", ""}:
            raise HTTPException(502, f"subclip {i}: unexpected mock")

        old = part_paths[i]
        part_paths[i] = out_part
        subs[i] = {
            **subs[i],
            "file": out_part.name,
            "provider": meta.get("provider"),
            "model": meta.get("model"),
            "mode": str(meta.get("mode") or "i2v"),
            "is_mock": bool(meta.get("is_mock")),
            "regenerated_at": storage._now(),
            "chain_frame": Path(cur_start).name if cur_start else subs[i].get("chain_frame"),
            "corrective_prompt": override or None,
        }
        try:
            if old.is_file() and old.resolve() != out_part.resolve():
                old.unlink()
        except OSError:
            pass

    final = clips_dir / Path(str(clip["file"])).name
    tmp_out = clips_dir / f"{sid}-{clip['id'][2:]}-rebuilt.mp4"
    try:
        if len(part_paths) == 1:
            tmp_out.write_bytes(part_paths[0].read_bytes())
        else:
            concat_video_files(part_paths, tmp_out, xfade=xfade_seconds())
    except Exception as e:
        raise HTTPException(500, f"再連結に失敗: {e}") from e
    if tmp_out.is_file():
        tmp_out.replace(final)

    clip["subclips"] = subs
    clip["subclip_count"] = len(subs)
    clip["is_mock"] = any(bool(sc.get("is_mock")) for sc in subs)
    clip["note"] = ((clip.get("note") or "") + f" | regen {idx_set}").strip(" |")
    clip["regenerated_at"] = storage._now()
    return clip
