from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


def separate_stems(src_audio: Path, work_dir: Path) -> dict[str, Any]:
    """P0.3 Demucs optional. Returns map stem_name -> relative path under work_dir.

    Requires: pip install demucs (pulls torch). Skip if missing.
    """
    stems_dir = work_dir / "stems"
    stems_dir.mkdir(parents=True, exist_ok=True)

    try:
        import demucs  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "demucs not installed. Optional: pip install demucs  (large torch dep)"
        ) from e

    # demucs CLI is the stable path
    out_root = work_dir / "demucs_out"
    if out_root.exists():
        shutil.rmtree(out_root, ignore_errors=True)
    cmd = [
        "python",
        "-m",
        "demucs",
        "-n",
        "htdemucs",
        "-o",
        str(out_root),
        str(src_audio),
    ]
    # prefer project venv python if available
    import sys

    cmd[0] = sys.executable
    subprocess.run(cmd, check=True, capture_output=True, timeout=3600)

    # demucs writes out_root/htdemucs/<trackname>/*.wav
    found: dict[str, str] = {}
    for wav in out_root.rglob("*.wav"):
        name = wav.stem.lower()
        if name in {"drums", "bass", "vocals", "other"}:
            dest = stems_dir / f"{name}.wav"
            shutil.copy2(wav, dest)
            found[name] = f"stems/{name}.wav"
    if not found:
        raise RuntimeError("demucs ran but no stems found")
    return found
