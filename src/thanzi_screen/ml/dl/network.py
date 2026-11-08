"""Small feed-forward neural network in plain Python (standard library only). JSON in and out, never pickle.

Built for modest hardware (a phone, a small server): dense layers, ReLU, Adam, early stopping, an enforced
parameter budget. Binary (one sigmoid output) or multiclass (softmax). Deterministic for a given dataset and seed.
This module imports nothing from the rest of the project, so it can be reused or tested alone.
"""
from __future__ import annotations

import math
import random
from operator import mul

PRESETS = {"tiny": (16,), "small": (32, 16), "base": (64, 32)}
MAX_PARAMS = 20_000          # lightweight budget (D146). Raise it knowingly with max_params=.
_EPS = 1e-12


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _softmax(z):
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v / s for v in e]


def _affine(W, b, rows):
    return [[bj + sum(map(mul, wj, a)) for wj, bj in zip(W, b)] for a in rows]


def parameter_count(n_in: int, hidden, n_out: int = 1) -> int:
    sizes = [n_in, *hidden, n_out]
    return sum(a * b + b for a, b in zip(sizes, sizes[1:]))


class Network:
    """Dense network. `outputs == 1` is a binary classifier, `outputs > 1` a softmax classifier over `classes`."""

    def __init__(self, names, hidden=(32, 16), classes=None, mean=None, std=None, layers=None,
                 clip: float = 10.0, max_params: int = MAX_PARAMS):
        self.names = list(names)
        self.hidden = tuple(int(h) for h in hidden)
        self.classes = list(classes) if classes else None
        if self.classes is not None and len(self.classes) < 2:
            raise ValueError("a multiclass network needs at least two classes")
        self.outputs = len(self.classes) if self.classes else 1
        if not self.names or any(h < 1 for h in self.hidden):
            raise ValueError("need at least one input and hidden layers of size 1 or more")
        self.clip = float(clip)
        n_in = len(self.names)
        self.params = parameter_count(n_in, self.hidden, self.outputs)
        if self.params > max_params:
            raise ValueError(f"{self.params} parameters exceeds the budget of {max_params}; use a smaller preset")
        self.mean = list(mean) if mean is not None else [0.0] * n_in
        self.std = list(std) if std is not None else [1.0] * n_in
        self.layers = layers if layers is not None else self._init(0)
        self._check()
        self.history: list[dict] = []

    # ---- construction and checks ----
    def _sizes(self):
        return [len(self.names), *self.hidden, self.outputs]

    def _init(self, seed: int):
        rng = random.Random(seed)
        layers, sizes = [], self._sizes()
        for k, (a, b) in enumerate(zip(sizes, sizes[1:])):
            scale = math.sqrt((2.0 if k < len(sizes) - 2 else 1.0) / a)      # He for ReLU layers, Xavier-like at the output
            layers.append({"w": [[rng.gauss(0.0, scale) for _ in range(a)] for _ in range(b)], "b": [0.0] * b})
        return layers

    def _check(self):
        sizes = self._sizes()
        n_in = sizes[0]
        if len(self.mean) != n_in or len(self.std) != n_in:
            raise ValueError("mean and std must match the number of inputs")
        if len(self.layers) != len(sizes) - 1:
            raise ValueError("layer count does not match the architecture")
        values = list(self.mean) + list(self.std)
        for layer, (a, b) in zip(self.layers, zip(sizes, sizes[1:])):
            if len(layer["w"]) != b or len(layer["b"]) != b or any(len(r) != a for r in layer["w"]):
                raise ValueError("layer shape does not match the architecture")
            values += layer["b"] + [v for r in layer["w"] for v in r]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            raise ValueError("weights must be finite numbers")
        if any(s <= 0 for s in self.std):
            raise ValueError("std must be positive")

    # ---- forward ----
    def _standardise(self, x):
        if len(x) != len(self.names):
            raise ValueError("input length does not match the model")
        c = self.clip
        return [max(-c, min(c, (v - m) / s)) for v, m, s in zip(x, self.mean, self.std)]

    def _logits(self, z):
        a = z
        last = len(self.layers) - 1
        for k, layer in enumerate(self.layers):
            out = [bj + sum(map(mul, wj, a)) for wj, bj in zip(layer["w"], layer["b"])]
            a = out if k == last else [v if v > 0.0 else 0.0 for v in out]
        return a

    def predict_proba(self, x) -> float:
        """Binary networks: probability of the positive class."""
        if self.outputs != 1:
            raise ValueError("predict_proba is for binary networks; use predict_dist")
        return _sigmoid(self._logits(self._standardise(x))[0])

    def predict_dist(self, x) -> dict:
        """Multiclass networks: class to probability (a binary network gives {0: 1-p, 1: p} style via predict_proba)."""
        if self.classes is None:
            raise ValueError("predict_dist is for multiclass networks; use predict_proba")
        return dict(zip(self.classes, _softmax(self._logits(self._standardise(x)))))

    def predict_batch(self, X) -> list:
        """Probabilities for many rows (binary: floats; multiclass: dicts)."""
        return [self.predict_proba(x) if self.classes is None else self.predict_dist(x) for x in X]

    def top_signals(self, x, k=3):
        """Inputs whose removal (set to the training mean) moves the output most. Transparent, no gradients needed."""
        z = self._standardise(x)
        if self.classes is None:
            def score(v):
                return self._logits(v)[0]
        else:
            top = max(range(self.outputs), key=lambda i: self._logits(z)[i])

            def score(v):
                return _softmax(self._logits(v))[top]
        base = score(z)
        moves = []
        for j, name in enumerate(self.names):
            if z[j] == 0.0:
                continue
            z2 = list(z)
            z2[j] = 0.0
            moves.append((abs(score(z2) - base), name))
        moves.sort(key=lambda t: (-t[0], t[1]))
        return tuple(n for d, n in moves[:k] if d > 0.0)

    # ---- training ----
    def _loss(self, Z, y, class_weights):
        total = 0.0
        for z, t in zip(Z, y):
            lg = self._logits(z)
            if self.classes is None:
                p = min(1.0 - _EPS, max(_EPS, _sigmoid(lg[0])))
                total += -(class_weights[1] * math.log(p) if t else class_weights[0] * math.log(1.0 - p))
            else:
                total += -class_weights[t] * math.log(max(_EPS, _softmax(lg)[t]))
        return total / max(1, len(Z))

    def fit(self, X, y, X_val=None, y_val=None, seed=0, epochs=30, lr=0.003, batch=64, l2=1e-5, dropout=0.0,
            pos_weight=1.0, class_weights=None, patience=6, beta1=0.9, beta2=0.999):
        """Train with Adam. Binary `y` is 0/1. Multiclass `y` is a class value from `classes`.
        With validation data the best epoch is kept (early stopping on validation loss)."""
        n, d = len(X), len(self.names)
        if n == 0 or len(y) != n:
            raise ValueError("need matching, non-empty X and y")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("dropout must be in [0, 1)")
        self.mean = [sum(r[j] for r in X) / n for j in range(d)]
        self.std = [max(1e-9, math.sqrt(sum((r[j] - self.mean[j]) ** 2 for r in X) / n)) for j in range(d)]
        Z = [self._standardise(r) for r in X]
        if self.classes is None:
            T = [1 if t else 0 for t in y]
            cw = {0: 1.0, 1: float(pos_weight)}
        else:
            index = {c: i for i, c in enumerate(self.classes)}
            T = [index[t] for t in y]
            cw = {i: 1.0 for i in range(self.outputs)}
            for c, w in (class_weights or {}).items():
                cw[index[c]] = float(w)
        Zv = Tv = None
        if X_val is not None and len(X_val):
            Zv = [self._standardise(r) for r in X_val]
            Tv = [1 if t else 0 for t in y_val] if self.classes is None else [index[t] for t in y_val]

        rng = random.Random(seed)
        self.layers = self._init(seed)
        # Adam state, one (m, v) pair per weight row and bias vector
        mw = [[[0.0] * len(r) for r in L["w"]] for L in self.layers]
        vw = [[[0.0] * len(r) for r in L["w"]] for L in self.layers]
        mb = [[0.0] * len(L["b"]) for L in self.layers]
        vb = [[0.0] * len(L["b"]) for L in self.layers]
        step, order = 0, list(range(n))
        best = (math.inf, -1, None)
        self.history = []
        n_layers, keep = len(self.layers), 1.0 - dropout
        for ep in range(epochs):
            rng.shuffle(order)
            run = 0.0
            for s in range(0, n, batch):
                idx = order[s:s + batch]
                m = len(idx)
                acts, gates = [[Z[i] for i in idx]], []
                for k, layer in enumerate(self.layers):          # forward, keeping what backward needs
                    pre = _affine(layer["w"], layer["b"], acts[-1])
                    if k == n_layers - 1:
                        acts.append(pre)
                        break
                    if dropout:
                        gate = [[(1.0 / keep if (v > 0.0 and rng.random() < keep) else 0.0) for v in row] for row in pre]
                    else:
                        gate = [[1.0 if v > 0.0 else 0.0 for v in row] for row in pre]
                    gates.append(gate)
                    acts.append([[v * g if g else 0.0 for v, g in zip(row, grow)] for row, grow in zip(pre, gate)])
                out = acts[-1]
                delta = []
                for row, i in zip(out, idx):                      # output error, with class weights
                    t = T[i]
                    if self.classes is None:
                        p = _sigmoid(row[0])
                        w = cw[1] if t else cw[0]
                        run += -w * math.log(max(_EPS, p if t else 1.0 - p))
                        delta.append([(p - t) * w])
                    else:
                        p = _softmax(row)
                        w = cw[t]
                        run += -w * math.log(max(_EPS, p[t]))
                        delta.append([(pk - (1.0 if k == t else 0.0)) * w for k, pk in enumerate(p)])
                step += 1
                c1, c2 = 1.0 - beta1 ** step, 1.0 - beta2 ** step
                for k in range(n_layers - 1, -1, -1):             # backward
                    layer = self.layers[k]
                    a_in_cols = list(zip(*acts[k]))
                    d_cols = list(zip(*delta))
                    if k > 0:
                        wt = list(zip(*layer["w"]))
                        gate = gates[k - 1]
                        prev = [[sum(map(mul, dr, wi)) * g for wi, g in zip(wt, grow)] for dr, grow in zip(delta, gate)]
                    for j, dj in enumerate(d_cols):
                        wj, mj, vj = layer["w"][j], mw[k][j], vw[k][j]
                        for i, ai in enumerate(a_in_cols):
                            g = sum(map(mul, dj, ai)) / m + l2 * wj[i]
                            mj[i] = beta1 * mj[i] + (1 - beta1) * g
                            vj[i] = beta2 * vj[i] + (1 - beta2) * g * g
                            wj[i] -= lr * (mj[i] / c1) / (math.sqrt(vj[i] / c2) + 1e-8)
                        g = sum(dj) / m
                        mb[k][j] = beta1 * mb[k][j] + (1 - beta1) * g
                        vb[k][j] = beta2 * vb[k][j] + (1 - beta2) * g * g
                        layer["b"][j] -= lr * (mb[k][j] / c1) / (math.sqrt(vb[k][j] / c2) + 1e-8)
                    if k > 0:
                        delta = prev
            rec = {"epoch": ep + 1, "train_loss": run / n}
            if Zv is not None:
                rec["val_loss"] = self._loss(Zv, Tv, cw)
                if rec["val_loss"] < best[0] - 1e-6:
                    best = (rec["val_loss"], ep + 1, self._snapshot())
            self.history.append(rec)
            if Zv is not None and ep + 1 - best[1] >= patience:
                break
        if best[2] is not None:
            self.layers = best[2]
        self.best_epoch = best[1] if best[2] is not None else len(self.history)
        return self

    def _snapshot(self):
        return [{"w": [list(r) for r in L["w"]], "b": list(L["b"])} for L in self.layers]

    # ---- JSON ----
    def to_dict(self):
        return {"type": "mlp", "names": self.names, "hidden": list(self.hidden), "classes": self.classes,
                "activation": "relu", "clip": self.clip, "mean": self.mean, "std": self.std,
                "parameters": self.params, "layers": self.layers}

    @classmethod
    def from_dict(cls, d, max_params: int = MAX_PARAMS):
        if d.get("type") != "mlp" or d.get("activation") != "relu":
            raise ValueError("not a supported network file")
        return cls(d["names"], d["hidden"], d.get("classes"), d["mean"], d["std"], d["layers"],
                   clip=d.get("clip", 10.0), max_params=max_params)
