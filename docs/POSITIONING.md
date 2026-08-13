# Xochipilli — market positioning & differentiation

**English** | [日本語](POSITIONING.ja.md)

Last reviewed: **2026-08-04** (HKT)  
Purpose: keep a durable log of how this product differs from similar “music → video” tools, so design and messaging stay consistent.

This is **not** a competitor attack sheet. It is an internal product map: same shelf, different object.

---

## One-line position

> Others turn a **song into a finished music video**.  
> Xochipilli is a **local workbench** where you open the track’s world **segment by segment**, write the picture yourself, and keep the takes on your machine.

---

## Xochipilli’s product DNA (comparison axes)

| # | Axis | Xochipilli |
|---|------|------------|
| 1 | Runtime | **Local** Mac workbench (FastAPI + UI; optional desktop window) |
| 2 | Timeline authority | **Music first** — waveform / pins define the cut |
| 3 | Segmentation | **User pins** intervals (not only auto storyboard) |
| 4 | Direction | **Per-segment visual prompt** written by the author |
| 5 | Continuity | Last-frame I2V + optional **xAI Video Extension**; micro-xfade on I2V seams |
| 6 | Iteration | Multi-take per segment, adopt / discard, Unmatch log |
| 7 | Credentials | **BYOK** (xAI / fal / mock; keys stay local) |
| 8 | Outcome | Craft material & program stitch — not primarily “post-ready MV in one click” |

If a tool does not combine **local × author-cut segments × per-segment scene prompts × continuity × BYOK**, it is adjacent, not a clone.

---

## Market map (2026-08 review)

### A. Closest in *control philosophy* (cloud)

| Product | Overlap | Decisive difference |
|---------|---------|---------------------|
| [Neural Frames](https://www.neuralframes.com/) | Timeline prompts, per-clip regen, music-aware editor | **Cloud SaaS**; strong audio-reactive / frame animation product |
| [sup.video](https://sup.video/) | Music-structure timeline, scene direction, multi-model | **Cloud**; heavier AI storyboard automation |

### B. Local, but *pipeline / finished MV* oriented

| Product | Overlap | Decisive difference |
|---------|---------|---------------------|
| [MusicVision](https://github.com/tsondo/musicvision) | Local, song → scenes → clips | Auto lip-sync **MV pipeline**, not interactive scene workbench |
| [Videoboom](https://github.com/lBroth/videoboom) | Desktop, per-scene re-roll | Lyrics → **story → finished MV** pipeline |
| Synesthesia AI Video Director, Audio2KineticVid, KupkaProd-style LTX pipelines | Local generation | Batch / script pipelines; lyric or full-auto focus |

### C. Local *timeline craft*, not music-primary product

| Product | Overlap | Decisive difference |
|---------|---------|---------------------|
| Sonder Editor (ComfyUI timeline) | Local, range prompts, takes, first/last frame | **General** video node editor — music digest / pin workflow is not the product |

### D. Cloud “song → finished MV” factories (same *category*, different object)

| Product | Role |
|---------|------|
| [Freebeat](https://freebeat.ai/) | Agent-style full MV / dance / lyric video from a track |
| [Renderforest](https://www.renderforest.com/) AI Music Video | Cloud suite feature: templates + multi-model MV |
| Kaiber (Cuts / Montage / etc.) | Cloud beat-sync and music-video tool family |

---

## Verdict from the 2026-08 survey

| Question | Answer |
|----------|--------|
| Exact clone? | **No** |
| ≥80% same product? | **No** |
| Category neighbors? | **Yes** (music → video AI) |
| Closest *ideas* | Neural Frames / sup.video (control), but cloud |
| Closest *local* | MusicVision / Videoboom, but auto pipelines |

**No shipping product combined all five:** local × user-cut segments × per-segment scene prompts × continuity chaining × BYOK.

---

## Messaging cheat-sheet

**When someone asks “isn’t this like Freebeat?”**

> Freebeat (and similar) generate a **finished music video from a song**.  
> Xochipilli is a **local workbench**: you pin segments, write the scene per segment, and assemble takes yourself.

**What to keep emphasizing in product work**

- Segment craft (pin → prompt → generate → take)
- Continuity (extension / chain / lock when the author wants it)
- Local data + BYOK
- Style / camera control as author tools, not only autopilot aesthetics

**What not to chase**

- One-click full-song social MV as the core identity (that shelf is crowded)

---

## Maintenance

- Revisit this file when a new tool claims “local music segment workbench” or when positioning questions repeat.
- Shipped design choices are in [DECISIONS.md](DECISIONS.md). This file is the **positioning** source of truth.
- Survey snapshot date: 2026-08-04.
