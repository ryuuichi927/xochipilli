"""Dev helper: F-measure-ish between hand pins and structure_candidates (needs mir_eval)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/mir_eval_structure.py data/projects/<pid>")
        return 2
    root = Path(sys.argv[1])
    dig = json.loads((root / "digest.json").read_text(encoding="utf-8"))
    proj = json.loads((root / "project.json").read_text(encoding="utf-8"))
    ref_bounds = sorted(
        {0.0}
        | {float(s["t0"]) for s in proj.get("segments") or []}
        | {float(s["t1"]) for s in proj.get("segments") or []}
    )
    est_bounds = sorted(
        {0.0}
        | {float(c["t0"]) for c in dig.get("structure_candidates") or []}
        | {float(c["t1"]) for c in dig.get("structure_candidates") or []}
    )
    try:
        import mir_eval
    except ImportError:
        print("mir_eval not installed — bounds only")
        print("ref", ref_bounds)
        print("est", est_bounds)
        return 0
    # hit rate @ 0.5s
    ref = mir_eval.util.boundaries_to_intervals(ref_bounds)
    est = mir_eval.util.boundaries_to_intervals(est_bounds)
    # use boundary detection metric
    p, r, f = mir_eval.segment.detection(ref_bounds, est_bounds, window=0.5)
    print(f"boundary P={p:.3f} R={r:.3f} F={f:.3f} (window=0.5s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
