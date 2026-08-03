# Xochipilli — wiring the video API

**English** | [日本語](VIDEO_API.ja.md) | [中文](VIDEO_API.zh.md)

## Providers

| `VIDEO_PROVIDER` | Auth | Notes |
|------------------|------|-------|
| **`mock`** (default) | none | Local placeholder video |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`** (alias `grok`) | **SuperGrok OAuth (Ben's Tool)** or `XAI_API_KEY` | Grok Imagine Video |

On failure the pipeline **falls back to mock** (reason in the segment note).

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

## Not built yet

- Entering keys from the UI (secrets stay out of the browser)  
- xAI edit / extend as direct segment tools (generate only today)  
- Conditioning xAI on segment audio (text→video is primary)

---

## Code map

- `app/xai_auth.py` — OAuth / API key resolution  
- `app/video_gen.py` — `generate_xai_clip` (`/v1/videos/generations`)  
- `docs/VIDEO_API*.md` — this guide family
