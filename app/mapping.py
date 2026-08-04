from __future__ import annotations

import json
import re
from typing import Any

from .paths import THEORY

# Strong camera lock used for continuity chaining and optional UI toggle.
CAMERA_LOCK_TEXT = (
    "CAMERA LOCK — PHYSICALLY LOCKED STATIC SHOT:\n"
    "Physically locked static camera on a heavy tripod. "
    "Zero zoom, zero push-in, zero dolly, zero pan, zero tilt, zero camera movement of any kind. "
    "Framing, viewpoint, focal length and composition must stay 100% identical to the starting frame. "
    "Only the subject and environment may animate. Do not change the camera position or angle at all."
)

# Soft tags that fight a locked camera (filtered when lock/chain is on).
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
) -> str:
    """Build the final prompt sent to the video provider.

    camera_lock / chain_from_prev:
        When True, a hard locked-camera block is placed at the top and
        camera-implying soft_tags are stripped.
    style:
        Project-level visual style (hand-drawn look, palette, medium, etc.).
    negative_prompt:
        Things to avoid; merged with a small default when locking camera.
    """
    lock = bool(camera_lock or chain_from_prev)
    c = build_constraints(feat)
    soft_tags = _filter_soft_tags(list(c.get("soft_tags") or []), lock_camera=lock)
    parts: list[str] = []

    # Hard lock first — model pays most attention to the opening instructions.
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
            "CONTINUITY FROM PREVIOUS SHOT: A still of the exact last frame of the previous clip "
            "is provided as the starting image. Begin from that frame and evolve into the new action. "
            "Keep the camera completely locked (see CAMERA LOCK above). "
            "Preserve lighting, palette, and spatial logic unless the user prompt clearly resets the world."
        )

    if soft_tags:
        parts.append(
            "Music-derived visual bias (soft, do not override explicit user intent or STYLE LOCK): "
            + ", ".join(soft_tags)
        )

    neg = (negative_prompt or "").strip()
    if lock:
        # Always reinforce anti-camera + common style failures under lock.
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
