#!/usr/bin/env python3
"""Optional, dev-only: compare the plain-Python models with scikit-learn. Never needed at runtime.

Try it on Termux first (pip install scikit-learn). If it will not install, skip it; nothing else depends on it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.tree import DecisionTreeClassifier
except ImportError:
    print("scikit-learn is not installed. Skipping the optional comparison. Nothing else is affected.")
    raise SystemExit(0)

from thanzi_screen import data
from thanzi_screen.ml.features import ERROR_TO_FIELD, features_from_inputs, row_inputs, vector
from thanzi_screen.anthro import InputError


def main(path="data/synthetic/synthetic_children.csv"):
    rows = data.load_dataset(path)
    X = {"train": [], "test": []}
    y = {"train": [], "test": []}
    yf = {"train": [], "test": []}
    for r in rows:
        if r["split"] not in X:
            continue
        try:
            f, _, _ = features_from_inputs(*row_inputs(r))
        except InputError:
            continue
        X[r["split"]].append(vector(f))
        y[r["split"]].append(int(r["injected_error"] != "none"))
        yf[r["split"]].append(ERROR_TO_FIELD.get(r["injected_error"]))
    from sklearn.preprocessing import StandardScaler
    sc = StandardScaler().fit(X["train"])
    lr = LogisticRegression(max_iter=500, class_weight="balanced").fit(sc.transform(X["train"]), y["train"])
    print("sklearn logistic AUC (test):", round(roc_auc_score(y["test"], lr.predict_proba(sc.transform(X["test"]))[:, 1]), 4))
    idx = [i for i, v in enumerate(yf["train"]) if v]
    tr = DecisionTreeClassifier(max_depth=4, min_samples_leaf=15, random_state=0).fit([X["train"][i] for i in idx], [yf["train"][i] for i in idx])
    jdx = [i for i, v in enumerate(yf["test"]) if v]
    acc = sum(tr.predict([X["test"][i]])[0] == yf["test"][i] for i in jdx) / len(jdx)
    print("sklearn tree field accuracy (test):", round(acc, 4))
    print("Compare with models/MODEL_CARD.md (plain-Python AUC and field accuracy).")


if __name__ == "__main__":
    main(*sys.argv[1:])
