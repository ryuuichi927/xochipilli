# Xochipilli — local app launch

**English** | [日本語](DESKTOP.ja.md) | [中文](DESKTOP.zh.md)

## Easiest path
1. Click **Xochipilli** in the Dock  
   or **Applications** → `Xochipilli.app`
2. A dedicated window opens (content is local `http://127.0.0.1:8787`)

Layout:
- `/Applications/Xochipilli.app` (official icon = concept 03)
- Source tree: your clone of `music-film-workbench/`

## How launch works (2026-08-04 night — no Chrome)
macOS **rejects direct exec of scripts inside Documents from a .app**.

Chain:

1. Dock → `/Applications/Xochipilli.app`
2. → **`exec`** `~/Library/Application Support/Xochipilli/run.sh` (process stays alive)
3. → `desktop_app.py` starts/reuses FastAPI on `:8787`
4. → **native pywebview window only** (WKWebView). **Does not open Google Chrome.**

Optional: `XOCHIPILLI_SHELL=browser` opens the system browser (opt-in only).

Legacy Chrome `--app` profiles are **killed on launch** so old sessions do not reappear.

See [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md).
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
- **White empty window (title only):**
  1. Open http://127.0.0.1:8787/ in a normal browser — if dark UI shows, the **server is fine**
  2. `session.log` must contain `cocoa contentView=NSView container` and `using url= navigation (single)`
  3. If missing, update `desktop_app.py` and relaunch Dock (do **not** re-enable Chrome auto-launch)
  4. Details: [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md) Incident E/G
- **Dark UI but dead clicks / no resize:**
  1. Confirm single `url=` path (no load_html thrash logs)
  2. If log still has `cocoa early setContentView_(WKWebView)` → old E/F patch (Incident G)
  3. Healthy: `contentView=NSView container + WKWebView subview` + `styleMask=… resizable=True` + `event loaded` + `nav ok`
  4. Relaunch Dock / `./RUN_DESKTOP.sh` with latest `desktop_app.py`
- **Traceback / icon argument:** `desktop_app.py` is patched for pywebview builds without `icon=`
- **Port clash:** set `PORT=` in `.env`, or free 8787
- **No pywebview:** `.venv/bin/pip install pywebview`
- **Ben's Tool PYTHONPATH pollution:** run.sh unsets it; desktop_app also strips `/.bentool/` from `sys.path`
- **Browser only when you want it:** `XOCHIPILLI_SHELL=browser` (never default from Dock)
