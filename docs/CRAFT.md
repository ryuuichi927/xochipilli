# Craft / Taste layer

Personalization and segment craft controls for Xochipilli.

## Endpoints (via `app.server` — also Desktop)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/taste` | User taste memory (Unmatch accumulation) |
| `PUT` | `/api/projects/{pid}/segments/{sid}/mode` | Set `hold` \| `shift` \| `motion` |
| `POST` | `/api/projects/{pid}/segments/{sid}/unmatch-v2` | Structured Unmatch → taste.json |
| `POST` | `/api/projects/{pid}/segments/{sid}/clips/{clip_id}/regen-subclips` | Partial subclip regen |

## Modes (wired into **generate**)

| Mode | Meaning | Generate behavior |
|------|---------|-------------------|
| **hold** (default) | Same scene / framing | Previous last-frame chain OK; camera_lock respected; xAI Extension OK |
| **shift** | World / scene change | No chain from previous segment; lock forced off; Extension off for chain policy |
| **motion** | Camera may move | Chain OK; lock forced off |

Pin creates segments with `mode=hold` via `enrich_new_segment`.

## UI

- Segment card: mode dropdown + hint
- Unmatch: reason (`emotion|world|camera|style|other`) + note → unmatch-v2
- Materials: if take has multiple 5s subclips, enter indices `2,3` → partial regen
- Adopt: mock takes blocked when real provider is set

## Launch

```bash
./RUN_ME.sh          # app.server:app
./RUN_DESKTOP.sh     # desktop_app → app.server:app
```

## Partial regen

```bash
curl -X POST http://127.0.0.1:8787/api/projects/PID/segments/SID/clips/CLIP_ID/regen-subclips \
  -H 'Content-Type: application/json' \
  -d '{"indices":[2,3,4]}'
```

0-based indices into the 5s blocks. Take is re-stitched after.
