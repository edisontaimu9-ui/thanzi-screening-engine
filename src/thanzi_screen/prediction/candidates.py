"""The candidate models: logistic regression, random forest, XGBoost, and a best-single-feature baseline.

Training libraries (numpy, scikit-learn, XGBoost) are imported INSIDE the functions that need them, so importing
`thanzi_screen.prediction` never pulls them in. They are development-machine only (the `train` extra), never in the service.

Settings are fixed and conservative, not tuned on the test set. Classes are NOT reweighted, so the probabilities stay on the
real scale and calibration is a fair question. XGBoost carries the monotone constraints from the feature registry (a lower
z-score or MUAC never lowers the risk), aligned to the preprocessor's columns. Missing-value indicator columns are
unconstrained.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .evaluate import auroc, sigmoid
from .features import FEATURES, MONOTONE

CANDIDATES = ("lr", "rf", "xgb")
LABELS = {"lr": "Logistic regression", "rf": "Random forest", "xgb": "XGBoost", "baseline": "Best single feature"}

PARAMS = {
    "lr": {"C": 0.5, "max_iter": 2000},          # L2 penalty (the default)
    "rf": {"n_estimators": 300, "max_depth": 6, "min_samples_leaf": 50, "max_features": "sqrt"},
    "xgb": {"n_estimators": 300, "max_depth": 3, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8,
            "min_child_weight": 20, "reg_lambda": 5.0, "monotone_constraints": "from feature registry"},
}


class MissingLibraryError(ImportError):
    pass


@dataclass
class Fitted:
    name: str
    params: dict
    _predict: object = field(repr=False, default=None)

    def predict_proba(self, X) -> list[float]:
        return [float(p) for p in self._predict(X)]


def available(name: str) -> bool:
    try:
        if name == "lr" or name == "rf":
            import numpy  # noqa: F401
            import sklearn  # noqa: F401
        elif name == "xgb":
            import numpy  # noqa: F401
            import xgboost  # noqa: F401
        return True
    except ImportError:
        return False


def versions() -> dict:
    out = {}
    for mod in ("numpy", "sklearn", "xgboost"):
        try:
            out[mod] = __import__(mod).__version__
        except ImportError:
            out[mod] = None
    return out


def monotone_for(columns) -> tuple[int, ...]:
    return tuple(MONOTONE.get(c, 0) if c in FEATURES else 0 for c in columns)


def fit_candidate(name: str, X, y, columns, seed: int = 0) -> Fitted:
    if name not in CANDIDATES:
        raise ValueError(f"unknown candidate {name!r}")
    if not available(name):
        raise MissingLibraryError(f"{name} needs numpy and {'xgboost' if name == 'xgb' else 'scikit-learn'} (pip install -e '.[train]')")
    import numpy as np
    Xa, ya = np.asarray(X, dtype=float), np.asarray(y, dtype=int)
    if name == "lr":
        from sklearn.linear_model import LogisticRegression
        m = LogisticRegression(random_state=seed, **PARAMS["lr"]).fit(Xa, ya)
    elif name == "rf":
        from sklearn.ensemble import RandomForestClassifier
        m = RandomForestClassifier(random_state=seed, n_jobs=1, **{k: v for k, v in PARAMS["rf"].items()}).fit(Xa, ya)
    else:
        import xgboost as xgb
        params = {k: v for k, v in PARAMS["xgb"].items() if k != "monotone_constraints"}
        m = xgb.XGBClassifier(monotone_constraints=monotone_for(columns), tree_method="hist", random_state=seed, n_jobs=1,
                              **params).fit(Xa, ya)
    return Fitted(name, dict(PARAMS[name]), lambda Z, m=m: m.predict_proba(np.asarray(Z, dtype=float))[:, 1])


def fit_baseline(X, y, columns) -> Fitted:
    """The yardstick: the ONE column with the best training AUROC, signed by its training direction. Nothing else is learned.

    Chosen on training rows only (never validation or test), so it is a fair, stronger-than-clinical-habit rival: a model
    that cannot beat its best single feature has not earned its complexity. The columns are already imputed and scaled."""
    best, best_auc = None, 0.5
    for j, name in enumerate(columns):
        col = [row[j] for row in X]
        a = auroc(col, y)
        if a == a and abs(a - 0.5) > abs(best_auc - 0.5):
            best, best_auc = j, a
    if best is None:
        raise ValueError("no column separates the classes in the training rows")
    sign = 1 if best_auc > 0.5 else -1
    return Fitted("baseline", {"feature": columns[best], "direction": "higher is riskier" if sign > 0 else "lower is riskier",
                               "train_auroc": max(best_auc, 1 - best_auc)},
                  lambda Z, j=best, s=sign: [sigmoid(s * row[j]) for row in Z])
