"""Model comparison and calibration, one target at a time. Standard library plus the candidates (see candidates.py).

Order of work, fixed in advance so the test split is opened once and cannot steer any choice:

  1. Rows are labelled and split by child (Phase 2). The preprocessor is fitted on TRAINING rows only.
  2. Each candidate is fitted on training rows. Rows with a gap never seen in training are counted, not imputed.
  3. Platt calibration is fitted on VALIDATION rows (positive slope only, so the order of risks is kept).
  4. Selection: logistic regression is the reference. A challenger replaces it only if its validation AUROC gain is at least
     `min_gain` AND the paired child-level bootstrap interval of the gain excludes zero. Otherwise the simpler model stays.
  5. Alert thresholds are chosen on validation rows for target alert rates.
  6. Test rows are used once, to report: AUROC, AUPRC, Brier with child-level intervals, calibration before and after Platt,
     paired differences against logistic regression and against the baseline, operating points, net benefit, subgroups.

`fit_stage` never receives test rows. `test_stage` never changes a choice. A target with too few events in any split is
reported as not trained, never fitted on a handful of cases.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import candidates as cand
from . import evaluate as ev
from .assemble import Example, label_summary, matrix, select
from .preprocess import Preprocessor
from .targets import TARGETS

REFERENCE = "lr"


@dataclass(frozen=True)
class CompareConfig:
    seed: int = 0
    n_boot: int = 300
    alert_rates: tuple = (0.10, 0.20)
    min_events: int = 30            # in each of train, validation and test
    min_gain: float = 0.01          # validation AUROC gain a challenger needs over logistic regression
    candidates: tuple = cand.CANDIDATES
    min_subgroup_n: int = 50
    min_subgroup_events: int = 20


@dataclass
class Prepared:
    target: str
    pre: Preprocessor
    X: dict = field(default_factory=dict)
    y: dict = field(default_factory=dict)
    rows: dict = field(default_factory=dict)
    skipped: dict = field(default_factory=dict)


def _clean(v):
    """JSON-safe: NaN and infinity become None."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def split_counts(examples: list[Example], target: str) -> dict:
    out = {}
    for s in ("train", "val", "test"):
        rows = select(examples, target, s)
        out[s] = {"rows": len(rows), "events": sum(e.labels[target] for e in rows),
                  "children": len({e.child_id for e in rows})}
    return out


def prepare(examples: list[Example], target: str) -> Prepared:
    train = select(examples, target, "train")
    pre = Preprocessor.fit([e.features for e in train])
    prep = Prepared(target, pre)
    for s in ("train", "val", "test"):
        skipped: list = []
        prep.X[s], prep.y[s], prep.rows[s] = matrix(examples, target, s, pre, skipped)
        prep.skipped[s] = len(skipped)
    return prep


def choose_model(val_scores: dict, y_val, groups_val, cfg: CompareConfig) -> dict:
    """Pre-set rule. `val_scores` maps candidate name to validation probabilities. Returns the decision and its evidence."""
    base = val_scores[REFERENCE]
    rs = ev.resamples(groups_val, cfg.n_boot, cfg.seed)
    base_auc = ev.auroc(base, y_val)
    out = {"reference": REFERENCE, "reference_val_auroc": base_auc, "min_gain": cfg.min_gain, "challengers": {}}
    best, best_gain = None, 0.0
    for name, p in val_scores.items():
        if name == REFERENCE:
            continue
        d, lo, hi = ev.paired_diff_ci(ev.auroc, p, base, y_val, rs)
        passes = d >= cfg.min_gain and lo > 0
        out["challengers"][name] = {"val_auroc": ev.auroc(p, y_val), "gain": d, "gain_ci": [lo, hi], "passes": passes}
        if passes and d > best_gain:
            best, best_gain = name, d
    out["selected"] = best or REFERENCE
    out["reason"] = (f"{best} beat logistic regression by {best_gain:.3f} AUROC on validation with an interval above zero"
                     if best else "no challenger cleared the pre-set gain and interval rule, so the simpler model is kept")
    return out


