"""Turn fitted scikit-learn or XGBoost models into the plain JSON the service evaluates. Development machine only.

These helpers take already-fitted objects. The tree walkers import nothing; `from_xgboost` imports xgboost lazily. The service
never imports this module, scikit-learn or XGBoost. The export script checks every exported model against the library on real
rows (parity) and refuses to write a file that differs by more than PARITY_TOLERANCE.
"""
from __future__ import annotations

import json

from .trees import TreeEnsemble

PARITY_TOLERANCE = 1e-5


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
    """One tree from XGBoost's JSON model (full-precision arrays). Left child is the "yes" branch (x < threshold)."""
    left, right = t["left_children"][node], t["right_children"][node]
    cover = float(t["sum_hessian"][node])
    if left == -1:
        return {"v": float(t["split_conditions"][node]), "c": cover}
    return {"f": int(t["split_indices"][node]), "t": float(t["split_conditions"][node]),
            "l": _xgb_tree(t, left), "r": _xgb_tree(t, right), "c": cover}


def from_xgboost(booster, names, sample_x) -> TreeEnsemble:
    """`booster` is the fitted XGBClassifier's booster, trained on a numpy matrix. Numeric splits only. The base margin is read
    back from one row so it is right whatever the library version stores."""
    import xgboost as xgb  # development-only
    model = json.loads(booster.save_raw(raw_format="json"))["learner"]["gradient_booster"]["model"]
    trees = [_xgb_tree(t) for t in model["trees"]]
    probe = TreeEnsemble(names, "gbm_logit", "lt", trees, 0.0)
    margin = float(booster.predict(xgb.DMatrix([sample_x]), output_margin=True)[0])
    return TreeEnsemble(names, "gbm_logit", "lt", trees, margin - probe.raw_output(sample_x))


def from_sklearn_logistic(model, columns, column_means) -> dict:
    """Logistic regression on the PREPROCESSED columns (already standardised, so the coefficients are on that scale).
    `column_means` are the training means of those columns, so contributions can be reported against an average child."""
    coef = [float(c) for c in model.coef_[0]]
    if len(coef) != len(columns) or len(column_means) != len(columns):
        raise ValueError("columns, coefficients and column means differ in length")
    return {"type": "logistic", "names": list(columns), "coef": coef, "bias": float(model.intercept_[0]),
            "column_mean": [float(m) for m in column_means]}


def export_candidate(name: str, estimator, columns, X_train, sample_x):
    """(kind, model part) for a fitted candidate: 'lr' (logistic), 'rf' (rf_prob) or 'xgb' (gbm_logit)."""
    if name == "lr":
        means = [sum(r[j] for r in X_train) / len(X_train) for j in range(len(columns))]
        return "logistic", from_sklearn_logistic(estimator, columns, means)
    if name == "rf":
        return "rf_prob", from_sklearn_forest(estimator, columns).to_dict()
    if name == "xgb":
        return "gbm_logit", from_xgboost(estimator.get_booster(), columns, sample_x).to_dict()
    raise ValueError(f"the baseline is a yardstick, not a model, and is never exported ({name!r})")
