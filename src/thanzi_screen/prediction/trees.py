"""Tree ensembles in plain Python: evaluation and exact TreeSHAP. JSON in and out, never pickle.

A copy of thanzi_screen.ml.risk.trees, kept here because the prediction module never imports thanzi_screen.ml. A test checks
that the two give identical predictions and identical SHAP values, so they cannot drift apart unnoticed.

Trained offline (scikit-learn or XGBoost) and exported to this format, so the service keeps its standard-library-only
runtime. Node format: internal {"f": feature index, "t": threshold, "l": left, "r": right, "c": cover},
leaf {"v": value, "c": cover}. `split` is "le" (scikit-learn: go left when x <= t) or "lt" (XGBoost: x < t).
Inputs and thresholds are compared as 32-bit floats, as both libraries do, so predictions match the library.

kind "gbm_logit": output is a margin, base + sum of leaf values; probability = sigmoid(margin). SHAP is in logit units.
kind "rf_prob":   output is the mean of leaf probabilities. SHAP is in probability units.
"""
from __future__ import annotations

import math
import struct

from .errors import PredictionModelError

MAX_DEPTH = 8
MAX_TREES = 500
MAX_NODES = 400_000
COVER_TOLERANCE = 1e-3        # children covers must add up to the parent's, relative


def f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def logit(p: float, eps: float = 1e-9) -> float:
    p = min(1.0 - eps, max(eps, p))
    return math.log(p / (1.0 - p))


def _is_leaf(n: dict) -> bool:
    return "v" in n


def _check_tree(node, n_features: int, depth: int, counter: list) -> None:
    if not isinstance(node, dict):
        raise PredictionModelError("tree node is not an object")
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise PredictionModelError("model has too many nodes")
    if depth > MAX_DEPTH:
        raise PredictionModelError(f"tree deeper than {MAX_DEPTH}")
    c = node.get("c")
    if not isinstance(c, (int, float)) or isinstance(c, bool) or not math.isfinite(c) or c <= 0:
        raise PredictionModelError("every node needs a positive finite cover")
    if _is_leaf(node):
        v = node["v"]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise PredictionModelError("leaf value is not a finite number")
        return
    f, t = node.get("f"), node.get("t")
    if not isinstance(f, int) or isinstance(f, bool) or not (0 <= f < n_features):
        raise PredictionModelError("split feature index out of range")
    if not isinstance(t, (int, float)) or isinstance(t, bool) or not math.isfinite(t):
        raise PredictionModelError("split threshold is not a finite number")
    left, right = node.get("l"), node.get("r")
    if not isinstance(left, dict) or not isinstance(right, dict):
        raise PredictionModelError("internal node needs two children")
    if abs(left["c"] + right["c"] - c) > COVER_TOLERANCE * c:
        raise PredictionModelError("child covers do not add up to the parent cover")
    _check_tree(left, n_features, depth + 1, counter)
    _check_tree(right, n_features, depth + 1, counter)


def _round_thresholds(node: dict) -> None:
    stack = [node]
    while stack:
        n = stack.pop()
        if not _is_leaf(n):
            n["t"] = f32(n["t"])
            stack += [n["l"], n["r"]]


def _leaf_value(node: dict, x: list[float], le: bool) -> float:
    while not _is_leaf(node):
        v = x[node["f"]]
        go_left = v <= node["t"] if le else v < node["t"]
        node = node["l"] if go_left else node["r"]
    return node["v"]


def _expected(node: dict) -> float:
    """Cover-weighted mean leaf value."""
    total, weight = 0.0, 0.0
    stack = [node]
    while stack:
        n = stack.pop()
        if _is_leaf(n):
            total += n["v"] * n["c"]
            weight += n["c"]
        else:
            stack += [n["l"], n["r"]]
    return total / weight


