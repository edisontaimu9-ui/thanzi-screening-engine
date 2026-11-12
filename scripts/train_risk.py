"""Train, calibrate, validate and export the advisory risk model (logistic regression, random forest, XGBoost).

    python scripts/simulate_risk_outcomes.py
    python scripts/train_risk.py --allow-simulated                       # writes models/risk_sim/ (NON-CLINICAL)
    python scripts/train_risk.py --data <dir>/risk_dataset.csv --out models/risk --clinical-signoff REF ...

Logistic regression trains in plain Python. Random forest and XGBoost need scikit-learn and XGBoost (development
machine only, not the service): a missing library skips that candidate. Same dataset and seed give identical files.

Method (the order matters, and the test split is opened once):
  1. Features come from the same function the service uses. Children who cannot be scored are counted, not imputed.
  2. Split by time: the last two periods are the test set, the one before is validation, the rest is training.
     A child stays in one split (by the child's first period).
  3. Fit each candidate on training data. Calibrate on validation data (Platt scaling).
  4. A challenger replaces logistic regression only if its AUROC gain on validation is at least 0.01 and the paired
     bootstrap interval of the gain excludes zero. Otherwise the simpler model ships.
  5. The alert threshold is chosen on validation data for a target alert rate.
  6. Report once on the test set, with intervals, subgroups and a comparison with the rules alone.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thanzi_screen.ml.features import features_from_inputs  # noqa: E402
from thanzi_screen.ml.models import LogisticModel  # noqa: E402
from thanzi_screen.ml.risk import evaluate as ev  # noqa: E402
from thanzi_screen.ml.risk.data import load_dataset, row_inputs  # noqa: E402
from thanzi_screen.ml.risk.errors import RiskModelError  # noqa: E402
from thanzi_screen.ml.risk.features import MONOTONE, RISK_FEATURES, risk_features, risk_vector  # noqa: E402
from thanzi_screen.ml.risk.model import MODEL_FILE, SCHEMA, RiskModel  # noqa: E402
from thanzi_screen.ml.risk.trees import TreeEnsemble  # noqa: E402

AGE_RANGE = (6.0, 60.0)
CANDIDATES = ("lr", "rf", "xgb")
PARITY_TOLERANCE = 1e-5
MIN_GAIN = 0.01


# ---------------------------------------------------------------- data
def build_matrix(rows):
    """Score every row with the service's own feature function. Returns kept rows with features, and reason counts."""
    kept, reasons = [], Counter()
    for r in rows:
        args = row_inputs(r)
        f, why = risk_features(*args, age_months_range=AGE_RANGE)
        if f is None:
            reasons[why] += 1
            continue
        cls = features_from_inputs(*args[:6])[2].classification.value
        age = f["age_months"]
        kept.append({"x": risk_vector(f), "y": int(r["outcome"]), "child": r["child_id"], "period": r["period"],
                     "district": r["district"], "sex": r["sex"], "rules_flag": cls.startswith("SAM") or cls == "MAM",
                     "age_band": "6-11 months" if age < 12 else ("12-23 months" if age < 24 else "24-59 months")})
    return kept, reasons


def split_by_time(kept):
    periods = sorted({k["period"] for k in kept})
    if len(periods) < 4:
        raise SystemExit("need at least 4 distinct periods for a temporal split")
    test_p, val_p = set(periods[-2:]), {periods[-3]}
    first = {}
    for k in kept:
        first[k["child"]] = min(first.get(k["child"], k["period"]), k["period"])
    out = {"train": [], "val": [], "test": []}
    for k in kept:
        p = first[k["child"]]
        out["test" if p in test_p else "val" if p in val_p else "train"].append(k)
    return out, {"train": [p for p in periods if p not in test_p | val_p], "val": sorted(val_p), "test": sorted(test_p)}


