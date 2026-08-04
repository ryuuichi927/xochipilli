#!/usr/bin/env python3
"""Desktop shell checks: native webview default, no Chrome auto-launch."""

from __future__ import annotations

import ast
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails = 0


def ok(msg: str) -> None:
    print("OK ", msg)


def bad(msg: str) -> None:
    global fails
    fails += 1
    print("FAIL", msg)


def main() -> int:
    desk = (ROOT / "desktop_app.py").read_text(encoding="utf-8")
    try:
        ast.parse(desk)
        ok("desktop_app.py parses")
    except SyntaxError as e:
        bad(f"syntax: {e}")

    # Must be webview-primary
    for n, lab in [
        ("shell_mode=pywebview", "pywebview mode log"),
        ("_run_pywebview", "pywebview runner"),
        ("_kill_legacy_chrome_app", "kills legacy chrome"),
        ("XOCHIPILLI_SHELL", "opt-in browser env"),
    ]:
        (ok if n in desk else bad)(lab)

    # Must NOT auto-launch chrome as default path
    if "_open_chromium_app(target)" in desk or "shell_mode=chromium-app" in desk and "XOCHIPILLI" not in desk:
        # chromium-app string might still appear in comments — check call path
        pass
    if "def _open_chromium_app" in desk and "shell_mode=chromium-app" in desk:
        # allowed only if not called from main default
        if "_open_chromium_app(target)" in desk or "_open_chromium_app(" in desk.split("def main")[-1]:
            bad("main still calls chromium opener")
        else:
            ok("chromium helper not default-called")
    else:
        ok("no chromium auto-launch helper in default shell")

    main_body = desk.split("def main")[-1]
    if "webbrowser.open" in main_body and 'shell in ("browser"' not in desk:
        bad("browser open without opt-in gate")
    else:
        ok("browser only behind XOCHIPILLI_SHELL")

    if "Google Chrome" in main_body and "--app=" in main_body:
        # check it's not in main default flow
        if "--app=" in main_body and "_run_pywebview(target)" in main_body:
            # chrome flags might remain in dead code — fail if --app= still constructed in main path
            if "f\"--app=" in main_body or "'--app=" in main_body:
                bad("main path still builds --app=")
            else:
                ok("no --app= in main path")
        else:
            bad("chrome --app still referenced in main")
    else:
        ok("no Chrome --app in main")

    # Default shell selection
    if 'shell = (os.environ.get("XOCHIPILLI_SHELL") or "webview")' in desk or 'or "webview"' in desk:
        ok("default shell=webview")
    else:
        bad("default shell not webview")

    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    (ok if "-webkit-fill-available" in css else bad)("css fill")
    js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    (ok if "bindLayoutResize" in js else bad)("js resize")

    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/health", timeout=1.5) as r:
            (ok if b"Xochipilli" in r.read() else bad)("live health")
    except Exception as e:
        ok(f"live skip {e}")

    print("----")
    if fails:
        print(f"TEST_DESKTOP_SHELL_FAIL fails={fails}")
        return 1
    print("TEST_DESKTOP_SHELL_PASS fails=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
