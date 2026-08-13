"""Phase checks + digest smoke (P0–P3). Run: .venv/bin/python tests/test_digest_phases.py"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _make_tone_wav(path: Path, sr: int = 22050, sec: float = 8.0) -> None:
    import numpy as np
    import soundfile as sf

    t = np.linspace(0, sec, int(sr * sec), endpoint=False)
    # two sections: lower then higher energy
    y = 0.2 * np.sin(2 * np.pi * 220 * t)
    y[int(sr * 4) :] += 0.25 * np.sin(2 * np.pi * 440 * t[int(sr * 4) :])
    # weak beats
    for i in range(0, int(sec * 2)):
        idx = int(i * sr / 2)
        if idx < len(y):
            y[idx : idx + 200] += 0.4
    sf.write(str(path), y.astype(np.float32), sr)


def check_p0(work: Path) -> dict:
    from app.digest import digest_audio, segment_features

    src = work / "tone.wav"
    _make_tone_wav(src)
    dig = digest_audio(src, work)
    assert dig["global"].get("engine") == "librosa"
    assert dig["global"]["duration_sec"] > 7
    assert dig["global"]["tempo_bpm"] > 0
    assert len(dig.get("beats", {}).get("times") or []) >= 1
    assert dig.get("waveform_peaks")
    feat = segment_features(dig, 0.0, 3.0)
    assert "music_summary" in feat and "Music window" in feat["music_summary"]
    return {
        "ok": True,
        "tempo": dig["global"]["tempo_bpm"],
        "n_beats": dig["global"].get("n_beats"),
        "n_structure": len(dig.get("structure_candidates") or []),
        "music_summary_head": feat["music_summary"][:80],
    }


def check_p1(work: Path) -> dict:
    dig = json.loads((work / "digest.json").read_text(encoding="utf-8"))
    cands = dig.get("structure_candidates") or []
    # structure may be empty on pure tones; still OK if list exists
    return {
        "ok": True,
        "structure_engine": (dig.get("phase") or {}).get("p1_structure_engine"),
        "n_candidates": len(cands),
        "lyrics_n": len(dig.get("lyrics") or []),
        "note": "all-in-one/whisper optional; librosa candidates preferred default",
    }


def check_p2() -> dict:
    from app.mapping import compose_video_prompt

    feat = {
        "duration_sec": 5.0,
        "music_summary": "Music window 0.0–5.0s (5.0s). Approx. chorus, tempo ~120 BPM, high energy.",
        "tempo_bpm": 120,
    }
    text = compose_video_prompt("a red lantern in the rain", feat)
    assert "MUSIC WINDOW" in text
    assert "red lantern" in text
    return {"ok": True, "prompt_has_music_window": True, "sample": text.split("\n")[0][:60]}


def check_p3(work: Path) -> dict:
    from app.otio_export import export_project_otio

    proj = {
        "id": "test",
        "title": "phase-check",
        "segments": [
            {"id": "a", "t0": 0.0, "t1": 2.5, "video": None},
            {"id": "b", "t0": 2.5, "t1": 5.0, "video": None},
        ],
    }
    out = work / "t.otio"
    export_project_otio(proj, work, out)
    assert out.exists() and out.stat().st_size > 20
    # scenedetect import
    import scenedetect  # noqa: F401

    return {"ok": True, "otio_bytes": out.stat().st_size, "scenedetect": True}


def main() -> int:
    print("=== Xochipilli phase check ===")
    ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    print("P0.1 ffmpeg:", "ok" if ffmpeg.returncode == 0 else "FAIL")
    # ffmpeg is required at runtime for import and export, so a missing binary is a failure
    # rather than a note.
    assert ffmpeg.returncode == 0, "ffmpeg is not runnable (brew install ffmpeg)"
    with tempfile.TemporaryDirectory(prefix="xochi-phase-") as td:
        work = Path(td)
        r0 = check_p0(work)
        print("P0 check:", json.dumps(r0, ensure_ascii=False))
        r1 = check_p1(work)
        print("P1 check:", json.dumps(r1, ensure_ascii=False))
        r2 = check_p2()
        print("P2 check:", json.dumps(r2, ensure_ascii=False))
        r3 = check_p3(work)
        print("P3 check:", json.dumps(r3, ensure_ascii=False))
    # shell test still exists
    shell = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "test_desktop_shell.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    print("shell test exit:", shell.returncode)
    if shell.returncode != 0:
        print(shell.stdout[-500:] if shell.stdout else "")
        print(shell.stderr[-500:] if shell.stderr else "")
        return shell.returncode
    print("ALL PHASE CHECKS PASSED")
    return 0


def test_digest_phases() -> None:
    """Entry point for pytest; run this file directly to see the per-phase output."""
    assert main() == 0, "phase checks failed — run tests/test_digest_phases.py for detail"


if __name__ == "__main__":
    raise SystemExit(main())
