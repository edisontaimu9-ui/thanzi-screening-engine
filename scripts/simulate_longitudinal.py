"""Write a SIMULATED longitudinal dataset (one row per visit) and print the label summary.

    python scripts/simulate_longitudinal.py                  # data/synthetic/longitudinal/ (git-ignored)
    python scripts/simulate_longitudinal.py --n 6000 --seed 1 --out /tmp/long

NOT CLINICAL. Every association is an assumption written into thanzi_screen.prediction.simulate. A model trained on this
data can only learn those assumptions. Its purpose is to exercise the pipeline end to end.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thanzi_screen.prediction import (  # noqa: E402
    SimConfig, TargetConfig, build_examples, label_summary, simulate_children, write_dataset,
)
from thanzi_screen.prediction.simulate import A  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=6000, help="children (default 6000)")
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--out", default=str(ROOT / "data" / "synthetic" / "longitudinal"))
    args = ap.parse_args()
    cfg = SimConfig(n_children=args.n, seed=args.seed)
    children = simulate_children(cfg)
    summary = label_summary(build_examples(children, TargetConfig()))
    manifest = write_dataset(children, {
        "provenance": "simulated", "simulation_seed": args.seed, "assumed_effects": A,
        "note": "SIMULATED, NON-CLINICAL. Associations are assumptions, not estimates.",
    }, args.out)
    print(f"wrote {manifest['rows']} visits of {manifest['children']} children to {args.out} (sha256 {manifest['sha256'][:16]}...)")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
