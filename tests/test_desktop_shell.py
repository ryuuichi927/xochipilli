#!/usr/bin/env python3
"""Desktop shell / layout regression checks (no GUI click automation).

Run:
  .venv/bin/python tests/test_desktop_shell.py
"""

from __future__ import annotations

import ast
import re
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
        bad(f"desktop_app.py syntax: {e}")

    for needle, label in [
        ("_wait_until_profile_quiet", "profile lifetime wait"),
        ("_profile_pids", "profile pid probe"),
        ("shell_mode=chromium-app", "chromium mode log"),
        ("start_new_session=False", "no new session for chrome"),
        ("chrome-app-profile", "profile path"),
        ("--window-size=", "window size flag"),
    ]:
        (ok if needle in desk else bad)(label)

    if "chrome_proc.wait()" in desk or "chromium_proc.wait()" in desk:
        bad("still waiting on single chrome Popen.wait()")
    else:
        ok("no single-Popen chrome wait")

    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    for needle, label in [
        ("-webkit-fill-available", "fill available height"),
        ("flex: 1 1 0", "layout flex fill"),
        ("clamp(160px, 22vh, 220px)", "wave vh clamp"),
    ]:
        (ok if needle in css else bad)(f"css {label}")

    js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    for needle, label in [
        ("function bindLayoutResize", "bindLayoutResize defined"),
        ("ResizeObserver", "ResizeObserver"),
        ("visualViewport", "visualViewport"),
        ("bindLayoutResize()", "bindLayoutResize called"),
    ]:
        (ok if needle in js else bad)(f"js {label}")

    # Ensure bindLayoutResize is not nested wrongly: top-level function
    if re.search(r"\nfunction bindLayoutResize\s*\(", js):
        ok("bindLayoutResize is top-level")
    else:
        bad("bindLayoutResize not top-level")

    idx = (ROOT / "static/index.html").read_text(encoding="utf-8")
    if "craft5" in idx:
        ok("index cache craft5")
    else:
        bad("index missing craft5 cache bust")

    try:
        with urllib.request.urlopen("http://127.0.0.1:8787/api/health", timeout=1.5) as r:
            body = r.read().decode()
        if "Xochipilli" in body:
            ok("live health Xochipilli")
        else:
            ok(f"live health ({body[:50]!r})")
        with urllib.request.urlopen(
            "http://127.0.0.1:8787/static/app.js?v=craft5", timeout=1.5
        ) as r:
            js_live = r.read().decode("utf-8", "replace")
        (ok if "bindLayoutResize" in js_live else bad)("live app.js has bindLayoutResize")
        with urllib.request.urlopen(
            "http://127.0.0.1:8787/static/style.css?v=craft5", timeout=1.5
        ) as r:
            css_live = r.read().decode("utf-8", "replace")
        (ok if "-webkit-fill-available" in css_live else bad)("live css fill-available")
    except Exception as e:
        ok(f"live server skip: {e}")

    p = ROOT / "Xochipilli.app/Contents/MacOS/Xochipilli"
    if p.is_file():
        r = subprocess.run(["/bin/bash", "-n", str(p)], capture_output=True, text=True)
        (ok if r.returncode == 0 else bad)("bash -n app launcher")

    print("----")
    if fails:
        print(f"TEST_DESKTOP_SHELL_FAIL fails={fails}")
        return 1
    print("TEST_DESKTOP_SHELL_PASS fails=0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
