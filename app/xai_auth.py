"""Resolve xAI credentials for Xochipilli video gen.

Preference order (SuperGrok Heavy / Ben's Tool-aligned):
1. Ben's Tool-managed xAI OAuth (``~/.bentool`` auth pool) via bentool-agent helper
2. ``XAI_API_KEY`` env / project ``.env``
3. Raw ``access_token`` in ``~/.bentool/auth.json`` (last resort; may be stale)

Never log full tokens.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _bentool_home() -> Path:
    return Path(os.environ.get("BENTOOL_HOME") or (Path.home() / ".bentool")).expanduser()


def _bentool_agent_root() -> Path:
    return Path(
        os.environ.get("BENTOOL_AGENT_ROOT")
        or (_bentool_home() / "bentool-agent")
    ).expanduser()


def resolve_xai_credentials() -> dict[str, Any]:
    """Return ``{api_key, base_url, source}`` or raise RuntimeError."""
    # 1) Ben's Tool OAuth (refresh-aware)
    bentool = _try_bentool_oauth()
    if bentool:
        return bentool

    # 2) Explicit API key
    key = (os.environ.get("XAI_API_KEY") or "").strip()
    if key:
        base = (
            os.environ.get("XAI_BASE_URL")
            or os.environ.get("BENTOOL_XAI_BASE_URL")
            or "https://api.x.ai/v1"
        ).rstrip("/")
        return {"api_key": key, "base_url": base, "source": "xai_api_key"}

    # 3) Stale-friendly raw token peek
    raw = _try_auth_json_token()
    if raw:
        return raw

    raise RuntimeError(
        "xAI credentials not found. SuperGrok OAuth: run Ben's Tool login "
        "(`bentool auth` / Desktop xAI login) so ~/.bentool/auth.json has xai-oauth. "
        "Or set XAI_API_KEY in .env."
    )


def credentials_status() -> dict[str, Any]:
    """Safe status for /api/health (no secrets)."""
    home = _bentool_home()
    auth_path = home / "auth.json"
    out: dict[str, Any] = {
        "bentool_home": str(home),
        "auth_json_present": auth_path.is_file(),
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
        # surface bentool relogin flag if present
        try:
            if auth_path.is_file():
                store = json.loads(auth_path.read_text(encoding="utf-8"))
                err = (
                    (store.get("providers") or {})
                    .get("xai-oauth", {})
                    .get("last_auth_error")
                )
                if isinstance(err, dict) and err.get("relogin_required"):
                    out["relogin_hint"] = err.get("message") or "relogin_required"
        except Exception:
            pass
    return out


def _try_bentool_oauth() -> dict[str, Any] | None:
    agent = _bentool_agent_root()
    py = agent / "venv" / "bin" / "python"
    if not py.is_file() or not (agent / "tools" / "xai_http.py").is_file():
        # try import from current interpreter if bentool is on path
        try:
            if str(agent) not in sys.path and agent.is_dir():
                sys.path.insert(0, str(agent))
            from tools.xai_http import resolve_xai_http_credentials  # type: ignore

            creds = resolve_xai_http_credentials() or {}
            token = str(creds.get("api_key") or "").strip()
            base = str(creds.get("base_url") or "https://api.x.ai/v1").rstrip("/")
            if token:
                return {
                    "api_key": token,
                    "base_url": base,
                    "source": creds.get("provider") or "bentool-oauth-import",
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
        "'base_url': c.get('base_url') or 'https://api.x.ai/v1', "
        "'source': c.get('provider') or 'bentool-oauth'"
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
        "base_url": str(data.get("base_url") or "https://api.x.ai/v1").rstrip("/"),
        "source": str(data.get("source") or "bentool-oauth"),
    }


def _try_auth_json_token() -> dict[str, Any] | None:
    auth_path = _bentool_home() / "auth.json"
    if not auth_path.is_file():
        return None
    try:
        store = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    token = ""
    providers = store.get("providers") if isinstance(store, dict) else None
    xai = providers.get("xai-oauth") if isinstance(providers, dict) else None
    tokens = xai.get("tokens") if isinstance(xai, dict) else None
    if isinstance(tokens, dict):
        token = str(tokens.get("access_token") or "").strip()
    if not token:
        pool = store.get("credential_pool") if isinstance(store, dict) else None
        entries = pool.get("xai-oauth") if isinstance(pool, dict) else None
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    token = str(entry.get("access_token") or "").strip()
                    if token:
                        break
    if not token:
        return None
    base = (
        os.environ.get("XAI_BASE_URL")
        or os.environ.get("BENTOOL_XAI_BASE_URL")
        or "https://api.x.ai/v1"
    ).rstrip("/")
    return {
        "api_key": token,
        "base_url": base,
        "source": "bentool-auth.json-raw",
    }
