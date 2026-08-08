from __future__ import annotations

import json
import re
from typing import Any, Optional

from .paths import THEORY

# Strong camera lock — ONLY when user explicitly enables camera_lock.
CAMERA_LOCK_TEXT = (
    "CAMERA LOCK — PHYSICALLY LOCKED STATIC SHOT:\n"
    "Physically locked static camera on a heavy tripod. "
    "Zero zoom, zero push-in, zero dolly, zero pan, zero tilt, zero camera movement of any kind. "
    "Framing, viewpoint, focal length and composition must stay 100% identical to the starting frame. "
    "Only the subject and environment may animate. Do not change the camera position or angle at all."
)

# Soft tags that fight a locked camera (filtered when lock is on).
_CAMERA_TAG_RE = re.compile(
    r"camera|pan|tilt|zoom|dolly|push[- ]?in|orbit|tracking shot|long takes",
    re.IGNORECASE,
)

DEFAULT_NEGATIVE = (
    "no camera movement, no zoom, no pan, no tilt, no dolly, no push-in, "
    "no subtitles, no watermark, no disney style, no generic 3d cgi look, "
    "no photorealistic faces unless requested"
)


def load_mapping() -> dict[str, Any]:
    return json.loads((THEORY / "mapping_v0.json").read_text(encoding="utf-8"))


def _eval_when(expr: str, feat: dict[str, Any]) -> bool:
    # very small safe evaluator: "name OP number"
    m = re.match(
        r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(>=|<=|>|<|==)\s*(-?[0-9]+(?:\.[0-9]+)?)\s*$",
        expr,
    )
    if not m:
        return False
    key, op, num_s = m.group(1), m.group(2), m.group(3)
    if key not in feat:
        return False
    left = float(feat[key])
    right = float(num_s)
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    if op == "==":
        return abs(left - right) < 1e-9
    return False


def build_constraints(feat: dict[str, Any]) -> dict[str, Any]:
    mapping = load_mapping()
    tags: list[str] = []
    fired: list[str] = []
    for rule in mapping.get("soft_constraints") or []:
        when = rule.get("when") or ""
        if _eval_when(when, feat):
            fired.append(when)
            for t in rule.get("prompt_tags") or []:
                if t not in tags:
                    tags.append(t)
    hard = mapping.get("hard_defaults") or {}
    max_sec = float(hard.get("max_clip_seconds") or 30)
    dur = float(feat.get("duration_sec") or 0)
    return {
        "mapping_id": mapping.get("mapping_id"),
        "soft_tags": tags,
        "fired_rules": fired,
        "duration_sec": min(dur, max_sec) if dur > 0 else None,
        "user_prompt_wins": bool(mapping.get("user_prompt_wins", True)),
    }


def _filter_soft_tags(tags: list[str], *, lock_camera: bool) -> list[str]:
    if not lock_camera:
        return list(tags)
    out: list[str] = []
    for t in tags:
        if _CAMERA_TAG_RE.search(t or ""):
            continue
        out.append(t)
    return out


def affect_visual_hints(
    valence: Optional[float] = None,
    arousal: Optional[float] = None,
) -> list[str]:
    """Map local affect axes → short visual bias phrases (not Episode labels)."""
    hints: list[str] = []
    if arousal is not None:
        if arousal >= 0.7:
            hints.append("higher subject energy, clearer directional motion")
        elif arousal <= 0.3:
            hints.append("low energy, soft motion, sparse activity")
    if valence is not None:
        if valence <= -0.4:
            hints.append("lower brightness, quieter palette, restrained space")
        elif valence >= 0.4:
            hints.append("warmer or clearer light, more open spatial feel")
    return hints


