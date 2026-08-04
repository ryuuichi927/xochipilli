"""
Xochipilli desktop shell (B): local uvicorn + native window (pywebview).

Usage:
  .venv/bin/python desktop_app.py
  ./RUN_DESKTOP.sh
"""

from __future__ import annotations

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

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
        # argv avoids quote escaping bugs in Japanese messages
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
        # minimal parse
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
    # Prefer our own product on this port
    prod = str(h.get("product") or "")
    return (not prod) or prod == "Xochipilli"


def _start_server() -> subprocess.Popen | None:
    """Start uvicorn if nothing healthy is already on PORT."""
    if _health_ok():
        h = _health_payload() or {}
        print(f"[xochipilli] reuse server at {URL} (product={h.get('product')})")
        return None
    if _port_open(PORT):
        # something else on port — wait a bit for health (slow boot)
        for _ in range(24):
            if _health_ok():
                print(f"[xochipilli] reuse server at {URL} (became healthy)")
                return None
            time.sleep(0.25)
        # Port occupied by a non-Xochipilli process or a broken half-boot
        msg = (
            f"ポート {PORT} は使われているが、Xochipilli の /api/health が応答しない。"
            " 別アプリが 8787 を占有しているか、前回のサーバが壊れている。"
            " ターミナルで確認: lsof -iTCP:8787 -sTCP:LISTEN"
        )
        print(f"[xochipilli] WARN: {msg}", file=sys.stderr)
        _alert(msg, critical=True)
        # Still try to start — uvicorn will fail fast if bind fails; user saw the alert.

    py = str(VENV_PY if VENV_PY.is_file() else sys.executable)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
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


def main() -> int:
    os.chdir(ROOT)
    _load_dotenv()

    try:
        import webview
    except ImportError:
        print(
            "pywebview missing. Install:\n"
            f"  {VENV_PY} -m pip install pywebview\n"
            "or: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    server = _start_server()
    atexit.register(_stop_server, server)

    if not _health_ok():
        # Window may still open to show error page; user already got an alert if bind failed.
        print("[xochipilli] continuing to open window without healthy API", file=sys.stderr)

    window_kwargs = {
        "title": "Xochipilli",
        "url": URL,
        "width": 1440,
        "height": 900,
        "min_size": (960, 640),
        "background_color": "#0c0e12",
        "text_select": True,
    }

    try:
        webview.create_window(**window_kwargs)
    except TypeError:
        # older pywebview without text_select etc.
        window_kwargs.pop("text_select", None)
        webview.create_window(**window_kwargs)

    # private_mode=False keeps localStorage (lang, play rate)
    try:
        webview.start(private_mode=False)
    except TypeError:
        webview.start()
    _stop_server(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
