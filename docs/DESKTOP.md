# Xochipilli — local app launch

**English** | [日本語](DESKTOP.ja.md) | [中文](DESKTOP.zh.md)

## Easiest path
1. Click **Xochipilli** in the Dock  
   or **Applications** → `Xochipilli.app`
2. A dedicated window opens (content is local `http://127.0.0.1:8787`)

Layout:
- `/Applications/Xochipilli.app` (official icon = concept 03)
- Source tree: your clone of `music-film-workbench/`

## How launch works (fixed 2026-08-04 evening)
macOS **rejects direct exec of scripts inside Documents from a .app**  
(symptom: click does nothing / log shows `Operation not permitted`).

The working chain is:

1. Dock → `/Applications/Xochipilli.app`
2. → **`exec`** `~/Library/Application Support/Xochipilli/run.sh`  
   (the `.app` process **stays alive** as the GUI process — do **not** `nohup … &` then `exit 0`)
3. → project `.venv` Python runs `desktop_app.py` (pywebview window)

**Do not go back to osascript+nohup background.** That made Dock think the app quit; the orphan Python hung on exit and no usable window stayed frontmost.

## Other ways to start

| Method | Path |
|--------|------|
| .app | `/Applications/Xochipilli.app` |
| run.sh | `~/Library/Application Support/Xochipilli/run.sh` |
| Shell | `./RUN_DESKTOP.sh` (from a terminal) |
| Browser only | `./RUN_ME.sh` → http://127.0.0.1:8787 |

## Logs (when nothing opens)
- `~/Library/Logs/Xochipilli/launch.log` (.app side)
- `~/Library/Logs/Xochipilli/session.log` (Python / window)

Healthy session lines look like:
```text
exec run.sh (stay as app process)
… desktop_app start …
reuse server … (or server ready)
window created → http://127.0.0.1:8787
```

## Troubleshooting
- **Nothing happens:** check the logs above. Try `xattr -cr /Applications/Xochipilli.app` then click again
- **Dock bounce then die:** confirm MacOS launcher still `exec`s run.sh (not nohup+exit)
- **White empty window (title only):** WKWebView failed to paint URL. Fixed path uses dark bootstrap + `load_html(..., base_uri=http://127.0.0.1:8787/)`. See [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md). Expect `load_html ok` in session.log
- **Traceback / icon argument:** `desktop_app.py` is patched for pywebview builds without `icon=`
- **Port clash:** set `PORT=` in `.env`, or free 8787
- **No pywebview:** `.venv/bin/pip install pywebview`
- **Ben's Tool PYTHONPATH pollution:** run.sh unsets it; desktop_app also strips `/.bentool/` from `sys.path`
