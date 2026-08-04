"""
Xochipilli desktop shell (B): local uvicorn + native-feeling window.

Primary: Google Chrome / Edge / Brave / Chromium  --app=http://127.0.0.1:PORT/
  (WKWebView/pywebview stayed pure white on this host while HTTP served full HTML.)

Fallback: Safari via `open`, then pywebview last resort.

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
SUPPORT = Path.home() / "Library/Application Support/Xochipilli"


def _alert(message: str, *, critical: bool = False) -> None:
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
            " 別アプリが占有しているか、前回のサーバが壊れている。"
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
                msg = f"起動失敗: ポート {PORT} が使用中。"
            else:
                msg = "ローカルサーバの起動に失敗した。Logs/Xochipilli/session.log を確認。"
            print(f"[xochipilli] server exited early: {err[:400]}", file=sys.stderr)
            _alert(msg, critical=True)
            return proc
        time.sleep(0.15)
    print("[xochipilli] server did not become healthy in time", file=sys.stderr)
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


# Chromium-based browsers: reliable --app= window for local FastAPI UI
_CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Arc.app/Contents/MacOS/Arc"),
)


def _find_chromium() -> Path | None:
    for p in _CHROME_CANDIDATES:
        if p.is_file():
            return p
    return None


def _open_chromium_app(url: str) -> tuple[subprocess.Popen | None, str]:
    """Open a frameless-ish app window. Returns (proc, engine_name)."""
    chrome = _find_chromium()
    if chrome is None:
        return None, ""
    profile = SUPPORT / "chrome-app-profile"
    profile.mkdir(parents=True, exist_ok=True)
    target = url if url.endswith("/") else url + "/"
    cmd = [
        str(chrome),
        f"--app={target}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
    ]
    print(f"[xochipilli] chromium app mode: {chrome.name} → {target}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return proc, chrome.name
    except OSError as e:
        print(f"[xochipilli] chromium launch failed: {e}")
        return None, ""


def _open_safari(url: str) -> bool:
    target = url if url.endswith("/") else url + "/"
    try:
        subprocess.run(
            ["/usr/bin/open", "-a", "Safari", target],
            check=False,
            capture_output=True,
        )
        print(f"[xochipilli] opened Safari {target}")
        return True
    except OSError as e:
        print(f"[xochipilli] Safari open failed: {e}")
        return False


def _run_pywebview(url: str) -> int:
    """Last resort. On this Mac WKWebView often painted pure white; kept for machines without Chrome."""
    try:
        import webview
    except ImportError:
        _alert("Chrome も pywebview も使えません。", critical=True)
        return 1

    target = url if url.endswith("/") else url + "/"
    # Minimal inline page first so we never ship a white void if URL fails
    splash = f"""<!DOCTYPE html><html><head><meta charset=utf-8>
<style>html,body{{margin:0;height:100%;background:#0c0e12;color:#c9a227;
font:15px system-ui;display:flex;align-items:center;justify-content:center}}
a{{color:#e8d48b}}</style></head><body>
<div style="text-align:center">
<strong>Xochipilli</strong>
<p style="opacity:.8;font-size:13px">Opening workbench…</p>
<p><a href="{target}">Open manually</a></p>
</div>
<script>setTimeout(function(){{location.replace({target!r})}}, 50)</script>
</body></html>"""

    kwargs = {
        "title": "Xochipilli",
        "url": target,
        "width": 1440,
        "height": 900,
        "min_size": (960, 640),
        "background_color": "#0c0e12",
        "text_select": True,
    }
    try:
        window = webview.create_window(**kwargs)
    except TypeError:
        kwargs.pop("text_select", None)
        try:
            window = webview.create_window(**kwargs)
        except Exception:
            window = webview.create_window(title="Xochipilli", html=splash, width=1440, height=900)

    print(f"[xochipilli] pywebview fallback url={target}")

    def _shown() -> None:
        try:
            window.load_url(target)
            print("[xochipilli] pywebview load_url", target)
        except Exception as e:
            print("[xochipilli] pywebview load_url failed", e)
            try:
                window.load_html(splash)
            except Exception:
                pass

    try:
        window.events.shown += _shown
    except Exception:
        pass

    storage = SUPPORT / "webview"
    storage.mkdir(parents=True, exist_ok=True)
    try:
        webview.start(private_mode=False, storage_path=str(storage))
    except TypeError:
        try:
            webview.start(private_mode=False)
        except TypeError:
            webview.start()
    except Exception:
        traceback.print_exc()
        return 1
    return 0


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()
    SUPPORT.mkdir(parents=True, exist_ok=True)

    print(f"[xochipilli] desktop_app start pid={os.getpid()} py={sys.executable}")
    print(f"[xochipilli] sys.path[0:4]={sys.path[:4]}")

    server = _start_server()
    atexit.register(_stop_server, server)

    ok_http, http_msg = _preflight_http()
    print(f"[xochipilli] preflight: {http_msg}")
    if not ok_http:
        _alert(
            "ローカル UI に届かない。\n"
            f"{http_msg}\n"
            "session.log を確認するか、ターミナルで ./RUN_ME.sh を試してください。",
            critical=True,
        )
        # still try to open — user may fix port

    target = f"{URL}/"

    # --- Primary: Chromium --app= (avoids white WKWebView) ---
    chrome_proc, engine = _open_chromium_app(target)
    if chrome_proc is not None:
        print(f"[xochipilli] shell_mode=chromium-app engine={engine} pid={chrome_proc.pid}")
        # Keep this process alive while the app window runs so Dock treats us as open.
        # Poll: if chrome exits quickly (<2s), fall through to other shells.
        for i in range(20):
            time.sleep(0.1)
            if chrome_proc.poll() is not None:
                print(f"[xochipilli] chromium exited early code={chrome_proc.returncode}")
                break
        else:
            # Still running after 2s — wait until user closes the app window
            print("[xochipilli] waiting for chromium app window to close…")
            try:
                chrome_proc.wait()
            except KeyboardInterrupt:
                chrome_proc.terminate()
            print(f"[xochipilli] chromium closed code={chrome_proc.returncode}")
            _stop_server(server)
            return 0

    # --- Secondary: Safari ---
    if _open_safari(target):
        print("[xochipilli] shell_mode=safari")
        _alert(
            "Chrome 系が使えなかったため Safari で開きました。\n"
            f"{target}",
            critical=False,
        )
        # Don't block forever on Safari; user has a browser tab.
        time.sleep(1.5)
        _stop_server(server)
        return 0

    # --- Last resort: pywebview ---
    print("[xochipilli] shell_mode=pywebview-fallback")
    rc = _run_pywebview(target)
    _stop_server(server)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
