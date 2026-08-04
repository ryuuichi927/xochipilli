"""
Xochipilli desktop shell: local FastAPI + **native pywebview window only**.

Chrome / Safari are NOT opened from Dock (user request 2026-08-04).
Optional escape hatch: XOCHIPILLI_SHELL=browser opens the system default browser.

Usage:
  .venv/bin/python desktop_app.py
  ./RUN_DESKTOP.sh
  Dock → /Applications/Xochipilli.app
"""

from __future__ import annotations

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# Strip agent/Ben's Tool pollution before any third-party import
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

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("PORT", "8787"))
URL = f"http://{HOST}:{PORT}"
VENV_PY = ROOT / ".venv" / "bin" / "python"
SUPPORT = Path.home() / "Library/Application Support/Xochipilli"
CHROME_PROFILE = SUPPORT / "chrome-app-profile"  # legacy; kill on launch if still running


def _log(msg: str) -> None:
    print(f"[xochipilli] {msg}", flush=True)


def _alert(message: str, *, critical: bool = False) -> None:
    try:
        style = "critical" if critical else "informational"
        msg = str(message)[:500]
        script = (
            "on run argv\n"
            f'  display alert "Xochipilli" message (item 1 of argv) as {style} giving up after 14\n'
            "end run"
        )
        subprocess.run(
            ["/usr/bin/osascript", "-e", script, msg],
            check=False,
            capture_output=True,
        )
    except Exception:
        print(f"[xochipilli] ALERT: {message}", file=sys.stderr, flush=True)


def _health_payload() -> dict | None:
    try:
        with urllib.request.urlopen(f"{URL}/api/health", timeout=1.2) as r:
            if r.status != 200:
                return None
            import json

            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None


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


def _preflight_http() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(f"{URL}/", timeout=2.0) as r:
            body = r.read()
            if r.status != 200:
                return False, f"GET / status={r.status}"
            if b"<html" not in body.lower() and b"<!DOCTYPE" not in body[:200]:
                return False, f"GET / not html ({len(body)} bytes)"
            return True, f"GET / ok ({len(body)} bytes)"
    except Exception as e:
        return False, f"GET / failed: {e}"


def _start_server() -> subprocess.Popen | None:
    if _health_ok():
        h = _health_payload() or {}
        _log(f"reuse server at {URL} (product={h.get('product')})")
        return None
    if _port_open(PORT):
        for _ in range(24):
            if _health_ok():
                _log(f"reuse server at {URL} (became healthy)")
                return None
            time.sleep(0.25)
        msg = f"ポート {PORT} は使われているが Xochipilli の /api/health が応答しない。"
        _log(f"WARN: {msg}")
        _alert(msg, critical=True)

    py = str(VENV_PY if VENV_PY.is_file() else sys.executable)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.setdefault("VIDEO_PROVIDER", env.get("VIDEO_PROVIDER", "mock"))
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
    _log(f"starting {URL} …")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    for _ in range(80):
        if _health_ok():
            _log("server ready")
            return proc
        if proc.poll() is not None:
            err = ""
            try:
                err = (proc.stderr.read() or "") if proc.stderr else ""
            except Exception:
                err = ""
            _log(f"server exited early: {err[:400]}")
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


def _kill_legacy_chrome_app() -> None:
    """Stop previous --app chrome profile so Dock never leaves a Chrome window around."""
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


def _activate_cocoa() -> None:
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        _log("cocoa activateIgnoringOtherApps")
    except Exception as e:
        _log(f"cocoa activate skipped: {e}")


def _fetch_index_html() -> str | None:
    try:
        with urllib.request.urlopen(f"{URL}/", timeout=3.0) as r:
            if r.status != 200:
                return None
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        _log(f"fetch index failed: {e}")
        return None


def _absolutize_html(html: str, base: str) -> str:
    """Point /static and root-relative assets at the live server origin."""
    b = base if base.endswith("/") else base + "/"
    return (
        html.replace('href="/static/', f'href="{b}static/')
        .replace("href='/static/", f"href='{b}static/")
        .replace('src="/static/', f'src="{b}static/')
        .replace("src='/static/", f"src='{b}static/")
        .replace('href="/favicon', f'href="{b}favicon')
        .replace('action="/', f'action="{b}')
    )


