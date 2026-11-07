"""Small transparent models in plain Python. JSON in and out, never pickle."""
from __future__ import annotations

import math
import random


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


class LogisticModel:
    def __init__(self, names, mean=None, std=None, coef=None, bias=0.0):
        self.names = list(names)
        self.mean, self.std = mean or [0.0] * len(names), std or [1.0] * len(names)
        self.coef, self.bias = coef or [0.0] * len(names), bias

    def fit(self, X, y, seed=0, epochs=12, lr=0.05, l2=1e-4, pos_weight=1.0, batch=64, momentum=0.9):
        n, d = len(X), len(self.names)
        self.mean = [sum(r[j] for r in X) / n for j in range(d)]
        self.std = [max(1e-9, math.sqrt(sum((r[j] - self.mean[j]) ** 2 for r in X) / n)) for j in range(d)]
        Z = [[(r[j] - self.mean[j]) / self.std[j] for j in range(d)] for r in X]
        w, b = [0.0] * d, 0.0
        vw, vb = [0.0] * d, 0.0
        rng = random.Random(seed)
        order = list(range(n))
        for ep in range(epochs):
            rng.shuffle(order)
            step = lr / (1 + 0.3 * ep)
            for s in range(0, n, batch):
                idx = order[s:s + batch]
                gw, gb = [0.0] * d, 0.0
                for i in idx:
                    z = Z[i]
                    p = _sigmoid(b + sum(w[j] * z[j] for j in range(d)))
                    g = (p - y[i]) * (pos_weight if y[i] else 1.0)
                    gb += g
                    for j in range(d):
                        gw[j] += g * z[j]
                m = len(idx)
                for j in range(d):
                    vw[j] = momentum * vw[j] - step * (gw[j] / m + l2 * w[j])
                    w[j] += vw[j]
                vb = momentum * vb - step * gb / m
                b += vb
        self.coef, self.bias = w, b
        return self

    def predict_proba(self, x) -> float:
        return _sigmoid(self.bias + sum(c * (v - m) / s for c, v, m, s in zip(self.coef, x, self.mean, self.std)))

    def top_signals(self, x, k=3):
        contrib = [(abs(c * (v - m) / s), n) for c, v, m, s, n in zip(self.coef, x, self.mean, self.std, self.names)]
        return tuple(n for _, n in sorted(contrib, reverse=True)[:k])

    def to_dict(self):
        return {"type": "logistic", "names": self.names, "mean": self.mean, "std": self.std, "coef": self.coef, "bias": self.bias}

    @classmethod
    def from_dict(cls, d):
        return cls(d["names"], d["mean"], d["std"], d["coef"], d["bias"])


class TreeModel:
    """Shallow classification tree (gini, quantile thresholds)."""

    def __init__(self, names, classes, root=None):
        self.names, self.classes, self.root = list(names), list(classes), root

    def fit(self, X, y, max_depth=4, min_leaf=15, n_thresholds=12):
        self.root = self._grow(X, y, list(range(len(X))), 0, max_depth, min_leaf, n_thresholds)
        return self

    def _dist(self, y, idx):
        total = len(idx)
        return {c: sum(1 for i in idx if y[i] == c) / total for c in self.classes}

    def _gini(self, y, idx):
        total = len(idx)
        return 1 - sum((sum(1 for i in idx if y[i] == c) / total) ** 2 for c in self.classes)

    def _grow(self, X, y, idx, depth, max_depth, min_leaf, n_thr):
        if depth >= max_depth or len(idx) < 2 * min_leaf or self._gini(y, idx) == 0:
            return {"leaf": self._dist(y, idx), "n": len(idx)}
        best = None
        base = self._gini(y, idx)
        for j in range(len(self.names)):
            vals = sorted({X[i][j] for i in idx})
            if len(vals) < 2:
                continue
            step = max(1, len(vals) // n_thr)
            for t in [(vals[k] + vals[k + 1]) / 2 for k in range(0, len(vals) - 1, step)]:
                left = [i for i in idx if X[i][j] <= t]
                right = [i for i in idx if X[i][j] > t]
                if len(left) < min_leaf or len(right) < min_leaf:
                    continue
                score = (len(left) * self._gini(y, left) + len(right) * self._gini(y, right)) / len(idx)
                if best is None or score < best[0] - 1e-12:
                    best = (score, j, t, left, right)
        if best is None or best[0] >= base - 1e-9:
            return {"leaf": self._dist(y, idx), "n": len(idx)}
        _, j, t, left, right = best
        return {"feature": self.names[j], "index": j, "threshold": t,
                "left": self._grow(X, y, left, depth + 1, max_depth, min_leaf, n_thr),
                "right": self._grow(X, y, right, depth + 1, max_depth, min_leaf, n_thr)}

    def predict_dist(self, x) -> dict:
        node = self.root
        while "leaf" not in node:
            node = node["left"] if x[node["index"]] <= node["threshold"] else node["right"]
        return node["leaf"]

    def to_dict(self):
        return {"type": "tree", "names": self.names, "classes": self.classes, "root": self.root}

    @classmethod
    def from_dict(cls, d):
        return cls(d["names"], d["classes"], d["root"])


def auc(scores, labels) -> float:
    """Rank-based AUC."""
    pairs = sorted(zip(scores, labels))
    pos = sum(labels)
    neg = len(labels) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    rank_sum, i = 0.0, 0
    while i < len(pairs):
        j = i
        while j < len(pairs) and pairs[j][0] == pairs[i][0]:
            j += 1
        avg = (i + j + 1) / 2
        rank_sum += avg * sum(1 for k in range(i, j) if pairs[k][1])
        i = j
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)