def fit_stage(prep: Prepared, cfg: CompareConfig) -> dict:
    """Everything that depends on training and validation rows only. Does not touch test rows."""
    columns = prep.pre.columns
    models = {}
    for name in cfg.candidates:
        if cand.available(name):
            models[name] = cand.fit_candidate(name, prep.X["train"], prep.y["train"], columns, cfg.seed)
    if REFERENCE not in models:
        raise cand.MissingLibraryError("logistic regression (scikit-learn) is required as the reference model")
    models["baseline"] = cand.fit_baseline(prep.X["train"], prep.y["train"], columns)
    y_val = prep.y["val"]
    raw_val = {n: m.predict_proba(prep.X["val"]) for n, m in models.items()}
    platt, cal_val = {}, {}
    for n, raw in raw_val.items():
        a, b = ev.fit_platt(raw, y_val)
        platt[n] = (a, b) if a > 0 else (1.0, 0.0)           # a non-positive slope would reverse the order: refuse
        cal_val[n] = ev.apply_platt(raw, *platt[n])
    groups_val = [e.child_id for e in prep.rows["val"]]
    selection = choose_model({n: raw_val[n] for n in models if n != "baseline"}, y_val, groups_val, cfg)
    thresholds = {rate: {n: ev.threshold_for_alert_rate(cal_val[n], rate) for n in models} for rate in cfg.alert_rates}
    return {"models": models, "platt": platt, "selection": selection, "thresholds": thresholds,
            "val_auroc": {n: ev.auroc(raw_val[n], y_val) for n in models}}


def _age_band(m: float) -> str:
    return "6-11 months" if m < 12 else "12-23 months" if m < 24 else "24-59 months"


def test_stage(prep: Prepared, state: dict, cfg: CompareConfig) -> dict:
    """The only place test rows are read. Reports; changes no choice."""
    models, platt = state["models"], state["platt"]
    y, rows = prep.y["test"], prep.rows["test"]
    groups = [e.child_id for e in rows]
    rs = ev.resamples(groups, cfg.n_boot, cfg.seed + 1)
    prevalence_train = sum(prep.y["train"]) / len(prep.y["train"])
    ref_brier = ev.brier([prevalence_train] * len(y), y)
    raw = {n: m.predict_proba(prep.X["test"]) for n, m in models.items()}
    cal = {n: ev.apply_platt(raw[n], *platt[n]) for n in models}
    res = {}
    for n in models:
        table = ev.calibration_table(cal[n], y)
        raw_a, raw_b = ev.fit_platt(raw[n], y)
        cal_a, cal_b = ev.fit_platt(cal[n], y)
        entry = {
            "auroc": ev.auroc(cal[n], y), "auroc_ci": ev.ci_from(ev.auroc, cal[n], y, rs),
            "auprc": ev.auprc(cal[n], y), "auprc_ci": ev.ci_from(ev.auprc, cal[n], y, rs),
            "brier": ev.brier(cal[n], y), "brier_ci": ev.ci_from(ev.brier, cal[n], y, rs),
            "brier_skill_vs_prevalence": 1 - ev.brier(cal[n], y) / ref_brier,
            "calibration_before": {"slope": raw_a, "intercept": raw_b, "brier": ev.brier(raw[n], y),
                                   "ece": ev.expected_calibration_error(ev.calibration_table(raw[n], y))},
            "calibration_after": {"slope": cal_a, "intercept": cal_b, "ece": ev.expected_calibration_error(table)},
            "platt": {"slope": platt[n][0], "intercept": platt[n][1]},
            "calibration_table": table, "operating_points": {}}
        for rate in cfg.alert_rates:
            t = state["thresholds"][rate][n]
            op = ev.at_threshold(cal[n], y, t)
            prev = sum(y) / len(y)
            op["net_benefit"] = ev.net_benefit(cal[n], y, min(max(t, 1e-6), 0.999))
            op["net_benefit_treat_all"] = prev - (1 - prev) * (t / (1 - t)) if 0 < t < 1 else float("nan")
            entry["operating_points"][str(rate)] = op
        if n != REFERENCE:
            d, lo, hi = ev.paired_diff_ci(ev.auroc, cal[n], cal[REFERENCE], y, rs)
            entry["auroc_diff_vs_lr"] = {"diff": d, "ci": [lo, hi]}
        if n != "baseline":
            d, lo, hi = ev.paired_diff_ci(ev.auroc, cal[n], cal["baseline"], y, rs)
            entry["auroc_diff_vs_baseline"] = {"diff": d, "ci": [lo, hi]}
        res[n] = entry
    sel = state["selection"]["selected"]
    rate = cfg.alert_rates[0]
    t = state["thresholds"][rate][sel]
    sub = {}
    for label, key in (("age_band", lambda e: _age_band(e.features["age_months"])),
                       ("sex", lambda e: "male" if e.features["sex_male"] == 1.0 else "female"),
                       ("district", lambda e: e.district or "unknown")):
        sub[label] = ev.subgroup_table([key(e) for e in rows], cal[sel], y, t, cfg.min_subgroup_n, cfg.min_subgroup_events)
    out = {"n": len(y), "events": sum(y), "prevalence": sum(y) / len(y), "models": res,
           "subgroups": {"model": sel, "alert_rate": rate, "tables": sub}}
    if len(cfg.alert_rates) >= 2:           # strata for the selected model: cut-offs fixed on validation, observed rates on test
        hi_rate, el_rate = sorted(cfg.alert_rates)[:2]
        cuts = {"high": state["thresholds"][hi_rate][sel], "elevated": state["thresholds"][el_rate][sel]}
        out["strata"] = {"model": sel, "alert_rates": {"high": hi_rate, "elevated": el_rate}, "cutoffs": cuts,
                         "table": ev.strata_table(cal[sel], y, cuts)}
    return out


