"""Metrics, operating point, baselines and subgroup reports. All plain Python."""
from __future__ import annotations

from collections import defaultdict

from .models import auc


def prf(pred: list[bool], truth: list[bool]) -> dict:
    tp = sum(p and t for p, t in zip(pred, truth))
    fp = sum(p and not t for p, t in zip(pred, truth))
    fn = sum((not p) and t for p, t in zip(pred, truth))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    return {"precision": prec, "recall": rec, "f1": f1, "alert_rate": sum(pred) / len(pred) if pred else None,
            "n": len(pred), "positives": sum(truth)}


def choose_threshold(probs, error, p1, max_alert=0.10, min_recall_missed=0.80):
    """Among thresholds with alert rate <= max_alert, maximise recall on errors Phase 1 misses."""
    n = len(probs)
    missed = [p for p, e, q in zip(probs, error, p1) if e and not q]
    cands = sorted(set(probs))
    step = max(1, len(cands) // 400)
    best = None
    for t in cands[::step] + [1.0 + 1e-9]:
        alert = sum(p >= t for p in probs) / n
        if alert > max_alert:
            continue
        rec = sum(p >= t for p in missed) / len(missed) if missed else 0.0
        key = (rec, t)
        if best is None or key > best[0]:
            best = (key, t, alert, rec)
    if best is None:
        return {"threshold": 1.0, "alert_rate": 0.0, "recall_on_missed": 0.0, "operating_point_met": False}
    _, t, alert, rec = best
    return {"threshold": t, "alert_rate": alert, "recall_on_missed": rec, "operating_point_met": rec >= min_recall_missed}


def calibration(probs, labels, bins=10):
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if idx:
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": len(idx), "mean_probability": sum(probs[i] for i in idx) / len(idx),
                        "observed_rate": sum(labels[i] for i in idx) / len(idx)})
    return out


def age_band(age_months: float) -> str:
    return "0-5m" if age_months < 6 else ("6-23m" if age_months < 24 else "24-59m")


def subgroup_report(records: list[dict], key: str, min_n=200) -> dict:
    groups = defaultdict(list)
    for r in records:
        groups[r[key]].append(r)
    out = {}
    for g, rs in sorted(groups.items()):
        m = prf([r["ml"] for r in rs], [r["error"] for r in rs])
        m["note"] = "small group, interpret with care" if len(rs) < min_n else ""
        out[g] = m
    recalls = [m["recall"] for m in out.values() if m["recall"] is not None and m["positives"] >= 5]
    out["_max_recall_gap"] = (max(recalls) - min(recalls)) if len(recalls) >= 2 else None
    return out


def error_type_recall(records: list[dict]) -> dict:
    out = {}
    for t in sorted({r["error_type"] for r in records if r["error"]}):
        rs = [r for r in records if r["error_type"] == t]
        out[t] = {"n": len(rs), "ml_recall": sum(r["ml"] for r in rs) / len(rs),
                  "phase1_recall": sum(r["p1"] for r in rs) / len(rs),
                  "union_recall": sum(r["ml"] or r["p1"] for r in rs) / len(rs)}
    return out


def full_report(records: list[dict]) -> dict:
    probs = [r["prob"] for r in records]
    err = [r["error"] for r in records]
    missed = [r for r in records if r["error"] and not r["p1"]]
    return {
        "n": len(records), "errors": sum(err), "auc": auc(probs, err),
        "ml": prf([r["ml"] for r in records], err),
        "phase1_only": prf([r["p1"] for r in records], err),
        "union": prf([r["ml"] or r["p1"] for r in records], err),
        "errors_missed_by_phase1": len(missed),
        "ml_recall_on_missed_by_phase1": (sum(r["ml"] for r in missed) / len(missed)) if missed else None,
        "by_error_type": error_type_recall(records),
        "by_sex": subgroup_report(records, "sex"),
        "by_age_band": subgroup_report(records, "age_band"),
        "by_district": subgroup_report(records, "district"),
        "calibration": calibration(probs, [float(e) for e in err]),
    }
