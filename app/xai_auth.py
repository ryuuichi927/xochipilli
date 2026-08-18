"""Resolve xAI credentials for Xochipilli video gen.

Bring your own key. Preference order:

1. An external OAuth helper, if ``XAI_OAUTH_HELPER`` points at a directory
   exposing ``tools/xai_http.py`` with ``resolve_xai_http_credentials()``.
   This is the refresh-aware path.
2. ``XAI_API_KEY`` from the environment or the project ``.env``.
3. A raw ``access_token`` read from the JSON file named by ``XAI_TOKEN_STORE``
   (last resort; the token may be stale).

Steps 1 and 3 are opt-in. With neither variable set, only ``XAI_API_KEY`` is
used, which is the normal path for anyone running this from a clone.

Never log full tokens.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1"


def _token_store() -> Path | None:
    """JSON file holding an OAuth token, if the operator configured one."""
    raw = (os.environ.get("XAI_TOKEN_STORE") or "").strip()
    return Path(raw).expanduser() if raw else None


def _oauth_helper_root() -> Path | None:
    """Directory exposing ``tools/xai_http.py``, if the operator configured one."""
    raw = (os.environ.get("XAI_OAUTH_HELPER") or "").strip()
    return Path(raw).expanduser() if raw else None


def _base_url() -> str:
    return (os.environ.get("XAI_BASE_URL") or XAI_DEFAULT_BASE_URL).rstrip("/")


def resolve_xai_credentials() -> dict[str, Any]:
    """Return ``{api_key, base_url, source}`` or raise RuntimeError."""
    # 1) External OAuth helper (refresh-aware)
    helper = _try_oauth_helper()
    if helper:
        return helper

    # 2) Explicit API key
    key = (os.environ.get("XAI_API_KEY") or "").strip()
    if key:
        return {"api_key": key, "base_url": _base_url(), "source": "xai_api_key"}

    # 3) Stale-friendly raw token peek
    raw = _try_token_store()
    if raw:
        return raw

    raise RuntimeError(
        "xAI credentials not found. Set XAI_API_KEY in .env. "
        "To reuse an existing OAuth session instead, point XAI_OAUTH_HELPER at a "
        "helper directory or XAI_TOKEN_STORE at a token file."
    )


def credentials_status() -> dict[str, Any]:
    """Safe status for /api/health (no secrets, no filesystem paths)."""
    store = _token_store()
    out: dict[str, Any] = {
        "token_store_configured": store is not None,
        "token_store_present": bool(store and store.is_file()),
        "oauth_helper_configured": _oauth_helper_root() is not None,
        "xai_api_key_env": bool((os.environ.get("XAI_API_KEY") or "").strip()),
        "source": None,
        "ok": False,
        "error": None,
        "relogin_hint": None,
    }
    try:
        creds = resolve_xai_credentials()
        out["ok"] = True
        out["source"] = creds.get("source")
        out["base_url"] = creds.get("base_url")
    except Exception as e:
        out["error"] = str(e)
        # surface a relogin flag from the token store if one is present
        try:
            if store and store.is_file():
                data = json.loads(store.read_text(encoding="utf-8"))
                err = (
                    (data.get("providers") or {})
                    .get("xai-oauth", {})
                    .get("last_auth_error")
                )
                if isinstance(err, dict) and err.get("relogin_required"):
                    out["relogin_hint"] = err.get("message") or "relogin_required"
        except Exception:
            pass
    return out


def _try_oauth_helper() -> dict[str, Any] | None:
    agent = _oauth_helper_root()
    if agent is None:
        return None
    py = agent / "venv" / "bin" / "python"
    if not py.is_file() or not (agent / "tools" / "xai_http.py").is_file():
        # try import from the current interpreter if the helper is importable
        try:
            if str(agent) not in sys.path and agent.is_dir():
                sys.path.insert(0, str(agent))
            from tools.xai_http import resolve_xai_http_credentials  # type: ignore

            creds = resolve_xai_http_credentials() or {}
            token = str(creds.get("api_key") or "").strip()
            base = str(creds.get("base_url") or XAI_DEFAULT_BASE_URL).rstrip("/")
            if token:
                return {
                    "api_key": token,
                    "base_url": base,
                    "source": creds.get("provider") or "oauth-helper-import",
                }
        except Exception:
            pass
        return None

    code = (
        "import json\n"
        "from tools.xai_http import resolve_xai_http_credentials\n"
        "c = resolve_xai_http_credentials() or {}\n"
        "print(json.dumps({"
        "'api_key': c.get('api_key') or '', "
        f"'base_url': c.get('base_url') or '{XAI_DEFAULT_BASE_URL}', "
        "'source': c.get('provider') or 'oauth-helper'"
        "}))\n"
    )
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    try:
        r = subprocess.run(
            [str(py), "-c", code],
            cwd=str(agent),
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    line = (r.stdout or "").strip().splitlines()
    if not line:
        return None
    try:
        data = json.loads(line[-1])
    except json.JSONDecodeError:
        return None
    token = str(data.get("api_key") or "").strip()
    if not token:
        return None
    return {
        "api_key": token,
        "base_url": str(data.get("base_url") or XAI_DEFAULT_BASE_URL).rstrip("/"),
        "source": str(data.get("source") or "oauth-helper"),
    }


def _try_token_store() -> dict[str, Any] | None:
    store = _token_store()
    if store is None or not store.is_file():
        return None
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except Exception:
        return None
    token = ""
    providers = data.get("providers") if isinstance(data, dict) else None
    xai = providers.get("xai-oauth") if isinstance(providers, dict) else None
    tokens = xai.get("tokens") if isinstance(xai, dict) else None
    if isinstance(tokens, dict):
        token = str(tokens.get("access_token") or "").strip()
    if not token:
        pool = data.get("credential_pool") if isinstance(data, dict) else None
        entries = pool.get("xai-oauth") if isinstance(pool, dict) else None
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    token = str(entry.get("access_token") or "").strip()
                    if token:
                        break
    if not token:
        return None
    return {
        "api_key": token,
        "base_url": _base_url(),
        "source": "token-store-raw",
    }
