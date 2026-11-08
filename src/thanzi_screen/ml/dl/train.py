"""Train the deep models from a verified Phase 3 dataset. Deterministic for a given dataset, seed and settings.
Same data, same splits, same operating-point rule and same report as Phase 4, so the numbers compare directly."""
from __future__ import annotations

import json
from pathlib import Path

from ... import data as _data
from .. import evaluate as ev
from ..features import FEATURES, FIELDS
from ..train import A_FILE, _dump, _pct, _records
from .network import PRESETS, Network
from .predict import ERROR_FILE, FIELD_FILE

DL_VERSION = "0.1.0"
CARD_FILE = "DL_MODEL_CARD.md"
STATEMENT = ("Demonstration deep models trained on synthetic data only. Not validated on real children. "
             "Not for clinical deployment. Advisory flags only: they never change a clinical classification.")


def _history(net: Network) -> dict:
    h = net.history
    return {"epochs_run": len(h), "best_epoch": net.best_epoch,
            "first_val_loss": h[0].get("val_loss"), "best_val_loss": min((r["val_loss"] for r in h if "val_loss" in r), default=None),
            "final_train_loss": h[-1]["train_loss"]}


def _baseline(directory, sha):
    """Phase 4 logistic test metrics, only when trained on this very dataset."""
    if directory is None:
        return None
    path = Path(directory) / A_FILE
    if not path.exists():
        return None
    obj = json.loads(path.read_text())
    if obj["metadata"]["trained_on_manifest_sha256"] != sha:
        return None
    return obj["metrics"]["test"]


def train_deep(csv_path, out_dir, seed: int = 0, epochs: int = 40, preset: str = "small", field_hidden=(16,),
               lr: float = 0.003, dropout: float = 0.0, patience: int = 6, baseline_dir=None) -> dict:
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {sorted(PRESETS)}")
    hidden = PRESETS[preset]
    csv_path, out = Path(csv_path), Path(out_dir)
    rows = _data.load_dataset(csv_path)          # refuses unverified or non-synthetic data
    manifest = json.loads(csv_path.with_name("MANIFEST.json").read_text())
    recs, skipped = _records(rows)
    by = {s: [r for r in recs if r["split"] == s] for s in ("train", "val", "test", "boundary")}

    # ---- A: recording error flag (binary network) ----
    tr, va = by["train"], by["val"]
    pos = sum(r["error"] for r in tr)
    pos_weight = max(1.0, (len(tr) - pos) / max(1, pos)) ** 0.5
    net = Network(FEATURES, hidden).fit(
        [r["x"] for r in tr], [int(r["error"]) for r in tr], [r["x"] for r in va], [int(r["error"]) for r in va],
        seed=seed, epochs=epochs, lr=lr, dropout=dropout, pos_weight=pos_weight, patience=patience)
    for s in by:
        for r in by[s]:
            r["prob"] = net.predict_proba(r["x"])
    op = ev.choose_threshold([r["prob"] for r in va], [r["error"] for r in va], [r["p1"] for r in va])
    for s in by:
        for r in by[s]:
            r["ml"] = r["prob"] >= op["threshold"]
    report = {s: ev.full_report(by[s]) for s in ("val", "test")}
    b_alerts = [r for r in by["boundary"] if r["ml"]]
    boundary = {"n": len(by["boundary"]), "ml_alerts": len(b_alerts),
                "alerts_with_exact_6_month_age": sum(r["age_heap"] for r in b_alerts),
                "note": "Boundary records have no injected errors; alerts here are false alarms."}

    # ---- field attribution (small multiclass network, error records only) ----
    err_tr, err_va = [r for r in tr if r["error"]], [r for r in va if r["error"]]
    fnet = Network(FEATURES, tuple(field_hidden), classes=FIELDS).fit(
        [r["x"] for r in err_tr], [r["field"] for r in err_tr], [r["x"] for r in err_va], [r["field"] for r in err_va],
        seed=seed + 1, epochs=epochs, lr=lr, dropout=dropout, patience=patience)
    err_te = [r for r in by["test"] if r["error"]]
    acc = sum(max(fnet.predict_dist(r["x"]).items(), key=lambda kv: kv[1])[0] == r["field"] for r in err_te) / max(1, len(err_te))
    field_metrics = {"test_accuracy_on_error_records": acc, "n_test_error_records": len(err_te), "train_error_records": len(err_tr)}

    meta = {"version": DL_VERSION, "seed": seed, "epochs_max": epochs, "learning_rate": lr, "dropout": dropout,
            "patience": patience, "preset": preset, "hidden": list(hidden), "field_hidden": list(field_hidden),
            "feature_names": list(FEATURES), "trained_on_manifest_sha256": manifest["sha256"],
            "dataset_rows": manifest["rows"], "rows_skipped_invalid_input": skipped,
            "validated_on_real_data": False, "statement": STATEMENT}
    out.mkdir(parents=True, exist_ok=True)
    _dump(out / ERROR_FILE, {"model": net.to_dict(), "production": False, "role": "recording_error_flag_deep",
                             "threshold": op["threshold"], "operating_point": op, "metrics": report,
                             "boundary_stress_test": boundary, "training": _history(net), "metadata": meta})
    _dump(out / FIELD_FILE, {"model": fnet.to_dict(), "production": False, "role": "suggested_field_to_recheck_deep",
                             "metrics": field_metrics, "training": _history(fnet), "metadata": meta})
    summary = {"operating_point": op, "test": report["test"], "field": field_metrics, "boundary": boundary,
               "parameters": {"error": net.params, "field": fnet.params},
               "training": {"error": _history(net), "field": _history(fnet)},
               "baseline_test": _baseline(baseline_dir, manifest["sha256"])}
    (out / CARD_FILE).write_text(_card(summary, meta), encoding="utf-8")
    return summary


