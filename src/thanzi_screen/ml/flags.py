"""Inference: advisory flags for one record. Pure Python, offline. Never alters a classification."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..rules import ClinicalInputs, ReviewResult, review
from .features import FEATURES, features_from_inputs, vector
from .models import LogisticModel, TreeModel

DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
ADVISORY = "Advisory flag only. It does not change the classification. A trained health worker decides."
FIELD_MESSAGES = {
    "weight": "Recheck the weight (possible decimal or unit slip).",
    "length_height": "Recheck the length or height (possible digit slip).",
    "muac": "Recheck the MUAC (possible unit slip, cm versus mm).",
    "age": "Check the child's age (it may be rounded or guessed).",
}


@dataclass(frozen=True)
class ErrorFlag:
    flagged: bool
    probability: float
    suggested_field: str | None
    field_probability: float | None
    messages: tuple[str, ...]
    top_signals: tuple[str, ...]


@dataclass(frozen=True)
class MlFlags:
    recording_error: ErrorFlag       # ML (target A)
    review: ReviewResult             # rules-based (target B)
    model_version: str
    advisory: str = ADVISORY


@dataclass(frozen=True)
class Models:
    error: LogisticModel
    threshold: float
    field: TreeModel
    version: str


def load_models(directory=None) -> Models:
    d = Path(directory or DEFAULT_MODELS_DIR)
    a = json.loads((d / "recording_error_lr.json").read_text())
    f = json.loads((d / "recording_field_tree.json").read_text())
    for obj in (a, f):
        if tuple(obj["metadata"]["feature_names"]) != FEATURES:
            raise ValueError("model feature list does not match this code version; retrain")
    return Models(LogisticModel.from_dict(a["model"]), a["threshold"], TreeModel.from_dict(f["model"]), a["metadata"]["version"])


def flag_record(sex: str, age_days: int, weight_kg: float, length_height_cm: float, measure_position: str,
                clinical: ClinicalInputs, models: Models) -> MlFlags:
    f, anthro, result = features_from_inputs(sex, age_days, weight_kg, length_height_cm, measure_position, clinical)
    x = vector(f)
    p = models.error.predict_proba(x)
    flagged = p >= models.threshold
    field = fprob = None
    messages: tuple[str, ...] = ()
    if flagged:
        dist = models.field.predict_dist(x)
        field, fprob = max(dist.items(), key=lambda kv: kv[1])
        messages = (FIELD_MESSAGES[field],)
    err = ErrorFlag(flagged, p, field, fprob, messages, models.error.top_signals(x) if flagged else ())
    rev = review(anthro, result, clinical.muac_cm, clinical.oedema.value != "none")
    return MlFlags(err, rev, models.version)
