# Xochipilli — writing segment prompts

English only, like [DECISIONS.md](DECISIONS.md) — this is working reference, not product copy.

Companion data: [`theory/prompt_vocab_v0.json`](../theory/prompt_vocab_v0.json) — a controlled
vocabulary of film terms with JA / ZH labels, ready to become chips in the segment prompt
editor. Nothing reads it yet.

## The layered structure

Subject → action → camera → environment → lighting → style. Sora 2, Veo 3.1 and the Grok
Imagine family all reward roughly this order, and it is the one part of 2025-era prompting
advice that has not moved. Models with native audio add a seventh layer for sound, which
does not apply here (see below).

Xochipilli assembles most of this for you. What you type in a segment is the subject,
action and environment; STYLE LOCK, the music-derived bias, the affect bias, the AVOID
block and the duration line are appended by `compose_video_prompt` in `app/mapping.py`.

## Rules that survive contact with a 5-second clip

- **One primary camera move per clip**, in its own sentence. Two moves fight and produce drift.
- **Describe one beat, not a narrative.** A part is ~5s (`CLIP_UNIT_SECONDS`). The TIME WINDOW
  paragraph already tells the model not to compress the whole story into it, but a prompt
  written as a three-act scene will still lose.
- **Write positively.** Negation inside the positive prompt is unreliable across current
  models. Exclusions belong in the project negative field, which lands in the
  `AVOID / NEGATIVE` block. Holding a frame still is a positive instruction — that is why
  `CAMERA_LOCK_TEXT` describes a locked tripod rather than listing "no pan, no tilt".
- **Reference stills beat seeds for continuity.** The chain (`extension` / `i2v`) is the
  mechanism here; there is no seed field in the UI and adding one would be the weaker tool.
- **Specific beats evocative.** "白い子猫が晴れた公園の芝生を跳ねる" survives; "きれいな景色" does not.

## What is not prompt text

Seed, resolution, frame rate, duration and motion strength are call parameters, and in this
app they are env vars — `XAI_VIDEO_RESOLUTION`, `XAI_VIDEO_ASPECT`, `CLIP_UNIT_SECONDS`.
Writing `Resolution: 4K, Frame rate: 60fps` into a prompt does nothing twice over: the
provider ignores it, and `_normalize_part` re-encodes every part to 1280x720@24 for concat
and xfade anyway.

## Native audio

Grok Imagine, Veo 3.1 and Sora 2 all generate a synced audio track now. This pipeline drops
it (`ffmpeg -an`) and muxes the segment's own music instead, which is correct for a
music→film workbench. Consequence: audio direction in a prompt is wasted effort, and any
provider setting that bills extra for audio is money spent on a track that is discarded.
Worth revisiting only if a "keep provider audio" mode is ever wanted for diegetic sound.

## Vocabulary notes

The camera terms carrying `lock_conflict: true` in the vocab file are the same family that
`_CAMERA_TAG_RE` strips from music-derived soft tags when camera lock is on. Keep the two in
step if either changes.

Two entries are marked `caution` because they read well in a guide and fail in practice:
`split_screen` is a layout instruction that belongs in the program edit, and `whip_pan` /
`dolly_zoom` ask for more camera motion than five seconds can carry. Named-studio style
prompts ("in the style of <studio>") are filtered or refused by providers and are also what
`DEFAULT_NEGATIVE` already pushes against — name the technique, not the studio.