def _run_pywebview(target: str) -> int:
    try:
        import webview
    except ImportError:
        _alert(
            "pywebview が入っていない。\n"
            f"{VENV_PY} -m pip install pywebview\n"
            "Dock からは Chrome を自動起動しません。",
            critical=True,
        )
        return 1

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    webview.settings["ALLOW_FILE_URLS"] = True

    storage = SUPPORT / "webview"
    storage.mkdir(parents=True, exist_ok=True)

    base = target if target.endswith("/") else target + "/"

    # Single path: native window loads the live FastAPI origin directly.
    # (Earlier html/load_html races left a white frame and skipped `loaded`.)
    window_kwargs: dict = {
        "title": "Xochipilli",
        "url": base,
        "width": 1440,
        "height": 900,
        "min_size": (960, 640),
        "background_color": "#0c0e12",
        "text_select": True,
        "resizable": True,
        "confirm_close": False,
        "focus": True,
    }

    try:
        window = webview.create_window(**window_kwargs)
    except TypeError:
        window_kwargs.pop("text_select", None)
        window_kwargs.pop("focus", None)
        window = webview.create_window(**window_kwargs)

    print("[xochipilli] shell_mode=pywebview", flush=True)
    _log(f"window created url={base}")

    def _on_shown() -> None:
        _log("event shown")
        _activate_cocoa()

    def _on_loaded() -> None:
        _log("event loaded")
        try:
            snippet = window.evaluate_js(
                "(document.body && (document.body.innerText||'').trim().slice(0,80)) || ''"
            )
            _log(f"dom snippet={snippet!r}")
            if not snippet or len(str(snippet).strip()) < 4:
                _log("blank DOM → reload url")
                window.load_url(base)
        except Exception as e:
            _log(f"loaded check: {e}")

    try:
        window.events.shown += _on_shown
        window.events.loaded += _on_loaded
    except Exception as e:
        _log(f"events hook skipped: {e}")

    def _boot() -> None:
        time.sleep(0.05)
        _activate_cocoa()
        # Soft reload once after show (helps WKWebView first paint on some macOS builds)
        try:
            time.sleep(0.4)
            window.load_url(base)
            _log(f"boot load_url {base}")
        except Exception as e:
            _log(f"boot load_url failed: {e}")

    try:
        webview.start(
            func=_boot,
            gui="cocoa",
            private_mode=False,
            storage_path=str(storage),
            debug=False,
        )
    except TypeError:
        try:
            webview.start(func=_boot, private_mode=False, storage_path=str(storage))
        except TypeError:
            try:
                webview.start(private_mode=False)
            except TypeError:
                webview.start()
    except Exception:
        traceback.print_exc()
        _alert("ネイティブ窓の表示に失敗した。session.log を確認。", critical=True)
        return 1

    _log("webview.start returned (window closed)")
    return 0


def _run_browser_only(target: str) -> int:
    """Opt-in only: XOCHIPILLI_SHELL=browser"""
    _log(f"shell_mode=browser (explicit) → {target}")
    print("[xochipilli] shell_mode=browser", flush=True)
    webbrowser.open(target)
    _alert(
        "ブラウザで開きました（XOCHIPILLI_SHELL=browser）。\n"
        "通常の Dock 起動はネイティブ窓のみです。",
        critical=False,
    )
    time.sleep(1.0)
    return 0


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()
    SUPPORT.mkdir(parents=True, exist_ok=True)

    _log(f"desktop_app start pid={os.getpid()} py={sys.executable}")
    _log(f"sys.path[0:4]={sys.path[:4]}")

    # Never leave a previous Chrome --app session hanging off Dock
    _kill_legacy_chrome_app()

    server = _start_server()
    atexit.register(_stop_server, server)

    ok_http, http_msg = _preflight_http()
    _log(f"preflight: {http_msg}")
    if not ok_http:
        _alert(
            "ローカル UI に届かない。\n"
            f"{http_msg}\n"
            "session.log を確認するか ./RUN_ME.sh を試してください。",
            critical=True,
        )

    target = f"{URL}/"
    shell = (os.environ.get("XOCHIPILLI_SHELL") or "webview").strip().lower()

    if shell in ("browser", "chrome", "safari", "system"):
        # Explicit opt-in only — never default
        rc = _run_browser_only(target)
        _stop_server(server)
        return rc

    rc = _run_pywebview(target)
    _stop_server(server)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
