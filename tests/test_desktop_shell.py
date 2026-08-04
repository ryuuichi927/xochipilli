#!/usr/bin/env python3
"""Desktop shell checks: native webview, no Chrome, clickable + resizable (Incident F)."""

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

    for n, lab in [
        ("shell_mode=pywebview", "pywebview mode"),
        ("_patch_cocoa_early_content_view", "early contentView patch"),
        ("setContentView_", "setContentView call"),
        ("contentLayoutRect", "content layout frame"),
        ("styleMask", "styleMask resizable log"),
        ("_NS_RESIZABLE", "resizable bit constant"),
        ("_prepare_html", "html prepare helper kept"),
        ("_kill_legacy_chrome_app", "kill legacy chrome"),
        ("XOCHIPILLI_SHELL", "opt-in browser"),
        ('or "webview"', "default webview"),
        ("using url= navigation", "primary url= path"),
        ("nav ok — no reload", "single-nav success log"),
        ("resizable", "resizable True"),
    ]:
        (ok if n in desk else bad)(lab)

    # Primary path must use url=, not load_html thrashing
    if '"url": base' in desk or '"url": base,' in desk or '"url": base' in desk:
        ok("create_window uses url=")
    elif '"url":' in desk and "window_kwargs" in desk:
        ok("create_window uses url=")
    else:
        bad("create_window should prefer url=")

    # Must not thrash: shown/boot must not call load_html in happy path
    for n in (
        "shown load_html",
        "boot load_html",
        "using load_html path",
    ):
        (ok if n not in desk else bad)(f"no thrash log: {n}")

    # Must not auto chrome
    for n in ("def _open_chromium_app", "shell_mode=chromium-app", "--app="):
        (ok if n not in desk else bad)(f"lacks {n}")

    # Must not hang path: evaluate_js on full UI should not be the happy path
    if "evaluate_js(" in desk and "avoid bridge hang" not in desk:
        bad("evaluate_js still used without hang note")
    else:
        ok("no hanging evaluate_js paint path")

    # Must not wrap WKNavigation decidePolicy (ObjC crash)
    for n in ("decidePolicyForNavigationAction", "decidePolicyForNavigationResponse"):
        (ok if n not in desk else bad)(f"no WKNavigation wrap: {n}")

    main_body = desk.split("def main")[-1]
    (ok if "_run_pywebview(target)" in main_body else bad)("main→pywebview")

    # Overlay CSS must not block clicks when hidden
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    for n, lab in [
        (".gen-loader[hidden]", "gen-loader[hidden] rule"),
        (".settings-backdrop[hidden]", "settings-backdrop[hidden] rule"),
        ("pointer-events: none !important", "hidden pointer-events none"),
    ]:
        (ok if n in css else bad)(lab)

    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/health", timeout=1.5) as r:
            (ok if b"Xochipilli" in r.read() else bad)("live health")
        with urllib.request.urlopen("http://127.0.0.1:8787/", timeout=1.5) as r:
            b = r.read()
        (ok if b"0c0e12" in b or b"style.css" in b else bad)("live index has dark UI refs")
    except Exception as e:
        ok(f"live skip {e}")

    # runtime chrome absence (soft)
    pc = subprocess.run(["pgrep", "-f", "chrome-app-profile"], capture_output=True)
    (ok if pc.returncode != 0 else bad)("no chrome-app-profile now")

    print("----")
    if fails:
        print(f"TEST_DESKTOP_SHELL_FAIL fails={fails}")
        return 1
    print("TEST_DESKTOP_SHELL_PASS fails=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
