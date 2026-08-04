# Craft / Taste layer

Personalization and segment craft controls for Xochipilli.

## Endpoints (via `app.server`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/taste` | User taste memory (Unmatch accumulation) |
| `PUT` | `/api/projects/{pid}/segments/{sid}/mode` | Set `hold` \| `shift` \| `motion` |
| `POST` | `/api/projects/{pid}/segments/{sid}/unmatch-v2` | Structured Unmatch → taste.json |
| `POST` | `/api/projects/{pid}/segments/{sid}/clips/{clip_id}/regen-subclips` | Partial subclip regen |

## Modes

- **hold** (default): same scene continuity; camera_lock respected
- **shift**: scene/world change — no continuity frame, lock off
- **motion**: intentional camera language — lock forced off

```bash
# Example: mark a transition segment
curl -X PUT http://127.0.0.1:8787/api/projects/PID/segments/SID/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode":"shift"}'
```

## Structured Unmatch

```bash
curl -X POST http://127.0.0.1:8787/api/projects/PID/segments/SID/unmatch-v2 \
  -H 'Content-Type: application/json' \
  -d '{"reason":"emotion","editor_note":"too bright","editor_keywords":["暗い"]}'
```

Reasons: `emotion` | `world` | `camera` | `style` | `other`

Accumulates into `data/user/taste.json` (gitignored).

## Partial regen (expert)

```bash
curl -X POST http://127.0.0.1:8787/api/projects/PID/segments/SID/clips/CLIP_ID/regen-subclips \
  -H 'Content-Type: application/json' \
  -d '{"indices":[2,3,4]}'
```

Only the listed 5s subclips are re-generated and the take is re-stitched.

## Launch

`./RUN_ME.sh` now loads `app.server:app` (registers craft routes automatically).
Desktop entry uses the same server module if pointed at RUN_ME / uvicorn app.server.
