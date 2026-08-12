"""Cold storage: projects nobody opened for a while move to iCloud Drive.

Local disk holds what is in use; everything older than `COLD_DAYS` is copied to
`paths.ARCHIVE`, verified, removed locally and then evicted from the local iCloud cache so
the space actually comes back. A small stub project.json stays behind so the project keeps
appearing in the picker and can be pulled back on demand.

Safety rules that must not be relaxed:
  * copy → verify → delete. The local copy is only removed once every file exists in the
    archive with the same size.
  * never touch a project whose lock is held (import / generate in flight).
  * never touch the project the UI currently has open (`skip` argument).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .paths import ARCHIVE, PROJECTS
from . import storage

COLD_DAYS = int(os.environ.get("XOCHIPILLI_COLD_DAYS", "7"))

#: Files that are stubbed out locally; anything else in the folder travels with it.
_STUB_KEYS = (
    "id",
    "title",
    "created_at",
    "updated_at",
    "opened_at",
    "duration_sec",
)

_RUN_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"running": False, "last": None, "busy": set()}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _read(pid: str) -> dict[str, Any] | None:
    try:
        return json.loads((PROJECTS / pid / "project.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def archive_dir(pid: str) -> Path:
    return ARCHIVE / storage.safe_project_id(pid)


def is_archived(pid: str) -> bool:
    data = _read(storage.safe_project_id(pid))
    return bool(data and data.get("archived"))


def status() -> dict[str, Any]:
    return {
        "cold_days": COLD_DAYS,
        "archive_root": str(ARCHIVE),
        "running": bool(_STATE["running"]),
        "last_run": _STATE["last"],
        "busy": sorted(_STATE["busy"]),
    }


def cold_projects(*, days: int | None = None, skip: set[str] | None = None) -> list[str]:
    """Project ids whose last human contact is older than the cutoff."""
    cutoff = _now() - timedelta(days=days if days is not None else COLD_DAYS)
    out: list[str] = []
    for p in sorted(PROJECTS.glob("*/project.json")):
        pid = p.parent.name
        if skip and pid in skip:
            continue
        data = _read(pid)
        if not data or data.get("archived"):
            continue
        seen = _parse(storage.last_seen(data))
        if seen is None or seen < cutoff:
            out.append(pid)
    return out


def _copy_tree_verified(src: Path, dst: Path) -> None:
    """Copy src → dst, then fail loudly unless every file arrived at the same size."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        target = dst / f.relative_to(src)
        if not target.is_file():
            raise OSError(f"archive copy missing {f.relative_to(src)}")
        if target.stat().st_size != f.stat().st_size:
            raise OSError(f"archive copy size mismatch on {f.relative_to(src)}")


