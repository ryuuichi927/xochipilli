from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .paths import THEORY


def load_theory() -> dict[str, Any]:
    return json.loads((THEORY / "digest_v0.json").read_text(encoding="utf-8"))


def _ffmpeg_to_wav(src: Path, dst: Path, sr: int = 22050) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        str(sr),
        "-vn",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _stft_mag(y: np.ndarray, n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    if len(y) < n_fft:
        y = np.pad(y, (0, n_fft - len(y)))
    window = np.hanning(n_fft).astype(np.float64)
    frames = 1 + max(0, (len(y) - n_fft) // hop)
    out = np.empty((n_fft // 2 + 1, frames), dtype=np.float64)
    for i in range(frames):
        start = i * hop
        frame = y[start : start + n_fft] * window
        spec = np.fft.rfft(frame)
        out[:, i] = np.abs(spec)
    return out


def _estimate_tempo(onset_env: np.ndarray, fps: float) -> float:
    """Crude tempo from onset envelope autocorrelation. Returns BPM."""
    if onset_env.size < 8:
        return 120.0
    x = onset_env - float(np.mean(onset_env))
    if np.allclose(x, 0):
        return 120.0
    corr = np.correlate(x, x, mode="full")[len(x) - 1 :]
    # search 60–180 BPM
    min_lag = max(1, int(fps * 60.0 / 180.0))
    max_lag = min(len(corr) - 1, int(fps * 60.0 / 60.0))
    if max_lag <= min_lag:
        return 120.0
    segment = corr[min_lag : max_lag + 1]
    lag = int(np.argmax(segment)) + min_lag
    bpm = 60.0 * fps / lag
    return float(np.clip(bpm, 50.0, 200.0))


def digest_audio(src_audio: Path, work_dir: Path) -> dict[str, Any]:
    """Import = digest. Write analysis wav + feature payload."""
    theory = load_theory()
    sr = int(theory.get("analysis_sr", 22050))
    analysis_wav = work_dir / "analysis.wav"
    _ffmpeg_to_wav(src_audio, analysis_wav, sr=sr)

    y, file_sr = sf.read(str(analysis_wav), always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    y = y.astype(np.float64)
    if file_sr != sr:
        # soundfile already at target via ffmpeg
        sr = int(file_sr)

    duration = float(len(y) / sr) if sr else 0.0
    hop = 512
    n_fft = 2048
    mag = _stft_mag(y, n_fft=n_fft, hop=hop)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)
    fps = sr / hop

    # frame RMS from time domain
    n_frames = mag.shape[1]
    rms = np.zeros(n_frames, dtype=np.float64)
    for i in range(n_frames):
        start = i * hop
        frame = y[start : start + n_fft]
        if frame.size == 0:
            continue
        rms[i] = float(np.sqrt(np.mean(frame**2) + 1e-12))

    # spectral centroid per frame
    denom = np.sum(mag, axis=0) + 1e-12
    centroid = np.sum(freqs[:, None] * mag, axis=0) / denom

    # low vs high energy
    split_hz = 250.0
    low_mask = freqs < split_hz
    high_mask = freqs >= split_hz
    low_e = np.sum(mag[low_mask, :], axis=0) + 1e-12
    high_e = np.sum(mag[high_mask, :], axis=0) + 1e-12
    low_high = low_e / high_e

    # onset-ish: positive rms diff
    onset = np.maximum(0.0, np.diff(rms, prepend=rms[0]))
    onset_density = float(np.mean(onset > (np.median(onset) + np.std(onset) * 0.5)) * fps)
    tempo = _estimate_tempo(onset, fps=fps)

    # waveform peaks for UI (max abs in bins)
    n_peaks = min(2000, max(100, int(duration * 100)))
    peaks = []
    if len(y) > 0:
        bin_size = max(1, len(y) // n_peaks)
        for i in range(n_peaks):
            chunk = y[i * bin_size : (i + 1) * bin_size]
            if chunk.size == 0:
                peaks.append(0.0)
            else:
                peaks.append(float(np.max(np.abs(chunk))))
        mx = max(peaks) or 1.0
        peaks = [p / mx for p in peaks]

    times = (np.arange(n_frames) * hop / sr).tolist()

    global_feat = {
        "tempo_bpm": round(tempo, 2),
        "rms_mean": round(float(np.mean(rms)), 5),
        "rms_std": round(float(np.std(rms)), 5),
        "spectral_centroid_mean_hz": round(float(np.mean(centroid)), 1),
        "low_high_ratio": round(float(np.mean(low_high)), 4),
        "onset_density": round(onset_density, 3),
        "duration_sec": round(duration, 3),
        "sr": sr,
    }

    # store series lightly for segment queries
    series = {
        "times": [round(t, 4) for t in times],
        "rms": [round(float(v), 5) for v in rms.tolist()],
        "centroid_hz": [round(float(v), 1) for v in centroid.tolist()],
        "low_high_ratio": [round(float(v), 4) for v in low_high.tolist()],
        "onset": [round(float(v), 5) for v in onset.tolist()],
    }

    payload = {
        "theory_id": theory.get("theory_id", "digest_v0"),
        "global": global_feat,
        "waveform_peaks": peaks,
        "series": series,
        "analysis_wav": str(analysis_wav.name),
    }
    out_path = work_dir / "digest.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def segment_features(digest: dict[str, Any], t0: float, t1: float) -> dict[str, Any]:
    """Average series features inside [t0, t1]."""
    if t1 < t0:
        t0, t1 = t1, t0
    series = digest.get("series") or {}
    times = series.get("times") or []
    if not times:
        g = dict(digest.get("global") or {})
        g["t0"] = t0
        g["t1"] = t1
        g["duration_sec"] = round(t1 - t0, 3)
        return g

    idx = [i for i, t in enumerate(times) if t0 <= t <= t1]
    if not idx:
        # nearest
        arr = np.array(times, dtype=float)
        mid = 0.5 * (t0 + t1)
        i = int(np.argmin(np.abs(arr - mid)))
        idx = [i]

    def mean_of(key: str, default: float = 0.0) -> float:
        vals = series.get(key) or []
        picked = [vals[i] for i in idx if i < len(vals)]
        if not picked:
            return default
        return float(np.mean(picked))

    onset_vals = [series.get("onset", [0])[i] for i in idx if i < len(series.get("onset", []))]
    fps = 1.0
    if len(times) >= 2:
        fps = 1.0 / max(1e-6, times[1] - times[0])
    onset_density = float(np.mean(np.array(onset_vals) > (np.median(onset_vals) + 1e-9)) * fps) if onset_vals else 0.0

    # reuse global tempo as segment tempo proxy (D1)
    tempo = float((digest.get("global") or {}).get("tempo_bpm") or 120.0)

    return {
        "t0": round(t0, 3),
        "t1": round(t1, 3),
        "duration_sec": round(t1 - t0, 3),
        "tempo_bpm": round(tempo, 2),
        "rms_mean": round(mean_of("rms"), 5),
        "rms_std": round(float(np.std([series.get("rms", [0])[i] for i in idx])), 5) if idx else 0.0,
        "spectral_centroid_mean_hz": round(mean_of("centroid_hz"), 1),
        "low_high_ratio": round(mean_of("low_high_ratio"), 4),
        "onset_density": round(onset_density, 3),
    }
