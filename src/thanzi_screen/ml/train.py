"""Train the Phase 4 models from a verified Phase 3 dataset. Deterministic for a given dataset and seed."""
from __future__ import annotations

import json
from pathlib import Path

from .. import data as _data
from ..anthro import InputError
from . import evaluate as ev
from .features import ERROR_TO_FIELD, FEATURES, FIELDS, features_from_inputs, row_inputs, vector
from .models import LogisticModel, TreeModel

VERSION = "0.4.0"
STATEMENT = ("Demonstration model trained on synthetic data only. Not validated on real children. "
             "Not for clinical deployment. Advisory flags only: it never changes a clinical classification.")
A_FILE, FIELD_FILE, B_FILE, CARD_FILE = ("recording_error_lr.json", "recording_field_tree.json",
                                         "review_replica_diagnostic.json", "MODEL_CARD.md")


def _records(rows):
    out, skipped = [], 0
    for r in rows:
        try:
            f, a, res = features_from_inputs(*row_inputs(r))
        except InputError:
            skipped += 1
            continue
        age_m = a.age_months
        out.append(dict(
            x=vector(f), p1=f["implaus_count"] > 0, error=r["injected_error"] != "none",
            error_type=r["injected_error"], field=ERROR_TO_FIELD.get(r["injected_error"]),
            review=r["review_needed"] == "true", age_heap=f["age_heap_exact"] == 1.0, sex=r["sex"], age_band=ev.age_band(age_m), district=r["district"],
            split=r["split"], cls=res.classification.value))
    return out, skipped


