"""Train, check and export the prediction models as plain JSON the service can run without scikit-learn or XGBoost.

    python scripts/simulate_longitudinal.py
    python scripts/export_prediction.py --allow-simulated              # models/prediction_sim/<target>.json, MODEL_CARD.md (NON-CLINICAL)
    python scripts/export_prediction.py --data <dir>/visits.csv --out <dir> --clinical-signoff <ref> --acceptance <file.json>

Runs the Phase 3 comparison (same fixed order: the test split is read once, to report), then exports ONLY the selected model for
each trained target. Every exported file is loaded back through the service's own loader and compared with the training library
on validation rows; a difference above 1e-5 stops the export. A target that was not trained is not exported.

Real data: the dataset manifest must carry ethics and data-agreement references (the loader enforces this). The export also needs
--clinical-signoff and an --acceptance file ({"set": true, "passed": true, "checks": [...]}) holding thresholds that were set before
the data were seen. Without them nothing is written. Simulated data is always exported as clinical_use false.

Needs the `train` extra. Development machine only: the service never imports it.
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
from thanzi_screen.prediction import compare, export  # noqa: E402
from thanzi_screen.prediction.card import render_model_card  # noqa: E402
from thanzi_screen.prediction.errors import PredictionModelError  # noqa: E402
from thanzi_screen.prediction.model import SCHEMA, PredictionModel  # noqa: E402
from thanzi_screen.prediction.targets import TARGETS  # noqa: E402

AGE_RANGE = (6.0, 60.0)
PLAIN = {"future_wasting": "wasting", "future_sam": "severe acute malnutrition", "future_faltering": "faltering weight gain"}
DEFINITION = {
    "future_wasting": "At a later visit in the window: weight-for-height z-score below -2, MUAC below 12.5 cm or oedema. Children already at the outcome are excluded.",
    "future_sam": "At a later visit in the window: weight-for-height z-score below -3, MUAC below 11.5 cm or oedema. Children already at the outcome are excluded.",
    "future_faltering": "At the first usable later visit in the window: weight-for-age z-score down by 1 or more since the index visit, or weight lower by at least 0.1 kg.",
}


def build_spec(target: str, r: dict, prep, state, manifest: dict, tcfg: TargetConfig, seed: int, signoff, acceptance) -> tuple[dict, float]:
    sel = r["selection"]["selected"]
    fitted = state["models"][sel]
    columns = list(prep.pre.columns)
    kind, part = export.export_candidate(sel, fitted.estimator, columns, prep.X["train"], prep.X["val"][0])
    rates = sorted(state["thresholds"])
    if len(rates) < 2:
        raise SystemExit("export needs two alert rates (for the elevated and high strata): pass --alert-rates 0.10 0.20")
    cuts = {"high": state["thresholds"][rates[0]][sel], "elevated": state["thresholds"][rates[1]][sel]}
    a, b = state["platt"][sel]
    simulated = manifest["provenance"] == "simulated"
    max_missing = max(sum(1 for v in e.features.values() if v is None) for e in prep.rows["train"])
    spec = {
        "schema": SCHEMA, "version": f"{target}-{'sim' if simulated else 'real'}-0.1.0", "kind": kind,
        "provenance": manifest["provenance"], "clinical_use": not simulated,
        "target": {"name": target, "plain": PLAIN[target], "definition": DEFINITION[target],
                   "horizon_min_days": tcfg.horizon_min_days, "horizon_max_days": tcfg.horizon_max_days},
        "preprocessor": prep.pre.to_dict(), "model": part, "calibration": {"a": a, "b": b},
        "strata": {"cutoffs": cuts, "alert_rates": {"high": rates[0], "elevated": rates[1]}, "basis": "validation children"},
        "eligibility": {"age_months_min": AGE_RANGE[0], "age_months_max": AGE_RANGE[1]},
        "safeguards": {"max_missing_features": max_missing},
        "dataset_sha256": manifest["sha256"], "seed": seed, "selected_candidate": sel,
        "metrics": {"test_auroc": r["test"]["models"][sel]["auroc"], "test_events": r["test"]["events"]},
        "acceptance": {"set": False, "passed": None, "checks": []},
    }
    if not simulated:
        spec["governance"] = {"ethics_ref": manifest["ethics_ref"], "data_agreement_ref": manifest["data_agreement_ref"],
                              "clinical_signoff": signoff}
        spec["acceptance"] = acceptance
    # Parity: load what will ship through the service's own loader and compare it with the training library on validation rows.
    shipped = PredictionModel(json.loads(json.dumps(spec, sort_keys=True)))      # same bytes as the file
    diff = max((abs(shipped._raw_probability(x) - p) for x, p in zip(prep.X["val"], fitted.predict_proba(prep.X["val"]))), default=0.0)
    if diff > export.PARITY_TOLERANCE:
        raise SystemExit(f"{target}: exported model differs from the library by {diff:.2e}. Not shipping.")
    return spec, diff


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(ROOT / "data" / "synthetic" / "longitudinal" / "visits.csv"))
    ap.add_argument("--out", default=str(ROOT / "models" / "prediction_sim"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--n-boot", type=int, default=300)
    ap.add_argument("--alert-rates", type=float, nargs=2, default=[0.10, 0.20], help="high and elevated alert rates")
    ap.add_argument("--candidates", default="lr,rf,xgb")
    ap.add_argument("--targets", default=",".join(TARGETS))
    ap.add_argument("--min-events", type=int, default=30)
    ap.add_argument("--allow-simulated", action="store_true")
    ap.add_argument("--clinical-signoff", default="", help="real data only: the sign-off reference")
    ap.add_argument("--acceptance", default="", help="real data only: JSON with set, passed and checks")
    args = ap.parse_args()

    try:
        children, manifest = load_dataset(args.data, allow_simulated=args.allow_simulated)
    except (DatasetError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    acceptance = None
    if manifest["provenance"] == "real":
        try:
            acceptance = json.loads(Path(args.acceptance).read_text(encoding="utf-8")) if args.acceptance else None
        except (OSError, ValueError):
            acceptance = None
        if not args.clinical_signoff.strip() or not acceptance or acceptance.get("set") is not True or acceptance.get("passed") is not True:
            print("refused: real data needs --clinical-signoff and an --acceptance file with set and passed true. Nothing written.", file=sys.stderr)
            return 2
    if not cand.available("lr"):
        print("refused: numpy and scikit-learn are required (pip install -e '.[train]')", file=sys.stderr)
        return 2
    wanted = tuple(c for c in args.candidates.split(",") if c in cand.CANDIDATES and cand.available(c))
    if "lr" not in wanted:
        wanted = ("lr",) + wanted
    targets = tuple(t for t in args.targets.split(",") if t in TARGETS)
    cfg = compare.CompareConfig(seed=args.seed, n_boot=args.n_boot, alert_rates=tuple(args.alert_rates), min_events=args.min_events,
                                candidates=wanted)
    tcfg = TargetConfig()
    examples = build_examples(children, tcfg, seed=args.seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {"config": {"seed": cfg.seed, "n_boot": cfg.n_boot, "alert_rates": list(cfg.alert_rates), "min_events": cfg.min_events,
                          "min_gain": cfg.min_gain},
               "label_summary": compare._clean(compare.label_summary(examples)), "libraries": cand.versions(), "targets": {}}
    specs, parities = {}, {}
    for t in targets:
        r, prep, state = compare.run_target_with_state(examples, t, cfg)
        results["targets"][t] = r
        if r["status"] != "trained":
            print(f"{t}: not trained, not exported ({r['reason']})")
            continue
        spec, diff = build_spec(t, r, prep, state, manifest, tcfg, args.seed, args.clinical_signoff.strip(), acceptance)
        (out / f"{t}.json").write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        specs[t], parities[t] = spec, diff
        print(f"{t}: exported {spec['selected_candidate']} ({spec['kind']}), version {spec['version']}, parity {diff:.1e}")
    results["dataset"] = {"sha256": manifest["sha256"], "rows": manifest["rows"], "children": manifest["children"],
                          "provenance": manifest["provenance"]}
    results["clinical_use"] = manifest["provenance"] == "real"
    results["exported"] = sorted(specs)
    (out / "results.json").write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "REPORT.md").write_text(compare.render_report(results, manifest["provenance"]), encoding="utf-8")
    card = render_model_card(results, specs, parities, manifest["provenance"])
    (out / "MODEL_CARD.md").write_text(card, encoding="utf-8")
    print(f"wrote {len(specs)} model file(s), results.json, REPORT.md and MODEL_CARD.md in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
