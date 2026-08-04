"""Canva Connect API — OAuth (PKCE) + asset upload for Xochipilli export.

Upload generated clips / program.mp4 into the user's Canva library.
Optional: for still images, create a blank design with the asset placed.

Requires private/public integration credentials in .env:
  CANVA_CLIENT_ID
  CANVA_CLIENT_SECRET
  CANVA_REDIRECT_URI  (default http://127.0.0.1:8787/api/canva/callback)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .paths import DATA

CANVA_AUTH = "https://www.canva.com/api/oauth/authorize"
CANVA_TOKEN = "https://api.canva.com/rest/v1/oauth/token"
CANVA_API = "https://api.canva.com/rest/v1"
DEFAULT_SCOPES = "asset:read asset:write design:content:write design:meta:read profile:read"
TOKEN_PATH = DATA / "canva_tokens.json"
PKCE_PATH = DATA / "canva_pkce.json"


def _client_id() -> str:
    return (os.environ.get("CANVA_CLIENT_ID") or "").strip()


def _client_secret() -> str:
    return (os.environ.get("CANVA_CLIENT_SECRET") or "").strip()


def redirect_uri() -> str:
    return (
        os.environ.get("CANVA_REDIRECT_URI")
        or "http://127.0.0.1:8787/api/canva/callback"
    ).strip()


def scopes() -> str:
    return (os.environ.get("CANVA_SCOPES") or DEFAULT_SCOPES).strip()


def configured() -> bool:
    return bool(_client_id() and _client_secret())


def status() -> dict[str, Any]:
    tok = _load_tokens()
    connected = bool(tok.get("access_token") or tok.get("refresh_token"))
    exp = tok.get("expires_at")
    return {
        "configured": configured(),
        "connected": connected,
        "expires_at": exp,
        "token_valid": bool(tok.get("access_token") and exp and float(exp) > time.time() + 30)
        or bool(tok.get("refresh_token")),
        "redirect_uri": redirect_uri(),
        "scopes": scopes(),
        "client_id_set": bool(_client_id()),
        "hint": None
        if configured()
        else "Set CANVA_CLIENT_ID and CANVA_CLIENT_SECRET in .env (Canva Developer Portal → Create integration).",
    }


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except Exception:
        pass


def _load_tokens() -> dict[str, Any]:
    return _load_json(TOKEN_PATH)


def _save_tokens(data: dict[str, Any]) -> None:
    _save_json(TOKEN_PATH, data)


def clear_tokens() -> None:
    if TOKEN_PATH.is_file():
        TOKEN_PATH.unlink()
    if PKCE_PATH.is_file():
        PKCE_PATH.unlink()


def start_authorize() -> dict[str, Any]:
    if not configured():
        raise RuntimeError(
            "Canva not configured. Add CANVA_CLIENT_ID and CANVA_CLIENT_SECRET to .env"
        )
    verifier = _b64url(secrets.token_bytes(64))
    if len(verifier) < 43:
        verifier = (verifier + _b64url(secrets.token_bytes(32)))[:96]
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    state = _b64url(secrets.token_bytes(32))
    _save_json(
        PKCE_PATH,
        {"code_verifier": verifier, "state": state, "created_at": time.time()},
    )
    q = {
        "code_challenge": challenge,
        "code_challenge_method": "s256",
        "scope": scopes(),
        "response_type": "code",
        "client_id": _client_id(),
        "state": state,
        "redirect_uri": redirect_uri(),
    }
    return {"authorize_url": f"{CANVA_AUTH}?{urlencode(q)}", "redirect_uri": redirect_uri()}


def finish_authorize(code: str, state: str | None) -> dict[str, Any]:
    pkce = _load_json(PKCE_PATH)
    if not pkce.get("code_verifier"):
        raise RuntimeError("PKCE session missing — click Connect to Canva again")
    if state and pkce.get("state") and state != pkce["state"]:
        raise RuntimeError("OAuth state mismatch")
    basic = base64.b64encode(f"{_client_id()}:{_client_secret()}".encode()).decode()
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": pkce["code_verifier"],
        "redirect_uri": redirect_uri(),
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            CANVA_TOKEN,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=data,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"token exchange {r.status_code}: {r.text[:400]}")
        body = r.json()
    _store_token_response(body)
    if PKCE_PATH.is_file():
        PKCE_PATH.unlink()
    return {"ok": True, "expires_in": body.get("expires_in")}


def _store_token_response(body: dict[str, Any]) -> None:
    now = time.time()
    expires_in = float(body.get("expires_in") or 3600)
    prev = _load_tokens()
    out = {
        "access_token": body.get("access_token"),
        "refresh_token": body.get("refresh_token") or prev.get("refresh_token"),
        "token_type": body.get("token_type") or "Bearer",
        "expires_at": now + expires_in - 60,
        "scope": body.get("scope") or scopes(),
        "updated_at": now,
    }
    if not out["access_token"]:
        raise RuntimeError(f"no access_token in response: {str(body)[:200]}")
    _save_tokens(out)


def _refresh() -> str:
    tok = _load_tokens()
    rt = tok.get("refresh_token")
    if not rt:
        raise RuntimeError("Not connected to Canva — connect in Settings")
    basic = base64.b64encode(f"{_client_id()}:{_client_secret()}".encode()).decode()
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            CANVA_TOKEN,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "refresh_token", "refresh_token": rt},
        )
        if r.status_code >= 400:
            clear_tokens()
            raise RuntimeError(f"refresh failed {r.status_code}: {r.text[:300]} — reconnect Canva")
        body = r.json()
    _store_token_response(body)
    return str(_load_tokens()["access_token"])


def access_token() -> str:
    if not configured():
        raise RuntimeError("Canva credentials not configured in .env")
    tok = _load_tokens()
    at = tok.get("access_token")
    exp = float(tok.get("expires_at") or 0)
    if at and exp > time.time() + 30:
        return str(at)
    return _refresh()


def _name_base64(name: str) -> str:
    # Canva max 50 chars unencoded
    n = (name or "xochipilli").strip()[:50]
    return base64.b64encode(n.encode("utf-8")).decode("ascii")


def upload_file(path: Path, display_name: str | None = None) -> dict[str, Any]:
    """Upload image or video; poll until success. Returns asset dict."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    name = display_name or path.stem
    token = access_token()
    raw = path.read_bytes()
    meta = json.dumps({"name_base64": _name_base64(name)})
    with httpx.Client(timeout=180.0) as client:
        r = client.post(
            f"{CANVA_API}/asset-uploads",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "Asset-Upload-Metadata": meta,
            },
            content=raw,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"upload start {r.status_code}: {r.text[:400]}")
        job = (r.json() or {}).get("job") or {}
        job_id = job.get("id")
        if not job_id:
            raise RuntimeError(f"no job id: {r.text[:300]}")

        # poll
        deadline = time.time() + 180
        last: dict[str, Any] = job
        while time.time() < deadline:
            st = (last.get("status") or "").lower()
            if st == "success":
                asset = last.get("asset") or {}
                return {
                    "ok": True,
                    "job_id": job_id,
                    "asset": asset,
                    "asset_id": asset.get("id"),
                    "type": asset.get("type"),
                    "name": asset.get("name"),
                    "thumbnail": (asset.get("thumbnail") or {}).get("url"),
                }
            if st == "failed":
                err = last.get("error") or {}
                raise RuntimeError(err.get("message") or err.get("code") or "upload failed")
            time.sleep(1.5)
            pr = client.get(
                f"{CANVA_API}/asset-uploads/{job_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if pr.status_code >= 400:
                raise RuntimeError(f"poll {pr.status_code}: {pr.text[:300]}")
            last = (pr.json() or {}).get("job") or {}
    raise RuntimeError("Canva upload timed out")


def create_design_from_image(
    asset_id: str,
    title: str = "Xochipilli",
    width: int = 1920,
    height: int = 1080,
) -> dict[str, Any]:
    """Create a design with an image asset (video asset_id not supported by API)."""
    token = access_token()
    payload = {
        "design_type": {"type": "custom", "width": width, "height": height},
        "asset_id": asset_id,
        "title": (title or "Xochipilli")[:255],
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            f"{CANVA_API}/designs",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"create design {r.status_code}: {r.text[:400]}")
        design = (r.json() or {}).get("design") or {}
        urls = design.get("urls") or {}
        return {
            "ok": True,
            "design_id": design.get("id"),
            "title": design.get("title"),
            "edit_url": urls.get("edit_url"),
            "view_url": urls.get("view_url"),
        }


def open_library_url() -> str:
    return "https://www.canva.com/folder"
