"""Evaluation for the prediction module, standard library only so every number can be reproduced anywhere.

Discrimination (AUROC, AUPRC), probability accuracy (Brier), calibration (slope, intercept, deciles, expected calibration
error), operating points chosen on one set and applied to another, net benefit, and subgroup tables.

Intervals are CLUSTER bootstraps: children are resampled, not rows. A child contributes several index visits and those rows
are not independent, so a row bootstrap would give intervals that are too narrow.
"""
from __future__ import annotations

import math
import random

__all__ = ["auroc", "auprc", "brier", "logit", "sigmoid", "fit_platt", "apply_platt", "calibration_table",
           "expected_calibration_error", "threshold_for_alert_rate", "at_threshold", "net_benefit", "resamples", "ci_from",
           "paired_diff_ci", "subgroup_table"]

NAN = float("nan")
_EPS = 1e-6


def logit(p: float) -> float:
    p = min(max(p, _EPS), 1 - _EPS)
    return math.log(p / (1 - p))


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def auroc(scores, labels) -> float:
    """Area under the ROC curve from average ranks (ties count half). NaN if one class is missing."""
    n = len(labels)
    pos = sum(labels)
    neg = n - pos
    if pos == 0 or neg == 0:
        return NAN
    order = sorted(range(n), key=scores.__getitem__)
    rank_sum = 0.0
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        rank_sum += avg * sum(labels[order[k]] for k in range(i, j + 1))
        i = j + 1
    return (rank_sum - pos * (pos + 1) / 2.0) / (pos * neg)


def auprc(scores, labels) -> float:
    """Average precision (step-wise area under the precision-recall curve), ties handled as one step."""
    pos = sum(labels)
    if pos == 0:
        return NAN
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    tp, total, i, n = 0, 0.0, 0, len(order)
    while i < n:
        j = i
        while j < n and scores[order[j]] == scores[order[i]]:
            j += 1
        gained = sum(labels[order[k]] for k in range(i, j))
        tp += gained
        if gained:
            total += (gained / pos) * (tp / j)
        i = j
    return total


def brier(probs, labels) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels) if labels else NAN


def fit_platt(probs, labels, iters: int = 50) -> tuple[float, float]:
    """Logistic regression of the outcome on logit(p): (slope a, intercept b).

    Fitted on a validation set it is Platt scaling. Fitted on the calibrated probabilities of a test set it is the
    calibration slope and intercept (ideal: 1 and 0)."""
    z = [logit(p) for p in probs]
    a, b = 1.0, 0.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for zi, yi in zip(z, labels):
            p = sigmoid(a * zi + b)
            w, r = p * (1 - p), p - yi
            ga += r * zi
            gb += r
            haa += w * zi * zi
            hab += w * zi
            hbb += w
        haa += 1e-6
        hbb += 1e-6
        det = haa * hbb - hab * hab
        if abs(det) < 1e-12:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-9:
            break
    return a, b


def apply_platt(probs, a: float, b: float) -> list[float]:
    return [sigmoid(a * logit(p) + b) for p in probs]


