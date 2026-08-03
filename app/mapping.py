from __future__ import annotations

import json
import re
from typing import Any

from .paths import THEORY


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


def compose_video_prompt(
    user_prompt: str,
    feat: dict[str, Any],
    world: str = "",
    *,
    chain_from_prev: bool = False,
    user_ref_image: bool = False,
) -> str:
    c = build_constraints(feat)
    parts = [user_prompt.strip()]
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
            "CONTINUITY FROM PREVIOUS SHOT: A still of the last frame of the previous clip "
            "is provided as the starting image. Begin from that frame and evolve into the new action. "
            "Prefer a natural camera/action continuation, or a brief cinematic transition "
            "(subtle dissolve, short fade through dark, match-cut) when the scene must change. "
            "Preserve lighting, palette, and spatial logic unless the user prompt clearly resets the world."
        )
    if c["soft_tags"]:
        parts.append(
            "Music-derived visual bias (soft, do not override explicit user intent): "
            + ", ".join(c["soft_tags"])
        )
    parts.append(
        f"Clip length about {feat.get('duration_sec', '?')} seconds; cinematic; no subtitles; no watermark."
    )
    return "\n".join(p for p in parts if p)
