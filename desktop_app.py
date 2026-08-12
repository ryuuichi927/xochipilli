"""
Xochipilli desktop shell — local FastAPI + stock pywebview (cocoa / WKWebView).

Dock chain: /Applications/Xochipilli.app Mach-O launcher → import desktop_app; main().

Shell default: pywebview only. Opt-in browser: XOCHIPILLI_SHELL=browser.

Load path (2026-08-04 rebuild 0.2.0):
  create_window(html=…) once with inlined CSS + __XOCHI_API_BASE__;
  craft_ui.js loaded dynamically after first paint (sync <script> can white WK).
  No cocoa content-view reassignment / NSView-container patches. No second load_html thrash.
  Skip inject_pywebview by default (UI uses FastAPI fetch).

See docs/DESKTOP.md and docs/DESKTOP_INCIDENTS_2026-08-04.md.
"""

from __future__ import annotations

import atexit
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 1. env / path hygiene / UTF-8 log
# ---------------------------------------------------------------------------

# Dock / Mach-O launcher often leaves stdout as ASCII; Japanese paths must not crash.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("LC_ALL", os.environ.get("LC_ALL") or "en_US.UTF-8")
os.environ.setdefault("LANG", os.environ.get("LANG") or "en_US.UTF-8")
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

os.environ.pop("PYTHONPATH", None)
os.environ.pop("PYTHONHOME", None)
_clean_path: list[str] = []
for _p in sys.path:
    if not _p:
        _clean_path.append(_p)
        continue
    low = _p.replace("\\", "/").lower()
    if "/.bentool/" in low or "bentool-agent" in low:
        continue
    _clean_path.append(_p)
sys.path[:] = _clean_path

# ---------------------------------------------------------------------------
# 2. constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8787"))
URL = f"http://{HOST}:{PORT}"
VENV_PY = ROOT / ".venv" / "bin" / "python"
SUPPORT = Path.home() / "Library/Application Support/Xochipilli"
CHROME_PROFILE = SUPPORT / "chrome-app-profile"
SESSION_LOG = Path.home() / "Library/Logs/Xochipilli/session.log"
TOKEN_FILE = SUPPORT / "api_token"
_DID_ACTIVATE_COCOA = False


def _log(msg: str) -> None:
    """UTF-8 safe logger — never raise (Dock crash was UnicodeEncodeError on JA paths)."""
    line = f"[xochipilli] {msg}"
    printed = False
    try:
        print(line, flush=True)
        printed = True
    except Exception:
        try:
            buf = getattr(sys.stdout, "buffer", None)
            if buf is not None:
                buf.write((line + "\n").encode("utf-8", errors="replace"))
                buf.flush()
                printed = True
        except Exception:
            pass
    if printed:
        return
    try:
        SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(SESSION_LOG, "a", encoding="utf-8", errors="replace") as lf:
            lf.write(line + "\n")
    except Exception:
        pass


def _alert(message: str, *, critical: bool = False) -> None:
    try:
        style = "critical" if critical else "informational"
        msg = str(message)[:520]
        script = (
            "on run argv\n"
            f'  display alert "Xochipilli" message (item 1 of argv) as {style} giving up after 16\n'
            "end run"
        )
        subprocess.run(
            ["/usr/bin/osascript", "-e", script, msg],
            check=False,
            capture_output=True,
        )
    except Exception:
        print(f"[xochipilli] ALERT: {message}", file=sys.stderr, flush=True)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
    except Exception:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ---------------------------------------------------------------------------
# 3. server lifecycle (start / reuse / stop) — app.server:app
# ---------------------------------------------------------------------------


def _health_payload() -> dict | None:
    try:
        with urllib.request.urlopen(f"{URL}/api/health", timeout=1.2) as r:
            if r.status != 200:
                return None
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.35)
        return s.connect_ex((HOST, port)) == 0


def _health_ok() -> bool:
    h = _health_payload()
    if not h or not h.get("ok"):
        return False
    prod = str(h.get("product") or "")
    return (not prod) or prod == "Xochipilli"


def _cors_ok() -> bool:
    """Desktop about:blank shell needs ACAO on API responses."""
    try:
        req = urllib.request.Request(
            f"{URL}/api/health",
            headers={"Origin": "null"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=1.5) as r:
            acao = r.headers.get("Access-Control-Allow-Origin") or ""
            return acao in ("*", "null") or "127.0.0.1" in acao or "localhost" in acao
    except Exception as e:
        _log(f"cors probe failed: {e}")
        return False


def _listener_pids_on_port(port: int) -> list[int]:
    try:
        r = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        _log(f"lsof port {port}: {e}")
        return []
    pids: list[int] = []
    for ln in (r.stdout or "").splitlines()[1:]:
        parts = ln.split()
        if len(parts) >= 2 and parts[1].isdigit():
            pids.append(int(parts[1]))
    return pids


def _process_command(pid: int) -> str:
    try:
        r = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        return (r.stdout or "").strip()
    except OSError:
        return ""


def _is_our_server_pid(pid: int) -> bool:
    """True if this PID looks like a Xochipilli/uvicorn server we may stop."""
    cmd = _process_command(pid).lower()
    if not cmd:
        # Fallback: if /api/health says Xochipilli on this port, treat listeners as ours.
        return False
    return any(
        m in cmd
        for m in (
            "uvicorn",
            "app.server",
            "desktop_app",
            "xochipilli",
            "music-film-workbench",
            "/projects/xochipilli",
        )
    )


def _kill_our_listeners_on_port(port: int, *, force_product: bool = False) -> None:
    """Stop Xochipilli/uvicorn listeners on PORT — never SIGKILL unrelated apps.

    force_product: also stop listeners when live /api/health is product=Xochipilli
    (covers cases where `ps` is unavailable or cmdline is truncated).
    """
    pids = _listener_pids_on_port(port)
    if not pids:
        return
    product_ours = False
    if force_product:
        h = _health_payload() or {}
        product_ours = bool(h.get("ok")) and (
            not h.get("product") or h.get("product") == "Xochipilli"
        )
    ours: list[int] = []
    for pid in pids:
        if _is_our_server_pid(pid) or product_ours:
            ours.append(pid)
        else:
            cmd = _process_command(pid) or "(unknown)"
            _log(f"leave foreign listener pid={pid} cmd={cmd[:120]}")
    if not ours:
        _log(f"no Xochipilli listeners on :{port} to stop")
        return
    _log(f"stopping our listeners on :{port} pids={ours[:12]}")
    for pid in ours:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            pass
    time.sleep(0.45)
    for pid in ours:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError, ValueError):
            pass


