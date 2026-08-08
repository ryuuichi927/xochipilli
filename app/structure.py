from __future__ import annotations

from pathlib import Path
from typing import Any


def try_all_in_one(src_audio: Path, work_dir: Path) -> list[dict[str, Any]] | None:
    """P1.1 optional: all-in-one if installed. Returns None to keep librosa fallback."""
    try:
        import allin1  # type: ignore
    except ImportError:
        return None

    try:
        # API varies by version; support result object with segments/beats
        result = allin1.analyze(str(src_audio))
    except Exception:
        return None

    cands: list[dict[str, Any]] = []
    segs = getattr(result, "segments", None) or getattr(result, "sections", None) or []
    for s in segs:
        # segment may be object or dict
        if isinstance(s, dict):
            t0 = float(s.get("start", s.get("t0", 0)))
            t1 = float(s.get("end", s.get("t1", 0)))
            lab = str(s.get("label", s.get("function", "section")))
        else:
            t0 = float(getattr(s, "start", getattr(s, "t0", 0)))
            t1 = float(getattr(s, "end", getattr(s, "t1", 0)))
            lab = str(getattr(s, "label", getattr(s, "function", "section")))
        if t1 - t0 < 0.5:
            continue
        cands.append(
            {
                "t0": round(t0, 3),
                "t1": round(t1, 3),
                "label": lab,
                "source": "all-in-one",
                "confidence": 0.7,
            }
        )
    return cands or None
