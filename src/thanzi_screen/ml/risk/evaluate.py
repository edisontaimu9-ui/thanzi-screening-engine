"""Evaluation for the risk model, in plain Python (no numpy), so the same numbers can be reproduced anywhere.

Discrimination (AUROC, AUPRC), calibration (slope, intercept, Brier, deciles), operating point (sensitivity, PPV and
alert rate at a threshold), decision-curve net benefit, bootstrap intervals, and subgroup tables.
"""
from __future__ import annotations

import math
import random

from ..models import auc as auroc
from .trees import logit, sigmoid

__all__ = ["auroc", "auprc", "brier", "fit_platt", "calibration_table", "threshold_for_alert_rate", "at_threshold",
           "net_benefit", "bootstrap_ci", "paired_auc_diff_ci", "subgroup_table"]


def auprc(scores, labels) -> float:
    """Average precision (step-wise area under the precision-recall curve)."""
    pos = sum(labels)
    if pos == 0:
        return float("nan")
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    tp = 0
    total = 0.0
    i = 0
    n = len(order)
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
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(labels)


def fit_platt(probs, labels, iters: int = 40, clip: float = 15.0) -> tuple[float, float]:
    """Logistic regression of the outcome on logit(p): returns (slope a, intercept b). Used both to calibrate on a
    validation set and, applied to a test set, as the calibration slope and intercept (ideal: 1 and 0)."""
    z = [max(-clip, min(clip, logit(p))) for p in probs]
    a, b = 1.0, 0.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for zi, yi in zip(z, labels):
            p = sigmoid(a * zi + b)
            w = p * (1 - p)
            r = p - yi
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


def calibration_table(probs, labels, bins: int = 10) -> list[dict]:
    order = sorted(range(len(probs)), key=lambda i: probs[i])
    n = len(order)
    out = []
    for k in range(bins):
        idx = order[k * n // bins:(k + 1) * n // bins]
        if idx:
            out.append({"bin": k + 1, "n": len(idx), "mean_predicted": sum(probs[i] for i in idx) / len(idx),
                        "observed_rate": sum(labels[i] for i in idx) / len(idx)})
    return out


def threshold_for_alert_rate(probs, rate: float) -> float:
    """Smallest threshold whose alert rate (share of children with p >= threshold) does not exceed `rate`."""
    s = sorted(probs, reverse=True)
    k = int(math.floor(rate * len(s)))
    if k <= 0:
        return min(1.0, s[0] + 1e-9)
    cut = s[k - 1]
    # ties: step above the cut-off value if including it would exceed the rate
    if sum(1 for p in s if p >= cut) > rate * len(s):
        above = [p for p in s if p > cut]
        return min(above) if above else min(1.0, cut + 1e-9)
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
    return {"threshold": threshold, "n": n, "events": tp + fn, "alert_rate": (tp + fp) / n if n else float("nan"),
            "sensitivity": tp / (tp + fn) if tp + fn else float("nan"), "ppv": tp / (tp + fp) if tp + fp else float("nan"),
            "specificity": tn / (tn + fp) if tn + fp else float("nan"), "npv": tn / (tn + fn) if tn + fn else float("nan"),
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def net_benefit(probs, labels, pt: float) -> float:
    """Decision-curve net benefit at threshold probability pt."""
    n = len(labels)
    tp = sum(1 for p, y in zip(probs, labels) if p >= pt and y)
    fp = sum(1 for p, y in zip(probs, labels) if p >= pt and not y)
    return tp / n - fp / n * (pt / (1 - pt))


def bootstrap_ci(metric, probs, labels, n_boot: int = 200, seed: int = 0, level: float = 0.95) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(labels)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        v = metric([probs[i] for i in idx], [labels[i] for i in idx])
        if not math.isnan(v):
            vals.append(v)
    vals.sort()
    if not vals:
        return float("nan"), float("nan")
    lo, hi = (1 - level) / 2, 1 - (1 - level) / 2
    return vals[int(lo * (len(vals) - 1))], vals[int(hi * (len(vals) - 1))]


def paired_auc_diff_ci(p_new, p_base, labels, n_boot: int = 200, seed: int = 0) -> tuple[float, float, float]:
    """AUROC(new) - AUROC(base) on the same children: (difference, low, high) of a 95% paired bootstrap interval."""
    rng = random.Random(seed)
    n = len(labels)
    diffs = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        y = [labels[i] for i in idx]
        a, b = auroc([p_new[i] for i in idx], y), auroc([p_base[i] for i in idx], y)
        if not (math.isnan(a) or math.isnan(b)):
            diffs.append(a - b)
    diffs.sort()
    d = auroc(p_new, labels) - auroc(p_base, labels)
    if not diffs:
        return d, float("nan"), float("nan")
    return d, diffs[int(0.025 * (len(diffs) - 1))], diffs[int(0.975 * (len(diffs) - 1))]


def subgroup_table(groups, probs, labels, threshold: float, min_n: int = 50) -> list[dict]:
    """Per-subgroup events, AUROC, sensitivity, PPV and alert rate. Small groups are reported but marked."""
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
                     "ppv": t["ppv"], "alert_rate": t["alert_rate"], "small": len(y) < min_n or sum(y) < 20})
    return rows