def _ensure_media_path(env: dict[str, str]) -> None:
    """Dock launches often omit Homebrew — put ffmpeg/ffprobe on PATH."""
    extras = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local/bin"),
    ]
    cur = env.get("PATH") or os.environ.get("PATH") or ""
    parts = [p for p in cur.split(":") if p]
    for p in reversed(extras):
        if p not in parts:
            parts.insert(0, p)
    env["PATH"] = ":".join(parts)


def _token_fingerprint(tok: str) -> str:
    import hashlib

    return hashlib.sha256(tok.encode("utf-8")).hexdigest()[:12]


def _write_api_token(tok: str) -> None:
    try:
        SUPPORT.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(tok + "\n", encoding="utf-8")
        try:
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass
    except OSError as e:
        _log(f"api_token write failed: {e}")


def _ensure_api_token(*, rotate: bool = False) -> str:
    """Stable local API token shared by Dock shell + uvicorn (file-backed)."""
    if not rotate:
        env_tok = (os.environ.get("XOCHIPILLI_API_TOKEN") or "").strip()
        if env_tok:
            _write_api_token(env_tok)
            return env_tok
        try:
            if TOKEN_FILE.is_file():
                file_tok = TOKEN_FILE.read_text(encoding="utf-8").strip()
                if file_tok:
                    os.environ["XOCHIPILLI_API_TOKEN"] = file_tok
                    return file_tok
        except OSError as e:
            _log(f"api_token read failed: {e}")
    tok = os.urandom(16).hex()
    os.environ["XOCHIPILLI_API_TOKEN"] = tok
    _write_api_token(tok)
    _log("generated XOCHIPILLI_API_TOKEN for this session")
    return tok


def _token_compatible(h: dict | None) -> bool:
    """Reuse only if live server expects the same API token we hold."""
    tok = (os.environ.get("XOCHIPILLI_API_TOKEN") or "").strip()
    want = bool(tok)
    have = bool((h or {}).get("api_token_required"))
    if want != have:
        return False
    if not want:
        return True
    fp = str((h or {}).get("api_token_fp") or "")
    if not fp:
        # Old server without fingerprint — do not reuse (restart with known token).
        return False
    return fp == _token_fingerprint(tok)


def _preflight_http() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{URL}/", timeout=2.0) as r:
            body = r.read()
            if r.status != 200:
                return False, f"GET / status={r.status}"
            low = body[:200].lower()
            if b"<html" not in low and b"<!doctype" not in low:
                return False, f"GET / not html ({len(body)} bytes)"
            return True, f"GET / ok ({len(body)} bytes)"
    except Exception as e:
        return False, f"GET / failed: {e}"


def _start_server() -> subprocess.Popen | None:
    _ensure_api_token()
    if _health_ok():
        h = _health_payload() or {}
        if _cors_ok() and _token_compatible(h):
            _log(
                f"reuse server at {URL} (product={h.get('product')}, cors=ok, "
                f"token_required={h.get('api_token_required')})"
            )
            return None
        _log("reuse blocked: CORS/token mismatch — restarting our listeners")
        _kill_our_listeners_on_port(PORT, force_product=True)
        time.sleep(0.35)
    elif _port_open(PORT):
        for _ in range(24):
            if _health_ok():
                h = _health_payload() or {}
                if _cors_ok() and _token_compatible(h):
                    _log(f"reuse server at {URL} (became healthy, cors/token ok)")
                    return None
                _log("port open + healthy but CORS/token mismatch — restarting")
                _kill_our_listeners_on_port(PORT, force_product=True)
                time.sleep(0.35)
                break
            time.sleep(0.25)
        else:
            msg = (
                f"ポート {PORT} は使用中だが Xochipilli の /api/health が応答しない。"
                " 別アプリの可能性があるため終了します。"
            )
            _log(f"WARN: {msg}")
            _alert(msg, critical=True)
            raise SystemExit(2)

    if _port_open(PORT) and not _health_ok():
        msg = f"ポート {PORT} がまだ塞がっている。Xochipilli を起動できない。"
        _log(f"WARN: {msg}")
        _alert(msg, critical=True)
        raise SystemExit(2)
    if _port_open(PORT) and _health_ok() and not _token_compatible(_health_payload()):
        msg = (
            f"ポート {PORT} の既存サーバを更新できなかった。"
            " 古いプロセスが残っている可能性がある。"
        )
        _log(f"WARN: {msg}")
        _alert(msg, critical=True)
        raise SystemExit(2)

    py = str(VENV_PY if VENV_PY.is_file() else sys.executable)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.setdefault("VIDEO_PROVIDER", env.get("VIDEO_PROVIDER", "mock"))
    env["XOCHIPILLI_API_TOKEN"] = _ensure_api_token()
    _ensure_media_path(env)
    cmd = [
        py,
        "-m",
        "uvicorn",
        "app.server:app",
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--app-dir",
        str(ROOT),
    ]
    SESSION_LOG.parent.mkdir(parents=True, exist_ok=True)
    _log(f"starting {URL} …")
    log_f = None
    try:
        log_f = open(SESSION_LOG, "a", encoding="utf-8", errors="replace")
        log_f.write(f"\n==== uvicorn spawn pid_parent={os.getpid()} ====\n")
        log_f.flush()
        stdout_target: Any = log_f
    except OSError as e:
        _log(f"session.log open failed ({e}); uvicorn stdout → DEVNULL")
        stdout_target = subprocess.DEVNULL
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=stdout_target,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    for _ in range(200):  # ~30s — cold librosa/numpy import can be slow under Dock
        if _health_ok() and _token_compatible(_health_payload()):
            cors = _cors_ok()
            _log(f"server ready cors={'ok' if cors else 'MISSING'} token=ok")
            if not cors:
                _log("WARN: server up but CORS headers still missing")
            return proc
        if proc.poll() is not None:
            _log("server exited early — see session.log")
            _alert("ローカルサーバの起動に失敗した。session.log を確認。", critical=True)
            return proc
        time.sleep(0.15)
    _log("server did not become healthy in time")
    _alert(f"サーバが {URL} で準備完了しなかった。", critical=True)
    return proc


