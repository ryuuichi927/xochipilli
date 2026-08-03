from __future__ import annotations

from typing import Any


def emotion_keywords(feat: dict[str, Any]) -> list[str]:
    """
    Reference-only keywords from thin signal rules (D1).
    Not forced on the editor. Unmatch is logged separately.
    """
    tempo = float(feat.get("tempo_bpm") or 120)
    cent = float(feat.get("spectral_centroid_mean_hz") or 1500)
    rms = float(feat.get("rms_mean") or 0.05)
    dens = float(feat.get("onset_density") or 1.0)
    lh = float(feat.get("low_high_ratio") or 1.0)

    # crude arousal / valence proxies
    arousal = 0.0
    arousal += (tempo - 100) / 80.0
    arousal += (dens - 1.5) / 3.0
    arousal += (rms - 0.05) / 0.1

    brightness = (cent - 1500) / 1500.0
    weight = (lh - 1.0) / 1.0

    tags: list[str] = []
    if arousal >= 0.6:
        tags.append("高揚")
        tags.append("緊張")
    elif arousal <= -0.4:
        tags.append("静けさ")
        tags.append("落ち着き")
    else:
        tags.append("中庸")

    if brightness >= 0.35:
        tags.append("明るい")
    elif brightness <= -0.35:
        tags.append("暗い")
        tags.append("沈静")

    if weight >= 0.5:
        tags.append("重厚")
    elif weight <= -0.3:
        tags.append("軽やか")

    if dens >= 3.0:
        tags.append("密")
    elif dens < 1.0:
        tags.append("疎")

    if tempo >= 140:
        tags.append("疾走")
    elif tempo < 85:
        tags.append("緩徐")

    # unique preserve order
    seen = set()
    out = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:6]
