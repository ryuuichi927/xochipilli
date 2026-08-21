# Xochipilli

**English** | [日本語](README.ja.md) | [中文](README.zh.md)

A local workbench for turning a piece of music into film, a segment at a time. It runs on your
own Mac. The song is the timeline, you pin the intervals that matter, you write the direction
for each one, and the takes stay on your disk.

There is no "make me a music video" button, and adding one would make it a different tool.
Named after **Xochipilli**, the Aztec deity associated with song, dance, and art.

By **Ryuichi Hamakawa**.

## Importing a track

An imported track is a waveform and nothing else.

![An imported track before analysis: waveform only](docs/media/digest-before.png)

Analysis ("digest") reads the track and proposes sections. Those are the gold blocks below, 21
of them here, from librosa novelty detection. The control for them is a button reading **Apply
section drafts**, so you can take them, replace them, or leave them alone and pin the intervals
yourself. Why it stops at proposing is in [DECISIONS.md](docs/DECISIONS.md).

![The same track after analysis, with proposed section drafts over the waveform](docs/media/digest-after.png)

## Directing one segment

![The segment editor: the prompt, segment mode, optional feel sliders, two takes, and the time-window bundle sent to the model](docs/media/segment.png)

The large field is yours, and it is the only thing describing the shot. Above it, the machine's
contribution is labelled **AI emotion (reference)**: four keywords you can ignore. **Segment
mode** is `Hold` here, meaning same scene and framing, which is what makes a camera lock safe
to apply. `Shift` and `Motion` say otherwise. The **Feel** sliders stay unset unless you move
them.

The generate button reads **`Generate another take · ~4 API calls`**. This segment runs 15.4
seconds and the unit is five, so each take is four chained clips, recorded as `4×5s`. Both
takes here were generated for the same segment, which is the normal way to work: keep going
until one of them holds. When a single part of a chain is wrong, **Partial regen** takes the
numbered parts `0 1 2 3` and redoes only what you select, so a bad second in the middle doesn't
cost the three that worked.

The last line shows what the model actually received:

> TIME WINDOW – This is part 1 of 4 of a 15.4-second sequence, covering seconds 0.0–5.0.
> Depict ONLY the events that belong to this time window. Do not compress …

The picture has to fit the song's clock, five seconds at a time.

## Status

**Work in progress — `0.1.0-d1`, stage D1.** Started August 2026 and still moving. It runs, and
I use it for real work, but it isn't packaged for anyone else: setup means a Python virtualenv,
`ffmpeg` and your own API key. The seams between chained clips don't yet reach the level of a
single professional take.

