from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_scenes(video_path: Path) -> list[dict[str, Any]]:
    """P3.3 PySceneDetect marks on a take mp4."""
    try:
        from scenedetect import ContentDetector, detect
    except ImportError as e:
        raise RuntimeError("scenedetect not installed") from e

    if not video_path.exists():
        raise FileNotFoundError(str(video_path))

    scene_list = detect(str(video_path), ContentDetector())
    marks: list[dict[str, Any]] = []
    for i, (start, end) in enumerate(scene_list):
        marks.append(
            {
                "index": i,
                "t0": round(start.get_seconds(), 3),
                "t1": round(end.get_seconds(), 3),
                "source": "PySceneDetect.ContentDetector",
            }
        )
    return marks