def _stop_server(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.terminate()
        except OSError:
            pass
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()


# ---------------------------------------------------------------------------
# 4. chrome legacy kill
# ---------------------------------------------------------------------------


def _kill_legacy_chrome_app() -> None:
    try:
        r = subprocess.run(
            ["pgrep", "-f", str(CHROME_PROFILE)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return
    pids = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip().isdigit()]
    if not pids:
        return
    _log(f"stopping legacy chrome-app profile pids={pids[:12]}")
    subprocess.run(["pkill", "-f", str(CHROME_PROFILE)], check=False, capture_output=True)
    time.sleep(0.35)


# ---------------------------------------------------------------------------
# 5. cocoa helpers: activate, inspectable, skip-inject, debug menu
# ---------------------------------------------------------------------------


def _activate_cocoa(*, force: bool = False) -> None:
    """Bring app forward. Default: only once per process (avoids window bounce)."""
    global _DID_ACTIVATE_COCOA
    try:
        if _DID_ACTIVATE_COCOA and not force:
            return
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        _DID_ACTIVATE_COCOA = True
        _log("cocoa activateIgnoringOtherApps")
    except Exception as e:
        _log(f"cocoa activate skipped: {e}")


def _webview_debug_enabled() -> bool:
    """Default OFF for Dock product builds. On: XOCHIPILLI_WEBVIEW_DEBUG=1."""
    v = (os.environ.get("XOCHIPILLI_WEBVIEW_DEBUG") or "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _skip_pywebview_inject_enabled() -> bool:
    """Skip inject_pywebview (default ON). Off: XOCHIPILLI_SKIP_PYWEBVIEW_INJECT=0.
    Workbench talks to FastAPI via fetch; bridge inject hangs didFinish/loaded on this Mac.
    """
    v = (os.environ.get("XOCHIPILLI_SKIP_PYWEBVIEW_INJECT") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _each_wkwebview():
    """Yield native WKWebView from the cocoa module webview.start actually loaded."""
    mod = sys.modules.get("webview.platforms.cocoa")
    if mod is None:
        try:
            import webview.platforms.cocoa as mod  # noqa: WPS433
        except Exception:
            return
    BrowserView = getattr(mod, "BrowserView", None)
    if BrowserView is None:
        return
    inst = getattr(BrowserView, "instances", None) or {}
    _log(f"cocoa BrowserView id={id(BrowserView)} instances={len(inst)}")
    for i in list(inst.values()):
        wv = getattr(i, "webview", None) or getattr(i, "webkit", None)
        if wv is not None:
            yield i, wv


def _patch_skip_pywebview_inject() -> None:
    """No-op inject + still fire loaded so didFinish path can finish without bridge hang."""
    try:
        import webview.util as util
    except Exception as e:
        _log(f"skip-inject import util: {e}")
        return
    if getattr(util, "_xochi_skip_inject_patched", False):
        return

    def _noop_inject(platform: str, window) -> str:  # type: ignore[no-untyped-def]
        _log(f"inject_pywebview SKIPPED platform={platform}")
        try:
            window.events.before_load.set()
        except Exception:
            pass
        try:
            window.events.loaded.set()
        except Exception:
            pass
        try:
            window.events._pywebviewready.set()
        except Exception:
            pass
        return ""

    util.inject_pywebview = _noop_inject  # type: ignore[assignment]
    util._xochi_skip_inject_patched = True  # type: ignore[attr-defined]
    try:
        import webview.platforms.cocoa as cocoa  # noqa: WPS433

        cocoa.inject_pywebview = _noop_inject  # type: ignore[attr-defined]
        _log("skip-inject: patched util + cocoa.inject_pywebview")
    except Exception as e:
        _log(f"skip-inject: util patched; cocoa not yet ({e})")


def _call_on_main(fn, reason: str) -> None:
    """AppKit menu/UI must run on main thread."""
    try:
        from PyObjCTools import AppHelper

        AppHelper.callAfter(fn)
        _log(f"main-thread scheduled ({reason}): {getattr(fn, '__name__', fn)}")
    except Exception as e:
        _log(f"main-thread schedule failed ({reason}): {e} — calling inline")
        try:
            fn()
        except Exception as e2:
            _log(f"inline {reason}: {e2}")


def _apply_inspectable(reason: str) -> None:
    """macOS 13.3+: WKWebView.isInspectable must be YES or right-click is dead."""
    n = 0
    for _i, wv in _each_wkwebview() or []:
        n += 1
        try:
            prefs = wv.configuration().preferences()
            prefs.setValue_forKey_(True, "developerExtrasEnabled")
        except Exception as e:
            _log(f"inspectable ({reason}): developerExtras: {e}")
        applied = False
        if hasattr(wv, "setInspectable_"):
            try:
                wv.setInspectable_(True)
                applied = True
                _log(f"inspectable ({reason}): setInspectable_(True) ok")
            except Exception as e:
                _log(f"inspectable ({reason}): setInspectable_: {e}")
        if not applied:
            try:
                wv.setValue_forKey_(True, "inspectable")
                applied = True
                _log(f"inspectable ({reason}): KVC inspectable=YES ok")
            except Exception as e:
                _log(f"inspectable ({reason}): KVC failed: {e}")
        try:
            win = wv.window()
            cv = win.contentView() if win is not None else None
            url = None
            title = None
            try:
                u = wv.URL()
                url = str(u.absoluteString()) if u is not None else None
            except Exception:
                pass
            try:
                title = str(wv.title()) if wv.title() is not None else None
            except Exception:
                pass
            _log(
                f"inspectable ({reason}): wk.inWindow={win is not None} "
                f"contentView={type(cv).__name__ if cv is not None else None} "
                f"url={url!r} title={title!r}"
            )
        except Exception as e:
            _log(f"inspectable ({reason}): hierarchy: {e}")
    if n == 0:
        _log(f"inspectable ({reason}): no WKWebView instances yet")


def _patch_cocoa_inspectable_on_init() -> None:
    """Patch BrowserView.__init__ only — set isInspectable. Never touch setContentView."""
    try:
        from webview.platforms.cocoa import BrowserView
    except Exception as e:
        _log(f"inspectable init-patch import: {e}")
        return
    if getattr(BrowserView, "_xochi_inspectable_patched", False):
        return
    orig = BrowserView.__init__

    def _wrapped(self, window):  # type: ignore[no-untyped-def]
        orig(self, window)
        try:
            wv = getattr(self, "webview", None)
            if wv is None:
                return
            try:
                wv.configuration().preferences().setValue_forKey_(
                    True, "developerExtrasEnabled"
                )
            except Exception:
                pass
            if hasattr(wv, "setInspectable_"):
                wv.setInspectable_(True)
            else:
                try:
                    wv.setValue_forKey_(True, "inspectable")
                except Exception:
                    pass
        except Exception as e:
            _log(f"inspectable init-patch body: {e}")

    BrowserView.__init__ = _wrapped  # type: ignore[method-assign]
    BrowserView._xochi_inspectable_patched = True  # type: ignore[attr-defined]
    _log("cocoa BrowserView.__init__ patched for isInspectable only")


def _open_web_inspector(reason: str) -> None:
    """Open Web Inspector via pywebview helper (no auto-open on boot)."""
    _apply_inspectable(reason)
    try:
        from webview.platforms.cocoa import BrowserView
    except Exception as e:
        _log(f"inspector ({reason}): import cocoa failed: {e}")
        return
    instances = list(getattr(BrowserView, "instances", {}) or {}.values())
    if not instances:
        _log(f"inspector ({reason}): no BrowserView instances yet")
        return
    for i in instances:
        wv = getattr(i, "webview", None) or getattr(i, "webkit", None)
        if wv is None:
            continue
        try:
            ok = BrowserView._open_web_inspector(wv)
            _log(f"inspector ({reason}): _open_web_inspector → {ok}")
        except Exception as e:
            _log(f"inspector ({reason}): open failed: {e}")


def _install_debug_menu() -> None:
    """Menu bar Debug → Web Inspector (⌥⌘I). No auto inspector."""
    try:
        from AppKit import NSApp, NSMenu, NSMenuItem
    except Exception as e:
        _log(f"debug menu skipped (AppKit): {e}")
        return

    app = NSApp()
    if app is None:
        _log("debug menu skipped: no NSApp")
        return

    menubar = app.mainMenu()
    if menubar is None:
        menubar = NSMenu.alloc().init()
        app.setMainMenu_(menubar)

    for i in range(menubar.numberOfItems()):
        it = menubar.itemAtIndex_(i)
        if it is not None and it.title() in ("Debug", "调试", "デバッグ"):
            return

    class _DbgTarget(object):
        def openInspector_(self, _sender) -> None:
            _log("debug menu: Open Web Inspector clicked")
            _open_web_inspector("menu")

    target = _DbgTarget()
    _install_debug_menu._target = target  # type: ignore[attr-defined]

    dbg = NSMenu.alloc().initWithTitle_("Debug")
    item_open = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Open Web Inspector",
        "openInspector:",
        "i",
    )
    try:
        from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagOption

        item_open.setKeyEquivalentModifierMask_(
            NSEventModifierFlagCommand | NSEventModifierFlagOption
        )
    except Exception:
        pass
    item_open.setTarget_(target)
    dbg.addItem_(item_open)

    top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Debug", None, "")
    top.setSubmenu_(dbg)
    menubar.addItem_(top)
    _log("debug menu installed (Debug → Open Web Inspector, ⌥⌘I)")


def _http_json(method: str, path: str, *, data: bytes | None = None, content_type: str | None = None) -> Any:
    url = f"{URL}{path}" if path.startswith("/") else f"{URL}/{path}"
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    tok = (os.environ.get("XOCHIPILLI_API_TOKEN") or "").strip()
    if tok and method.upper() not in ("GET", "HEAD"):
        headers["X-Xochi-Token"] = tok
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        if not raw:
            return None
        ct = r.headers.get("content-type") or ""
        if "application/json" in ct:
            return json.loads(raw.decode("utf-8", "replace"))
        return raw


def _multipart_file(field: str, file_path: Path) -> tuple[bytes, str]:
    boundary = f"----xochi{os.getpid()}{int(time.time())}"
    # Escape quotes / CR in filename for multipart header safety
    name = (
        file_path.name.replace("\\", "_")
        .replace('"', "_")
        .replace("\r", "_")
        .replace("\n", "_")
    )
    body = file_path.read_bytes()
    # naive mime
    suffix = file_path.suffix.lower()
    mime = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".flac": "audio/flac",
        ".aiff": "audio/aiff",
        ".aif": "audio/aiff",
    }.get(suffix, "application/octet-stream")
    chunks = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8", "replace"),
        body,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _native_import_track(window) -> None:
    """Native file dialog + POST /import — about:blank <input type=file> is flaky in WK."""
    try:
        import webview
    except Exception as e:
        _log(f"native import: webview missing {e}")
        return
    try:
        paths = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=(
                "Audio (*.mp3;*.wav;*.m4a;*.flac;*.aiff;*.aif)",
                "All files (*.*)",
            ),
        )
    except Exception as e:
        _log(f"native import dialog failed: {e}")
        _alert(f"ファイル選択に失敗: {e}", critical=True)
        return
    if not paths:
        _log("native import cancelled")
        return
    path = Path(str(paths[0] if isinstance(paths, (list, tuple)) else paths))
    if not path.is_file():
        _alert(f"ファイルが見つからない: {path}", critical=True)
        return
    _log(f"native import start path={path}")
    try:
        # Require currently selected project — never auto-target "richest".
        pid = None
        try:
            pid = _timed_evaluate_js(
                window,
                "(function(){try{var s=document.getElementById('projectSelect');"
                "return (s&&s.value)||(window.state&&window.state.project&&window.state.project.id)||'';}"
                "catch(e){return '';}})()",
                "import-pid",
                timeout=1.2,
            )
        except Exception:
            pid = None
        if isinstance(pid, str):
            pid = pid.strip().strip('"') or None
        else:
            pid = None
        if not pid:
            _alert(
                "曲を導入するプロジェクトを選んでから、もう一度「曲を導入…」を実行してください。",
                critical=True,
            )
            return
        body, ctype = _multipart_file("file", path)
        result = _http_json(
            "POST",
            f"/api/projects/{pid}/import",
            data=body,
            content_type=ctype,
        )
        title = (result or {}).get("title") or path.stem
        _log(f"native import ok pid={pid} title={title}")
        # Reload UI project list / current project
        js = (
            "(function(){try{"
            f"var id={json.dumps(pid)};"
            "if(typeof refreshProjectList==='function'){refreshProjectList(id);}"
            "if(typeof loadProject==='function'){loadProject(id);}"
            "var s=document.getElementById('status');"
            f"if(s)s.textContent={json.dumps('導入完了: ' + str(title))};"
            "return 'ok';}catch(e){return String(e);}})()"
        )
        _timed_evaluate_js(window, js, "import-reload", timeout=2.0)
        _alert(f"曲を導入しました。\n{title}", critical=False)
    except Exception as e:
        _log(f"native import failed: {e}")
        traceback.print_exc()
        _alert(f"曲の導入に失敗: {e}", critical=True)


def _install_file_menu(window) -> None:
    """Menu File → 曲を導入… (⌘O) — backup when HTML file input fails on about:blank."""
    try:
        from AppKit import NSApp, NSMenu, NSMenuItem, NSEventModifierFlagCommand
        from PyObjCTools import AppHelper
    except Exception as e:
        _log(f"file menu skipped (AppKit): {e}")
        return

    app = NSApp()
    if app is None:
        return
    menubar = app.mainMenu()
    if menubar is None:
        menubar = NSMenu.alloc().init()
        app.setMainMenu_(menubar)

    for i in range(menubar.numberOfItems()):
        it = menubar.itemAtIndex_(i)
        if it is not None and it.title() in ("File", "ファイル"):
            return

    class _FileTarget(object):
        def importTrack_(self, _sender) -> None:
            _log("file menu: Import track")
            # Keep dialog/evaluate_js on main thread; only HTTP stays sync here.
            def _run() -> None:
                try:
                    _native_import_track(window)
                except Exception as e:
                    _log(f"importTrack main-thread failed: {e}")

            try:
                AppHelper.callAfter(_run)
            except Exception:
                _run()

        def reloadProjects_(self, _sender) -> None:
            _log("file menu: Reload projects")
            js = (
                "(function(){try{"
                "if(typeof refreshProjectList==='function'){"
                "return refreshProjectList().then(function(d){"
                "var ps=(d&&d.projects)||[];"
                "if(ps.length&&typeof loadProject==='function'){"
                "var cur=(window.state&&window.state.project&&window.state.project.id)||'';"
                "var id=cur;"
                "if(!id){var s=document.getElementById('projectSelect');id=(s&&s.value)||ps[0].id;}"
                "return loadProject(id);"
                "}"
                "});}"
                "return 'no-fn';}catch(e){return String(e);}})()"
            )
            _timed_evaluate_js(window, js, "reload-projects", timeout=2.5)

    target = _FileTarget()
    _install_file_menu._target = target  # type: ignore[attr-defined]

    file_menu = NSMenu.alloc().initWithTitle_("ファイル")
    item_imp = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "曲を導入…",
        "importTrack:",
        "o",
    )
    try:
        item_imp.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
    except Exception:
        pass
    item_imp.setTarget_(target)
    file_menu.addItem_(item_imp)

    item_rel = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "プロジェクト再読込",
        "reloadProjects:",
        "r",
    )
    try:
        item_rel.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
    except Exception:
        pass
    item_rel.setTarget_(target)
    file_menu.addItem_(item_rel)

    top = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("ファイル", None, "")
    top.setSubmenu_(file_menu)
    # Insert near the left (after app menu if present)
    try:
        if menubar.numberOfItems() > 1:
            menubar.insertItem_atIndex_(top, 1)
        else:
            menubar.addItem_(top)
    except Exception:
        menubar.addItem_(top)
    _log("file menu installed (ファイル → 曲を導入… / プロジェクト再読込)")