What falls short is listed in
[DECISIONS.md § Known limitations](docs/DECISIONS.md#known-limitations).

## Where the thinking is written down

Most of what I have worked out about this problem is in three documents rather than in the
code:

| Document | What it holds |
|----------|---------------|
| [DECISIONS.md](docs/DECISIONS.md) | Every choice that shipped, why, what was tried and rejected, and where it currently falls short |
| [POSITIONING.md](docs/POSITIONING.md) | Survey of neighboring tools and the specific combination none of them shipped |
| [RESEARCH-CONTEXT.md](docs/RESEARCH-CONTEXT.md) | The one place my research on everyday listening reached into the design, and the places I kept it out |

## How the work goes

1. **Import a track (digest)** — builds analysis audio; re-importing resets segments and clips
2. Play and seek. Click a segment frame to edit. **Pin with `P`** at the playhead
3. Write a **video prompt** per segment. Machine-suggested emotion keywords are hints, never decisions
4. Take feels wrong → **Unmatch**, with a reason. Repeated signals bias later prompts
5. **Generate** — 5-second units, chained, with the overhang tucked under the next segment

Design rationale for each of these is in [DECISIONS.md](docs/DECISIONS.md).

## Run it

Requires macOS, Python 3, and `ffmpeg`.

### Desktop window
```bash
cd /path/to/xochipilli
./RUN_DESKTOP.sh          # or Xochipilli.app, built by native/build_launcher.sh
```
Details: [docs/DESKTOP.md](docs/DESKTOP.md) · [JA](docs/DESKTOP.ja.md) · [ZH](docs/DESKTOP.zh.md)

### Browser only
```bash
./RUN_ME.sh               # then open http://127.0.0.1:8787
```

### Generation provider (bring your own key)
```bash
cp .env.example .env
# VIDEO_PROVIDER=xai    # Grok Imagine (needs XAI_API_KEY)
# VIDEO_PROVIDER=fal    # optional
# VIDEO_PROVIDER=mock   # no API, the default
```

Without `.env` the provider is `mock`. Under a real provider, a failed generation returns an
error — it is never quietly replaced by a mock take that looks like success. Full guide:
[docs/VIDEO_API.md](docs/VIDEO_API.md) · [JA](docs/VIDEO_API.ja.md) · [ZH](docs/VIDEO_API.zh.md)

### Keyboard
`Space` play · `R` restart · **`P` pin** · `K` frame start · `L` loop · `F` fit · `Tab` ·
disabled while typing. Canonical list: [docs/KEYS.md](docs/KEYS.md) ·
[JA](docs/KEYS.ja.md) · [ZH](docs/KEYS.zh.md)

UI language (Japanese / English / Chinese) is the ⚙ menu, top right.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest        # desktop shell contracts + digest phase checks
./native/build_launcher.sh        # rebuild Xochipilli.app (build output, not in git)
```

## Data layout

Your work lives **outside the repo**, so updating, moving, or re-cloning the code can never
touch it. Default root is `~/Documents/Xochipilli`; override with `XOCHIPILLI_DATA`.
`<data>` below means that root.

| Path | Role |
|------|------|
| `<data>/projects/<id>/project.json` | Work metadata, segments, adopted clip refs (**no full series**) |
| `<data>/projects/<id>/digest.json` | Digest detail (series, peaks, …); used for segment features |
| `<data>/projects/<id>/source.*` | Imported audio (**one current** file; re-import replaces) |
| `<data>/projects/<id>/analysis.wav` | Mono signal for digest |
| `<data>/projects/<id>/clips/` | Take mp4s, segment audio slices, chain frames, `program.mp4` |
| `<data>/projects/<id>/refs/` | Per-segment stills (i2v) |
| `<data>/user/taste.json` | Unmatch history and prompt bias (local only) |
| iCloud `Xochipilli/Archive/` | Cold projects parked to free local disk (`XOCHIPILLI_COLD_DAYS`) |

In the repository itself: `app/` FastAPI backend · `static/` UI · `theory/` digest and
mapping JSON · `docs/` the documents above · `native/` macOS launcher sources.

Deletes (project / segment / take) keep **JSON and disk in sync**. Clips missing from JSON
are orphans from older takes and may be collected.

## Documentation

| Topic | English | 日本語 | 中文 |
|-------|---------|--------|------|
| This README | [README.md](README.md) | [README.ja.md](README.ja.md) | [README.zh.md](README.zh.md) |
| **Design decisions** | [DECISIONS](docs/DECISIONS.md) | — | — |
| **Positioning** | [POSITIONING](docs/POSITIONING.md) | [POSITIONING.ja](docs/POSITIONING.ja.md) | — |
| **Research context** | [RESEARCH-CONTEXT](docs/RESEARCH-CONTEXT.md) | — | — |
| Craft / taste layer | [CRAFT](docs/CRAFT.md) | — | — |
| Writing segment prompts | [PROMPTING](docs/PROMPTING.md) | — | — |
| Desktop launch | [DESKTOP](docs/DESKTOP.md) | [DESKTOP.ja](docs/DESKTOP.ja.md) | [DESKTOP.zh](docs/DESKTOP.zh.md) |
| Keyboard | [KEYS](docs/KEYS.md) | [KEYS.ja](docs/KEYS.ja.md) | [KEYS.zh](docs/KEYS.zh.md) |
| Video API | [VIDEO_API](docs/VIDEO_API.md) | [VIDEO_API.ja](docs/VIDEO_API.ja.md) | [VIDEO_API.zh](docs/VIDEO_API.zh.md) |
| Brand marks | [BRAND](docs/BRAND.md) | [BRAND.ja](docs/BRAND.ja.md) | [BRAND.zh](docs/BRAND.zh.md) |
| Index | [docs/README.md](docs/README.md) | | |

## License

Copyright (c) 2026 Ryuichi Hamakawa. **All rights reserved.**
No license to use, copy, or distribute is granted.
See [LICENSE](./LICENSE) (Japanese / English / 中文).
