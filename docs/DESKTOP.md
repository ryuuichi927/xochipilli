# Xochipilli — local app launch

**English** | [日本語](DESKTOP.ja.md) | [中文](DESKTOP.zh.md)

## Easiest path
1. Click **Xochipilli** in the Dock  
   or **Applications** → `Xochipilli.app`
2. A dedicated window opens (content is local `http://127.0.0.1:8787`)

Layout:
- `/Applications/Xochipilli.app` (official icon = concept 03)
- Source tree: your clone of `music-film-workbench/`

## How launch works (fixed 2026-08-04)
macOS **rejects direct exec of scripts inside Documents from a .app**  
(symptom: click does nothing / log shows `Operation not permitted`).

So the chain is:
1. Dock → `/Applications/Xochipilli.app`
2. → `~/Library/Application Support/Xochipilli/run.sh` via **osascript**
3. → project `.venv` Python runs `desktop_app.py` (pywebview window)

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

## Troubleshooting
- **Nothing happens:** check the logs above. Try `xattr -cr /Applications/Xochipilli.app` then click again
- **Traceback / icon argument:** `desktop_app.py` is patched for pywebview builds without `icon=`
- **Port clash:** set `PORT=` in `.env`, or free 8787
- **No pywebview:** `.venv/bin/pip install pywebview`
