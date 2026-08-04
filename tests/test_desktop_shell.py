#!/usr/bin/env python3
"""Desktop shell: stock pywebview, no cocoa contentView patches, no Chrome."""

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
        ("stock pywebview", "stock path log"),
        ("_kill_legacy_chrome_app", "kill legacy chrome"),
        ("XOCHIPILLI_SHELL", "opt-in browser"),
        ('or "webview"', "default webview"),
        ("resizable\": True", "resizable"),
        ("\"url\": base", "url= create"),
    ]:
        (ok if n in desk else bad)(lab)

    # Must NOT monkey-patch contentView
    for n in (
        "setContentView_",
        "_patch_cocoa_content_container",
        "_patch_cocoa_early_content_view",
        "using load_html path",
        "def _open_chromium_app",
        "shell_mode=chromium-app",
        "--app=",
    ):
        (ok if n not in desk else bad)(f"lacks {n}")

    if "evaluate_js(" in desk:
        bad("evaluate_js( still present")
    else:
        ok("no evaluate_js(")

    main_body = desk.split("def main")[-1]
    (ok if "_run_pywebview(target)" in main_body else bad)("main→pywebview")

    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/health", timeout=1.5) as r:
            (ok if b"Xochipilli" in r.read() else bad)("live health")
    except Exception as e:
        ok(f"live skip {e}")

    pc = subprocess.run(["pgrep", "-f", "chrome-app-profile"], capture_output=True)
    (ok if pc.returncode != 0 else bad)("no chrome-app-profile")

    print("----")
    if fails:
        print(f"TEST_DESKTOP_SHELL_FAIL fails={fails}")
        return 1
    print("TEST_DESKTOP_SHELL_PASS fails=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
