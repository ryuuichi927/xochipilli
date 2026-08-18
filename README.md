# Xochipilli

**English** | [日本語](README.ja.md) | [中文](README.zh.md)

Local, **Manual-oriented** music → film workbench for your Mac.  
The name comes from the Aztec deity **Xochipilli** 

Designed by **Ryuichi Hamakawa**.

## Launch

### Desktop window (recommended)
```bash
cd /path/to/xochipilli
./RUN_DESKTOP.sh
# or Dock / Applications → Xochipilli.app
```
Details: [docs/DESKTOP.md](docs/DESKTOP.md) · [JA](docs/DESKTOP.ja.md) · [ZH](docs/DESKTOP.zh.md)

### Browser only
```bash
./RUN_ME.sh
```
Open http://127.0.0.1:8787

## Quick workflow
1. **Import a track (digest)** — builds analysis audio (re-import resets segments and clips)
2. Play / seek. Click a segment frame to edit. **Pin with P** (playhead)
3. Write a **video prompt** per segment. AI emotion keywords are hints only
4. Feels wrong → **Unmatch**
5. **Generate video** — set `VIDEO_PROVIDER` in `.env` (default: `mock`)

## Keyboard
**Canonical list:** [docs/KEYS.md](docs/KEYS.md) · [JA](docs/KEYS.ja.md) · [ZH](docs/KEYS.zh.md)

Space play · R to start · **P** pin · **K** frame start · **L** loop · **F** fit · **Tab** · more in KEYS (disabled while typing)

## UI language
Top-right ⚙ — Japanese / English / Chinese (`mfw.lang`)

## Video API (your keys / SuperGrok OAuth)

**Canonical guide:** [docs/VIDEO_API.md](docs/VIDEO_API.md) · [JA](docs/VIDEO_API.ja.md) · [ZH](docs/VIDEO_API.zh.md)

```bash
cp .env.example .env
# VIDEO_PROVIDER=xai   # Grok Imagine (needs XAI_API_KEY)
# VIDEO_PROVIDER=fal   # optional
# VIDEO_PROVIDER=mock  # no API
./RUN_ME.sh
```

Without `.env`, the default is `mock`. Under a real provider (`xai` / `fal`), failures return an error — they are not silently treated as successful takes.

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
| iCloud `Xochipilli/Archive/` | Cold projects parked to free local disk (`XOCHIPILLI_COLD_DAYS`) |
| `theory/` | Digest / mapping theory JSON |
| `static/` | UI (`app.js`, i18n, style, brand, fonts) |
| `app/` | FastAPI backend |
| `docs/` | KEYS, VIDEO_API, BRAND, DESKTOP, DECISIONS, … |

Deletes (project / segment / take) keep **JSON and disk in sync**.  
Clips missing from JSON are orphans (old takes) and may be GC’d.

## Documentation (EN · JA · ZH)

| Topic | English | 日本語 | 中文 |
|-------|---------|--------|------|
| This README | [README.md](README.md) | [README.ja.md](README.ja.md) | [README.zh.md](README.zh.md) |
| Desktop launch | [DESKTOP](docs/DESKTOP.md) | [DESKTOP.ja](docs/DESKTOP.ja.md) | [DESKTOP.zh](docs/DESKTOP.zh.md) |
| Keyboard | [KEYS](docs/KEYS.md) | [KEYS.ja](docs/KEYS.ja.md) | [KEYS.zh](docs/KEYS.zh.md) |
| Video API | [VIDEO_API](docs/VIDEO_API.md) | [VIDEO_API.ja](docs/VIDEO_API.ja.md) | [VIDEO_API.zh](docs/VIDEO_API.zh.md) |
| Brand | [BRAND](docs/BRAND.md) | [BRAND.ja](docs/BRAND.ja.md) | [BRAND.zh](docs/BRAND.zh.md) |
| Design decisions | [DECISIONS](docs/DECISIONS.md) | — | — |
| Positioning | [POSITIONING](docs/POSITIONING.md) | [POSITIONING.ja](docs/POSITIONING.ja.md) | — |
| Docs index | [docs/README.md](docs/README.md) | | |

## Brand & type
- Logo roles: [docs/BRAND.md](docs/BRAND.md) (primary=03 / casual=01 / wait flower=02)
- Header typeface: **Cinzel** (`.brand-title` only) — [docs/DECISIONS.md](docs/DECISIONS.md)

## Privacy note
This repo is **private** while the product is pre-release. Personal working notes are kept
out of it entirely, in a git-ignored `private/` folder. Do not commit `.env`, imported
media, or anything holding an absolute path to your own machine (see `.gitignore`).

## License
Copyright (c) 2026 Ryuichi Hamakawa. **All rights reserved.**  
See [LICENSE](./LICENSE) (Japanese / English / 中文).
