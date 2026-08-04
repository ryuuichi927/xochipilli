from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def clip_unit_seconds() -> float:
    """Default generation unit length (seconds). Longer segments are auto-split.

    xAI T2V accepts up to ~15s per request; keep headroom via env CLIP_UNIT_SECONDS.
    """
    try:
        v = float(os.environ.get("CLIP_UNIT_SECONDS") or "5")
    except ValueError:
        v = 5.0
    return max(2.0, min(v, 15.0))


def xai_max_single_seconds() -> float:
    """Prefer one xAI shot when segment duration fits (avoids brittle multi-part)."""
    try:
        v = float(os.environ.get("XAI_MAX_SINGLE_SEC") or "15")
    except ValueError:
        v = 15.0
    return max(5.0, min(v, 15.0))


def xai_chain_mode() -> str:
    """How multi-part xAI continuity is done: 'extension' (native) or 'i2v' (last-frame)."""
    m = (os.environ.get("XAI_CHAIN_MODE") or "extension").lower().strip()
    if m in {"i2v", "image", "frame", "last-frame", "last_frame"}:
        return "i2v"
    return "extension"


def xfade_seconds() -> float:
    """Technical micro-crossfade at hard seams (not cinematic fades).

    Default 0.12s (~3 frames at 24fps). Set XOCHI_XFADE_SEC=0 to disable.
    """
    try:
        v = float(os.environ.get("XOCHI_XFADE_SEC") or "0.12")
    except ValueError:
        v = 0.12
    return max(0.0, min(v, 0.35))


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return 0.0
    try:
        return float((r.stdout or "").strip() or 0)
    except ValueError:
        return 0.0