def compose_video_prompt(
    user_prompt: str,
    feat: dict[str, Any],
    world: str = "",
    *,
    chain_from_prev: bool = False,
    user_ref_image: bool = False,
    camera_lock: bool = False,
    style: str = "",
    negative_prompt: str = "",
    valence: Optional[float] = None,
    arousal: Optional[float] = None,
    part_index: Optional[int] = None,
    total_parts: Optional[int] = None,
    window_t0: Optional[float] = None,
    window_t1: Optional[float] = None,
    sequence_duration: Optional[float] = None,
) -> str:
    """Build the final prompt sent to the video provider.

    camera_lock:
        ONLY when True (user toggle). Hard tripod lock + strip camera soft_tags.
    chain_from_prev:
        Continuity paragraph from previous last-frame (softer than hard lock).
    style / negative_prompt:
        Optional project-level style and avoid-list.
    valence / arousal:
        Optional local affect axes → soft visual hints (not Episode taxonomy).
    part_index / total_parts / window_t0 / window_t1 / sequence_duration:
        Optional multi-part TIME WINDOW (only when total_parts > 1).
    """
    lock = bool(camera_lock)
    c = build_constraints(feat)
    soft_tags = _filter_soft_tags(list(c.get("soft_tags") or []), lock_camera=lock)
    parts: list[str] = []

    if (
        part_index is not None
        and total_parts is not None
        and int(total_parts) > 1
    ):
        t0s = f"{float(window_t0):.1f}" if window_t0 is not None else "?"
        t1s = f"{float(window_t1):.1f}" if window_t1 is not None else "?"
        seq = (
            f"{float(sequence_duration):.1f}"
            if sequence_duration is not None
            else "?"
        )
        parts.append(
            f"TIME WINDOW — This is part {int(part_index) + 1} of {int(total_parts)} "
            f"of a {seq}-second sequence, covering seconds {t0s}–{t1s}. "
            "Depict ONLY the events that belong to this time window. "
            "Do not compress or summarize the entire narrative into this short clip. "
            "The full description below is for context only; act solely within this window."
        )

    # P2 MUSIC WINDOW — music facts from digest (soft; user prompt still wins)
    music_summary = str(feat.get("music_summary") or "").strip()
    if music_summary:
        parts.append(
            "MUSIC WINDOW — Musical facts for this segment (soft bias; "
            "do not override explicit user intent or STYLE LOCK):\n"
            + music_summary
        )

    if lock:
        parts.append(CAMERA_LOCK_TEXT)

    if style.strip():
        parts.append(
            "STYLE LOCK (must preserve across the whole clip):\n" + style.strip()
        )

    if user_prompt.strip():
        parts.append(user_prompt.strip())

    if world.strip():
        parts.append(f"World / continuity: {world.strip()}")

    if user_ref_image:
        parts.append(
            "START FROM ATTACHED REFERENCE IMAGE: The provided still is the opening frame / visual anchor. "
            "Begin from that image and evolve into the action described by the user. "
            "Preserve subject identity, palette, and composition unless the user prompt clearly changes them. "
            "Cinematic motion; no subtitles; no watermark."
        )
    elif chain_from_prev:
        parts.append(
            "CONTINUITY FROM PREVIOUS SHOT: A still of the previous clip's near-end frame "
            "is provided as the starting image. Begin from that frame and evolve into the new action. "
            "Preserve lighting, palette, subject identity, and spatial logic unless the user prompt "
            "clearly resets the world or changes the camera. Match the energy of the user prompt."
        )

    if soft_tags:
        parts.append(
            "Music-derived visual bias (soft, do not override explicit user intent or STYLE LOCK): "
            + ", ".join(soft_tags)
        )

    affect = affect_visual_hints(valence=valence, arousal=arousal)
    if affect:
        parts.append(
            "Local affect bias (soft): " + "; ".join(affect)
        )

    neg = (negative_prompt or "").strip()
    if lock:
        if neg:
            neg = neg + ", " + DEFAULT_NEGATIVE
        else:
            neg = DEFAULT_NEGATIVE
    if neg:
        parts.append("AVOID / NEGATIVE: " + neg)

    parts.append(
        f"Clip length about {feat.get('duration_sec', '?')} seconds; cinematic; no subtitles; no watermark."
    )
    return "\n".join(p for p in parts if p)