def calibration_table(probs, labels, bins: int = 10) -> list[dict]:
    """Equal-count bins by predicted risk: mean predicted against observed rate."""
    order = sorted(range(len(probs)), key=probs.__getitem__)
    n = len(order)
    out = []
    for k in range(bins):
        idx = order[k * n // bins:(k + 1) * n // bins]
        if idx:
            out.append({"bin": k + 1, "n": len(idx), "mean_predicted": sum(probs[i] for i in idx) / len(idx),
                        "observed_rate": sum(labels[i] for i in idx) / len(idx)})
    return out


def expected_calibration_error(table: list[dict]) -> float:
    n = sum(r["n"] for r in table)
    return sum(r["n"] / n * abs(r["mean_predicted"] - r["observed_rate"]) for r in table) if n else NAN


def threshold_for_alert_rate(probs, rate: float) -> float:
    """Smallest threshold whose alert rate (share with p >= threshold) does not exceed `rate`."""
    s = sorted(probs, reverse=True)
    k = int(math.floor(rate * len(s)))
    if k <= 0:
        return s[0] + 1e-9
    cut = s[k - 1]
    if sum(1 for p in s if p >= cut) > rate * len(s):
        above = [p for p in s if p > cut]
        return min(above) if above else cut + 1e-9
    return cut


def at_threshold(probs, labels, threshold: float) -> dict:
    tp = fp = fn = tn = 0
    for p, y in zip(probs, labels):
        flag = p >= threshold
        if flag and y:
            tp += 1
        elif flag:
            fp += 1
        elif y:
            fn += 1
        else:
            tn += 1
    n = len(labels)
    return {"threshold": threshold, "n": n, "events": tp + fn, "alert_rate": (tp + fp) / n if n else NAN,
            "sensitivity": tp / (tp + fn) if tp + fn else NAN, "ppv": tp / (tp + fp) if tp + fp else NAN,
            "specificity": tn / (tn + fp) if tn + fp else NAN, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def net_benefit(probs, labels, pt: float) -> float:
    """Decision-curve net benefit at threshold probability pt (0 < pt < 1)."""
    n = len(labels)
    tp = sum(1 for p, y in zip(probs, labels) if p >= pt and y)
    fp = sum(1 for p, y in zip(probs, labels) if p >= pt and not y)
    return tp / n - fp / n * (pt / (1 - pt))


def resamples(groups, n_boot: int, seed: int = 0) -> list[list[int]]:
    """Cluster bootstrap resamples: lists of ROW indices built by drawing whole groups (children) with replacement.
    Compute once and reuse for every model so paired comparisons see the same resamples."""
    by: dict = {}
    for i, g in enumerate(groups):
        by.setdefault(g, []).append(i)
    members = list(by.values())
    rng = random.Random(seed)
    k = len(members)
    out = []
    for _ in range(n_boot):
        idx: list[int] = []
        for _ in range(k):
            idx.extend(members[rng.randrange(k)])
        out.append(idx)
    return out


def ci_from(metric, probs, labels, rs, level: float = 0.95) -> tuple[float, float]:
    vals = []
    for idx in rs:
        v = metric([probs[i] for i in idx], [labels[i] for i in idx])
        if not math.isnan(v):
            vals.append(v)
    return _percentiles(vals, level)


def paired_diff_ci(metric, p_new, p_base, labels, rs, level: float = 0.95) -> tuple[float, float, float]:
    """metric(new) - metric(base) on the same children: (difference, low, high)."""
    d = metric(p_new, labels) - metric(p_base, labels)
    diffs = []
    for idx in rs:
        y = [labels[i] for i in idx]
        a, b = metric([p_new[i] for i in idx], y), metric([p_base[i] for i in idx], y)
        if not (math.isnan(a) or math.isnan(b)):
            diffs.append(a - b)
    lo, hi = _percentiles(diffs, level)
    return d, lo, hi


def _percentiles(vals: list[float], level: float) -> tuple[float, float]:
    if not vals:
        return NAN, NAN
    vals = sorted(vals)
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    return vals[int(lo * (len(vals) - 1))], vals[int(round(hi * (len(vals) - 1)))]


def subgroup_table(groups, probs, labels, threshold: float, min_n: int = 50, min_events: int = 20) -> list[dict]:
    """Per subgroup: n, events, AUROC, sensitivity, PPV and alert rate. Small groups are reported and marked, not hidden."""
    by: dict = {}
    for g, p, y in zip(groups, probs, labels):
        by.setdefault(g, ([], []))
        by[g][0].append(p)
        by[g][1].append(y)
    rows = []
    for g in sorted(by, key=str):
        p, y = by[g]
        t = at_threshold(p, y, threshold)
        rows.append({"group": g, "n": len(y), "events": sum(y), "auroc": auroc(p, y), "sensitivity": t["sensitivity"],
                     "ppv": t["ppv"], "alert_rate": t["alert_rate"], "small": len(y) < min_n or sum(y) < min_events})
    return rows


def strata_table(probs, labels, cutoffs: dict) -> list[dict]:
    """Observed event rate per risk stratum. `cutoffs` maps 'elevated' and 'high' to calibrated-probability thresholds. The
    lowest group is called 'not flagged': it is the children the model has no extra concern about, not a 'low risk' group."""
    def name(p):
        return "high" if p >= cutoffs["high"] else "elevated" if p >= cutoffs["elevated"] else "not flagged"
    by = {k: [0, 0] for k in ("high", "elevated", "not flagged")}
    for p, y in zip(probs, labels):
        by[name(p)][0] += 1
        by[name(p)][1] += int(y)
    n, events = len(labels), sum(labels)
    return [{"stratum": k, "n": c[0], "share_of_children": c[0] / n if n else NAN, "events": c[1],
             "event_rate": c[1] / c[0] if c[0] else NAN, "share_of_all_events": c[1] / events if events else NAN}
            for k, c in by.items()]
