"""Stitch adopted segment clips into one continuous program MP4 (local ffmpeg)."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-800:]
        raise RuntimeError(f"ffmpeg failed: {err}")


def _active_clip(seg: dict[str, Any]) -> dict[str, Any] | None:
    clips = seg.get("clips") or []
    aid = seg.get("active_clip_id")
    if aid:
        hit = next((c for c in clips if c.get("id") == aid), None)
        if hit and hit.get("file"):
            return hit
    if isinstance(seg.get("video"), dict) and seg["video"].get("file"):
        return seg["video"]
    if clips and clips[-1].get("file"):
        return clips[-1]
    return None


def adopted_items(project: dict[str, Any]) -> list[dict[str, Any]]:
    segs = sorted(project.get("segments") or [], key=lambda s: float(s.get("t0") or 0))
    out: list[dict[str, Any]] = []
    for s in segs:
        c = _active_clip(s)
        if not c:
            continue
        t0 = float(s.get("t0") or 0)
        t1 = float(s.get("t1") or 0)
        if t1 <= t0 + 0.05:
            continue
        out.append({"seg": s, "clip": c, "t0": t0, "t1": t1, "dur": t1 - t0})
    return out


def _make_black(path: Path, duration: float, *, w: int = 1280, h: int = 720, fps: int = 24) -> None:
    dur = max(0.05, float(duration))
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s={w}x{h}:r={fps}",
            "-t",
            f"{dur:.4f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
    )


def _normalize_clip(
    src: Path,
    dst: Path,
    duration: float,
    *,
    w: int = 1280,
    h: int = 720,
    fps: int = 24,
) -> None:
    """Fit source into fixed canvas/fps and force exact duration (pad last frame if short)."""
    dur = max(0.05, float(duration))
    # scale+pad, then tpad to fill, then hard -t
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={fps},format=yuv420p,"
        f"tpad=stop_mode=clone:stop_duration=30"
    )
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-t",
            f"{dur:.4f}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(dst),
        ]
    )


def build_program_mp4(
    project: dict[str, Any],
    clips_dir: Path,
    out_path: Path,
    *,
    include_gaps: bool = True,
) -> dict[str, Any]:
    """Build continuous program from adopted clips. Optional black gaps between segments."""
    items = adopted_items(project)
    if not items:
        raise ValueError("no adopted clips")

    clips_dir = Path(clips_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="xochi-program-"))
    part_paths: list[Path] = []
    manifest: list[dict[str, Any]] = []

    try:
        cursor: float | None = None
        for i, it in enumerate(items):
            src = clips_dir / it["clip"]["file"]
            if not src.is_file():
                raise FileNotFoundError(f"missing clip file: {it['clip']['file']}")

            if include_gaps and cursor is not None:
                gap = it["t0"] - cursor
                if gap > 0.04:
                    gpath = work / f"gap_{i:03d}.mp4"
                    _make_black(gpath, gap)
                    part_paths.append(gpath)
                    manifest.append({"type": "gap", "t0": cursor, "t1": it["t0"], "dur": gap})

            ppath = work / f"part_{i:03d}.mp4"
            _normalize_clip(src, ppath, it["dur"])
            part_paths.append(ppath)
            manifest.append(
                {
                    "type": "clip",
                    "segment_id": it["seg"].get("id"),
                    "file": it["clip"].get("file"),
                    "t0": it["t0"],
                    "t1": it["t1"],
                    "dur": it["dur"],
                }
            )
            cursor = it["t1"]

        # concat
        lst = work / "list.txt"
        lines = []
        for p in part_paths:
            # concat demuxer needs escaped single quotes
            lines.append(f"file '{p.resolve()}'")
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tmp_out = work / "program.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c",
                "copy",
                str(tmp_out),
            ]
        )
        # re-encode once for clean timestamps + fixed 24fps canvas (copy can glitch)
        _run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_out),
                "-an",
                "-vf",
                "scale=1280:720:force_original_aspect_ratio=decrease,"
                "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p",
                "-r",
                "24",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
        )

        total = sum(m["dur"] for m in manifest)
        return {
            "file": out_path.name,
            "path": str(out_path),
            "bytes": out_path.stat().st_size if out_path.is_file() else 0,
            "clip_count": sum(1 for m in manifest if m["type"] == "clip"),
            "gap_count": sum(1 for m in manifest if m["type"] == "gap"),
            "duration_sec": round(total, 4),
            "t0": items[0]["t0"],
            "t1": items[-1]["t1"],
            "manifest": manifest,
            "id": "prog_" + uuid.uuid4().hex[:8],
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