def _log_bundle_identity() -> None:
    """Log whether we still own Xochipilli.app (needed for WKWebView local HTTP)."""
    try:
        from Foundation import NSBundle

        b = NSBundle.mainBundle()
        path = b.bundlePath() if b else None
        bid = b.bundleIdentifier() if b else None
        _log(f"NSBundle path={path!r} id={bid!r}")
        if path and "Xochipilli.app" not in str(path):
            _log(
                "WARN: mainBundle is not Xochipilli.app — WKWebView may block "
                "localhost (launch via Dock .app in-bundle launcher, not bare python)"
            )
    except Exception as e:
        _log(f"NSBundle probe skipped: {e}")


def _timed_evaluate_js(window, js: str, reason: str, timeout: float = 1.5) -> Any:
    """evaluate_js with hard timeout — never block forever (bridge can hang)."""
    box: dict = {"done": False, "val": None, "err": None}

    def _run() -> None:
        try:
            box["val"] = window.evaluate_js(js)
        except Exception as e:
            box["err"] = repr(e)
        finally:
            box["done"] = True

    t = threading.Thread(target=_run, name="xochi-eval-js", daemon=True)
    t.start()
    t.join(timeout=timeout)
    if not box["done"]:
        _log(f"evaluate_js ({reason}): TIMEOUT after {timeout}s")
        return None
    if box["err"]:
        _log(f"evaluate_js ({reason}): error {box['err']}")
        return None
    return box["val"]


