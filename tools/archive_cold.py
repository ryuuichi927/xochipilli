#!/usr/bin/env python3
"""Park projects nobody opened lately in iCloud Drive, and install the daily agent.

    .venv/bin/python tools/archive_cold.py --dry-run     # what would move
    .venv/bin/python tools/archive_cold.py               # move it
    .venv/bin/python tools/archive_cold.py --restore ID  # pull one back
    .venv/bin/python tools/archive_cold.py --install-agent
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import archive, storage  # noqa: E402
from app.paths import ARCHIVE, PROJECTS  # noqa: E402

LABEL = "local.xochipilli.archive"
AGENT_PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
AGENT_LOG = Path.home() / "Library/Logs/Xochipilli/archive.log"


def install_agent(hour: int = 4, minute: int = 30) -> int:
    py = REPO / ".venv/bin/python"
    if not py.is_file():
        print(f"missing {py} — build the venv first")
        return 1
    AGENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [str(py), str(REPO / "tools/archive_cold.py")],
        "WorkingDirectory": str(REPO),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(AGENT_LOG),
        "StandardErrorPath": str(AGENT_LOG),
        "ProcessType": "Background",
        "LowPriorityIO": True,
    }
    AGENT_PLIST.write_bytes(plistlib.dumps(plist))
    uid = os.getuid()
    subprocess.run(
        ["/bin/launchctl", "bootout", f"gui/{uid}/{LABEL}"],
        capture_output=True,
        text=True,
    )
    r = subprocess.run(
        ["/bin/launchctl", "bootstrap", f"gui/{uid}", str(AGENT_PLIST)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"launchctl bootstrap failed rc={r.returncode}: {(r.stderr or '').strip()}")
        return 1
    print(f"installed {LABEL} — daily at {hour:02d}:{minute:02d}, log: {AGENT_LOG}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--restore", metavar="ID", default=None)
    ap.add_argument("--install-agent", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.install_agent:
        return install_agent()

    if args.status:
        rows = storage.list_projects()
        print(f"projects: {PROJECTS}")
        print(f"archive : {ARCHIVE}")
        for r in rows:
            mark = "☁" if r.get("archived") else "·"
            print(f"  {mark} {r['id']}  {r.get('title')!r}  last seen {storage.last_seen(r)}")
        return 0

    if args.restore:
        print(json.dumps(archive.restore_project(args.restore), ensure_ascii=False))
        return 0

    if args.dry_run:
        cold = archive.cold_projects(days=args.days)
        if not cold:
            print(f"nothing colder than {args.days or archive.COLD_DAYS} days")
            return 0
        for pid in cold:
            d = PROJECTS / pid
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            print(f"would archive {pid}  ({size / 1e6:.1f} MB)")
        return 0

    out = archive.run_once(days=args.days)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
