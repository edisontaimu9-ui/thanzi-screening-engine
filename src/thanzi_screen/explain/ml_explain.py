"""Explanations for the ML recording-error flag (Phase 5). Exact for these models, no SHAP or LIME (Q2).

Logistic model: contribution_j = coef_j * (x_j - mean_j) / std_j, so logit = bias + sum(contributions) exactly.
Tree: the path of splits that led to the leaf. Contributions are not causal and correlated features share credit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..ml.models import LogisticModel, TreeModel
from . import messages as M


@dataclass(frozen=True)
class Contribution:
    feature: str
    value: float
    contribution: float        # signed, in logit units
    direction: str             # "raises" or "lowers" the error probability
    text: str                  # plain-language statement of the feature value


@dataclass(frozen=True)
class TreeStep:
    feature: str
    threshold: float
    value: float
    went: str                  # "<=" or ">"
    text: str


@dataclass(frozen=True)
class FlagTrace:
    flagged: bool
    probability: float
    threshold: float
    bias: float
    logit: float
    contributions: tuple[Contribution, ...]     # all features, largest magnitude first
    top_raising: tuple[Contribution, ...]       # up to 3, the signals behind a flag
    suggested_field: str | None
    field_probability: float | None
    tree_path: tuple[TreeStep, ...]
    leaf_distribution: dict
    leaf_size: int | None
    model_version: str
    note: str


def contributions(model: LogisticModel, x, features: dict) -> tuple[float, list[Contribution]]:
    """Return (logit, contributions). logit equals bias plus the sum of contributions."""
    out = []
    for n, c, v, m, s in zip(model.names, model.coef, x, model.mean, model.std):
        k = c * (v - m) / s
        out.append(Contribution(n, v, k, "raises" if k > 0 else "lowers", M.feature_phrase(n, features)))
    logit = model.bias + sum(c.contribution for c in out)
    out.sort(key=lambda c: (-abs(c.contribution), c.feature))
    return logit, out


def tree_path(model: TreeModel, x, features: dict):
    """Walk the tree exactly as `predict_dist` does and record each split."""
    node, steps = model.root, []
    while "leaf" not in node:
        v = x[node["index"]]
        went = "<=" if v <= node["threshold"] else ">"
        steps.append(TreeStep(node["feature"], node["threshold"], v, went, M.feature_phrase(node["feature"], features)))
        node = node["left"] if went == "<=" else node["right"]
    return steps, node["leaf"], node.get("n")


def build_flag_trace(models, x, features: dict, flags) -> FlagTrace:
    err = flags.recording_error
    logit, contribs = contributions(models.error, x, features)
    raising = tuple(c for c in contribs if c.contribution > 0)[:3]
    steps, leaf, n = tree_path(models.field, x, features)
    if err.flagged:
        note = ("The model flagged this record because of the signals listed. This says why the model raised the flag, "
                "not what the error is. Recheck the suggested field.")
    else:
        note = "The model did not flag this record. Contributions are shown for audit."
    return FlagTrace(
        flagged=err.flagged, probability=err.probability, threshold=models.threshold, bias=models.error.bias,
        logit=logit, contributions=tuple(contribs), top_raising=raising,
        suggested_field=err.suggested_field, field_probability=err.field_probability,
        tree_path=tuple(steps), leaf_distribution=dict(leaf), leaf_size=n, model_version=models.version, note=note)


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))