def _dump(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def train_all(csv_path, out_dir, seed: int = 0, epochs: int = 12) -> dict:
    csv_path, out = Path(csv_path), Path(out_dir)
    rows = _data.load_dataset(csv_path)          # refuses unverified or non-synthetic data
    manifest = json.loads(csv_path.with_name("MANIFEST.json").read_text())
    recs, skipped = _records(rows)
    by = {s: [r for r in recs if r["split"] == s] for s in ("train", "val", "test", "boundary")}

    # ---- A: recording error flag (logistic regression) ----
    tr = by["train"]
    pos = sum(r["error"] for r in tr)
    lr = LogisticModel(FEATURES).fit([r["x"] for r in tr], [int(r["error"]) for r in tr], seed=seed, epochs=epochs,
                                     pos_weight=max(1.0, (len(tr) - pos) / max(1, pos)) ** 0.5)
    for s in by:
        for r in by[s]:
            r["prob"] = lr.predict_proba(r["x"])
    op = ev.choose_threshold([r["prob"] for r in by["val"]], [r["error"] for r in by["val"]], [r["p1"] for r in by["val"]])
    for s in by:
        for r in by[s]:
            r["ml"] = r["prob"] >= op["threshold"]
    report = {s: ev.full_report(by[s]) for s in ("val", "test")}
    b_alerts = [r for r in by["boundary"] if r["ml"]]
    boundary = {"n": len(by["boundary"]), "ml_alerts": len(b_alerts),
                "alerts_with_exact_6_month_age": sum(r["age_heap"] for r in b_alerts),
                "note": "Boundary records have no injected errors; alerts here are false alarms."}

    # ---- field attribution (shallow tree, error records only) ----
    err_tr = [r for r in tr if r["error"]]
    tree = TreeModel(FEATURES, FIELDS).fit([r["x"] for r in err_tr], [r["field"] for r in err_tr])
    err_te = [r for r in by["test"] if r["error"]]
    acc = sum(max(tree.predict_dist(r["x"]).items(), key=lambda kv: kv[1])[0] == r["field"] for r in err_te) / max(1, len(err_te))
    field_metrics = {"test_accuracy_on_error_records": acc, "n_test_error_records": len(err_te), "train_error_records": len(err_tr)}

    # ---- B replica (diagnostic only; B is rules-based, D45) ----
    posb = sum(r["review"] for r in tr)
    rep = LogisticModel(FEATURES).fit([r["x"] for r in tr], [int(r["review"]) for r in tr], seed=seed + 1, epochs=epochs,
                                      pos_weight=max(1.0, (len(tr) - posb) / max(1, posb)) ** 0.5)
    te = by["test"]
    rep_pred = [rep.predict_proba(r["x"]) >= 0.5 for r in te]
    replica = ev.prf(rep_pred, [r["review"] for r in te])
    replica["note"] = "How well a model copies the rules-based review flag. Diagnostic only; not used in flags."

    base_meta = {"version": VERSION, "seed": seed, "epochs": epochs, "feature_names": list(FEATURES),
                 "trained_on_manifest_sha256": manifest["sha256"], "dataset_rows": manifest["rows"],
                 "rows_skipped_invalid_input": skipped, "validated_on_real_data": False, "statement": STATEMENT}
    out.mkdir(parents=True, exist_ok=True)
    _dump(out / A_FILE, {"model": lr.to_dict(), "production": True, "role": "recording_error_flag",
                         "threshold": op["threshold"], "operating_point": op, "metrics": report,
                         "boundary_stress_test": boundary, "metadata": base_meta})
    _dump(out / FIELD_FILE, {"model": tree.to_dict(), "production": True, "role": "suggested_field_to_recheck",
                             "metrics": field_metrics, "metadata": base_meta})
    _dump(out / B_FILE, {"model": rep.to_dict(), "production": False, "role": "diagnostic_replica_of_rules_review",
                         "metrics": replica, "metadata": base_meta})
    summary = {"operating_point": op, "test": report["test"], "field": field_metrics, "replica": replica, "boundary": boundary}
    (out / CARD_FILE).write_text(_card(summary, base_meta), encoding="utf-8")
    return summary


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _card(s: dict, meta: dict) -> str:
    t, op = s["test"], s["operating_point"]
    lines = [
        "# Model card: Phase 4 advisory flags", "", f"**{STATEMENT}**", "",
        f"Version {meta['version']}. Trained on synthetic dataset SHA-256 `{meta['trained_on_manifest_sha256'][:16]}...` "
        f"({meta['dataset_rows']} rows), seed {meta['seed']}. Plain-Python models saved as JSON.", "",
        "## Models",
        "- `recording_error_lr.json`: logistic regression, flags a possible recording error (target A).",
        "- `recording_field_tree.json`: shallow decision tree, suggests which field to recheck.",
        "- `review_replica_diagnostic.json`: NOT production. Target B is a rules-based flag (`thanzi_screen.rules.review`); this model only measures how well ML copies it.", "",
        "## Operating point (chosen on validation)",
        f"Threshold {op['threshold']:.4f}. Target: at least 80% recall on errors Phase 1 flags miss, at most 10% of records flagged. "
        f"Met on validation: **{op['operating_point_met']}**.", "",
        "## Test results (synthetic data)",
        f"- ML flag: precision {_pct(t['ml']['precision'])}, recall {_pct(t['ml']['recall'])}, alert rate {_pct(t['ml']['alert_rate'])}, AUC {t['auc']:.3f}.",
        f"- Phase 1 flags alone: precision {_pct(t['phase1_only']['precision'])}, recall {_pct(t['phase1_only']['recall'])}.",
        f"- Phase 1 or ML: recall {_pct(t['union']['recall'])}, alert rate {_pct(t['union']['alert_rate'])}.",
        f"- Recall on errors Phase 1 misses ({t['errors_missed_by_phase1']} records): {_pct(t['ml_recall_on_missed_by_phase1'])}.",
        f"- Field suggestion accuracy on error records: {_pct(s['field']['test_accuracy_on_error_records'])}.",
        f"- Boundary stress test: {s['boundary']['ml_alerts']} false alarms in {s['boundary']['n']} records; "
        f"{s['boundary']['alerts_with_exact_6_month_age']} of them have an age that is an exact 6-month multiple (the boundary set uses 365 days), which the model treats as age heaping. "
        "A child legitimately aged exactly 12 months would be flagged the same way.",
        f"- B replica agreement with the rules: precision {_pct(s['replica']['precision'])}, recall {_pct(s['replica']['recall'])}.", "",
        "## Recall by error type (test)",
    ]
    for k, v in t["by_error_type"].items():
        lines.append(f"- {k}: ML {_pct(v['ml_recall'])}, Phase 1 {_pct(v['phase1_recall'])}, either {_pct(v['union_recall'])} (n={v['n']}).")
    lines += ["", "## Limits",
              "- Error types and rates are assumptions (D41). Real recording errors are messier.",
              "- Age heaping is caught here only because the synthetic injection rounds ages exactly to 6-month multiples. Real heaping is fuzzy and is a population pattern, so this result will not transfer.",
              "- Synthetic districts carry no signal, so the district report checks the code, not real fairness. Fairness testing needs real data.",
              "- Retrain when real prevalence figures (R9) and WHO MUAC tables (R8) are used in Phase 3.", ""]
    return "\n".join(lines)
