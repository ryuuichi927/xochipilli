#!/usr/bin/env python3
"""Desktop shell contracts: stock webview + in-bundle Mach-O launcher."""

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

    for n in (
        "stock pywebview",
        "shell_mode=pywebview",
        '"url": base',
        "resizable\": True",
        "_log_bundle_identity",
        "_kill_legacy_chrome_app",
        "XOCHIPILLI_SHELL",
    ):
        (ok if n in desk else bad)(f"has {n}")

    for n in (
        "setContentView_",
        "_patch_cocoa_content_container",
        "_patch_cocoa_early_content_view",
        "using load_html path",
        "def _open_chromium_app",
        "--app=",
        "evaluate_js(",
    ):
        (ok if n not in desk else bad)(f"lacks {n}")

    launcher = ROOT / "Xochipilli.app/Contents/MacOS/Xochipilli"
    if not launcher.is_file():
        bad("repo launcher missing")
    else:
        r = subprocess.run(["file", str(launcher)], capture_output=True, text=True)
        out = r.stdout + r.stderr
        if "Mach-O" in out:
            ok("repo launcher is Mach-O")
        else:
            bad(f"repo launcher not Mach-O: {out.strip()}")

    apps = Path("/Applications/Xochipilli.app/Contents/MacOS/Xochipilli")
    if apps.is_file():
        r = subprocess.run(["file", str(apps)], capture_output=True, text=True)
        (ok if "Mach-O" in r.stdout else bad)("Apps launcher Mach-O")
    else:
        bad("Apps launcher missing")

    plist = (ROOT / "Xochipilli.app/Contents/Info.plist").read_text(encoding="utf-8")
    (ok if "NSLocalNetworkUsageDescription" in plist else bad)("plist local network usage")
    (ok if "NSAllowsLocalNetworking" in plist else bad)("plist allows local networking")

    csrc = ROOT / "native/xochipilli_launcher.c"
    (ok if csrc.is_file() and "Py_Initialize" in csrc.read_text() else bad)("native launcher source")

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
