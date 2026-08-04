# Xochipilli — wiring the video API

**English** | [日本語](VIDEO_API.ja.md) | [中文](VIDEO_API.zh.md)

## Providers

| `VIDEO_PROVIDER` | Auth | Notes |
|------------------|------|-------|
| **`mock`** (default) | none | Local placeholder video |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`** (alias `grok`) | **SuperGrok OAuth (Ben's Tool)** or `XAI_API_KEY` | Grok Imagine Video |

Under a **real** provider, failures **raise an error** (they are not silently sold as successful takes). Mock is only used when `VIDEO_PROVIDER=mock`.

---

## Recommended: SuperGrok → OAuth (Grok video)

If Ben's Tool is already on `provider: xai-oauth` / `video_gen.provider: xai`,  
Xochipilli reuses **the same OAuth token** (no separate paid API key required).

### Steps

1. Be logged into xAI on the Ben's Tool side  
   - Desktop xAI / SuperGrok login  
   - or CLI: `bentool auth` (xai-oauth)  
   - `~/.bentool/auth.json` should contain `providers.xai-oauth.tokens`

2. Project `.env`:

```bash
cd /path/to/music-film-workbench
cp .env.example .env
```

```bash
VIDEO_PROVIDER=xai
# optional
XAI_VIDEO_MODEL=grok-imagine-video
XAI_VIDEO_RESOLUTION=720p
XAI_VIDEO_ASPECT=16:9
# optional continuity
# XAI_CHAIN_MODE=extension   # default; or i2v
# CLIP_UNIT_SECONDS=5
```

3. Restart the server:

```bash
./RUN_ME.sh
```

4. Check (token body is never printed):

```bash
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool
```

Expect:
- `video_provider`: `"xai"`
- `xai_auth.ok`: `true`
- `xai_auth.source`: e.g. `bentool-oauth`

5. In the UI: segment prompt → Generate.  
   One clip may take **tens of seconds to a few minutes**.

### Duration contract (xAI) — must stay aligned

| Call | What we send | API limit |
|------|----------------|-----------|
| T2V / I2V (`/videos/generations`) | **integer** seconds | **1–15** |
| Extension (`/videos/extensions`) | **integer** seconds of *new* tail only | **2–10**; source clip ~2–15s |

Planner (`plan_generation_parts`):

- Segment **≤15s** → **one** T2V/I2V shot (no 5s split). A 6.7s pin becomes `duration=7`, not 5+2.
- Segment **>15s** → first chunk ≤15s, then extension chunks of 2–10s only (never a &lt;2s extension tail).
- Meta stores `duration_requested` / `duration_api` / `duration_actual` (ffprobe after download).
- If a later part fails, earlier parts are kept as a **partial take** (not discarded orphans).

Optional env: `XAI_MAX_SINGLE_SEC` (default 15), `CLIP_UNIT_SECONDS` (multi-part first-chunk bias), `XAI_CHAIN_MODE=extension|i2v`.

Health exposes limits under `xai_duration`.

### When OAuth expires

`xai_auth.relogin_hint` on health, or an auth error in the segment note.  
**Re-login to xAI in Ben's Tool**, then `./RUN_ME.sh`.

### Auth priority (code)

1. Ben's Tool `resolve_xai_http_credentials` (with refresh)  
2. `XAI_API_KEY`  
3. Raw `access_token` in `auth.json` (last resort; expires easily)

---

## Using FAL

```bash
VIDEO_PROVIDER=fal
FAL_KEY=...
FAL_VIDEO_MODEL=fal-ai/minimax-video
```

---

## Back to mock

```bash
VIDEO_PROVIDER=mock
```

---

## Not in the UI yet

- Entering keys from the UI (secrets stay out of the browser)  
- Manual “extend this take” button (Extension already runs inside multi-part generate)  
- Conditioning xAI on segment audio (text→video is primary)

---

## Code map

- `app/xai_auth.py` — OAuth / API key resolution  
- `app/video_gen.py` — generate + native Extension  
- `docs/VIDEO_API*.md` — this guide family
