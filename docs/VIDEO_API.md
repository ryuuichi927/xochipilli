# Xochipilli — wiring the video API

**English** | [日本語](VIDEO_API.ja.md) | [中文](VIDEO_API.zh.md)

## Providers

| `VIDEO_PROVIDER` | Auth | Notes |
|------------------|------|-------|
| **`mock`** (default) | none | Local placeholder video |
| **`fal`** | `FAL_KEY` | FAL text-to-video |
| **`xai`** (alias `grok`) | `XAI_API_KEY`, or an existing OAuth session | Grok Imagine Video |

Under a **real** provider, failures **raise an error** (they are not silently sold as successful takes). Mock is only used when `VIDEO_PROVIDER=mock`.

You bring your own credentials. Nothing is proxied through anyone else's account.

---

## Grok video with your own key

### Steps

1. Get an xAI API key and put it in the project `.env` as `XAI_API_KEY`.

   If you already hold an xAI OAuth session from another tool, you can reuse it
   instead of buying a key. Both routes are opt-in and off by default:

   - `XAI_OAUTH_HELPER` — a directory exposing `tools/xai_http.py` with
     `resolve_xai_http_credentials()`. This route refreshes tokens.
   - `XAI_TOKEN_STORE` — a JSON file holding an OAuth access token, read at
     `providers.xai-oauth.tokens.access_token`. No refresh, so it can go stale.

2. Project `.env`:

```bash
cd /path/to/xochipilli
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
- `xai_auth.source`: e.g. `xai_api_key`, or `oauth-helper` when a helper is configured

5. In the UI: segment prompt → Generate.  
   One clip may take **tens of seconds to a few minutes**.

### Duration contract (xAI) — 5s unit stays; wire ints clamp

| Call | What we send | API limit |
|------|----------------|-----------|
| T2V / I2V (`/videos/generations`) | **integer** seconds | **1–15** |
| Extension (`/videos/extensions`) | **integer** seconds of *new* tail only | **2–10**; source clip ~2–15s |

**Split policy (product — do not collapse to one long shot):**

- Default unit = `CLIP_UNIT_SECONDS` (**5**).
- **6.7s pin → 5s T2V + 2s Extension** (not one 7s shot).
- Last remainder &lt;2s is padded to **2s** (API min). Planned video can be slightly longer than music (e.g. 7s video for 6.7s pin).
- That **overhang** is intentional: micro-xfade **under the start of the next segment** at program continuity — not discarded time.
- Meta: `duration_plan`, `overhang_for_next`, `duration_requested` / `duration_api` / `duration_actual`.
- If a later part fails, earlier parts stay as a **partial take**.

Optional env: `CLIP_UNIT_SECONDS=5`, `XAI_CHAIN_MODE=extension|i2v`, `XOCHI_XFADE_SEC` (seam glue).

Health exposes limits under `xai_duration` (`split_policy: unit_5s_default`).

### When OAuth expires

`xai_auth.relogin_hint` on health, or an auth error in the segment note.  
Re-login to xAI wherever the session is managed, then `./RUN_ME.sh`. A plain
`XAI_API_KEY` does not expire this way.

### Auth priority (code)

1. `XAI_OAUTH_HELPER` → `resolve_xai_http_credentials()` (with refresh), if configured  
2. `XAI_API_KEY`  
3. Raw `access_token` from `XAI_TOKEN_STORE` (last resort; expires easily)

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
