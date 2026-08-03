# Xochipilli — brand marks (canonical)

**English** | [日本語](BRAND.ja.md) | [中文](BRAND.zh.md)

Adopted: 2026-08-03 (all three concepts kept; roles fixed)

| Role | File | Source concept |
|------|------|----------------|
| **Primary icon** (official · favicon · OS) | `static/brand/icon-primary.png` | 03 unique hybrid |
| **Casual** (header, etc.) | `static/brand/icon-casual.png` | 01 elegant profile |
| **Loader flower** (waiting on generate) | `static/brand/loader-flower.png` | 02 retro line flower |

## Loader motion (concept 02)
While waiting (e.g. video gen), **only the flower** floats center screen (no card / copy).
- Waiting: petal open **1→2→3 loop**
- Success only: **glow → scatter**
- Failure: fade out without scatter

Implementation: `#genLoader` / `#flowerLoad` (`static/index.html` + `app.js` `showGenLoader`)

## Color
UI gold accent toward `#C9A227`. Black ground assumed.

## UI background
Faint Aztec flower lattice: `static/brand/bg-aztec-flower.svg` (`body::before` opacity ~0.045). Panels keep readability.

## Header typeface
**Cinzel** (candidate #1, adopted). See `FONT_CANDIDATES.md`.