# ---------------------------------------------------------------- candidates
def fit_candidate(name, X, y, seed):
    """Return (kind, model_dict, predict_one(x) -> raw probability, library_probs(X) or None)."""
    if name == "lr":
        m = LogisticModel(RISK_FEATURES).fit(X, y, seed=seed, epochs=15, lr=0.05, l2=1e-4)
        return "logistic", m.to_dict(), m.predict_proba, None
    import numpy as np
    from thanzi_screen.ml.risk import export
    Xa, ya = np.array(X), np.array(y)
    if name == "rf":
        from sklearn.ensemble import RandomForestClassifier
        lib = RandomForestClassifier(n_estimators=60, max_depth=5, min_samples_leaf=50, random_state=seed, n_jobs=1).fit(Xa, ya)
        ens = export.from_sklearn_forest(lib, list(RISK_FEATURES))
        return "rf_prob", ens.to_dict(), ens.probability, lambda Z: lib.predict_proba(np.array(Z))[:, 1]
    import xgboost as xgb
    mono = tuple(MONOTONE.get(n, 0) for n in RISK_FEATURES)
    lib = xgb.XGBClassifier(n_estimators=150, max_depth=3, learning_rate=0.08, subsample=0.8, min_child_weight=20,
                            monotone_constraints=mono, tree_method="hist", random_state=seed, n_jobs=1).fit(Xa, ya)
    ens = export.from_xgboost(lib.get_booster(), list(RISK_FEATURES), list(X[0]))
    return "gbm_logit", ens.to_dict(), ens.probability, lambda Z: lib.predict_proba(np.array(Z))[:, 1]


def available(name):
    try:
        if name == "rf":
            import sklearn  # noqa: F401
        elif name == "xgb":
            import xgboost  # noqa: F401
        return True
    except ImportError:
        return False


def vec(rows):
    return [r["x"] for r in rows], [r["y"] for r in rows]


def calibrate(raw_val, y_val):
    a, b = ev.fit_platt(raw_val, y_val)
    return (a, b) if a > 0 else (1.0, 0.0)


def apply_cal(raw, a, b):
    from thanzi_screen.ml.risk.trees import logit, sigmoid
    return [sigmoid(a * logit(p) + b) for p in raw]


# ---------------------------------------------------------------- reporting
def pct(v, d=1):
    return "n/a" if v != v else f"{100 * v:.{d}f}%"


def num(v, d=3):
    return "n/a" if v != v else f"{v:.{d}f}"


def ci(pair, d=3):
    return f"{pair[0]:.{d}f} to {pair[1]:.{d}f}"


