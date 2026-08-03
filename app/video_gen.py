from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from typing import Any


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
    """
    Local stand-in video so the D1 loop works without a paid video API.
    Colored field + prompt text; optional mux of the segment audio.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.5, min(float(duration or 3.0), 30.0))
    label = (user_prompt or "segment").strip().replace("\n", " ")
    if len(label) > 80:
        label = label[:77] + "..."
    tagline = ", ".join(tags[:4]) if tags else "music-bias"
    text = _escape_drawtext(f"{label} | {tagline}")

    # color from tags
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
    # fallback font
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
        # retry without drawtext
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
        "note": "mock clip — set VIDEO_PROVIDER=fal and FAL_KEY for real gen later",
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
    """Grab near-end frame for continuity chaining."""
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    # -sseof seeks from end; fallback to last decoded frame
    cmd = [
        "ffmpeg",
        "-y",
        "-sseof",
        "-0.08",
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
            "select=eq(n\\,0)",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_jpg),
        ]
        # better: take last frame via reverse
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


async def generate_fal_clip(prompt: str, duration: float, out_path: Path) -> dict[str, Any]:
    import httpx

    key = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if not key:
        raise RuntimeError("FAL_KEY not set")

    # Generic fal queue endpoint pattern — model id overridable
    model = os.environ.get("FAL_VIDEO_MODEL", "fal-ai/minimax-video")
    url = f"https://queue.fal.run/{model}"
    headers = {"Authorization": f"Key {key}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "duration": str(int(max(1, min(duration, 6))))}

    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"FAL error {r.status_code}: {r.text[:400]}")
        data = r.json()
        # Some models return sync video url
        video_url = None
        if isinstance(data, dict):
            video_url = (
                (data.get("video") or {}).get("url")
                if isinstance(data.get("video"), dict)
                else data.get("video_url")
            )
            if not video_url and data.get("response_url"):
                # poll
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
        return {"provider": "fal", "path": str(out_path), "model": model, "url": video_url}


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


async def generate_xai_clip(
    prompt: str,
    duration: float,
    out_path: Path,
    *,
    start_image: Path | None = None,
) -> dict[str, Any]:
    """Grok Imagine video via SuperGrok OAuth (Ben's Tool) or XAI_API_KEY.

    Text-to-video: grok-imagine-video (default).
    Image-to-video (continuity): start_image → grok-imagine-video-1.5 by default.
    """
    import asyncio
    import base64
    import mimetypes
    import uuid

    import httpx

    from .xai_auth import resolve_xai_credentials

    creds = resolve_xai_credentials()
    api_key = creds["api_key"]
    base_url = str(creds["base_url"]).rstrip("/")
    aspect = (os.environ.get("XAI_VIDEO_ASPECT") or "16:9").strip()
    resolution = (os.environ.get("XAI_VIDEO_RESOLUTION") or "720p").strip().lower()
    if resolution not in {"480p", "720p"}:
        resolution = "720p"
    dur = int(max(1, min(round(float(duration or 8)), 15)))

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
) -> dict[str, Any]:
    provider = (os.environ.get("VIDEO_PROVIDER") or "mock").lower().strip()
    # aliases
    if provider in {"grok", "grok-imagine", "xai-oauth", "imagine"}:
        provider = "xai"

    if provider == "fal":
        try:
            return await generate_fal_clip(composed_prompt, duration, out_path)
        except Exception as e:
            meta = generate_mock_clip(out_path, duration, user_prompt, tags, audio_segment)
            meta["fal_error"] = str(e)
            meta["note"] = f"fal failed, used mock: {e}"
            return meta

    if provider == "xai":
        try:
            return await generate_xai_clip(
                composed_prompt, duration, out_path, start_image=start_image
            )
        except Exception as e:
            meta = generate_mock_clip(out_path, duration, user_prompt, tags, audio_segment)
            meta["xai_error"] = str(e)
            meta["note"] = f"xai failed, used mock: {e}"
            if start_image:
                meta["chain_attempted"] = True
            return meta

    meta = generate_mock_clip(out_path, duration, user_prompt, tags, audio_segment)
    if start_image:
        meta["chained"] = True
        meta["note"] = (meta.get("note") or "") + " (mock; continuity frame noted only)"
    return meta
