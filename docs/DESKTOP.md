# Xochipilli — local app launch

**English** | [日本語](DESKTOP.ja.md) | [中文](DESKTOP.zh.md)

## Easiest path
1. Click **Xochipilli** in the Dock  
   or **Applications** → `Xochipilli.app`
2. A dedicated window opens (content is local `http://127.0.0.1:8787`)

Layout:
- `/Applications/Xochipilli.app` (official icon = concept 03)
- Source tree: path in `Contents/Resources/ProjectRoot` (e.g. `~/Projects/xochipilli`)

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

See [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md) and [CRAFT.md](CRAFT.md).

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
  4. Details: [DESKTOP_INCIDENTS_2026-08-04.md](DESKTOP_INCIDENTS_2026-08-04.md)
- **Dark UI but no Unmatch / affect sliders:** Craft loads after first paint. Check Web Inspector console for `craft_ui load failed`; ensure server serves `/static/craft_ui.js`.
- **Dark UI but dead clicks / no resize:** if log has `setContentView_(WKWebView)` → old Incident G/H patch; use stock pywebview only.
- **Port clash:** set `PORT=` in `.env`, or free 8787
- **No pywebview:** `.venv/bin/pip install pywebview`
- **Ben's Tool PYTHONPATH pollution:** desktop_app strips `/.bentool/` from `sys.path`
- **Browser only when you want it:** `XOCHIPILLI_SHELL=browser` (never default from Dock)