def md_table(header, rows):
    return "\n".join(["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(ROOT / "data" / "synthetic" / "risk" / "risk_dataset.csv"))
    ap.add_argument("--out", default=str(ROOT / "models" / "risk_sim"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--alert-rate", type=float, default=0.10, help="target share of scored children flagged (default 0.10)")
    ap.add_argument("--candidates", default="lr,rf,xgb")
    ap.add_argument("--allow-simulated", action="store_true", help="required to train on a simulated dataset (non-clinical model)")
    ap.add_argument("--lodo", action="store_true", help="also run leave-one-district-out validation")
    ap.add_argument("--version", default=None)
    ap.add_argument("--clinical-signoff", default="", help="reference to the clinical sign-off (real data only)")
    ap.add_argument("--min-auroc-lower", type=float, default=None, help="acceptance: lower 95%% bound of test AUROC")
    ap.add_argument("--min-sensitivity", type=float, default=None, help="acceptance: sensitivity at the alert threshold")
    ap.add_argument("--slope-range", type=float, nargs=2, default=None, metavar=("LOW", "HIGH"), help="acceptance: test calibration slope")
    args = ap.parse_args()

    try:
        rows, manifest = load_dataset(args.data, allow_simulated=args.allow_simulated)
    except RiskModelError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    simulated = manifest["provenance"] == "simulated"
    target = manifest["target"]
    kept, reasons = build_matrix(rows)
    split, periods = split_by_time(kept)
    print(f"{len(rows)} rows, {len(kept)} scoreable ({pct(len(kept) / len(rows))}); not scored: {dict(reasons)}")
    print({k: (len(v), sum(r['y'] for r in v)) for k, v in split.items()}, "(rows, events)")
    Xtr, ytr = vec(split["train"])
    Xva, yva = vec(split["val"])
    Xte, yte = vec(split["test"])
    for name, (_, yy) in (("training", (None, ytr)), ("validation", (None, yva)), ("test", (None, yte))):
        if sum(yy) < 30:
            raise SystemExit(f"too few events in {name} ({sum(yy)}): not enough to train or validate")

    # 3. fit and calibrate every candidate
    wanted = [c for c in args.candidates.split(",") if c in CANDIDATES]
    if "lr" not in wanted:
        wanted.insert(0, "lr")
    fitted, skipped = {}, []
    for name in wanted:
        if not available(name):
            skipped.append(name)
            print(f"skipping {name}: library not installed")
            continue
        kind, mdict, predict, lib = fit_candidate(name, Xtr, ytr, args.seed)
        if lib is not None:       # parity: what ships must match the library
            sample = Xte[:2000] + Xva[:500]
            diff = max(abs(predict(x) - p) for x, p in zip(sample, lib(sample)))
            if diff > PARITY_TOLERANCE:
                raise SystemExit(f"{name}: exported model differs from the library by {diff:.2e}. Not shipping.")
        else:
            diff = 0.0
        raw_va = [predict(x) for x in Xva]
        a, b = calibrate(raw_va, yva)
        fitted[name] = {"kind": kind, "model": mdict, "predict": predict, "parity": diff, "a": a, "b": b,
                        "val": apply_cal(raw_va, a, b), "test_raw": [predict(x) for x in Xte]}
        print(f"{name}: validation AUROC {ev.auroc(fitted[name]['val'], yva):.4f}, parity diff {diff:.1e}")

    # 4. selection on validation data
    base = fitted["lr"]
    table, accepted = [], []
    for name, c in fitted.items():
        if name == "lr":
            table.append((name, ev.auroc(c["val"], yva), None, "baseline"))
            continue
        d, lo, hi = ev.paired_auc_diff_ci(c["val"], base["val"], yva, seed=args.seed)
        ok = d >= MIN_GAIN and lo > 0
        table.append((name, ev.auroc(c["val"], yva), (d, lo, hi), "accepted" if ok else "not accepted (gain too small or interval includes zero)"))
        if ok:
            accepted.append((d, name))
    chosen = max(accepted)[1] if accepted else "lr"
    C = fitted[chosen]
    print("selected:", chosen)

    # 5. operating point on validation data
    threshold = ev.threshold_for_alert_rate(C["val"], args.alert_rate)
    threshold = min(max(threshold, 1e-6), 1 - 1e-6)

    # 6. test set, opened once
    pte = apply_cal(C["test_raw"], C["a"], C["b"])
    auc_ci = ev.bootstrap_ci(ev.auroc, pte, yte, seed=args.seed)
    cal_a, cal_b = ev.fit_platt(pte, yte)
    op = ev.at_threshold(pte, yte, threshold)
    sens_ci = ev.bootstrap_ci(lambda p, y: ev.at_threshold(p, y, threshold)["sensitivity"], pte, yte, seed=args.seed)
    prev = sum(yte) / len(yte)
    rules_flag = [r["rules_flag"] for r in split["test"]]
    model_flag = [p >= threshold for p in pte]
    events = sum(yte)
    rules_tp = sum(1 for f, y in zip(rules_flag, yte) if f and y)
    union = [a or b for a, b in zip(rules_flag, model_flag)]
    union_tp = sum(1 for f, y in zip(union, yte) if f and y)
    missed_by_rules = sum(1 for f, y in zip(rules_flag, yte) if y and not f)
    caught_extra = sum(1 for f, m, y in zip(rules_flag, model_flag, yte) if y and not f and m)
    nb = [(pt, ev.net_benefit(pte, yte, pt), prev - (1 - prev) * pt / (1 - pt)) for pt in (0.05, 0.10, 0.20)]
    cal_rows = ev.calibration_table(pte, yte)

    acc_set = any(v is not None for v in (args.min_auroc_lower, args.min_sensitivity, args.slope_range))
    checks = []
    if args.min_auroc_lower is not None:
        checks.append(("AUROC lower bound >= %.3f" % args.min_auroc_lower, auc_ci[0] >= args.min_auroc_lower))
    if args.min_sensitivity is not None:
        checks.append(("Sensitivity at threshold >= %.3f" % args.min_sensitivity, op["sensitivity"] >= args.min_sensitivity))
    if args.slope_range is not None:
        checks.append(("Calibration slope in [%.2f, %.2f]" % tuple(args.slope_range), args.slope_range[0] <= cal_a <= args.slope_range[1]))
    passed = (all(ok for _, ok in checks) if checks else None)

    subgroup_md = []
    for label, key in (("Sex", "sex"), ("Age band", "age_band"), ("District", "district"), ("Period", "period")):
        sub = ev.subgroup_table([r[key] for r in split["test"]], pte, yte, threshold)
        subgroup_md.append(f"**{label}**\n\n" + md_table(["Group", "n", "Events", "AUROC", "Sensitivity", "PPV", "Alert rate", "Note"],
                           [(s["group"], s["n"], s["events"], num(s["auroc"]), pct(s["sensitivity"]), pct(s["ppv"]), pct(s["alert_rate"]),
                             "small group, unreliable" if s["small"] else "") for s in sub]))

    lodo_md = ""
    if args.lodo:
        pool = split["train"] + split["val"] + split["test"]
        by_d = defaultdict(list)
        for r in pool:
            by_d[r["district"]].append(r)
        res = []
        for d in sorted(by_d):
            held = by_d[d]
            rest = [r for r in pool if r["district"] != d]
            if len(held) < 200 or sum(r["y"] for r in held) < 20:
                continue
            Xr, yr = vec(rest)
            _, _, pred, _ = fit_candidate(chosen, Xr, yr, args.seed)
            res.append((d, len(held), sum(r["y"] for r in held), ev.auroc([pred(r["x"]) for r in held], [r["y"] for r in held])))
        if res:
            aucs = sorted(r[3] for r in res)
            lodo_md = ("## Leave-one-district-out (external validity)\n\nRetrained without each district, scored on that district. "
                       f"Districts with at least 200 scoreable children and 20 events. Median AUROC {num(aucs[len(aucs) // 2])}, "
                       f"range {num(aucs[0])} to {num(aucs[-1])}.\n\n" + md_table(["District", "n", "Events", "AUROC"], [(d, n, e, num(a)) for d, n, e, a in res]) + "\n")

    version = args.version or ("risk-sim-0.1.0" if simulated else "risk-0.1.0")
    spec = {
        "schema": SCHEMA, "version": version, "kind": C["kind"], "provenance": manifest["provenance"],
        "clinical_use": bool(not simulated and args.clinical_signoff and passed),
        "target": {k: target[k] for k in ("name", "plain", "horizon_weeks", "definition")},
        "calibration": {"a": C["a"], "b": C["b"]}, "threshold": threshold,
        "eligibility": {"age_months_min": AGE_RANGE[0], "age_months_max": AGE_RANGE[1]},
        "model": C["model"], "dataset_sha256": manifest["sha256"], "seed": args.seed, "alert_rate_target": args.alert_rate,
        "metrics": {"test_auroc": round(ev.auroc(pte, yte), 4), "test_sensitivity": round(op["sensitivity"], 4),
                    "test_alert_rate": round(op["alert_rate"], 4), "calibration_slope": round(cal_a, 3)},
        "acceptance": {"set": acc_set, "passed": passed, "checks": [{"check": c, "passed": ok} for c, ok in checks]},
    }
    if not simulated:
        spec["governance"] = {"ethics_ref": manifest["ethics_ref"], "data_agreement_ref": manifest["data_agreement_ref"],
                              "clinical_signoff": args.clinical_signoff}
    model = RiskModel(spec)          # the file must load, or it is not written
    # explanation must add up exactly, on rows the model never saw
    worst = 0.0
    for x in Xte[:30]:
        base_v, parts, _ = model.contributions(x)
        raw = model.model.predict_proba(x) if model.kind == "logistic" else model.model.raw_output(x)
        if model.kind == "logistic":
            from thanzi_screen.ml.risk.trees import logit
            raw = logit(raw)
        worst = max(worst, abs(base_v + sum(parts) - raw))
    if worst > 1e-6:
        raise SystemExit(f"explanation does not add up (error {worst:.2e}). Not shipping.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MODEL_FILE).write_text(json.dumps(spec, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")

    banner = ("**SIMULATED OUTCOMES. NOT CLINICAL. Trained on an assumed formula, so these numbers only show the code works. "
              "They say nothing about real children. The service refuses this model unless simulated models are explicitly allowed.**"
              if simulated else "**Trained on real data. Advisory only. Not a diagnostic device. Clinical sign-off: "
              + (args.clinical_signoff or "NOT GIVEN") + "**")
    cand_md = md_table(["Candidate", "Validation AUROC", "Gain over logistic (95% interval)", "Decision"],
                       [(n, num(a), "" if g is None else f"{g[0]:+.3f} ({ci(g[1:])})", d) for n, a, g, d in table])
    card = f"""# Model card: advisory clinical risk model

{banner}

Version {version}. Kind `{C['kind']}`. Target: {target['name']} within {target['horizon_weeks']} weeks. Definition: {target['definition']}
Dataset SHA-256 `{manifest['sha256'][:16]}...`, {len(rows)} rows, seed {args.seed}. Same dataset and seed give identical files.

## What it does
Estimates the chance of the target outcome for children aged 6 to 59 months. It can only add a concern ("closer follow-up
suggested"). It never changes a classification, tier, referral or warning, never says a child is low risk, and is not run when
a recording error is suspected, MUAC is missing, or the child is outside the age range. Not run for preterm or corrected-age babies.

## Data and split
Scoreable: {len(kept)} of {len(rows)} ({pct(len(kept) / len(rows))}). Not scored: {dict(reasons)}.
Temporal split, a child stays in one split. Train {periods['train']} ({len(split['train'])} rows, {sum(ytr)} events),
validation {periods['val']} ({len(split['val'])}, {sum(yva)}), test {periods['test']} ({len(split['test'])}, {sum(yte)}).
Test prevalence {pct(prev)}.

## Model selection (validation set)
{cand_md}

Libraries not installed, skipped: {skipped or 'none'}. Exported models match the library (largest difference per candidate): {', '.join(f"{n} {c['parity']:.1e}" for n, c in fitted.items())}. Limit {PARITY_TOLERANCE:g}.
Tree models use monotone constraints: a lower z-score or MUAC never lowers the risk.

## Operating point
Threshold {threshold:.4f} on calibrated probability, chosen on validation data for an alert rate of at most {pct(args.alert_rate, 0)}.

## Test results (opened once)
- AUROC {num(ev.auroc(pte, yte))} (95% interval {ci(auc_ci)}). AUPRC {num(ev.auprc(pte, yte))} (prevalence {num(prev)}). Brier {num(ev.brier(pte, yte))}.
- Calibration slope {num(cal_a, 2)} (ideal 1), intercept {num(cal_b, 2)} (ideal 0).
- At the threshold: alert rate {pct(op['alert_rate'])}, sensitivity {pct(op['sensitivity'])} (95% interval {ci(sens_ci)}), PPV {pct(op['ppv'])}, specificity {pct(op['specificity'])}.
- Rules alone (SAM or MAM): sensitivity {pct(rules_tp / events)}, alert rate {pct(sum(rules_flag) / len(rules_flag))}.
- Rules or model: sensitivity {pct(union_tp / events)}, alert rate {pct(sum(union) / len(union))}.
- Events the rules did not flag: {missed_by_rules}. The model flagged {caught_extra} of them ({pct(caught_extra / missed_by_rules if missed_by_rules else float('nan'))}).

Decision curve (net benefit; flag-everyone shown for comparison):

{md_table(['Threshold probability', 'Model', 'Flag everyone'], [(f"{pt:.2f}", f"{m:.4f}", f"{t:.4f}") for pt, m, t in nb])}

Calibration by decile of predicted risk:

{md_table(['Decile', 'n', 'Mean predicted', 'Observed'], [(r['bin'], r['n'], num(r['mean_predicted']), num(r['observed_rate'])) for r in cal_rows])}

## Subgroups (test set, at the threshold)
{chr(10).join(x + chr(10) for x in subgroup_md)}

{lodo_md}
## Acceptance
{'Thresholds set in advance:' if acc_set else 'Acceptance thresholds NOT SET. They must be agreed with clinical reviewers before the test set is opened.'}
{chr(10).join(f"- {c}: {'PASS' if ok else 'FAIL'}" for c, ok in checks)}

## Limits
- {'Outcomes are simulated from an assumed formula. Performance here is not evidence of anything clinical.' if simulated else 'Performance applies to the population, facilities and period in the training data.'}
- Advisory only. A trained health worker decides. Retraining or any change needs revalidation and clinical sign-off.
- Fairness is only as good as the subgroup sizes above. Small groups are marked.
"""
    (out / "RISK_MODEL_CARD.md").write_text(card, encoding="utf-8")
    print(f"wrote {out / MODEL_FILE} and RISK_MODEL_CARD.md ({C['kind']}, version {version}, threshold {threshold:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
