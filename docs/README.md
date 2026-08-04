# Xochipilli — documentation index

**English** · 日本語 · 中文  
Product docs ship in three languages. File order convention: **English (default bare name) · `.ja.md` · `.zh.md`**.

| Topic | EN | JA | ZH |
|-------|----|----|-----|
| Product README | [../README.md](../README.md) | [../README.ja.md](../README.ja.md) | [../README.zh.md](../README.zh.md) |
| Desktop launch | [DESKTOP.md](DESKTOP.md) | [DESKTOP.ja.md](DESKTOP.ja.md) | [DESKTOP.zh.md](DESKTOP.zh.md) |
| Keyboard | [KEYS.md](KEYS.md) | [KEYS.ja.md](KEYS.ja.md) | [KEYS.zh.md](KEYS.zh.md) |
| Video API | [VIDEO_API.md](VIDEO_API.md) | [VIDEO_API.ja.md](VIDEO_API.ja.md) | [VIDEO_API.zh.md](VIDEO_API.zh.md) |
| Brand | [BRAND.md](BRAND.md) | [BRAND.ja.md](BRAND.ja.md) | [BRAND.zh.md](BRAND.zh.md) |
| Header font | [FONT_CANDIDATES.md](FONT_CANDIDATES.md) | [FONT_CANDIDATES.ja.md](FONT_CANDIDATES.ja.md) | [FONT_CANDIDATES.zh.md](FONT_CANDIDATES.zh.md) |
| **Positioning / differentiation** | [POSITIONING.md](POSITIONING.md) | [POSITIONING.ja.md](POSITIONING.ja.md) | — |
| **Craft / Taste (standard edit + personalization layer)** | [CRAFT.md](CRAFT.md) | same file (JA section at top) | — |
| Dev / build log | [DEV_LOG.en.md](DEV_LOG.en.md) (summary) | [DEV_LOG.md](DEV_LOG.md) (full JA) | [DEV_LOG.zh.md](DEV_LOG.zh.md) (summary) |

## Note on DEV_LOG
The full working log stays in **Japanese** (`DEV_LOG.md`) because it is the day-to-day build diary.  
EN / ZH files are **short summaries** for orientation, not line-by-line translations.

## Note on POSITIONING
Market map and differentiation vs Freebeat, Neural Frames, local MV pipelines, etc.  
Update when a new neighbor appears or the same “isn’t this just …?” question repeats.

## Note on CRAFT
Craft is **standard product capability** (mode, structured Unmatch, taste memory, partial regen), not a private side fork.  
Code lives in separate modules for engineering clarity; product-wise it is one Xochipilli with `app.server` loading Craft on top of `app.main`. See [CRAFT.md](CRAFT.md).
