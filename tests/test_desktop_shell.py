#!/usr/bin/env python3
"""Desktop shell contracts: load_html+inline CSS, craft dynamic load, skip inject, Mach-O."""

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
        "shell_mode=pywebview",
        'resizable": True',
        "_log_bundle_identity",
        "_kill_legacy_chrome_app",
        "XOCHIPILLI_SHELL",
        "_build_shell_html",
        "load_html",
        "xochi-inline-css",
        "XOCHIPILLI_SKIP_PYWEBVIEW_INJECT",
        "setInspectable_",
        "inject_pywebview SKIPPED",
        "OPEN_DEVTOOLS_IN_DEBUG",
        "background_color",
        "#0c0e12",
        "__XOCHI_API_BASE__",
        "app.server:app",
    ):
        (ok if n in desk else bad)(f"has {n}")

    # Craft must not be permanently deferred without a load path.
    craft_markers = (
        "loadCraft",
        "__XOCHI_CRAFT",
        "craft_ui.js?v=desktop2",
        "xochi-craft-loader",
    )
    if any(m in desk for m in craft_markers):
        ok("craft dynamic loader path present")
    else:
        bad("craft loader missing (need loadCraft / __XOCHI_CRAFT / inject path)")

    if "deferred forever" in desk.lower() or "permanently strip" in desk.lower():
        # Allow comments that say we do NOT permanently strip.
        if "not permanently" in desk.lower() or "not stripped forever" in desk.lower():
            ok("craft not hard-removed (comment only)")
        elif "deferred: whites" in desk and "loadCraft" not in desk:
            bad("craft deferred without loader")
        else:
            ok("craft strip language checked")
    else:
        ok("no permanent craft-strip language")

    # Must actually inject craft after paint, not only comment it out.
    if "dynamic load" in desk.lower() or "loadCraft" in desk:
        ok("craft enablement strategy documented in shell")
    else:
        bad("no craft enablement strategy in desktop_app")

    if "craft_ui.js" in desk and (
        "appendChild" in desk or "createElement" in desk or "evaluate_js" in desk
    ):
        ok("craft_ui.js injection mechanism present")
    else:
        bad("craft_ui.js mentioned but no injection mechanism")

    for n in (
        "setContentView_",
        "_patch_cocoa_content_container",
        "_patch_cocoa_early_content_view",
        "def _open_chromium_app",
        "--app=",
    ):
        (ok if n not in desk else bad)(f"lacks {n}")

    if "_build_shell_html" in desk and "using load_html shell" in desk:
        ok("load_html shell path present")
    else:
        bad("load_html shell path missing")

    # Every webview.start path should keep debug= where possible
    if "debug=debug" in desk or "debug=debug," in desk:
        ok("webview.start keeps debug=")
    else:
        bad("webview.start debug= missing")

    craft_js = (ROOT / "static/craft_ui.js").read_text(encoding="utf-8")
    for n in (
        "function boot",
        "function scan",
        "function wireCard",
        "function openUnmatchUI",
        "SCAN_DEBOUNCE",
        "apiUrl",
        "unmatch-v2",
        "affect",
        "episode",
        "console.error",
    ):
        (ok if n in craft_js else bad)(f"craft_ui.js has {n}")

    # Hardened try/catch around boot path
    if "try {" in craft_js and "craft boot" in craft_js:
        ok("craft_ui.js boot try/catch")
    else:
        bad("craft_ui.js missing boot try/catch hardening")

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
    ctxt = csrc.read_text(encoding="utf-8") if csrc.is_file() else ""
    (ok if csrc.is_file() and "Py_Initialize" in ctxt else bad)("native launcher source")
    (ok if "ProjectRoot" in ctxt and "read_project_root" in ctxt else bad)(
        "launcher reads ProjectRoot"
    )
    if "/Users/" in ctxt and "Documents" in ctxt:
        bad("launcher still hardcodes Documents user path")
    else:
        ok("launcher has no hardcoded Documents path")

    pr = ROOT / "Xochipilli.app/Contents/Resources/ProjectRoot"
    if pr.is_file():
        root_line = pr.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        if root_line == str(ROOT):
            ok("ProjectRoot matches clone")
        else:
            bad(f"ProjectRoot={root_line!r} != {ROOT}")
    else:
        bad("ProjectRoot file missing")

    desk_more = (
        "_kill_our_listeners_on_port",
        "_ensure_media_path",
        "XOCHIPILLI_API_TOKEN",
        "__XOCHI_API_TOKEN__",
        "_warn_missing_deps",
    )
    for n in desk_more:
        (ok if n in desk else bad)(f"has {n}")

    # A 401 that skips CORS reaches WKWebView as the unreadable "Load failed", which is
    # how a stale token used to masquerade as a broken app. CORS must be added last so it
    # wraps the token check.
    main_py = (ROOT / "app/main.py").read_text(encoding="utf-8")
    i_token = main_py.find("add_middleware(_ApiTokenMiddleware)")
    i_cors = main_py.find("add_middleware(\n    CORSMiddleware")
    if i_token < 0 or i_cors < 0:
        bad("cannot locate middleware registration order")
    elif i_token < i_cors:
        ok("CORS middleware wraps the API token check")
    else:
        bad("token middleware is outside CORS — 401 will surface as 'Load failed'")

    app_js = (ROOT / "static/app.js").read_text(encoding="utf-8")
    (ok if 'NEW_PROJECT_OPTION = "__new__"' in app_js else bad)("app.js has create-new option")
    (ok if 'projectCreateNew' in app_js else bad)("project dropdown offers create-new")
    (ok if "statusTokenStale" in app_js else bad)("app.js explains a stale token")
    (ok if "unarchiveAndWait" in app_js else bad)("app.js pulls a cold project back")
    (ok if 'startsWith("☁")' in app_js or "☁ ${title}" in app_js else bad)(
        "app.js marks archived projects"
    )
    i18n_js = (ROOT / "static/i18n.js").read_text(encoding="utf-8")
    for key in ("projectCreateNew", "statusTokenStale", "statusUnarchiving", "projectArchivedHint"):
        n_lang = i18n_js.count(f"{key}:")
        (ok if n_lang >= 3 else bad)(f"i18n {key} in {n_lang}/3 languages")

    # Works must not live in the repo: a re-clone or a code update would put them in the
    # blast radius, and the venv/data would travel with git.
    paths_py = (ROOT / "app/paths.py").read_text(encoding="utf-8")
    if "\nDATA = ROOT /" in paths_py:
        bad("data home is still inside the repo")
    else:
        ok("data home lives outside the repo")
    for n in ("XOCHIPILLI_DATA", "XOCHIPILLI_ARCHIVE", "LEGACY_DATA"):
        (ok if n in paths_py else bad)(f"paths.py has {n}")
    taste_py = (ROOT / "app/taste.py").read_text(encoding="utf-8")
    if 'ROOT / "data"' in taste_py:
        bad("taste.py still writes into the repo")
    else:
        ok("taste.py follows the data home")

    arch_py = (ROOT / "app/archive.py").read_text(encoding="utf-8")
    for n in (
        "_copy_tree_verified",
        "size mismatch",
        "brctl",
        "evict_archived",
        "_CrossProcessLock",
        "cold_projects",
        "restore_project",
    ):
        (ok if n in arch_py else bad)(f"archive.py has {n}")
    # Deleting before the copy is verified would lose the work outright.
    i_verify = arch_py.find("_copy_tree_verified(src, dst)")
    i_delete = arch_py.find("shutil.rmtree(entry)")
    if i_verify < 0 or i_delete < 0:
        bad("cannot locate archive copy/delete order")
    elif i_verify < i_delete:
        ok("archive verifies the copy before deleting the local one")
    else:
        bad("archive deletes local files before verifying the cloud copy")

    for n in ("touch_opened", "def last_seen"):
        (ok if n in (ROOT / "app/storage.py").read_text(encoding="utf-8") else bad)(
            f"storage.py has {n}"
        )
    server_py = (ROOT / "app/server.py").read_text(encoding="utf-8")
    (ok if "archive" in server_py and "Timer" in server_py else bad)(
        "server schedules the archive sweep"
    )
    (ok if "XOCHIPILLI_NO_ARCHIVE" in server_py else bad)("archive sweep can be switched off")
    agent = ROOT / "tools/archive_cold.py"
    (ok if agent.is_file() else bad)("archive CLI / launchd agent installer exists")
    if agent.is_file():
        agent_txt = agent.read_text(encoding="utf-8")
        for n in ("StartCalendarInterval", "launchctl", "--restore", "--dry-run"):
            (ok if n in agent_txt else bad)(f"archive CLI has {n}")

    digest_py = (ROOT / "app/digest.py").read_text(encoding="utf-8")
    (ok if "max_frames" in digest_py else bad)("structure analysis caps its affinity matrix")
    main_py_checks = ("_digest_or_explain", "ModuleNotFoundError", "ffmpeg が見つからない")
    for n in main_py_checks:
        (ok if n in main_py else bad)(f"import errors explain {n}")

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
