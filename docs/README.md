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

## What is not here
The build diary, incident write-ups, planning notes, and the typeface shortlist are
personal working documents and are not part of this repository. Decisions from that log
that are worth publishing are rewritten into [DECISIONS.md](DECISIONS.md) by hand.

## Note on RESEARCH-CONTEXT
The author studies everyday listening. That background changed exactly one thing in the
product — the vocabulary for rejecting a take — and this file records both that and the
places where the framework was deliberately kept out. It is scoped to design influence; it
is not a research write-up and the tool is not a measurement instrument.

## Note on DECISIONS
Why the product behaves as it does, including the paths that were tried and rejected, and
an honest list of current limitations. English only — it is a specification, not a diary.

## Note on POSITIONING
Market map and differentiation vs Freebeat, Neural Frames, local MV pipelines, etc.  
Update when a new neighbor appears or the same “isn’t this just …?” question repeats.

## Note on PROMPTING
How to write a segment prompt that survives a 5-second clip, and what `compose_video_prompt`
appends on your behalf. Its companion `theory/prompt_vocab_v0.json` is a camera / lighting /
style vocabulary with JA · ZH labels, kept for the prompt-editor chips that do not exist yet.

## Note on CRAFT
Craft is **standard product capability** (mode, structured Unmatch, taste memory, partial regen), not a private side fork.  
Code lives in separate modules for engineering clarity; product-wise it is one Xochipilli with `app.server` loading Craft on top of `app.main`. See [CRAFT.md](CRAFT.md).