def _card(s: dict, meta: dict) -> str:
    t, op, tr = s["test"], s["operating_point"], s["training"]
    lines = [
        "# Model card: deep learning advisory flags", "", f"**{STATEMENT}**", "",
        f"Version {meta['version']}. Trained on synthetic dataset SHA-256 `{meta['trained_on_manifest_sha256'][:16]}...` "
        f"({meta['dataset_rows']} rows), seed {meta['seed']}. Plain-Python networks saved as JSON. "
        "Not wired into the API: `production` is false in both files until Edison decides.", "",
        "## Models",
        f"- `{ERROR_FILE}`: dense network {len(FEATURES)}-{'-'.join(map(str, meta['hidden']))}-1 ({s['parameters']['error']} parameters), "
        "ReLU, sigmoid output, flags a possible recording error (target A).",
        f"- `{FIELD_FILE}`: dense network {len(FEATURES)}-{'-'.join(map(str, meta['field_hidden']))}-{len(FIELDS)} "
        f"({s['parameters']['field']} parameters), softmax output, suggests which field to recheck.", "",
        "## Training",
        f"Adam, learning rate {meta['learning_rate']}, dropout {meta['dropout']}, up to {meta['epochs_max']} epochs, early stopping on validation loss "
        f"(patience {meta['patience']}). Error flag: {tr['error']['epochs_run']} epochs run, best epoch {tr['error']['best_epoch']}. "
        f"Field model: {tr['field']['epochs_run']} epochs run, best epoch {tr['field']['best_epoch']}.", "",
        "## Operating point (chosen on validation, same rule as Phase 4)",
        f"Threshold {op['threshold']:.4f}. Target: at least 80% recall on errors Phase 1 flags miss, at most 10% of records flagged. "
        f"Met on validation: **{op['operating_point_met']}**.", "",
        "## Test results (synthetic data)",
        f"- Deep flag: precision {_pct(t['ml']['precision'])}, recall {_pct(t['ml']['recall'])}, alert rate {_pct(t['ml']['alert_rate'])}, AUC {t['auc']:.3f}.",
        f"- Phase 1 flags alone: precision {_pct(t['phase1_only']['precision'])}, recall {_pct(t['phase1_only']['recall'])}.",
        f"- Phase 1 or deep flag: recall {_pct(t['union']['recall'])}, alert rate {_pct(t['union']['alert_rate'])}.",
        f"- Recall on errors Phase 1 misses ({t['errors_missed_by_phase1']} records): {_pct(t['ml_recall_on_missed_by_phase1'])}.",
        f"- Field suggestion accuracy on error records: {_pct(s['field']['test_accuracy_on_error_records'])}.",
        f"- Boundary stress test: {s['boundary']['ml_alerts']} false alarms in {s['boundary']['n']} records; "
        f"{s['boundary']['alerts_with_exact_6_month_age']} of them have an age that is an exact 6-month multiple.",
    ]
    b = s["baseline_test"]
    if b:
        lines += ["", "## Against the Phase 4 logistic model (same dataset, same test split)",
                  f"- Logistic: precision {_pct(b['ml']['precision'])}, recall {_pct(b['ml']['recall'])}, alert rate {_pct(b['ml']['alert_rate'])}, AUC {b['auc']:.3f}, "
                  f"recall on errors Phase 1 misses {_pct(b['ml_recall_on_missed_by_phase1'])}.",
                  f"- Deep: precision {_pct(t['ml']['precision'])}, recall {_pct(t['ml']['recall'])}, alert rate {_pct(t['ml']['alert_rate'])}, AUC {t['auc']:.3f}, "
                  f"recall on errors Phase 1 misses {_pct(t['ml_recall_on_missed_by_phase1'])}."]
    else:
        lines += ["", "## Against the Phase 4 logistic model", "Not compared in this run (no Phase 4 models trained on this dataset were given)."]
    lines += ["", "## Recall by error type (test)"]
    for k, v in t["by_error_type"].items():
        lines.append(f"- {k}: deep {_pct(v['ml_recall'])}, Phase 1 {_pct(v['phase1_recall'])}, either {_pct(v['union_recall'])} (n={v['n']}).")
    lines += ["", "## Limits",
              "- Same synthetic data and assumed error types as Phase 4 (D41). Real recording errors are messier, so these numbers say little about real use.",
              "- The synthetic task is nearly linearly separable, so a deeper network has little to gain here. Any gap to the logistic model on this data is not evidence about real data.",
              "- Age heaping is caught only because the synthetic injection rounds ages exactly (D54, I16). The same artefact applies here.",
              "- Fairness cannot be tested without real data (I15). Neural networks are harder to audit than the logistic model; `top_signals` is an occlusion check, not a full explanation.",
              "- Retrain when real prevalence figures (R9) and WHO MUAC tables (R8) are used in Phase 3.", ""]
    return "\n".join(lines)