def followup_balance(examples: list[Example], target: str,
                     features=("age_months", "whz", "muac_cm", "wealth_quintile", "food_insecure", "n_prior_visits")) -> dict:
    """Loss to follow-up is not random in real data. Compares index visits with a usable label against those lost
    (`no_followup_in_window`) on a few features. Large standardised differences mean the labelled rows are not a fair sample
    of the children the model is meant for. This is a warning light, not a correction."""
    kept = [e for e in examples if e.labels[target] is not None]
    lost = [e for e in examples if e.reasons[target] == "no_followup_in_window"]
    out = {"labelled": len(kept), "lost_to_followup": len(lost), "features": {}}
    for f in features:
        a = [e.features.get(f) for e in kept if e.features.get(f) is not None]
        b = [e.features.get(f) for e in lost if e.features.get(f) is not None]
        if len(a) < 2 or len(b) < 2:
            out["features"][f] = None
            continue
        ma, mb = sum(a) / len(a), sum(b) / len(b)
        va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
        vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
        pooled = math.sqrt((va + vb) / 2)
        out["features"][f] = {"mean_labelled": ma, "mean_lost": mb, "std_diff": (mb - ma) / pooled if pooled > 1e-12 else 0.0,
                              "missing_labelled": 1 - len(a) / len(kept), "missing_lost": 1 - len(b) / len(lost)}
    return out


def run_target_with_state(examples: list[Example], target: str, cfg: CompareConfig | None = None):
    """(result, prep, state). `prep` and `state` are None for a target that is not trained. The export step needs the fitted
    models, so it calls this instead of run_target; the test split is still read exactly once, inside test_stage."""
    cfg = cfg or CompareConfig()
    counts = split_counts(examples, target)
    out = {"target": target, "splits": counts, "followup_balance": followup_balance(examples, target)}
    short = [s for s, c in counts.items() if c["events"] < cfg.min_events]
    if short:
        out.update(status="not_trained", reason=f"fewer than {cfg.min_events} events in " + ", ".join(short)
                   + ": too few to train or to judge a model")
        return _clean(out), None, None
    prep = prepare(examples, target)
    state = fit_stage(prep, cfg)
    out.update(status="trained", skipped_unseen_missing=prep.skipped, n_columns=len(prep.pre.columns),
               train_prevalence=sum(prep.y["train"]) / len(prep.y["train"]),
               candidates=[n for n in state["models"]], params={n: m.params for n, m in state["models"].items()},
               selection=state["selection"], validation_auroc=state["val_auroc"],
               thresholds={str(r): t for r, t in state["thresholds"].items()},
               test=test_stage(prep, state, cfg))
    return _clean(out), prep, state


