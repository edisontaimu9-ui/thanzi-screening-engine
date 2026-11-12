"""Turn fitted scikit-learn or XGBoost models into the plain JSON ensemble the service evaluates.

Offline, development-only helpers: they take already-fitted objects and import no library themselves, so the service
never needs scikit-learn or XGBoost. The training script checks every export against the library on real rows (parity).
"""
from __future__ import annotations

import json

from .trees import TreeEnsemble, f32, sigmoid


def _sk_tree(t, node: int = 0) -> dict:
    """scikit-learn tree_ arrays to nested nodes. Leaf value = class-1 share. Cover = weighted samples."""
    cover = float(t.weighted_n_node_samples[node])
    left, right = int(t.children_left[node]), int(t.children_right[node])
    if left == -1:
        v = t.value[node][0]
        return {"v": float(v[1] / (v[0] + v[1])), "c": cover}
    return {"f": int(t.feature[node]), "t": float(t.threshold[node]), "l": _sk_tree(t, left), "r": _sk_tree(t, right), "c": cover}


def from_sklearn_forest(forest, names) -> TreeEnsemble:
    return TreeEnsemble(names, "rf_prob", "le", [_sk_tree(e.tree_) for e in forest.estimators_])


def _xgb_tree(t: dict, node: int = 0) -> dict:
    """One tree from XGBoost's JSON model (full-precision arrays, unlike get_dump, which rounds thresholds).
    Left child is the "yes" branch (x < threshold). In a leaf, split_conditions holds the leaf value."""
    left, right = t["left_children"][node], t["right_children"][node]
    cover = float(t["sum_hessian"][node])
    if left == -1:
        return {"v": float(t["split_conditions"][node]), "c": cover}
    return {"f": int(t["split_indices"][node]), "t": float(t["split_conditions"][node]),
            "l": _xgb_tree(t, left), "r": _xgb_tree(t, right), "c": cover}


def from_xgboost(booster, names, sample_x) -> TreeEnsemble:
    """`booster` is the fitted XGBClassifier's booster, trained on a numpy matrix. Numeric splits only.
    The base margin is read back from one row so it is right whatever the library version stores."""
    import xgboost as xgb  # development-only
    model = json.loads(booster.save_raw(raw_format="json"))["learner"]["gradient_booster"]["model"]
    trees = [_xgb_tree(t) for t in model["trees"]]
    probe = TreeEnsemble(names, "gbm_logit", "lt", trees, 0.0)
    margin = float(booster.predict(xgb.DMatrix([sample_x]), output_margin=True)[0])
    return TreeEnsemble(names, "gbm_logit", "lt", trees, margin - probe.raw_output(sample_x))


__all__ = ["f32", "from_sklearn_forest", "from_xgboost", "sigmoid"]