# ---------------------------------------------------------------------------
# 6. shell HTML builder (inline CSS, craft-safe script policy, craft loader)
# ---------------------------------------------------------------------------

# Craft load strategy (rebuild 0.2.0):
# Sync <script src=craft_ui.js> in the initial document whitened WK on this host.
# After first paint (double-RAF), run craft from an embedded JSON payload (no extra
# network from about:blank). Fallback: script src against __XOCHI_API_BASE__.
_CRAFT_LOADER_JS = """
(function () {
  function injectFromPayload() {
    if (window.__XOCHI_CRAFT_LOADED__ || window.__XOCHI_CRAFT_LOADING__) return 'skip';
    window.__XOCHI_CRAFT_LOADING__ = true;
    try {
      var el = document.getElementById('xochi-craft-src');
      var code = '';
      if (el && el.textContent) {
        try { code = JSON.parse(el.textContent); } catch (e1) { code = el.textContent; }
      }
      if (code && String(code).length > 20) {
        var s = document.createElement('script');
        s.id = 'xochi-craft-inline';
        s.text = code;
        (document.head || document.documentElement).appendChild(s);
        window.__XOCHI_CRAFT_LOADED__ = true;
        window.__XOCHI_CRAFT_LOADING__ = false;
        return 'inline';
      }
      var base = (window.__XOCHI_API_BASE__ || 'http://127.0.0.1:8787').replace(/\\/$/, '');
      var ext = document.createElement('script');
      ext.src = base + '/static/craft_ui.js?v=desktop2';
      ext.async = true;
      ext.onload = function () {
        window.__XOCHI_CRAFT_LOADED__ = true;
        window.__XOCHI_CRAFT_LOADING__ = false;
      };
      ext.onerror = function () {
        window.__XOCHI_CRAFT_LOADING__ = false;
        console.error('craft_ui load failed');
      };
      (document.head || document.documentElement).appendChild(ext);
      return 'src';
    } catch (e) {
      window.__XOCHI_CRAFT_LOADING__ = false;
      console.error('craft inject', e);
      return 'err';
    }
  }
  window.loadCraft = function loadCraft() {
    return injectFromPayload();
  };
  function afterPaint() {
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { injectFromPayload(); });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', afterPaint);
  } else {
    afterPaint();
  }
})();
""".strip()


