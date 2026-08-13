# Xochipilli — local app launch

**English** | [日本語](DESKTOP.ja.md) | [中文](DESKTOP.zh.md)

## Easiest path
1. Click **Xochipilli** in the Dock  
   or **Applications** → `Xochipilli.app`
2. A dedicated window opens (content is local `http://127.0.0.1:8787`)

Layout:
- `/Applications/Xochipilli.app` (official icon = concept 03) — a thin launcher that only
  reads where the real tree is
- Source tree: path in `Contents/Resources/ProjectRoot` (e.g. `~/Projects/xochipilli`)

## Where things live

| Thing | Path | Synced |
|-------|------|--------|
| The app itself (code + `.venv`) | `~/Projects/xochipilli` | git only |
| Dock launcher | `/Applications/Xochipilli.app` | no |
| Finished work | `~/Documents/Xochipilli/projects/<id>/` | local only |
| Taste model / Canva tokens | `~/Documents/Xochipilli/` | local only |
| Projects untouched for a week | `iCloud Drive/Xochipilli/Archive/<id>/` | iCloud (offloaded) |
| Token / logs | `~/Library/Application Support/Xochipilli/`, `~/Library/Logs/Xochipilli/` | no |

`.venv` must be a **real directory inside this clone**, never a symlink elsewhere: delete the
link target and the app stops launching.

Work lives outside the repo so updating or moving the code cannot reach it. Override with:

```bash
XOCHIPILLI_DATA=~/Documents/Xochipilli        # works
XOCHIPILLI_ARCHIVE=~/Library/Mobile\ Documents/com~apple~CloudDocs/Xochipilli/Archive
XOCHIPILLI_COLD_DAYS=7                        # days before a project is parked
```

Moving from an older in-repo `data/`:
```bash
.venv/bin/python tools/migrate_data.py --dry-run
.venv/bin/python tools/migrate_data.py
```

## Automatic iCloud parking (the 7-day rule)
A project nobody opened for a week moves to iCloud Drive and gives its local space back. It
stays in the picker marked `☁`; selecting it pulls it back (minutes for a big track).

- The clock is "last opened", and reading a project updates it without counting as an edit
- The move is **copy → compare every file size → delete local → `brctl evict`**; the local
  copy is only removed once the comparison passes
- A project that is importing or generating, or the one currently open, is never touched
- iCloud cannot evict a file it has not finished uploading, so every sweep retries the evict

When it runs: 90 s after the app starts (so the project you just opened is not mistaken for
cold), and daily at 04:30 via launchd (`local.xochipilli.archive`, log in
`~/Library/Logs/Xochipilli/archive.log`).

By hand:
```bash
.venv/bin/python tools/archive_cold.py --status
.venv/bin/python tools/archive_cold.py --dry-run
.venv/bin/python tools/archive_cold.py
.venv/bin/python tools/archive_cold.py --restore <id>
.venv/bin/python tools/archive_cold.py --install-agent
```

## How launch works (0.2.x — no Chrome)
macOS **rejects direct exec of scripts inside Documents from a .app**.

Chain:

1. Dock → `/Applications/Xochipilli.app`
2. → **in-bundle Mach-O** `Contents/MacOS/Xochipilli` embeds CPython
3. → reads `Contents/Resources/ProjectRoot`, runs `desktop_app.main()` there
4. → starts/reuses FastAPI (`app.server:app`) on `:8787` (Craft routes included)
5. → **native pywebview window only** (WKWebView). **Does not open Google Chrome.**

Rebuild:
```bash
./native/build_launcher.sh
```

### Shell load path (white-screen lessons)
- Prefer `create_window(html=…)` once with **inlined CSS** (`style.css` + `craft_ui.css`, id `xochi-inline-css`) over bare `url=` (bare url often stays white with correct title on this Mac).
- Single document load — **no** second `load_html` thrash after boot.
- Inject `window.__XOCHI_API_BASE__` so relative `/api` works on about:blank origin.
- Absolutize `/static/` script/src/href against `http://127.0.0.1:PORT/`.
- **Craft:** `craft_ui.js` is **not** sync-loaded in the initial HTML (that path painted pure white in WK). After first paint, an inline `loadCraft` script dynamically injects `/static/craft_ui.js` (belt-and-suspenders: timed `evaluate_js` on `loaded`). Affect sliders + Unmatch sheet are first-class desktop features.
- Default **skip `inject_pywebview`** (`XOCHIPILLI_SKIP_PYWEBVIEW_INJECT` default on). Off: `=0`.
- `OPEN_DEVTOOLS_IN_DEBUG=False` — Debug menu / ⌥⌘I only (no auto inspector).
- No cocoa `setContentView_` / NSView-container monkey-patches (they kill clicks + resize).

