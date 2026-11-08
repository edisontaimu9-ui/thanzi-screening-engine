"""Inference with the deep models: advisory flags for one record, and a side-by-side with the Phase 4 models.
Pure Python, offline. Never alters a classification (D9)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ...rules import ClinicalInputs, review
from ..features import FEATURES, FIELDS, features_from_inputs, vector
from ..flags import DEFAULT_MODELS_DIR, FIELD_MESSAGES, ErrorFlag, MlFlags, Models
from .network import Network

ERROR_FILE, FIELD_FILE = "recording_error_mlp.json", "recording_field_mlp.json"


@dataclass(frozen=True)
class DeepModels:
    error: Network
    threshold: float
    field: Network
    version: str


@dataclass(frozen=True)
class ModelComparison:
    """Phase 4 logistic flag and deep flag for the same record. Disagreement is a reason to look, not a result."""
    logistic: ErrorFlag
    deep: ErrorFlag
    agree: bool
    mean_probability: float
    advisory: str = "Advisory only. It does not change the classification. A trained health worker decides."


def load_deep_models(directory=None) -> DeepModels:
    d = Path(directory or DEFAULT_MODELS_DIR)
    a = json.loads((d / ERROR_FILE).read_text())
    f = json.loads((d / FIELD_FILE).read_text())
    for obj in (a, f):
        if tuple(obj["metadata"]["feature_names"]) != FEATURES:
            raise ValueError("model feature list does not match this code version; retrain")
    err, fld = Network.from_dict(a["model"]), Network.from_dict(f["model"])
    if err.classes is not None or fld.classes is None or tuple(fld.classes) != FIELDS:
        raise ValueError("deep model files do not have the expected outputs; retrain")
    return DeepModels(err, a["threshold"], fld, a["metadata"]["version"])


def _error_flag(x, net: Network, threshold: float, field_net: Network) -> ErrorFlag:
    p = net.predict_proba(x)
    flagged = p >= threshold
    field = fprob = None
    messages: tuple[str, ...] = ()
    if flagged:
        field, fprob = max(field_net.predict_dist(x).items(), key=lambda kv: kv[1])
        messages = (FIELD_MESSAGES[field],)
    return ErrorFlag(flagged, p, field, fprob, messages, net.top_signals(x) if flagged else ())


def flag_record_deep(sex: str, age_days: int, weight_kg: float, length_height_cm: float, measure_position: str,
                     clinical: ClinicalInputs, models: DeepModels) -> MlFlags:
    """Same output shape as `flag_record`, from the deep models."""
    f, anthro, result = features_from_inputs(sex, age_days, weight_kg, length_height_cm, measure_position, clinical)
    x = vector(f)
    err = _error_flag(x, models.error, models.threshold, models.field)
    rev = review(anthro, result, clinical.muac_cm, clinical.oedema.value != "none")
    return MlFlags(err, rev, models.version)


def compare_record(sex: str, age_days: int, weight_kg: float, length_height_cm: float, measure_position: str,
                   clinical: ClinicalInputs, logistic: Models, deep: DeepModels) -> ModelComparison:
    """Run both model families on one record. Features are computed once."""
    f, _, _ = features_from_inputs(sex, age_days, weight_kg, length_height_cm, measure_position, clinical)
    x = vector(f)
    p = logistic.error.predict_proba(x)
    lr_flag = ErrorFlag(p >= logistic.threshold, p, None, None, (), ())
    if lr_flag.flagged:
        field, fprob = max(logistic.field.predict_dist(x).items(), key=lambda kv: kv[1])
        lr_flag = ErrorFlag(True, p, field, fprob, (FIELD_MESSAGES[field],), logistic.error.top_signals(x))
    dl_flag = _error_flag(x, deep.error, deep.threshold, deep.field)
    return ModelComparison(lr_flag, dl_flag, lr_flag.flagged == dl_flag.flagged, (lr_flag.probability + dl_flag.probability) / 2)
