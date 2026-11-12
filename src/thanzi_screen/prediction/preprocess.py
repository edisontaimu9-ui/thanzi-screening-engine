"""Preprocessing, standard library only so the same code can run in the service.

- `split_children`: deterministic, by child. All rows of a child land in one split, whatever the row order.
- A feature missing at prediction time that was never missing in training raises UnseenMissingError (strict_missing),
  because the model has no learned meaning for that gap. Callers report such a row as not scored.
- `Preprocessor`: fitted on TRAINING rows only. Per feature it stores the training median, winsorising limits (1st and
  99th percentile, continuous and count features), mean and spread for scaling, and whether a missing-value indicator
  column is added. Missing values are imputed with the training median AND flagged by an indicator, so "not assessed" stays
  visible to the model and is never turned into a quiet "normal". It serialises to JSON.
"""
from __future__ import annotations

import hashlib
import math

from .features import FEATURES, FEATURE_NAMES

SPLITS = ("train", "val", "test")


class PreprocessError(ValueError):
    pass


class UnseenMissingError(PreprocessError):
    """A value is missing for a feature that was never missing in training. The model has no learned meaning for that
    gap (the median would stand in as a quiet "typical" value), so the row is refused instead of imputed."""


def split_children(child_ids, seed: int = 0, fractions=(0.70, 0.15, 0.15)) -> dict[str, str]:
    """{child_id: split}. Hash of seed and id, so the answer does not depend on order or on who else is in the data."""
    if abs(sum(fractions) - 1.0) > 1e-9 or any(f <= 0 for f in fractions):
        raise PreprocessError("fractions must be positive and sum to 1")
    out = {}
    for cid in child_ids:
        h = int(hashlib.sha256(f"{seed}:{cid}".encode()).hexdigest()[:12], 16) / float(16 ** 12)
        out[cid] = "train" if h < fractions[0] else "val" if h < fractions[0] + fractions[1] else "test"
    return out


def _quantile(sorted_vals: list[float], q: float) -> float:
    pos = q * (len(sorted_vals) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


class Preprocessor:
    def __init__(self, spec: dict):
        self.spec = spec
        self.names = tuple(spec["features"])
        self.columns = tuple(self.names) + tuple(f"{n}_missing" for n in self.names if spec["features"][n]["indicator"])

    @classmethod
    def fit(cls, rows: list[dict], scale: bool = True) -> "Preprocessor":
        if not rows:
            raise PreprocessError("no training rows")
        feats = {}
        for n in FEATURE_NAMES:
            kind = FEATURES[n].kind
            vals = sorted(r[n] for r in rows if r[n] is not None)
            if not all(math.isfinite(v) for v in vals):
                raise PreprocessError(f"non-finite value in {n}")
            missing = len(rows) - len(vals)
            if not vals:
                feats[n] = {"kind": kind, "median": 0.0, "lo": 0.0, "hi": 0.0, "mean": 0.0, "scale": 1.0,
                            "indicator": True, "train_missing_fraction": 1.0, "all_missing_in_training": True}
                continue
            lo, hi = (_quantile(vals, 0.01), _quantile(vals, 0.99)) if kind != "binary" else (0.0, 1.0)
            clipped = [min(max(v, lo), hi) for v in vals]
            mean = sum(clipped) / len(clipped)
            sd = math.sqrt(sum((v - mean) ** 2 for v in clipped) / len(clipped))
            feats[n] = {"kind": kind, "median": _quantile(vals, 0.5), "lo": lo, "hi": hi,
                        "mean": mean if (scale and kind != "binary") else 0.0,
                        "scale": sd if (scale and kind != "binary" and sd > 1e-9) else 1.0,
                        "indicator": missing > 0, "train_missing_fraction": round(missing / len(rows), 4),
                        "all_missing_in_training": False}
        return cls({"version": 1, "n_train_rows": len(rows), "scaled": bool(scale), "features": feats})

    def transform(self, row: dict, strict_missing: bool = True) -> list[float]:
        extra = set(row) - set(self.names)
        if extra or set(self.names) - set(row):
            raise PreprocessError("feature set differs from the one the preprocessor was fitted on")
        vec, flags = [], []
        for n in self.names:
            p, v = self.spec["features"][n], row[n]
            if v is not None and not math.isfinite(v):
                raise PreprocessError(f"non-finite value in {n}")
            miss = v is None
            if miss and not p["indicator"] and strict_missing:
                raise UnseenMissingError(f"{n} is missing but was never missing in training")
            x = p["median"] if miss else min(max(v, p["lo"]), p["hi"])
            vec.append((x - p["mean"]) / p["scale"])
            if p["indicator"]:
                flags.append(float(miss))
        return vec + flags

    def to_dict(self) -> dict:
        return self.spec

    @classmethod
    def from_dict(cls, spec: dict) -> "Preprocessor":
        if spec.get("version") != 1 or set(spec.get("features", {})) != set(FEATURE_NAMES):
            raise PreprocessError("unsupported preprocessor file")
        return cls(spec)