def _evict(path: Path) -> str:
    """Ask iCloud to drop the local copy. Best effort — the file stays in the cloud."""
    try:
        r = subprocess.run(
            ["/usr/bin/brctl", "evict", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return "evicted" if r.returncode == 0 else f"evict rc={r.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"evict skipped ({e})"


def archive_project(pid: str) -> dict[str, Any]:
    safe = storage.safe_project_id(pid)
    src = PROJECTS / safe
    if not (src / "project.json").is_file():
        raise FileNotFoundError(pid)
    data = _read(safe) or {}
    if data.get("archived"):
        return {"id": safe, "skipped": "already archived"}

    lock = storage.project_lock(safe)
    if not lock.acquire(blocking=False):
        return {"id": safe, "skipped": "busy"}
    _STATE["busy"].add(safe)
    try:
        dst = archive_dir(safe)
        _copy_tree_verified(src, dst)

        stub = {k: data.get(k) for k in _STUB_KEYS if data.get(k) is not None}
        stub["id"] = safe
        stub["archived"] = True
        stub["archived_at"] = _now().isoformat()
        stub["archive_path"] = str(dst)
        dig = (data.get("digest") or {}).get("global") or {}
        if dig.get("duration_sec") is not None:
            stub["duration_sec"] = dig["duration_sec"]

        freed = 0
        for entry in sorted(src.iterdir(), reverse=True):
            if entry.is_dir():
                freed += sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                shutil.rmtree(entry)
            else:
                freed += entry.stat().st_size
                entry.unlink()
        (src / "project.json").write_text(
            json.dumps(stub, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        note = _evict(dst)
        return {"id": safe, "archived": True, "freed_bytes": freed, "evict": note}
    finally:
        _STATE["busy"].discard(safe)
        lock.release()


def restore_project(pid: str) -> dict[str, Any]:
    """Pull a project back from iCloud. Can block for a while on an evicted folder."""
    safe = storage.safe_project_id(pid)
    data = _read(safe)
    if not data:
        raise FileNotFoundError(pid)
    if not data.get("archived"):
        return {"id": safe, "skipped": "not archived"}
    src = Path(data.get("archive_path") or archive_dir(safe))
    if not src.is_dir():
        raise FileNotFoundError(f"archive folder missing: {src}")

    lock = storage.project_lock(safe)
    if not lock.acquire(blocking=False):
        return {"id": safe, "skipped": "busy"}
    _STATE["busy"].add(safe)
    try:
        # Touching the files makes iCloud download whatever it evicted.
        _download(src)
        dst = PROJECTS / safe
        staging = dst.parent / f".{safe}.restoring"
        _copy_tree_verified(src, staging)
        if not (staging / "project.json").is_file():
            raise OSError("archived project.json missing")
        shutil.rmtree(dst, ignore_errors=True)
        os.replace(staging, dst)
        restored = json.loads((dst / "project.json").read_text(encoding="utf-8"))
        for k in ("archived", "archived_at", "archive_path"):
            restored.pop(k, None)
        restored["opened_at"] = _now().isoformat()
        (dst / "project.json").write_text(
            json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {"id": safe, "restored": True}
    finally:
        _STATE["busy"].discard(safe)
        lock.release()


def _download(path: Path) -> None:
    try:
        subprocess.run(
            ["/usr/bin/brctl", "download", str(path)],
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    # brctl download is asynchronous for some layouts; reading forces materialisation.
    for f in sorted(path.rglob("*")):
        if f.is_file():
            try:
                with f.open("rb") as fh:
                    fh.read(1)
            except OSError:
                pass


def local_bytes(path: Path) -> int:
    """Bytes this folder still occupies on the local disk (evicted files report 0 blocks)."""
    total = 0
    for f in path.rglob("*"):
        if f.is_file() and not f.name.endswith(".icloud"):
            try:
                total += f.stat().st_blocks * 512
            except OSError:
                pass
    return total


def evict_archived() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(PROJECTS.glob("*/project.json")):
        data = _read(p.parent.name)
        if not data or not data.get("archived"):
            continue
        target = Path(data.get("archive_path") or archive_dir(p.parent.name))
        if not target.is_dir():
            continue
        before = local_bytes(target)
        if before <= 0:
            continue
        note = _evict(target)
        out.append(
            {
                "id": p.parent.name,
                "evict": note,
                "local_bytes_before": before,
                "local_bytes_after": local_bytes(target),
            }
        )
    return out


class _CrossProcessLock:
    """The app and the nightly launchd agent must never sweep at the same time."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def __enter__(self) -> bool:
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._fh.close()
            self._fh = None
            return False
        return True

    def __exit__(self, *exc: Any) -> None:
        import fcntl

        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


def run_once(*, days: int | None = None, skip: set[str] | None = None) -> dict[str, Any]:
    """Archive everything cold. Safe to call from a thread; only one run at a time."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"skipped": "already running"}
    _STATE["running"] = True
    results: list[dict[str, Any]] = []
    try:
        with _CrossProcessLock(PROJECTS.parent / ".archive.lock") as got:
            if not got:
                return {"skipped": "another Xochipilli is sweeping"}
            ARCHIVE.mkdir(parents=True, exist_ok=True)
            for pid in cold_projects(days=days, skip=skip):
                try:
                    results.append(archive_project(pid))
                except (OSError, ValueError) as e:
                    results.append({"id": pid, "error": str(e)})
            # iCloud refuses to evict a file it has not finished uploading, so the eviction
            # right after archiving is often a no-op. Retry every archived folder each sweep.
            results.extend(evict_archived())
    finally:
        _STATE["running"] = False
        _STATE["last"] = {"at": _now().isoformat(), "results": results}
        _RUN_LOCK.release()
    return {"archived": [r for r in results if r.get("archived")], "results": results}


def run_in_background(*, skip: set[str] | None = None) -> None:
    threading.Thread(
        target=lambda: run_once(skip=skip),
        name="xochipilli-archive",
        daemon=True,
    ).start()
