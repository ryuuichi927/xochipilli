from __future__ import annotations

from pathlib import Path
from typing import Any


def transcribe_timed(audio_path: Path) -> list[dict[str, Any]]:
    """P1.3 Whisper optional. Returns [{t0,t1,text}, ...]."""
    try:
        import whisper
    except ImportError as e:
        raise RuntimeError(
            "whisper not installed. Optional: pip install openai-whisper"
        ) from e

    model_name = "base"
    model = whisper.load_model(model_name)
    result = model.transcribe(str(audio_path), word_timestamps=False)
    out: list[dict[str, Any]] = []
    for seg in result.get("segments") or []:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "t0": round(float(seg.get("start") or 0), 3),
                "t1": round(float(seg.get("end") or 0), 3),
                "text": text,
                "source": f"whisper:{model_name}",
            }
        )
    return out
