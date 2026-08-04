"""
Xochipilli desktop shell (B): local uvicorn + native window (pywebview).

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


def _alert(message: str, *, critical: bool = False) -> None:
    """Best-effort macOS user-visible notice (Dock launch has no terminal)."""
    try:
        style = "critical" if critical else "informational"
        msg = str(message)[:500]
        script = (
            "on run argv\n"
            f'  display alert "Xochipilli" message (item 1 of argv) as {style} giving up after 12\n'
            "end run"
        )
        subprocess.run(
            ["/usr/bin/osascript", "-e", script, msg],
            check=False,
            capture_output=True,
        )
    except Exception:
        print(f"[xochipilli] ALERT: {message}", file=sys.stderr)


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


def _start_server() -> subprocess.Popen | None:
    """Start uvicorn if nothing healthy is already on PORT."""
    if _health_ok():
        h = _health_payload() or {}
        print(f"[xochipilli] reuse server at {URL} (product={h.get('product')})")
        return None
    if _port_open(PORT):
        for _ in range(24):
            if _health_ok():
                print(f"[xochipilli] reuse server at {URL} (became healthy)")
                return None
            time.sleep(0.25)
        msg = (
            f"ポート {PORT} は使われているが、Xochipilli の /api/health が応答しない。"
            " 別アプリが 8787 を占有しているか、前回のサーバが壊れている。"
            " ターミナルで確認: lsof -iTCP:8787 -sTCP:LISTEN"
        )
        print(f"[xochipilli] WARN: {msg}", file=sys.stderr)
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
    print(f"[xochipilli] starting {URL} …")
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
            print("[xochipilli] server ready")
            return proc
        if proc.poll() is not None:
            err = ""
            try:
                err = (proc.stderr.read() or "") if proc.stderr else ""
            except Exception:
                err = ""
            err_l = err.lower()
            if "address already in use" in err_l or "errno 48" in err_l:
                msg = (
                    f"起動失敗: ポート {PORT} が使用中。"
                    " 既存の Xochipilli / 他サーバを終了するか、.env の PORT= を変えてください。"
                )
            else:
                msg = "ローカルサーバの起動に失敗した。Logs/Xochipilli/session.log を確認。"
            print(f"[xochipilli] server exited early: {err[:400]}", file=sys.stderr)
            _alert(msg, critical=True)
            return proc
        time.sleep(0.15)
    print("[xochipilli] server did not become healthy in time", file=sys.stderr)
    _alert(
        f"サーバが {URL} で準備完了しなかった。ログを確認するか、一度 8787 を空けて再起動。",
        critical=True,
    )
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


def _activate_cocoa() -> None:
    """Bring this process to the foreground on macOS (Dock launches)."""
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyRegular

        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        app.activateIgnoringOtherApps_(True)
        print("[xochipilli] cocoa activateIgnoringOtherApps")
    except Exception as e:
        print(f"[xochipilli] cocoa activate skipped: {e}")


def _preflight_http() -> tuple[bool, str]:
    """Confirm the workbench HTML is actually served before opening WebView."""
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


# Dark bootstrap so WKWebView never sits on a blank white document.
# JS then navigates to the local FastAPI UI after /api/health succeeds.
_BOOTSTRAP_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Xochipilli</title>
  <style>
    html, body {
      margin: 0; height: 100%;
      background: #0c0e12; color: #c9a227;
      font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      display: flex; align-items: center; justify-content: center;
    }
    .box { text-align: center; max-width: 28rem; padding: 1.5rem; }
    .sub { margin-top: .55rem; font-size: 13px; opacity: .72; color: #d8c98a; }
    .err { margin-top: 1rem; color: #e8a0a0; font-size: 13px; white-space: pre-wrap; }
    code { font-size: 12px; opacity: .85; }
  </style>
</head>
<body>
  <div class="box">
    <div><strong>Xochipilli</strong></div>
    <div class="sub" id="status">Connecting to local server…</div>
    <div class="err" id="err"></div>
  </div>
  <script>
    const targets = ["http://127.0.0.1:8787/", "http://localhost:8787/"];
    const st = document.getElementById("status");
    const er = document.getElementById("err");
    async function probe(base) {
      const r = await fetch(base + "api/health", { cache: "no-store" });
      if (!r.ok) throw new Error("health " + r.status);
      const j = await r.json();
      if (j && j.ok === false) throw new Error("health not ok");
      return base;
    }
    (async () => {
      let last = "";
      for (const t of targets) {
        try {
          st.textContent = "Found server at " + t;
          const base = await probe(t);
          st.textContent = "Opening workbench…";
          location.replace(base);
          return;
        } catch (e) {
          last = String(e && e.message ? e.message : e);
        }
      }
      st.textContent = "Local server not reachable";
      er.textContent =
        "Start failed or port busy.\\n" +
        "Tried 127.0.0.1:8787 and localhost:8787\\n" +
        "Last error: " + last + "\\n\\n" +
        "Logs: ~/Library/Logs/Xochipilli/session.log";
    })();
  </script>
</body>
</html>
"""


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()
    print(f"[xochipilli] desktop_app start pid={os.getpid()} py={sys.executable}")
    print(f"[xochipilli] sys.path[0:4]={sys.path[:4]}")

    try:
        import webview
    except ImportError:
        msg = (
            "pywebview が入っていない。\n"
            f"{VENV_PY} -m pip install pywebview\n"
            "または requirements.txt を入れてから再度開いてください。"
        )
        print(msg, file=sys.stderr)
        _alert(msg, critical=True)
        return 1

    server = _start_server()
    atexit.register(_stop_server, server)

    ok_http, http_msg = _preflight_http()
    print(f"[xochipilli] preflight: {http_msg}")
    if not ok_http and not _health_ok():
        print("[xochipilli] no healthy UI yet; bootstrap page will show error", file=sys.stderr)

    storage = Path.home() / "Library/Application Support/Xochipilli/webview"
    try:
        storage.mkdir(parents=True, exist_ok=True)
    except OSError:
        storage = Path.home() / "Library/Caches/Xochipilli-webview"
        storage.mkdir(parents=True, exist_ok=True)

    # Bootstrap first (never pure white). Navigate to FastAPI after health OK.
    window_kwargs = {
        "title": "Xochipilli",
        "html": _BOOTSTRAP_HTML,
        "width": 1440,
        "height": 900,
        "min_size": (960, 640),
        "background_color": "#0c0e12",
        "text_select": True,
        "focus": True,
    }

    try:
        window = webview.create_window(**window_kwargs)
    except TypeError:
        window_kwargs.pop("text_select", None)
        window_kwargs.pop("focus", None)
        window = webview.create_window(**window_kwargs)

    print(f"[xochipilli] window created (bootstrap) → target {URL}/")

    def _fetch_index_html() -> str | None:
        try:
            with urllib.request.urlopen(f"{URL}/", timeout=3.0) as r:
                if r.status != 200:
                    return None
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"[xochipilli] fetch index failed: {e}")
            return None

    def _on_shown() -> None:
        print("[xochipilli] event shown")
        _activate_cocoa()
        # Prefer load_html + base_uri: WKWebView on this host often stayed pure white
        # with load_url("http://127.0.0.1:…") alone (see DESKTOP_INCIDENTS_2026-08-04).
        try:
            html = _fetch_index_html()
            if html and ("<html" in html.lower() or "<!doctype" in html.lower()):
                base = f"{URL}/"
                # Absolute static/API roots so CSS/JS load even if base_uri is ignored
                html_abs = (
                    html.replace('href="/static/', f'href="{base}static/')
                    .replace("href='/static/", f"href='{base}static/")
                    .replace('src="/static/', f'src="{base}static/')
                    .replace("src='/static/", f"src='{base}static/")
                    .replace('href="/favicon', f'href="{base}favicon')
                    .replace('src="/api/', f'src="{base}api/')
                )
                try:
                    window.load_html(html_abs, base_uri=base)
                    print(f"[xochipilli] load_html ok base_uri={base} bytes={len(html_abs)}")
                except TypeError:
                    # older pywebview: no base_uri kw
                    window.load_html(html_abs)
                    print(f"[xochipilli] load_html ok (no base_uri) bytes={len(html_abs)}")
                return        except Exception as e:
            print(f"[xochipilli] load_html path failed: {e}")
        try:
            window.load_url(f"{URL}/")
            print(f"[xochipilli] fallback load_url {URL}/")
        except Exception as e:
            print(f"[xochipilli] load_url failed: {e}")

    def _on_loaded() -> None:
        print("[xochipilli] event loaded")

    try:
        window.events.shown += _on_shown
        window.events.loaded += _on_loaded
    except Exception as e:
        print(f"[xochipilli] events hook skipped: {e}")
        _activate_cocoa()
        _on_shown()
    # private_mode=False keeps localStorage (lang, play rate)
    try:
        webview.start(
            private_mode=False,
            storage_path=str(storage),
            debug=False,
        )
    except TypeError:
        try:
            webview.start(private_mode=False)
        except TypeError:
            webview.start()
    except Exception:
        traceback.print_exc()
        _alert("ウィンドウの表示に失敗した。session.log を確認してください。", critical=True)
        _stop_server(server)
        return 1

    print("[xochipilli] webview.start returned (window closed)")
    _stop_server(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
