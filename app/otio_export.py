from __future__ import annotations

from pathlib import Path
from typing import Any


def export_project_otio(project: dict[str, Any], project_dir: Path, out_path: Path) -> Path:
    """P3.2 OpenTimelineIO export of adopted segment clips (or empty gaps)."""
    try:
        import opentimelineio as otio
    except ImportError as e:
        raise RuntimeError("opentimelineio not installed") from e

    tl = otio.schema.Timeline(name=str(project.get("title") or project.get("id") or "xochipilli"))
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    tl.tracks.append(track)

    segs = sorted(project.get("segments") or [], key=lambda s: float(s.get("t0") or 0))
    cursor = 0.0
    rate = 24.0

    for seg in segs:
        t0 = float(seg.get("t0") or 0)
        t1 = float(seg.get("t1") or t0)
        if t0 > cursor + 1e-3:
            gap_dur = t0 - cursor
            track.append(
                otio.schema.Gap(
                    source_range=otio.opentime.TimeRange(
                        start_time=otio.opentime.RationalTime(0, rate),
                        duration=otio.opentime.RationalTime(gap_dur * rate, rate),
                    )
                )
            )
        dur = max(0.01, t1 - t0)
        media_ref = None
        v = seg.get("video") or {}
        # adopted clip path if present
        clip_name = None
        if isinstance(v, dict):
            clips = v.get("clips") or []
            if clips and isinstance(clips[0], dict):
                clip_name = clips[0].get("file") or clips[0].get("path")
            clip_name = clip_name or v.get("file") or v.get("path")
        if clip_name:
            media_path = project_dir / "clips" / str(clip_name)
            if not media_path.exists():
                media_path = project_dir / str(clip_name)
            if media_path.exists():
                media_ref = otio.schema.ExternalReference(target_url=media_path.resolve().as_uri())

        clip = otio.schema.Clip(
            name=f"{seg.get('id', 'seg')} {t0:.2f}-{t1:.2f}",
            media_reference=media_ref
            or otio.schema.MissingReference(name="no-clip-yet"),
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, rate),
                duration=otio.opentime.RationalTime(dur * rate, rate),
            ),
        )
        track.append(clip)
        cursor = t1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(tl, str(out_path))
    return out_path
