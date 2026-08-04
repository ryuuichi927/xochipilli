from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import ROOT

USER_DIR = ROOT / "data" / "user"
TASTE_PATH = USER_DIR / "taste.json"

# episode = functional mismatch (Episode Model as *interpretation*, not a 20s segment stamp)
VALID_REASONS = ("emotion", "world", "camera", "style", "episode", "other")
VALID_MODES = ("hold", "shift", "motion")


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _empty_taste() -> dict[str, Any]:
    return {
        "version": 2,
        "updated_at": None,
        "unmatch_count": 0,
        "reason_counts": {},
        "rejected_keywords": {},
        "mode_counts": {},
        "episode_mismatch_count": 0,
        "affect_samples": [],  # recent valence/arousal at unmatch
        "recent": [],
        "hints": [],
    }


def load_taste() -> dict[str, Any]:
    if not TASTE_PATH.is_file():
        return _empty_taste()
    try:
        data = json.loads(TASTE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_taste()
        # migrate v1 → v2 keys
        data.setdefault("version", 1)
        data.setdefault("episode_mismatch_count", 0)
        data.setdefault("affect_samples", [])
        return data
    except Exception:
        return _empty_taste()


def save_taste(data: dict[str, Any]) -> dict[str, Any]:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    data = dict(data)
    data["version"] = max(2, int(data.get("version") or 2))
    data["updated_at"] = _now()
    data["hints"] = build_hints(data)
    TASTE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def normalize_reason(raw: str | None) -> str:
    r = (raw or "other").strip().lower()
    # aliases
    if r in {"function", "purpose", "functional"}:
        r = "episode"
    return r if r in VALID_REASONS else "other"


def normalize_mode(raw: str | None) -> str:
    m = (raw or "hold").strip().lower()
    return m if m in VALID_MODES else "hold"


def _clamp_unit(v: float | None, lo: float, hi: float) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, x))


def record_unmatch(
    *,
    project_id: str,
    segment_id: str,
    reason: str,
    suggested_keywords: list[str],
    editor_note: str = "",
    mode: str | None = None,
    valence: float | None = None,
    arousal: float | None = None,
) -> dict[str, Any]:
    """Append one Unmatch judgement into user-level taste memory."""
    taste = load_taste()
    reason = normalize_reason(reason)
    mode_n = normalize_mode(mode) if mode else None
    val = _clamp_unit(valence, -1.0, 1.0)
    aro = _clamp_unit(arousal, 0.0, 1.0)

    taste["unmatch_count"] = int(taste.get("unmatch_count") or 0) + 1
    rc = dict(taste.get("reason_counts") or {})
    rc[reason] = int(rc.get(reason) or 0) + 1
    taste["reason_counts"] = rc

    if reason == "episode":
        taste["episode_mismatch_count"] = int(taste.get("episode_mismatch_count") or 0) + 1

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

    if val is not None or aro is not None:
        samples = list(taste.get("affect_samples") or [])
        samples.insert(
            0,
            {
                "at": _now(),
                "reason": reason,
                "valence": val,
                "arousal": aro,
                "segment_id": segment_id,
            },
        )
        taste["affect_samples"] = samples[:30]

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
            "valence": val,
            "arousal": aro,
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
            label = top_r[0][0]
            if label == "episode":
                hints.append(
                    f"体験の働き（Episode）のズレが多い（{top_r[0][1]}回）"
                    " — 画より『求めていた聴取の役割』が違う"
                )
            else:
                hints.append(f"Unmatch理由で多いもの: {label}（{top_r[0][1]}回）")
    ep_n = int(taste.get("episode_mismatch_count") or 0)
    if ep_n >= 2 and not any("Episode" in h for h in hints):
        hints.append(f"Episode ズレ累計 {ep_n} — 機能の不一致として記録されています")

    samples = list(taste.get("affect_samples") or [])
    aros = [float(s["arousal"]) for s in samples if s.get("arousal") is not None]
    if len(aros) >= 3:
        mean_a = sum(aros[:8]) / min(8, len(aros))
        if mean_a >= 0.65:
            hints.append("却下時の arousal が高め — 次は動き・刺激を抑える方向が有利かも")
        elif mean_a <= 0.35:
            hints.append("却下時の arousal が低め — 停滞しすぎ／暗すぎの可能性")

    n = int(taste.get("unmatch_count") or 0)
    if n and not hints:
        hints.append(f"Unmatch累計 {n} 件（傾向はまだ薄い）")
    return hints[:6]


def public_taste() -> dict[str, Any]:
    t = load_taste()
    return {
        "ok": True,
        "version": int(t.get("version") or 2),
        "unmatch_count": int(t.get("unmatch_count") or 0),
        "episode_mismatch_count": int(t.get("episode_mismatch_count") or 0),
        "reason_counts": t.get("reason_counts") or {},
        "rejected_keywords": t.get("rejected_keywords") or {},
        "mode_counts": t.get("mode_counts") or {},
        "affect_samples": (t.get("affect_samples") or [])[:8],
        "valid_reasons": list(VALID_REASONS),
        "hints": t.get("hints") or build_hints(t),
        "updated_at": t.get("updated_at"),
    }