def _build_shell_html(base: str) -> tuple[str, str]:
    """Fetch index + inline CSS; strip sync craft_ui.js; embed craft + delayed loader.

    Prefer create_window(html=…) over bare url= (url= often stays white on this Mac).
    Single document load — caller must not thrash load_html after boot.
    """
    base = base if base.endswith("/") else base + "/"
    try:
        with urllib.request.urlopen(base, timeout=2.5) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        return "", f"GET {base} failed: {e}"

    def _http_text(path: str) -> str:
        try:
            with urllib.request.urlopen(base.rstrip("/") + path, timeout=2.0) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            _log(f"shell html fetch {path}: {e}")
            return ""

    style = _http_text("/static/style.css")
    craft_css = _http_text("/static/craft_ui.css")
    craft_js = _http_text("/static/craft_ui.js")
    block = f'<style id="xochi-inline-css">\n{style}\n{craft_css}\n</style>'
    html2, n = re.subn(
        r'<link[^>]+href="[^"]*style\.css[^"]*"[^>]*>',
        block,
        html,
        count=1,
        flags=re.I,
    )
    if n == 0:
        html2, n = re.subn(
            r"<link[^>]+href='[^']*style\.css[^']*'[^>]*>",
            block,
            html,
            count=1,
            flags=re.I,
        )
    if n == 0:
        html2 = re.sub(
            r"(<head[^>]*>)",
            rf"\1\n{block}",
            html,
            count=1,
            flags=re.I,
        )
        _log("shell html: style.css link not found — injected <style> after <head>")
    html = html2
    # craft_ui.css is inlined above; drop the external link.
    html = re.sub(r"<link[^>]+craft_ui\.css[^>]*>", "", html, flags=re.I)

    if "<base " not in html.lower():
        html = re.sub(
            r"(<head[^>]*>)",
            rf'\1\n<base href="{base}">',
            html,
            count=1,
            flags=re.I,
        )

    # about:blank document: relative fetch("/api/...") fails — pin absolute API origin.
    api_origin = base.rstrip("/")
    api_token = (os.environ.get("XOCHIPILLI_API_TOKEN") or "").strip()
    boot_js = (
        "<script>"
        f"window.__XOCHI_API_BASE__={json.dumps(api_origin)};"
        f"window.__XOCHI_API_TOKEN__={json.dumps(api_token)};"
        "</script>"
    )
    if "__XOCHI_API_BASE__" not in html:
        html = re.sub(
            r"(<head[^>]*>)",
            rf"\1\n{boot_js}",
            html,
            count=1,
            flags=re.I,
        )
        _log(f"shell html: injected __XOCHI_API_BASE__={api_origin} token={'yes' if api_token else 'no'}")
    elif "__XOCHI_API_TOKEN__" not in html and api_token:
        html = re.sub(
            r"(<head[^>]*>)",
            rf"\1\n{boot_js}",
            html,
            count=1,
            flags=re.I,
        )
        _log("shell html: injected __XOCHI_API_TOKEN__")

    # Scripts/assets must stay http absolute so load_html origin can fetch them.
    for q in ('"', "'"):
        html = html.replace(f"href={q}/static/", f"href={q}{base}static/")
        html = html.replace(f"src={q}/static/", f"src={q}{base}static/")

    # Remove blocking craft_ui.js from initial HTML (sync load whites WK on this host).
    # Re-enable via delayed inline payload — Craft is first-class, not permanently stripped.
    html2, n_craft = re.subn(
        r"<script[^>]+craft_ui\.js[^>]*>\s*</script>",
        "<!-- craft_ui.js: delayed inline after first paint (loadCraft / __XOCHI_CRAFT) -->",
        html,
        flags=re.I,
    )
    if n_craft:
        html = html2
        _log(f"shell html: craft_ui.js → delayed inline loader (n={n_craft})")

    # Escape "<" so craft source cannot break the JSON script tag.
    # Escape "<" so craft source cannot break the JSON <script> tag.
    craft_json = json.dumps(craft_js if craft_js else "").replace("<", "\u003c")
    craft_payload = (
        "<!-- __XOCHI_CRAFT payload -->\n"
        '<script type="application/json" id="xochi-craft-src">'
        f"{craft_json}"
        "</script>\n"
        "<!-- __XOCHI_CRAFT dynamic loader -->\n"
        f'<script id="xochi-craft-loader">\n{_CRAFT_LOADER_JS}\n</script>\n'
    )
    # Do not re.sub(repl=payload) — backslashes in JSON (\u003c) break re replacement templates.
    m_body = re.search(r"</body\s*>", html, flags=re.I)
    if m_body:
        html = html[: m_body.start()] + craft_payload + html[m_body.start() :]
    else:
        html = html + craft_payload
    if craft_js:
        _log(f"shell html: embedded craft_ui.js payload bytes={len(craft_js)}")
    else:
        _log("shell html: craft_ui.js payload empty — loader will use script src fallback")

    # Optional paint-only diagnosis (strips all scripts including craft loader).
    if (os.environ.get("XOCHIPILLI_SHELL_NO_SCRIPTS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
        _log("shell html: scripts stripped (XOCHIPILLI_SHELL_NO_SCRIPTS)")

    return (
        html,
        f"ok bytes={len(html)} css={len(style)} craft_css={len(craft_css)} "
        f"craft_js={len(craft_js)}",
    )


# JS snippet for optional Python-side craft inject (if inline loader insufficient).
_EVAL_LOAD_CRAFT = (
    "(function(){"
    "if(window.__XOCHI_CRAFT_LOADED__)return 'already';"
    "if(typeof window.loadCraft==='function'){try{return 'loadCraft:'+window.loadCraft();}catch(e){return 'err:'+e;}}"
    "return 'no-loader';"
    "})()"
)


# ---------------------------------------------------------------------------
# 7. pywebview run
# ---------------------------------------------------------------------------


def _run_pywebview(target: str) -> int:
    try:
        import webview
    except ImportError:
        _alert(
            "pywebview が入っていない。\n"
            f"{VENV_PY} -m pip install pywebview\n"
            "Dock から Chrome は自動起動しません。",
            critical=True,
        )
        return 1

    # Never monkey-patch setContentView / containers (Incident H: kills clicks + resize).
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_FILE_URLS"] = True
    # Do NOT auto-pop inspector (covers half the UI; use Debug menu / ⌥⌘I).
    webview.settings["OPEN_DEVTOOLS_IN_DEBUG"] = False

    debug = _webview_debug_enabled()
    if debug:
        _patch_cocoa_inspectable_on_init()
    if _skip_pywebview_inject_enabled():
        _patch_skip_pywebview_inject()
        _log("XOCHIPILLI_SKIP_PYWEBVIEW_INJECT active (default on)")
    else:
        _log("XOCHIPILLI_SKIP_PYWEBVIEW_INJECT off — stock inject_pywebview")

    base = target if target.endswith("/") else target + "/"
    html, html_msg = _build_shell_html(base)
    if not html:
        _log(f"shell html build failed: {html_msg} — falling back to url=")
        use_html = False
    else:
        use_html = True
        _log(f"shell html build {html_msg} (load_html+inline CSS path)")

    _log(
        f"webview debug={debug} — right-click needs isInspectable; "
        "prefer menu Debug/⌥⌘I or Safari Develop"
    )

    window_kwargs: dict = {
        "title": "Xochipilli",
        "width": 1280,
        "height": 800,
        "min_size": (640, 480),
        "background_color": "#0c0e12",
        "text_select": True,
        "resizable": True,
        "focus": True,
        "easy_drag": False,
        "frameless": False,
    }
    if use_html:
        # Full document once at create — boot must NOT call load_html again (Incident F).
        window_kwargs["html"] = html
        _log(f"using load_html shell (create once, no boot reload) base={base}")
    else:
        window_kwargs["url"] = base
        _log(f"using stock url= fallback → {base}")

    try:
        window = webview.create_window(**window_kwargs)
    except TypeError as e:
        _log(f"create_window TypeError, dropping kwargs: {e}")
        for k in ("text_select", "focus", "easy_drag", "frameless"):
            window_kwargs.pop(k, None)
        window = webview.create_window(**window_kwargs)

    print("[xochipilli] shell_mode=pywebview", flush=True)
    _log(f"window created ({'html' if use_html else 'url'}) → {base}")

    state = {"loaded": False, "shown": False, "craft_eval": False}

    def _on_shown() -> None:
        state["shown"] = True
        _log("event shown")
        _activate_cocoa()
        _call_on_main(lambda: _install_file_menu(window), "shown-file-menu")
        if debug:
            _call_on_main(_install_debug_menu, "shown-menu")
            _apply_inspectable("event-shown")

    def _on_loaded() -> None:
        state["loaded"] = True
        _log("event loaded")
        if debug:
            _apply_inspectable("event-loaded")
        # Belt-and-suspenders: if inline loadCraft did not run, inject once via evaluate_js.
        if use_html and not state["craft_eval"]:
            state["craft_eval"] = True

            def _ensure_craft() -> None:
                time.sleep(0.35)
                result = _timed_evaluate_js(
                    window, _EVAL_LOAD_CRAFT, "craft-ensure", timeout=1.5
                )
                if result is not None:
                    _log(f"craft ensure evaluate_js → {result!r}")

            threading.Thread(
                target=_ensure_craft, name="xochi-craft-ensure", daemon=True
            ).start()

    try:
        window.events.shown += _on_shown
        window.events.loaded += _on_loaded
    except Exception as e:
        _log(f"events hook skipped: {e}")

    def _boot() -> None:
        time.sleep(0.05)
        _activate_cocoa()
        if use_html:
            _log("boot: html already set at create_window (no second load_html)")
        _call_on_main(lambda: _install_file_menu(window), "boot-file-menu")
        if debug:
            _call_on_main(_install_debug_menu, "boot-menu")
            time.sleep(0.5)
            _apply_inspectable("boot+0.5s")
            if state["loaded"]:
                _log("nav ok — load_html shell")
            else:
                time.sleep(1.5)
                _apply_inspectable("boot+2s")
                _log(
                    "loaded flag late/missing — native url/title above; "
                    "use menu Debug → Open Web Inspector if needed"
                )
            return

        time.sleep(2.0)
        if state["loaded"]:
            _log("nav ok")
        elif use_html:
            _log("loaded missing after create html (no thrash reload)")
        else:
            _log("loaded still missing — one load_url retry")
            try:
                window.load_url(base)
                _log(f"boot load_url {base}")
            except Exception as e:
                _log(f"boot load_url: {e}")

    _log(f"webview.start debug={debug} (XOCHIPILLI_WEBVIEW_DEBUG)")

    # Do not pass storage_path — empty custom store correlated with blank paint on this host.
    try:
        webview.start(
            func=_boot,
            gui="cocoa",
            private_mode=False,
            debug=debug,
        )
    except TypeError as e1:
        _log(f"start() signature fallback 1: {e1!r}")
        try:
            webview.start(func=_boot, private_mode=False, debug=debug)
        except TypeError as e2:
            _log(f"start() signature fallback 2: {e2!r}")
            try:
                webview.start(func=_boot, debug=debug)
            except TypeError as e3:
                _log(f"start() signature fallback 3 (LAST): {e3!r}")
                webview.start(func=_boot)
    except Exception:
        traceback.print_exc()
        _alert("ネイティブ窓の表示に失敗した。session.log を確認。", critical=True)
        return 1

    _log("webview.start returned (window closed)")
    return 0


# ---------------------------------------------------------------------------
# 8. browser opt-in
# ---------------------------------------------------------------------------


def _run_browser_only(target: str, *, keep_server: bool) -> int:
    _log(f"shell_mode=browser (explicit) → {target} keep_server={keep_server}")
    print("[xochipilli] shell_mode=browser", flush=True)
    webbrowser.open(target)
    _alert(
        "ブラウザで開きました（XOCHIPILLI_SHELL=browser）。\n"
        + (
            "サーバはこのプロセスが生きている間だけ動きます。"
            if keep_server
            else "既存サーバを再利用しています。"
        ),
        critical=False,
    )
    if keep_server:
        _log("browser mode: holding process so spawned server stays up (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            _log("browser mode interrupted")
            return 0
    time.sleep(1.0)
    return 0


# ---------------------------------------------------------------------------
# 9. main()
# ---------------------------------------------------------------------------


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()
    SUPPORT.mkdir(parents=True, exist_ok=True)

    _log(f"desktop_app start pid={os.getpid()} py={sys.executable}")
    _log(f"sys.path[0:4]={sys.path[:4]}")
    _log_bundle_identity()

    _kill_legacy_chrome_app()

    server = _start_server()
    atexit.register(_stop_server, server)

    ok_http, http_msg = _preflight_http()
    _log(f"preflight: {http_msg}")
    if not ok_http:
        _alert(
            "ローカル UI に届かない（サーバ側）。\n"
            f"{http_msg}\n"
            "session.log を確認するか ./RUN_ME.sh を試してください。",
            critical=True,
        )
        _stop_server(server)
        return 1

    target = f"{URL}/"
    shell = (os.environ.get("XOCHIPILLI_SHELL") or "webview").strip().lower()
    _log(f"entering shell={shell}")

    if shell in ("browser", "chrome", "safari", "system"):
        rc = _run_browser_only(target, keep_server=server is not None)
        if server is not None:
            _stop_server(server)
        return rc

    _log("starting pywebview window…")
    rc = _run_pywebview(target)
    _stop_server(server)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
