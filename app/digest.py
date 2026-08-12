from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .paths import THEORY

try:
    import librosa
except ImportError:  # pragma: no cover
    librosa = None  # type: ignore


def load_theory() -> dict[str, Any]:
    return json.loads((THEORY / "digest_v0.json").read_text(encoding="utf-8"))


def _ffmpeg_to_wav(src: Path, dst: Path, sr: int = 22050, mono: bool = True) -> None:
    """P0.1 — analysis wav via ffmpeg (do not replace this path lightly)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1" if mono else "2",
        "-ar",
        str(sr),
        "-vn",
        str(dst),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _waveform_peaks(y: np.ndarray, duration: float) -> list[float]:
    n_peaks = min(2000, max(100, int(duration * 100)))
    peaks: list[float] = []
    if len(y) <= 0:
        return peaks
    bin_size = max(1, len(y) // n_peaks)
    for i in range(n_peaks):
        chunk = y[i * bin_size : (i + 1) * bin_size]
        peaks.append(float(np.max(np.abs(chunk))) if chunk.size else 0.0)
    mx = max(peaks) or 1.0
    return [p / mx for p in peaks]


def _downsample_series(times: np.ndarray, values: np.ndarray, max_points: int = 800) -> tuple[list[float], list[float]]:
    n = len(times)
    if n == 0:
        return [], []
    if n <= max_points:
        return [round(float(t), 4) for t in times], [round(float(v), 5) for v in values]
    idx = np.linspace(0, n - 1, max_points).astype(int)
    return (
        [round(float(times[i]), 4) for i in idx],
        [round(float(values[i]), 5) for i in idx],
    )


def _structure_candidates_librosa(y: np.ndarray, sr: int, duration: float) -> list[dict[str, Any]]:
    """P1 fallback: novelty + agglomerative-ish boundaries via librosa (no MSAF install)."""
    if librosa is None or duration < 3.0:
        return []
    try:
        # The affinity matrix below is dense and frames². At hop=512 a 3.5 min track needs
        # ~670 MB (and several copies), which thrashed memory for minutes. Coarsen the hop
        # so frames stay bounded — boundaries are ~8 s apart, so this costs no accuracy.
        max_frames = 1200
        hop = 512
        est_frames = int(len(y) / hop) + 1
        if est_frames > max_frames:
            hop *= -(-est_frames // max_frames)  # ceil division
        y = np.asarray(y, dtype=np.float32)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)
        # Self-similarity novelty (checkerboard kernel via lag matrix)
        R = librosa.segment.recurrence_matrix(mfcc, mode="affinity", metric="cosine", sparse=False)
        # path enhancement + novelty curve
        nov = np.mean(np.abs(np.diff(R, axis=1)), axis=0)
        nov = librosa.util.normalize(nov)
        # peak pick
        fps = sr / hop
        # aim ~1 boundary per 12–20s
        wait = max(8, int(fps * 8))
        peaks = librosa.util.peak_pick(
            nov,
            pre_max=wait // 2,
            post_max=wait // 2,
            pre_avg=wait,
            post_avg=wait,
            delta=0.08,
            wait=wait,
        )
        times = librosa.frames_to_time(peaks, sr=sr, hop_length=hop)
        bounds = [0.0] + [float(t) for t in times if 0.4 < float(t) < duration - 0.4] + [duration]
        # unique sort
        uniq: list[float] = []
        for t in bounds:
            if not uniq or abs(t - uniq[-1]) > 0.35:
                uniq.append(t)
        if uniq[-1] < duration - 0.05:
            uniq.append(duration)
        labels = ["intro", "verse", "prechorus", "chorus", "bridge", "outro"]
        cands: list[dict[str, Any]] = []
        for i in range(len(uniq) - 1):
            t0, t1 = uniq[i], uniq[i + 1]
            if t1 - t0 < 1.0:
                continue
            lab = labels[min(i, len(labels) - 1)]
            cands.append(
                {
                    "t0": round(t0, 3),
                    "t1": round(t1, 3),
                    "label": lab,
                    "source": "librosa_novelty",
                    "confidence": 0.45,
                }
            )
        return cands
    except Exception:
        return []


def digest_audio(
    src_audio: Path,
    work_dir: Path,
    *,
    run_stems: bool | None = None,
    run_lyrics: bool | None = None,
) -> dict[str, Any]:
    """Import = digest. P0 librosa core; optional stems/lyrics hooks."""
    theory = load_theory()
    sr = int(theory.get("analysis_sr", 22050))
    analysis_wav = work_dir / "analysis.wav"
    _ffmpeg_to_wav(src_audio, analysis_wav, sr=sr, mono=True)

    if librosa is None:
        raise RuntimeError("librosa is required for digest (pip install librosa)")

    y, file_sr = librosa.load(str(analysis_wav), sr=sr, mono=True)
    y = y.astype(np.float64)
    duration = float(librosa.get_duration(y=y, sr=sr))
    hop = 512

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=hop, units="frames")
    if isinstance(tempo, np.ndarray):
        tempo_bpm = float(np.atleast_1d(tempo)[0])
    else:
        tempo_bpm = float(tempo)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop)
    # downbeat proxy: every 4 beats from first
    downbeat_times = beat_times[::4] if len(beat_times) else np.array([])

    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    cent = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onset_frames = librosa.onset.onset_detect(
        y=y, sr=sr, hop_length=hop, units="frames", backtrack=False
    )
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    # low vs high band energy via mel
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=hop))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    low_mask = freqs < 250.0
    high_mask = freqs >= 250.0
    low_e = np.sum(S[low_mask, :], axis=0) + 1e-12
    high_e = np.sum(S[high_mask, :], axis=0) + 1e-12
    # align lengths
    n = min(len(rms), len(cent), len(onset_env), len(low_e), len(times))
    rms, cent, onset_env, low_e, high_e, times = (
        rms[:n],
        cent[:n],
        onset_env[:n],
        low_e[:n],
        high_e[:n],
        times[:n],
    )
    low_high = low_e / high_e
    fps = float(sr / hop)
    onset_density = float(len(onset_frames) / max(duration, 1e-6))

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    chroma_mean = [round(float(v), 4) for v in np.mean(chroma, axis=1)]

    t_s, rms_s = _downsample_series(times, rms)
    _, cent_s = _downsample_series(times, cent)
    _, lh_s = _downsample_series(times, low_high)
    _, on_s = _downsample_series(times, onset_env)

    peaks = _waveform_peaks(y, duration)

    structure = _structure_candidates_librosa(y, sr, duration)

    global_feat = {
        "tempo_bpm": round(tempo_bpm, 2),
        "rms_mean": round(float(np.mean(rms)), 5),
        "rms_std": round(float(np.std(rms)), 5),
        "spectral_centroid_mean_hz": round(float(np.mean(cent)), 1),
        "low_high_ratio": round(float(np.mean(low_high)), 4),
        "onset_density": round(onset_density, 3),
        "duration_sec": round(duration, 3),
        "sr": sr,
        "n_beats": int(len(beat_times)),
        "engine": "librosa",
        "chroma_mean": chroma_mean,
    }

    series = {
        "times": t_s,
        "rms": rms_s,
        "centroid_hz": cent_s,
        "low_high_ratio": lh_s,
        "onset": on_s,
    }

    payload: dict[str, Any] = {
        "theory_id": theory.get("theory_id", "digest_v0"),
        "global": global_feat,
        "waveform_peaks": peaks,
        "series": series,
        "beats": {
            "times": [round(float(t), 4) for t in beat_times.tolist()],
            "downbeat_times": [round(float(t), 4) for t in np.atleast_1d(downbeat_times).tolist()],
        },
        "structure_candidates": structure,
        "lyrics": [],
        "stems": {},
        "analysis_wav": str(analysis_wav.name),
        "phase": {"p0": True, "p1_structure": bool(structure)},
    }

    # Optional heavy paths (env or args)
    if run_stems is None:
        run_stems = os.environ.get("XOCHI_RUN_STEMS", "").strip() in {"1", "true", "yes"}
    if run_lyrics is None:
        run_lyrics = os.environ.get("XOCHI_RUN_LYRICS", "").strip() in {"1", "true", "yes"}

    if run_stems:
        try:
            from . import stems as stems_mod

            payload["stems"] = stems_mod.separate_stems(src_audio, work_dir)
            payload["phase"]["p0_stems"] = bool(payload["stems"])
        except Exception as e:
            payload["stems_error"] = str(e)
            payload["phase"]["p0_stems"] = False

    if run_lyrics:
        try:
            from . import lyrics_asr

            audio_for_lyrics = work_dir / "stems" / "vocals.wav"
            if not audio_for_lyrics.exists():
                audio_for_lyrics = analysis_wav
            payload["lyrics"] = lyrics_asr.transcribe_timed(audio_for_lyrics)
            payload["phase"]["p1_lyrics"] = bool(payload["lyrics"])
        except Exception as e:
            payload["lyrics_error"] = str(e)
            payload["phase"]["p1_lyrics"] = False

    # Try all-in-one structure upgrade if installed
    try:
        from . import structure as structure_mod

        better = structure_mod.try_all_in_one(src_audio, work_dir)
        if better:
            payload["structure_candidates"] = better
            payload["phase"]["p1_structure_engine"] = "all-in-one"
        else:
            payload["phase"]["p1_structure_engine"] = "librosa_novelty"
    except Exception:
        payload["phase"]["p1_structure_engine"] = "librosa_novelty"

    out_path = work_dir / "digest.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def segment_features(digest: dict[str, Any], t0: float, t1: float) -> dict[str, Any]:
    """Average series features inside [t0, t1] + music_summary for MUSIC WINDOW."""
    if t1 < t0:
        t0, t1 = t1, t0
    series = digest.get("series") or {}
    times = series.get("times") or []
    g = digest.get("global") or {}
    tempo = float(g.get("tempo_bpm") or 120.0)

    if not times:
        out = dict(g)
        out["t0"] = t0
        out["t1"] = t1
        out["duration_sec"] = round(t1 - t0, 3)
        out["music_summary"] = _music_summary(out, digest, t0, t1)
        return out

    idx = [i for i, t in enumerate(times) if t0 <= float(t) <= t1]
    if not idx:
        arr = np.array(times, dtype=float)
        mid = 0.5 * (t0 + t1)
        i = int(np.argmin(np.abs(arr - mid)))
        idx = [i]

    def mean_of(key: str, default: float = 0.0) -> float:
        vals = series.get(key) or []
        picked = [float(vals[i]) for i in idx if i < len(vals)]
        return float(np.mean(picked)) if picked else default

    rms_vals = [float((series.get("rms") or [0])[i]) for i in idx if i < len(series.get("rms") or [])]
    onset_vals = [
        float((series.get("onset") or [0])[i]) for i in idx if i < len(series.get("onset") or [])
    ]
    fps = 1.0
    if len(times) >= 2:
        fps = 1.0 / max(1e-6, float(times[1]) - float(times[0]))
    thr = float(np.median(onset_vals) + 1e-9) if onset_vals else 0.0
    onset_density = float(np.mean(np.array(onset_vals) > thr) * fps) if onset_vals else 0.0

    # beats in window
    beat_times = (digest.get("beats") or {}).get("times") or []
    n_beats = sum(1 for b in beat_times if t0 <= float(b) <= t1)

    # structure label if any candidate covers midpoint
    mid = 0.5 * (t0 + t1)
    label = None
    for c in digest.get("structure_candidates") or []:
        if float(c.get("t0", -1)) <= mid <= float(c.get("t1", -1)):
            label = c.get("label")
            break

    # lyrics snippet
    lyric_bits = []
    for ly in digest.get("lyrics") or []:
        lt0 = float(ly.get("t0", 0))
        lt1 = float(ly.get("t1", lt0))
        if lt1 >= t0 and lt0 <= t1:
            txt = str(ly.get("text") or "").strip()
            if txt:
                lyric_bits.append(txt)
    lyric_snip = " ".join(lyric_bits)[:180]

    feat = {
        "t0": round(t0, 3),
        "t1": round(t1, 3),
        "duration_sec": round(t1 - t0, 3),
        "tempo_bpm": round(tempo, 2),
        "rms_mean": round(mean_of("rms"), 5),
        "rms_std": round(float(np.std(rms_vals)), 5) if rms_vals else 0.0,
        "spectral_centroid_mean_hz": round(mean_of("centroid_hz"), 1),
        "low_high_ratio": round(mean_of("low_high_ratio"), 4),
        "onset_density": round(onset_density, 3),
        "n_beats_in_window": n_beats,
        "structure_label": label,
        "lyrics_snippet": lyric_snip,
    }
    feat["music_summary"] = _music_summary(feat, digest, t0, t1)
    return feat


def _music_summary(feat: dict[str, Any], digest: dict[str, Any], t0: float, t1: float) -> str:
    """One plain paragraph for MUSIC WINDOW injection."""
    bpm = feat.get("tempo_bpm") or (digest.get("global") or {}).get("tempo_bpm") or "?"
    lab = feat.get("structure_label") or "section"
    dens = float(feat.get("onset_density") or 0)
    rms = float(feat.get("rms_mean") or 0)
    cent = float(feat.get("spectral_centroid_mean_hz") or 0)
    energy = "high energy" if rms >= 0.08 else ("low energy" if rms <= 0.03 else "mid energy")
    motion = "dense onsets" if dens >= 2.5 else ("sparse onsets" if dens < 1.0 else "moderate event density")
    bright = "brighter timbre" if cent >= 2200 else ("darker timbre" if cent <= 1200 else "balanced timbre")
    ly = (feat.get("lyrics_snippet") or "").strip()
    parts = [
        f"Music window {t0:.1f}–{t1:.1f}s ({feat.get('duration_sec', t1 - t0):.1f}s).",
        f"Approx. {lab}, tempo ~{bpm} BPM, {energy}, {motion}, {bright}.",
    ]
    if ly:
        parts.append(f'Lyrics in window (approx): "{ly}"')
    return " ".join(parts)


def candidates_to_segments_payload(digest: dict[str, Any]) -> list[dict[str, Any]]:
    """P1: structure_candidates → pin-ready rows (caller creates real segments)."""
    return list(digest.get("structure_candidates") or [])