Optional: `XOCHIPILLI_SHELL=browser` opens the system browser (opt-in only).

Legacy Chrome `--app` profiles are **killed on launch** so old sessions do not reappear.

See [CRAFT.md](CRAFT.md) and [DECISIONS.md](DECISIONS.md).

## Other ways to start

| Method | Path |
|--------|------|
| .app | `/Applications/Xochipilli.app` |
| Shell | `./RUN_DESKTOP.sh` (from a terminal) |
| Browser only | `./RUN_ME.sh` → http://127.0.0.1:8787 |

## Logs (when nothing opens)
- `~/Library/Logs/Xochipilli/launch.log` (.app side)
- `~/Library/Logs/Xochipilli/session.log` (Python / window)

Healthy session lines look like:
```text
… desktop_app start …
NSBundle path='…/Xochipilli.app' id='local.xochipilli.d1'
reuse server … (or server ready)
shell html build ok … (load_html+inline CSS path)
using load_html shell (create once, no boot reload)
shell_mode=pywebview
event loaded
nav ok — load_html shell
```

## Troubleshooting
- **Nothing happens:** check the logs above. Try `xattr -cr /Applications/Xochipilli.app` then click again
- **Dock bounce then die:** confirm `Contents/MacOS/Xochipilli` is Mach-O (rebuild: `./native/build_launcher.sh`)
- **White empty window (title only):**
  1. Open http://127.0.0.1:8787/ in a normal browser — if dark UI shows, the **server is fine**
  2. `session.log` should contain `using load_html shell` and `xochi-inline-css` build, **not** thrash reload / `setContentView_`
  3. Confirm launch via Dock `.app` so `NSBundle` id is `local.xochipilli.d1` (bare python may break WK local HTTP)
- **Dark UI but no Unmatch / affect sliders:** Craft loads after first paint. Check Web Inspector console for `craft_ui load failed`; ensure server serves `/static/craft_ui.js`.
- **Dark UI but dead clicks / no resize:** if log has `setContentView_(WKWebView)` → old Incident G/H patch; use stock pywebview only.
- **Port clash:** set `PORT=` in `.env`, or free 8787
- **No pywebview:** `.venv/bin/pip install pywebview`
- **Ben's Tool PYTHONPATH pollution:** desktop_app strips `/.bentool/` from `sys.path`
- **Browser only when you want it:** `XOCHIPILLI_SHELL=browser` (never default from Dock)
- **New project / import do nothing (`Auth token is stale`):** the window holds a different
  token than the server. Quit and relaunch. The token lives in
  `~/Library/Application Support/Xochipilli/api_token`, so it stays put across restarts
- **`音声解析ライブラリが足りない (…)` / missing analysis library:** the venv is incomplete —
  `.venv/bin/pip install -r requirements.txt`, then relaunch. Launch also preflights this
- **Import never finishes:** a track still stored in iCloud Drive blocks until macOS
  downloads it. Materialize it in Finder, or copy it locally first
- **A project shows `☁` and is slow to open:** it is parked in iCloud and comes back on
  selection. To stop the parking, raise `XOCHIPILLI_COLD_DAYS` or run
  `launchctl bootout gui/$(id -u)/local.xochipilli.archive`
- **`Could not pull it back from iCloud`:** iCloud Drive is off or the archived folder is
  gone — check `ls "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Xochipilli/Archive"`

## Button smoke test
Clicks every UI button (open folder, create, rename, delete, exports) and imports a real
track in a real browser:
```bash
.venv/bin/python -m uvicorn app.server:app --port 8788    # separate, token-less
.venv/bin/python tools/ui_smoke.py --port 8788 --import-file ~/path/to/track.mp3
```
It works inside a throwaway project and deletes it at the end, so existing projects are
never touched.

To check only the ☁ → back-from-iCloud path:
```bash
.venv/bin/python tools/ui_smoke.py --port 8788 --only-restore
```
