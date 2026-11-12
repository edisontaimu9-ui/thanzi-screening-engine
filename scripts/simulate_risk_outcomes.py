"""Write a SIMULATED risk dataset (assumed outcome formula) for building and testing the risk pipeline.

    python scripts/simulate_risk_outcomes.py                 # data/synthetic/risk/ (git-ignored)
    python scripts/simulate_risk_outcomes.py --n 3000 --seed 1 --out /tmp/risk

NOT CLINICAL. Outcomes come from an assumed formula, so a model trained on this data can only learn that formula.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thanzi_screen.ml.risk.data import write_dataset  # noqa: E402
from thanzi_screen.ml.risk.simulate import simulate_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=20_000, help="records before filtering (default 20000)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "data" / "synthetic" / "risk"))
    args = ap.parse_args()
    rows, extra = simulate_rows(args.n, args.seed)
    manifest = write_dataset(rows, extra, args.out)
    print(f"wrote {manifest['rows']} rows to {args.out} (simulated outcomes, prevalence {extra['observed_prevalence']}, "
          f"sha256 {manifest['sha256'][:16]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