def run_target(examples: list[Example], target: str, cfg: CompareConfig | None = None) -> dict:
    return run_target_with_state(examples, target, cfg)[0]


def run_all(examples: list[Example], cfg: CompareConfig | None = None, targets=TARGETS) -> dict:
    cfg = cfg or CompareConfig()
    return {"config": {"seed": cfg.seed, "n_boot": cfg.n_boot, "alert_rates": list(cfg.alert_rates),
                       "min_events": cfg.min_events, "min_gain": cfg.min_gain},
            "label_summary": _clean(label_summary(examples)), "libraries": cand.versions(),
            "targets": {t: run_target(examples, t, cfg) for t in targets}}


# ---------------------------------------------------------------- plain-text report
def _f(v, d=3):
    return "n/a" if v is None else f"{v:.{d}f}"


def _ci(p, d=3):
    return "n/a" if not p or p[0] is None else f"{p[0]:.{d}f} to {p[1]:.{d}f}"


def render_report(results: dict, provenance: str = "simulated") -> str:
    lines = ["# Prediction models: comparison and calibration", ""]
    if provenance == "simulated":
        lines += ["**SIMULATED DATA. NON-CLINICAL.** Every association was assumed by the simulator. These numbers show that the "
                  "pipeline works and say nothing about how a model would perform on Malawian children.", ""]
    lines += ["No model here is approved for clinical use. Intervals are 95% child-level bootstraps. The best-single-feature row is the yardstick a model must beat.", ""]
    for t, r in results["targets"].items():
        lines += [f"## {t}", ""]
        s = r["splits"]
        lines.append("Rows (events): " + ", ".join(f"{k} {v['rows']} ({v['events']})" for k, v in s.items()))
        if r["status"] != "trained":
            lines += ["", f"**Not trained.** {r['reason']}", ""]
            continue
        sel = r["selection"]
        bl = r["params"]["baseline"]
        lines += ["", f"Selected: **{cand.LABELS[sel['selected']]}**. Reason: {sel['reason']}.",
                  f"Baseline feature (best on training rows): `{bl['feature']}`, {bl['direction']}.", "",
                  "| Model | AUROC (95% CI) | AUPRC | Brier | Slope before | Slope after | ECE after |", "|---|---|---|---|---|---|---|"]
        for n, m in r["test"]["models"].items():
            lines.append(f"| {cand.LABELS[n]} | {_f(m['auroc'])} ({_ci(m['auroc_ci'])}) | {_f(m['auprc'])} | {_f(m['brier'], 4)} | "
                         f"{_f(m['calibration_before']['slope'], 2)} | {_f(m['calibration_after']['slope'], 2)} | "
                         f"{_f(m['calibration_after']['ece'], 4)} |")
        lines += ["", f"Test prevalence {_f(r['test']['prevalence'], 4)}. Brier of always predicting the training prevalence is the "
                  "yardstick for the Brier column.", ""]
        for rate in r["test"]["models"][sel["selected"]]["operating_points"]:
            op = r["test"]["models"][sel["selected"]]["operating_points"][rate]
            lines.append(f"- Alert on {float(rate):.0%} of children (threshold fixed on validation): sensitivity {_f(op['sensitivity'], 2)}, "
                         f"PPV {_f(op['ppv'], 2)}, actual alert rate {_f(op['alert_rate'], 3)}.")
        fb = r["followup_balance"]
        lines += ["", f"Lost to follow-up: {fb['lost_to_followup']} index visits with no visit in the window, against "
                  f"{fb['labelled']} labelled. Largest standardised differences: " + ", ".join(
                      f"{k} {v['std_diff']:+.2f}" for k, v in sorted(((k, v) for k, v in fb["features"].items() if v),
                                                                       key=lambda kv: -abs(kv[1]["std_diff"]))[:3]) + ".", ""]
    return "\n".join(lines) + "\n"
