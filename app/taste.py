from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .paths import ROOT

USER_DIR = ROOT / "data" / "user"
TASTE_PATH = USER_DIR / "taste.json"

VALID_REASONS = ("emotion", "world", "camera", "style", "other")
VALID_MODES = ("hold", "shift", "motion")


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def load_taste() -> dict[str, Any]:
    if not TASTE_PATH.is_file():
        return {
            "version": 1,
            "updated_at": None,
            "unmatch_count": 0,
            "reason_counts": {},
            "rejected_keywords": {},
            "mode_counts": {},
            "recent": [],
            "hints": [],
        }
    try:
        data = json.loads(TASTE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else load_taste.__defaults__  # type: ignore
    except Exception:
        return {
            "version": 1,
            "updated_at": None,
            "unmatch_count": 0,
            "reason_counts": {},
            "rejected_keywords": {},
            "mode_counts": {},
            "recent": [],
            "hints": [],
        }


def save_taste(data: dict[str, Any]) -> dict[str, Any]:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["updated_at"] = _now()
    data["hints"] = build_hints(data)
    TASTE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def normalize_reason(raw: str | None) -> str:
    r = (raw or "other").strip().lower()
    return r if r in VALID_REASONS else "other"


def normalize_mode(raw: str | None) -> str:
    m = (raw or "hold").strip().lower()
    return m if m in VALID_MODES else "hold"


def record_unmatch(
    *,
    project_id: str,
    segment_id: str,
    reason: str,
    suggested_keywords: list[str],
    editor_note: str = "",
    mode: str | None = None,
) -> dict[str, Any]:
    """Append one Unmatch judgement into user-level taste memory."""
    taste = load_taste()
    reason = normalize_reason(reason)
    mode_n = normalize_mode(mode) if mode else None

    taste["unmatch_count"] = int(taste.get("unmatch_count") or 0) + 1
    rc = dict(taste.get("reason_counts") or {})
    rc[reason] = int(rc.get(reason) or 0) + 1
    taste["reason_counts"] = rc

    rk = dict(taste.get("rejected_keywords") or {})
    for kw in suggested_keywords or []:
        k = str(kw).strip()
        if not k:
            continue
        rk[k] = int(rk.get(k) or 0) + 1
    taste["rejected_keywords"] = rk

    if mode_n:
        mc = dict(taste.get("mode_counts") or {})
        mc[mode_n] = int(mc.get(mode_n) or 0) + 1
        taste["mode_counts"] = mc

    recent = list(taste.get("recent") or [])
    recent.insert(
        0,
        {
            "at": _now(),
            "project_id": project_id,
            "segment_id": segment_id,
            "reason": reason,
            "suggested_keywords": list(suggested_keywords or []),
            "editor_note": (editor_note or "")[:500],
            "mode": mode_n,
        },
    )
    taste["recent"] = recent[:40]
    return save_taste(taste)


def build_hints(taste: dict[str, Any]) -> list[str]:
    """Short human-readable suggestions (not auto-applied)."""
    hints: list[str] = []
    rk = taste.get("rejected_keywords") or {}
    if rk:
        top = sorted(rk.items(), key=lambda x: (-int(x[1]), x[0]))[:3]
        if top and int(top[0][1]) >= 2:
            tags = "、".join(f"{k}×{v}" for k, v in top)
            hints.append(f"よく却下している感情タグ: {tags}")
    rc = taste.get("reason_counts") or {}
    if rc:
        top_r = sorted(rc.items(), key=lambda x: (-int(x[1]), x[0]))
        if top_r and int(top_r[0][1]) >= 2:
            hints.append(f"Unmatch理由で多いもの: {top_r[0][0]}（{top_r[0][1]}回）")
    n = int(taste.get("unmatch_count") or 0)
    if n and not hints:
        hints.append(f"Unmatch累計 {n} 件（傾向はまだ薄い）")
    return hints[:5]


def public_taste() -> dict[str, Any]:
    t = load_taste()
    return {
        "ok": True,
        "unmatch_count": int(t.get("unmatch_count") or 0),
        "reason_counts": t.get("reason_counts") or {},
        "rejected_keywords": t.get("rejected_keywords") or {},
        "mode_counts": t.get("mode_counts") or {},
        "hints": t.get("hints") or build_hints(t),
        "updated_at": t.get("updated_at"),
    }
