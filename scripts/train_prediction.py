"""Compare logistic regression, random forest and XGBoost for the three prediction targets, with calibration.

    python scripts/simulate_longitudinal.py
    python scripts/train_prediction.py --allow-simulated                  # writes models/prediction_sim/ (NON-CLINICAL)
    python scripts/train_prediction.py --data <dir>/visits.csv --out <dir>   # real data: the manifest must carry governance

Needs the `train` extra (numpy, scikit-learn, XGBoost). Development machine only: the service never imports them. A missing
XGBoost skips that candidate and says so. Same data and seed give identical numbers.

Phase 3 compares and calibrates. It exports no model file: tree export, explanations, risk strata and the model card are
Phase 4. Nothing written here is approved for clinical use.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thanzi_screen.prediction import DatasetError, TargetConfig, build_examples, load_dataset  # noqa: E402
from thanzi_screen.prediction import candidates as cand  # noqa: E402
from thanzi_screen.prediction import compare  # noqa: E402
from thanzi_screen.prediction.targets import TARGETS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(ROOT / "data" / "synthetic" / "longitudinal" / "visits.csv"))
    ap.add_argument("--out", default=str(ROOT / "models" / "prediction_sim"))
    ap.add_argument("--seed", type=int, default=0, help="child-level split seed and model seed")
    ap.add_argument("--n-boot", type=int, default=300, help="child-level bootstrap resamples (default 300)")
    ap.add_argument("--alert-rates", type=float, nargs="+", default=[0.10, 0.20])
    ap.add_argument("--candidates", default="lr,rf,xgb")
    ap.add_argument("--targets", default=",".join(TARGETS))
    ap.add_argument("--min-events", type=int, default=30, help="events needed in each split to train a target")
    ap.add_argument("--allow-simulated", action="store_true", help="required for a simulated dataset (non-clinical output)")
    args = ap.parse_args()

    try:
        children, manifest = load_dataset(args.data, allow_simulated=args.allow_simulated)
    except (DatasetError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    wanted = tuple(c for c in args.candidates.split(",") if c in cand.CANDIDATES)
    if "lr" not in wanted:
        wanted = ("lr",) + wanted
    for c in wanted:
        if not cand.available(c):
            print(f"skipping {c}: library not installed (pip install -e '.[train]')")
    if not cand.available("lr"):
        print("refused: logistic regression (numpy and scikit-learn) is the reference model and is required", file=sys.stderr)
        return 2
    targets = tuple(t for t in args.targets.split(",") if t in TARGETS)
    cfg = compare.CompareConfig(seed=args.seed, n_boot=args.n_boot, alert_rates=tuple(args.alert_rates),
                                min_events=args.min_events, candidates=wanted)
    examples = build_examples(children, TargetConfig(), seed=args.seed)
    results = compare.run_all(examples, cfg, targets)
    provenance = manifest["provenance"]
    results["dataset"] = {"sha256": manifest["sha256"], "rows": manifest["rows"], "children": manifest["children"],
                          "provenance": provenance}
    results["clinical_use"] = False
    results["note"] = ("Phase 3 comparison and calibration only. No acceptance check, no sign-off, no exported model. "
                       + ("Simulated data: every association is an assumption." if provenance == "simulated" else ""))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = compare.render_report(results, provenance)
    (out / "REPORT.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote {out / 'results.json'} and {out / 'REPORT.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
