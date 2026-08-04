"""
Xochipilli desktop shell: local FastAPI + stable UI window.

Shell priority
1. Chromium --app= (Chrome / Edge / Brave / Arc) with **profile-based lifetime**
   (do NOT wait on the first Popen pid — Chrome handoff exits with code=-5 on macOS
   and looks like “fullscreen killed the app”)
2. Safari
3. pywebview last resort

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
CHROME_PROFILE = SUPPORT / "chrome-app-profile"

# Stable flags for macOS app windows (avoid GPU/session flakiness)
_CHROME_BASE_FLAGS = (
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-session-crashed-bubble",
    "--disable-infobars",
    "--disable-features=Translate,MediaRouter",
    # Keep process model boring; reduces odd parent-exit (-5 / SIGTRAP) on FS transitions
    "--disable-background-mode",
    "--window-size=1440,900",
)


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
        msg = (
            f"ポート {PORT} は使われているが Xochipilli の /api/health が応答しない。"
        )
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


_CHROME_BINS = (
    ("Google Chrome", Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")),
    ("Microsoft Edge", Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")),
    ("Brave Browser", Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")),
    ("Chromium", Path("/Applications/Chromium.app/Contents/MacOS/Chromium")),
    ("Arc", Path("/Applications/Arc.app/Contents/MacOS/Arc")),
)


def _find_chromium() -> tuple[str, Path] | None:
    for name, p in _CHROME_BINS:
        if p.is_file():
            return name, p
    return None


def _profile_pids(profile: Path) -> list[int]:
    """PIDs whose command line references this user-data-dir."""
    needle = str(profile)
    try:
        r = subprocess.run(
            ["pgrep", "-f", needle],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if r.returncode not in (0, 1):
        return []
    out: list[int] = []
    for line in (r.stdout or "").split():
        try:
            out.append(int(line))
        except ValueError:
            continue
    return out


def _wait_until_profile_quiet(profile: Path, *, grace_s: float = 1.25) -> None:
    """Block while any process uses the Chrome profile. Survive parent handoff."""
    # Appear
    appeared = False
    for _ in range(80):  # ~12s
        pids = _profile_pids(profile)
        if pids:
            appeared = True
            _log(f"profile live pids={pids[:8]}{'…' if len(pids) > 8 else ''}")
            break
        time.sleep(0.15)
    if not appeared:
        _log("WARN: no chromium profile process appeared")
        return

    # Stay until gone (with short grace so FS / process restart does not kill us)
    gone_since: float | None = None
    while True:
        pids = _profile_pids(profile)
        if pids:
            gone_since = None
        else:
            now = time.monotonic()
            if gone_since is None:
                gone_since = now
            elif now - gone_since >= grace_s:
                _log("profile processes gone — UI closed")
                return
        time.sleep(0.4)


def _open_chromium_app(url: str) -> bool:
    found = _find_chromium()
    if not found:
        return False
    name, binary = found
    profile = CHROME_PROFILE
    profile.mkdir(parents=True, exist_ok=True)
    target = url if url.endswith("/") else url + "/"

    # Prefer macOS open -na (proper LaunchServices); also direct exec fallback.
    args = [
        f"--app={target}",
        f"--user-data-dir={profile}",
        *_CHROME_BASE_FLAGS,
    ]
    extra = os.environ.get("XOCHIPILLI_CHROME_FLAGS", "").strip()
    if extra:
        args.extend(extra.split())

    _log(f"chromium app mode: {name} → {target}")
    _log(f"profile={profile}")

    # Direct spawn WITHOUT start_new_session (avoids odd session/signal -5)
    try:
        subprocess.Popen(
            [str(binary), *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=False,
        )
    except OSError as e:
        _log(f"direct chromium spawn failed: {e}; trying open -na")
        try:
            subprocess.run(
                ["/usr/bin/open", "-na", name, "--args", *args],
                check=False,
                capture_output=True,
            )
        except OSError as e2:
            _log(f"open -na failed: {e2}")
            return False

    print(f"[xochipilli] shell_mode=chromium-app engine={name}", flush=True)
    _wait_until_profile_quiet(profile)
    return True


def _open_safari(url: str) -> bool:
    target = url if url.endswith("/") else url + "/"
    try:
        subprocess.run(
            ["/usr/bin/open", "-a", "Safari", target],
            check=False,
            capture_output=True,
        )
        _log(f"opened Safari {target}")
        print("[xochipilli] shell_mode=safari", flush=True)
        return True
    except OSError as e:
        _log(f"Safari open failed: {e}")
        return False


def _run_pywebview(url: str) -> int:
    try:
        import webview
    except ImportError:
        _alert("Chrome も pywebview も使えません。", critical=True)
        return 1

    target = url if url.endswith("/") else url + "/"
    kwargs = {
        "title": "Xochipilli",
        "url": target,
        "width": 1440,
        "height": 900,
        "min_size": (960, 640),
        "background_color": "#0c0e12",
        "text_select": True,
        "resizable": True,
    }
    try:
        webview.create_window(**kwargs)
    except TypeError:
        kwargs.pop("text_select", None)
        webview.create_window(**kwargs)

    print("[xochipilli] shell_mode=pywebview-fallback", flush=True)
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

    _log(f"desktop_app start pid={os.getpid()} py={sys.executable}")
    _log(f"sys.path[0:4]={sys.path[:4]}")

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

    if _open_chromium_app(target):
        _stop_server(server)
        return 0

    if _open_safari(target):
        # Keep helper alive a bit so Dock bounce is not instant-death
        time.sleep(2.0)
        _stop_server(server)
        return 0

    rc = _run_pywebview(target)
    _stop_server(server)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
