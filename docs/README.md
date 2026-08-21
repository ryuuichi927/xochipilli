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
| **Design decisions** | [DECISIONS.md](DECISIONS.md) | — | — |
| **Positioning / differentiation** | [POSITIONING.md](POSITIONING.md) | [POSITIONING.ja.md](POSITIONING.ja.md) | — |
| **Research context** | [RESEARCH-CONTEXT.md](RESEARCH-CONTEXT.md) | — | — |
| **Craft / Taste (standard edit + personalization layer)** | [CRAFT.md](CRAFT.md) | same file (JA section at top) | — |
| **Writing segment prompts** | [PROMPTING.md](PROMPTING.md) | — | — |
| Canva export | [CANVA.md](CANVA.md) | — | — |

## Where to look

[DECISIONS.md](DECISIONS.md) is the one to read first. It covers why the product behaves as it
does, the paths that were tried and dropped, and where it currently falls short. English only.

[POSITIONING.md](POSITIONING.md) is the survey of neighbouring tools. Worth updating when a new
one appears, or when the same “isn’t this just …?” question comes round again.

[RESEARCH-CONTEXT.md](RESEARCH-CONTEXT.md) covers the one place my work on everyday listening
reached into the design, and the places I kept it out.

[CRAFT.md](CRAFT.md) describes mode, structured Unmatch, taste memory and partial regen. These
are standard capability rather than a side fork; they load as separate modules (`app.server` on
top of `app.main`) for engineering clarity only.

[PROMPTING.md](PROMPTING.md) is about writing a segment prompt that survives a five-second
clip, and what `compose_video_prompt` appends on your behalf. Its companion
`theory/prompt_vocab_v0.json` holds a camera, lighting and style vocabulary with JA and ZH
labels, waiting on prompt-editor chips that don’t exist yet.

The build diary, incident write-ups, planning notes and the typeface shortlist aren’t in the
repository. They are working documents. Anything in them worth publishing gets rewritten into
DECISIONS by hand.