def _escape_drawtext(s: str) -> str:
    return (
        s.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def generate_mock_clip(
    out_path: Path,
    duration: float,
    user_prompt: str,
    tags: list[str],
    audio_segment: Path | None = None,
) -> dict[str, Any]:
    """Local stand-in video. Only when VIDEO_PROVIDER=mock."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.5, min(float(duration or 3.0), 30.0))
    label = (user_prompt or "segment").strip().replace("\n", " ")
    if len(label) > 80:
        label = label[:77] + "..."
    tagline = ", ".join(tags[:4]) if tags else "music-bias"
    text = _escape_drawtext(f"{label} | {tagline}")

    color = "0x1b2838"
    joined = " ".join(tags).lower()
    if "bright" in joined or "明るい" in joined:
        color = "0x3d5a80"
    if "dark" in joined or "暗い" in joined:
        color = "0x0d1b2a"
    if "fast" in joined or "疾走" in joined or "swift" in joined:
        color = "0x5c4d7a"

    vf = (
        f"drawtext=fontfile=/System/Library/Fonts/Supplemental/Arial Unicode.ttf:"
        f"text='{text}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=(h-text_h)/2:"
        f"box=1:boxcolor=black@0.45:boxborderw=16"
    )
    if not Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf").exists():
        vf = (
            f"drawtext=text='{text}':fontcolor=white:fontsize=28:"
            f"x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.45:boxborderw=16"
        )

    tmp_video = out_path.with_suffix(".silent.mp4")
    cmd_v = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1280x720:d={duration}:r=24",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-t",
        str(duration),
        str(tmp_video),
    ]
    r = subprocess.run(cmd_v, capture_output=True, text=True)
    if r.returncode != 0:
        cmd_v2 = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1280x720:d={duration}:r=24",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-t",
            str(duration),
            str(tmp_video),
        ]
        subprocess.run(cmd_v2, check=True, capture_output=True)

    if audio_segment and audio_segment.exists():
        cmd_m = [
            "ffmpeg",
            "-y",
            "-i",
            str(tmp_video),
            "-i",
            str(audio_segment),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
        subprocess.run(cmd_m, check=True, capture_output=True)
        tmp_video.unlink(missing_ok=True)
    else:
        tmp_video.replace(out_path)

    return {
        "provider": "mock",
        "path": str(out_path),
        "duration": duration,
        "note": "mock clip — VIDEO_PROVIDER=mock (placeholder only)",
        "is_mock": True,
    }


def extract_audio_segment(src_wav: Path, t0: float, t1: float, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.05, float(t1) - float(t0))
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(max(0.0, float(t0))),
        "-t",
        str(dur),
        "-i",
        str(src_wav),
        "-ac",
        "2",
        "-ar",
        "44100",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dst


def extract_last_frame(video_path: Path, out_jpg: Path) -> Path:
    """Grab near-end frame for continuity chaining (slightly before absolute end)."""
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.12",
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_jpg),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out_jpg.is_file() or out_jpg.stat().st_size < 100:
        cmd2 = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "reverse",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_jpg),
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True)
        if r2.returncode != 0 or not out_jpg.is_file():
            raise RuntimeError(f"ffmpeg last-frame failed: {(r.stderr or r2.stderr)[:400]}")
    return out_jpg


def _normalize_part(path: Path, work: Path, idx: int) -> Path:
    """Re-encode one part to stable 1280x720@24 for concat/xfade."""
    out = work / f"norm_{idx:02d}.mp4"
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(path),
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
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not out.is_file():
        raise RuntimeError(f"normalize failed part {idx}: {(r.stderr or '')[-400:]}")
    return out


def concat_video_files(paths: list[Path], out_path: Path, *, xfade: float | None = None) -> Path:
    """Concatenate mp4 parts. Optional micro-crossfade (technical glue, not cinematic)."""
    if not paths:
        raise ValueError("no parts to concat")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(paths) == 1:
        if paths[0].resolve() != out_path.resolve():
            out_path.write_bytes(paths[0].read_bytes())
        return out_path

    import tempfile
    import shutil

    xfade_d = xfade if xfade is not None else xfade_seconds()
    work = Path(tempfile.mkdtemp(prefix="xochi-concat-"))
    try:
        norms = [_normalize_part(p, work, i) for i, p in enumerate(paths)]

        if xfade_d <= 0.001 or len(norms) == 1:
            # hard cut via concat demuxer
            lst = work / "list.txt"
            lst.write_text(
                "\n".join(f"file '{p.resolve()}'" for p in norms) + "\n", encoding="utf-8"
            )
            r = subprocess.run(
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
                    "-movflags",
                    "+faststart",
                    str(out_path),
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0 or not out_path.is_file():
                r2 = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(lst),
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
                    ],
                    capture_output=True,
                    text=True,
                )
                if r2.returncode != 0 or not out_path.is_file():
                    raise RuntimeError(
                        f"ffmpeg concat failed: {(r.stderr or r2.stderr or '')[-600:]}"
                    )
            return out_path

        # Micro xfade chain: transition=fade, duration≈0.12s
        durs = [probe_duration(p) for p in norms]
        # Build filter_complex
        # [0][1]xfade=...:offset=d0-xfade[v01]; [v01][2]xfade=...:offset=...
        inputs: list[str] = []
        for p in norms:
            inputs.extend(["-i", str(p)])

        filters: list[str] = []
        prev_label = "0:v"
        acc = durs[0]
        for i in range(1, len(norms)):
            out_label = f"v{i:02d}" if i < len(norms) - 1 else "vout"
            offset = max(0.0, acc - xfade_d)
            filters.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={xfade_d:.3f}:offset={offset:.3f}[{out_label}]"
            )
            prev_label = out_label
            acc = acc + durs[i] - xfade_d

        fc = ";".join(filters)
        r = subprocess.run(
            [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                fc,
                "-map",
                "[vout]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "24",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0 or not out_path.is_file():
            # fallback hard-cut if xfade graph fails
            return concat_video_files(paths, out_path, xfade=0.0)
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)


async def generate_fal_clip(prompt: str, duration: float, out_path: Path) -> dict[str, Any]:
    import httpx

    key = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if not key:
        raise RuntimeError("FAL_KEY not set")

    model = os.environ.get("FAL_VIDEO_MODEL", "fal-ai/minimax-video")
    url = f"https://queue.fal.run/{model}"
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "duration": str(int(max(1, min(duration, 6))))}

    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"FAL error {r.status_code}: {r.text[:400]}")
        data = r.json()
        video_url = None
        if isinstance(data, dict):
            video_url = (
                (data.get("video") or {}).get("url")
                if isinstance(data.get("video"), dict)
                else data.get("video_url")
            )
            if not video_url and data.get("response_url"):
                for _ in range(60):
                    pr = await client.get(data["response_url"], headers=headers)
                    pj = pr.json()
                    status = pj.get("status")
                    if status in ("COMPLETED", "completed"):
                        resp = pj.get("response") or pj
                        video_url = (
                            (resp.get("video") or {}).get("url")
                            if isinstance(resp.get("video"), dict)
                            else resp.get("video_url")
                        )
                        break
                    if status in ("FAILED", "failed"):
                        raise RuntimeError(f"FAL failed: {pj}")
                    import asyncio

                    await asyncio.sleep(2)
        if not video_url:
            raise RuntimeError(f"FAL: no video url in response: {str(data)[:300]}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        vr = await client.get(video_url)
        vr.raise_for_status()
        out_path.write_bytes(vr.content)
        return {
            "provider": "fal",
            "path": str(out_path),
            "model": model,
            "url": video_url,
            "is_mock": False,
        }


def _xai_video_url_from_body(body: dict) -> str | None:
    video = body.get("video") or {}
    if not isinstance(video, dict):
        return None
    file_output = video.get("file_output") if isinstance(video.get("file_output"), dict) else {}
    for candidate in (
        file_output.get("public_url") if file_output else None,
        video.get("public_url"),
        video.get("url"),
        (video.get("file") or {}).get("url") if isinstance(video.get("file"), dict) else None,
    ):
        if candidate:
            return str(candidate)
    return None


def _normalize_xai_resolution(raw: str | None) -> str:
    r = (raw or "720p").strip().lower()
    if r in {"480", "480p"}:
        return "480p"
    if r in {"720", "720p"}:
        return "720p"
    if r in {"1080", "1080p", "fhd", "fullhd"}:
        return "1080p"
    return "720p"


async def _xai_poll_and_download(
    client: Any,
    base_url: str,
    headers: dict[str, str],
    request_id: str,
    out_path: Path,
    timeout_s: int,
    poll_s: float,
) -> tuple[str, dict[str, Any]]:
    import asyncio

    elapsed = 0.0
    last_status = "queued"
    done_body: dict[str, Any] = {}
    while elapsed < timeout_s:
        pr = await client.get(f"{base_url}/videos/{request_id}", headers=headers, timeout=30.0)
        if pr.status_code >= 400:
            raise RuntimeError(f"xAI poll {pr.status_code}: {pr.text[:400]}")
        done_body = pr.json()
        last_status = (done_body.get("status") or "").lower()
        if last_status == "done":
            break
        if last_status in {"failed", "error", "expired", "cancelled"}:
            msg = (
                ((done_body.get("error") or {}) if isinstance(done_body.get("error"), dict) else {}).get(
                    "message"
                )
                or done_body.get("message")
                or last_status
            )
            raise RuntimeError(f"xAI video {last_status}: {msg}")
        await asyncio.sleep(poll_s)
        elapsed += poll_s
    else:
        raise RuntimeError(f"xAI video timeout after {timeout_s}s (last={last_status})")

    video_url = _xai_video_url_from_body(done_body)
    if not video_url:
        raise RuntimeError(f"xAI done but no video url: {str(done_body)[:400]}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    vr = await client.get(video_url, timeout=180.0)
    vr.raise_for_status()
    out_path.write_bytes(vr.content)
    return video_url, done_body


async def generate_xai_clip(
    prompt: str,
    duration: float,
    out_path: Path,
    *,
    start_image: Path | None = None,
) -> dict[str, Any]:
    """Grok Imagine T2V / I2V via SuperGrok OAuth or XAI_API_KEY."""
    import base64
    import mimetypes
    import uuid

    import httpx

    from .xai_auth import resolve_xai_credentials

    creds = resolve_xai_credentials()
    api_key = creds["api_key"]
    base_url = str(creds["base_url"]).rstrip("/")
    aspect = (os.environ.get("XAI_VIDEO_ASPECT") or "16:9").strip()
    resolution = _normalize_xai_resolution(os.environ.get("XAI_VIDEO_RESOLUTION"))
    dur = int(max(1, min(round(float(duration or 5)), 15)))

    use_i2v = bool(start_image and Path(start_image).is_file())
    if use_i2v:
        model = (
            os.environ.get("XAI_VIDEO_I2V_MODEL")
            or os.environ.get("XAI_VIDEO_MODEL_I2V")
            or "grok-imagine-video-1.5"
        ).strip()
    else:
        model = (os.environ.get("XAI_VIDEO_MODEL") or "grok-imagine-video").strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Xochipilli/0.1 (local)",
        "x-idempotency-key": str(uuid.uuid4()),
    }
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "duration": dur,
        "aspect_ratio": aspect,
        "resolution": resolution,
    }
    if use_i2v:
        img_path = Path(start_image)
        mime = mimetypes.guess_type(img_path.name)[0] or "image/jpeg"
        b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
        payload["image"] = {"url": f"data:{mime};base64,{b64}"}

    timeout_s = int(os.environ.get("XAI_VIDEO_TIMEOUT") or "240")
    poll_s = float(os.environ.get("XAI_VIDEO_POLL") or "5")

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(f"{base_url}/videos/generations", headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"xAI submit {r.status_code}: {r.text[:500]}")
        body = r.json()
        request_id = body.get("request_id")
        if not request_id:
            raise RuntimeError(f"xAI: no request_id in {str(body)[:300]}")

        video_url, _ = await _xai_poll_and_download(
            client, base_url, headers, request_id, out_path, timeout_s, poll_s
        )

    return {
        "provider": "xai",
        "path": str(out_path),
        "model": model,
        "url": video_url,
        "request_id": request_id,
        "auth_source": creds.get("source"),
        "duration": dur,
        "resolution": resolution,
        "aspect_ratio": aspect,
        "chained": use_i2v,
        "start_image": str(start_image) if use_i2v else None,
        "mode": "i2v" if use_i2v else "t2v",
        "is_mock": False,
    }


async def extend_xai_clip(
    prompt: str,
    duration: float,
    source_video: Path,
    out_path: Path,
) -> dict[str, Any]:
    """Native xAI Video Extension: continue from an existing mp4 (not a still).

    POST /v1/videos/extensions
    - input video: 2–15s mp4 (data URI ok)
    - duration: length of NEW portion only (2–10s)
    - output: original + extension already stitched by the model
    - model: grok-imagine-video (extension does not use 1.5 I2V model)
    - resolution follows input, capped 720p by API
    """
    import base64
    import uuid

    import httpx

    from .xai_auth import resolve_xai_credentials

    src = Path(source_video)
    if not src.is_file() or src.stat().st_size < 1000:
        raise RuntimeError(f"extend: source video missing or too small: {src}")

    src_dur = probe_duration(src)
    if src_dur > 0 and src_dur < 1.8:
        raise RuntimeError(f"extend: source too short ({src_dur:.2f}s); need ≥2s")
    if src_dur > 15.5:
        raise RuntimeError(f"extend: source too long ({src_dur:.2f}s); API max 15s")

    # Extension length only — API range 2–10
    ext_dur = int(max(2, min(round(float(duration or 5)), 10)))

    creds = resolve_xai_credentials()
    api_key = creds["api_key"]
    base_url = str(creds["base_url"]).rstrip("/")
    model = (os.environ.get("XAI_VIDEO_EXTEND_MODEL") or "grok-imagine-video").strip()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "Xochipilli/0.1 (local)",
        "x-idempotency-key": str(uuid.uuid4()),
    }
    b64 = base64.b64encode(src.read_bytes()).decode("ascii")
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "duration": ext_dur,
        "video": {"url": f"data:video/mp4;base64,{b64}"},
    }

    timeout_s = int(os.environ.get("XAI_VIDEO_TIMEOUT") or "300")
    poll_s = float(os.environ.get("XAI_VIDEO_POLL") or "5")

    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(f"{base_url}/videos/extensions", headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"xAI extend submit {r.status_code}: {r.text[:500]}")
        body = r.json()
        request_id = body.get("request_id")
        if not request_id:
            raise RuntimeError(f"xAI extend: no request_id in {str(body)[:300]}")

        video_url, _ = await _xai_poll_and_download(
            client, base_url, headers, request_id, out_path, timeout_s, poll_s
        )

    return {
        "provider": "xai",
        "path": str(out_path),
        "model": model,
        "url": video_url,
        "request_id": request_id,
        "auth_source": creds.get("source"),
        "duration": ext_dur,
        "source_duration": src_dur,
        "mode": "extension",
        "chained": True,
        "is_mock": False,
    }


async def generate_clip(
    *,
    out_path: Path,
    duration: float,
    user_prompt: str,
    composed_prompt: str,
    tags: list[str],
    audio_segment: Path | None,
    start_image: Path | None = None,
    source_video: Path | None = None,
) -> dict[str, Any]:
    """Dispatch to the configured provider.

    source_video: when set under xai + extension mode, uses native Video Extension.
    Real providers raise on failure. Mock only when VIDEO_PROVIDER=mock.
    """
    provider = (os.environ.get("VIDEO_PROVIDER") or "mock").lower().strip()
    if provider in {"grok", "grok-imagine", "xai-oauth", "imagine"}:
        provider = "xai"

    if provider == "fal":
        return await generate_fal_clip(composed_prompt, duration, out_path)

    if provider == "xai":
        if source_video and Path(source_video).is_file():
            return await extend_xai_clip(
                composed_prompt, duration, Path(source_video), out_path
            )
        return await generate_xai_clip(
            composed_prompt, duration, out_path, start_image=start_image
        )

    meta = generate_mock_clip(out_path, duration, user_prompt, tags, audio_segment)
    if start_image:
        meta["chained"] = True
        meta["note"] = (meta.get("note") or "") + " (mock; continuity frame noted only)"
    if source_video:
        meta["mode"] = "extension-mock"
    return meta