def _tree_shap(root: dict, x: list[float], n_features: int, le: bool) -> list[float]:
    """Exact path-dependent TreeSHAP (Lundberg, Erion and Lee, 2018) for one tree. phi sums to output minus expected."""
    phi = [0.0] * n_features

    def extend(path, pz, po, pi):
        path = [p[:] for p in path]
        n = len(path)
        path.append([pi, pz, po, 1.0 if n == 0 else 0.0])
        for i in range(n - 1, -1, -1):
            path[i + 1][3] += po * path[i][3] * (i + 1) / (n + 1)
            path[i][3] = pz * path[i][3] * (n - i) / (n + 1)
        return path

    def unwind(path, i):
        path = [p[:] for p in path]
        n = len(path) - 1
        o, z = path[i][2], path[i][1]
        nxt = path[n][3]
        for j in range(n - 1, -1, -1):
            if o != 0:
                tmp = path[j][3]
                path[j][3] = nxt * (n + 1) / ((j + 1) * o)
                nxt = tmp - path[j][3] * z * (n - j) / (n + 1)
            else:
                path[j][3] = path[j][3] * (n + 1) / (z * (n - j))
        for j in range(i, n):
            path[j][0:3] = path[j + 1][0:3]
        path.pop()
        return path

    def unwound_sum(path, i):
        n = len(path) - 1
        o, z = path[i][2], path[i][1]
        nxt = path[n][3]
        total = 0.0
        for j in range(n - 1, -1, -1):
            if o != 0:
                tmp = nxt * (n + 1) / ((j + 1) * o)
                total += tmp
                nxt = path[j][3] - tmp * z * (n - j) / (n + 1)
            else:
                total += path[j][3] / z / ((n - j) / (n + 1))
        return total

    def recurse(node, path, pz, po, pi):
        path = extend(path, pz, po, pi)
        if _is_leaf(node):
            for i in range(1, len(path)):
                w = unwound_sum(path, i)
                phi[path[i][0]] += w * (path[i][2] - path[i][1]) * node["v"]
            return
        f = node["f"]
        v = x[f]
        go_left = v <= node["t"] if le else v < node["t"]
        hot, cold = (node["l"], node["r"]) if go_left else (node["r"], node["l"])
        iz = io = 1.0
        for k in range(1, len(path)):
            if path[k][0] == f:
                iz, io = path[k][1], path[k][2]
                path = unwind(path, k)
                break
        recurse(hot, path, iz * hot["c"] / node["c"], io, f)
        recurse(cold, path, iz * cold["c"] / node["c"], 0.0, f)

    recurse(root, [], 1.0, 1.0, -1)
    return phi


class TreeEnsemble:
    def __init__(self, names, kind, split, trees, base=0.0):
        if kind not in ("gbm_logit", "rf_prob"):
            raise PredictionModelError("unknown ensemble kind")
        if split not in ("le", "lt"):
            raise PredictionModelError("unknown split rule")
        if not isinstance(trees, list) or not trees or len(trees) > MAX_TREES:
            raise PredictionModelError("ensemble needs between 1 and %d trees" % MAX_TREES)
        if not isinstance(base, (int, float)) or isinstance(base, bool) or not math.isfinite(base):
            raise PredictionModelError("base is not a finite number")
        self.names, self.kind, self.split, self.trees, self.base = list(names), kind, split, trees, float(base)
        counter = [0]
        for t in trees:
            _check_tree(t, len(self.names), 0, counter)
        self._le = split == "le"
        if not self._le:                       # XGBoost compares 32-bit thresholds: round ours the same way (idempotent)
            for t in trees:
                _round_thresholds(t)
        self._expected = [_expected(t) for t in trees]

    # ---- evaluation ----
    def _x32(self, x) -> list[float]:
        if len(x) != len(self.names):
            raise PredictionModelError("wrong number of features")
        return [f32(float(v)) for v in x]

    def raw_output(self, x) -> float:
        """GBM: margin (logit). RF: probability."""
        xs = self._x32(x)
        total = sum(_leaf_value(t, xs, self._le) for t in self.trees)
        return self.base + total if self.kind == "gbm_logit" else total / len(self.trees)

    def probability(self, x) -> float:
        out = self.raw_output(x)
        return sigmoid(out) if self.kind == "gbm_logit" else min(1.0, max(0.0, out))

    # ---- explanation ----
    def contributions(self, x) -> tuple[float, list[float]]:
        """(expected value, per-feature SHAP) in the units of raw_output. expected + sum(phi) == raw_output."""
        xs = self._x32(x)
        phi = [0.0] * len(self.names)
        for t in self.trees:
            for j, v in enumerate(_tree_shap(t, xs, len(self.names), self._le)):
                phi[j] += v
        if self.kind == "gbm_logit":
            return self.base + sum(self._expected), phi
        n = len(self.trees)
        return sum(self._expected) / n, [p / n for p in phi]

    def to_dict(self) -> dict:
        return {"type": "tree_ensemble", "kind": self.kind, "split": self.split, "names": self.names,
                "base": self.base, "trees": self.trees}

    @classmethod
    def from_dict(cls, d: dict) -> "TreeEnsemble":
        if not isinstance(d, dict) or d.get("type") != "tree_ensemble":
            raise PredictionModelError("not a tree ensemble")
        return cls(d["names"], d["kind"], d["split"], d["trees"], d.get("base", 0.0))
