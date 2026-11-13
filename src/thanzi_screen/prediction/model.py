"""The prediction model as shipped: ONE JSON file per target holding the preprocessor, the model, its calibration, the risk
strata cut-offs, the eligibility range, the target definition and the provenance. Standard library only. Refused (fail closed)
unless every part is present and valid.

A model trained on simulated outcomes is marked `provenance: simulated` and `clinical_use: false`. It is refused unless the
caller explicitly allows simulated models. A model trained on real data is refused unless ethics, data agreement and clinical
sign-off references are filled in AND acceptance thresholds were set in advance and passed.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from .errors import PredictionModelError
from .features import FEATURE_NAMES
from .preprocess import PreprocessError, Preprocessor, UnseenMissingError
from .trees import TreeEnsemble, logit, sigmoid

log = logging.getLogger("thanzi.api")
SCHEMA = "thanzi-prediction-model/1"
GOVERNANCE_FIELDS = ("ethics_ref", "data_agreement_ref", "clinical_signoff")
KINDS = ("logistic", "gbm_logit", "rf_prob")
STRATA = ("elevated", "high")           # no stratum below "elevated": the model never says a child is low risk
MAX_FILE_BYTES = 50_000_000

# Codes for "not scored". Stable: integrators may translate them.
NOT_SCORED = {
    "age_outside_model_range": "The child's age is outside the range the prediction model was built for.",
    "essential_input_unavailable": "An input that is essential for this prediction pathway was not available.",
    "too_many_missing_inputs": "Too many inputs were not recorded for the prediction model to be used.",
    "gap_never_seen_in_training": "An input is missing that was always recorded in the data the model learned from.",
    "invalid_input": "The record could not be turned into valid inputs.",
    "model_error": "The prediction model could not run. Screening is not affected.",
}

DEFAULT_REQUIRED = ("age_months", "sex_male", "waz", "haz", "whz", "oedema_present")   # anthropometric pathway minimum


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class PredictionModel:
    def __init__(self, spec: dict):
        if not isinstance(spec, dict) or spec.get("schema") != SCHEMA:
            raise PredictionModelError("not a prediction model file")
        try:
            self.version = str(spec["version"])
            self.kind = spec["kind"]
            self.provenance = spec["provenance"]
            self.clinical_use = spec["clinical_use"]
            self.target = dict(spec["target"])
            cal = spec["calibration"]
            self.platt_a, self.platt_b = cal["a"], cal["b"]
            self.cutoffs = {k: spec["strata"]["cutoffs"][k] for k in STRATA}
            self.age_months_range = (float(spec["eligibility"]["age_months_min"]), float(spec["eligibility"]["age_months_max"]))
            self.max_missing_features = spec["safeguards"]["max_missing_features"]     # what training saw: a record, no longer a gate
            pathway = spec.get("pathway") or {}
            self.pathway = str(pathway.get("name", "full"))
            self.required_features = tuple(pathway.get("required_features", DEFAULT_REQUIRED))
            pre_spec, model_spec = spec["preprocessor"], spec["model"]
        except (KeyError, TypeError, ValueError):
            raise PredictionModelError("prediction model file is missing a required part") from None
        self.spec = spec
        if self.kind not in KINDS:
            raise PredictionModelError("unknown model kind")
        if self.provenance not in ("simulated", "real") or not isinstance(self.clinical_use, bool):
            raise PredictionModelError("provenance or clinical_use is invalid")
        if self.provenance == "simulated" and self.clinical_use:
            raise PredictionModelError("a model trained on simulated data can never be marked for clinical use")
        if self.provenance == "real":
            gov = spec.get("governance") or {}
            if not all(isinstance(gov.get(k), str) and gov[k].strip() for k in GOVERNANCE_FIELDS):
                raise PredictionModelError("a model trained on real data needs ethics, data agreement and clinical sign-off references")
            acc = spec.get("acceptance") or {}
            if acc.get("set") is not True or acc.get("passed") is not True:
                raise PredictionModelError("a model trained on real data needs acceptance thresholds that were set in advance and passed")
        for k in ("name", "plain"):
            if not isinstance(self.target.get(k), str) or not self.target[k]:
                raise PredictionModelError("target needs a name and a plain-language description")
        for k in ("horizon_min_days", "horizon_max_days"):
            if not isinstance(self.target.get(k), int) or isinstance(self.target[k], bool) or self.target[k] <= 0:
                raise PredictionModelError("target needs a horizon in whole days")
        if self.target["horizon_min_days"] >= self.target["horizon_max_days"]:
            raise PredictionModelError("target horizon is invalid")
        if not (_finite(self.platt_a) and _finite(self.platt_b)) or self.platt_a <= 0:
            raise PredictionModelError("calibration must be finite with a positive slope (it must keep the order of the risks)")
        lo, hi = self.cutoffs["elevated"], self.cutoffs["high"]
        if not (_finite(lo) and _finite(hi)) or not (0.0 < lo <= hi < 1.0):
            raise PredictionModelError("strata cut-offs must satisfy 0 < elevated <= high < 1")
        if not (0.0 <= self.age_months_range[0] < self.age_months_range[1] <= 60.0):
            raise PredictionModelError("eligibility age range is invalid")
        if not isinstance(self.max_missing_features, int) or isinstance(self.max_missing_features, bool) \
                or not (0 <= self.max_missing_features < len(FEATURE_NAMES)):
            raise PredictionModelError("max_missing_features is invalid")
        if not self.required_features or any(n not in FEATURE_NAMES for n in self.required_features):
            raise PredictionModelError("pathway required_features must name known features")
        try:
            self.pre = Preprocessor.from_dict(pre_spec)
        except (PreprocessError, KeyError, TypeError):
            raise PredictionModelError("preprocessor part is invalid") from None
        self.columns = list(self.pre.columns)
        if any(n not in self.pre.names for n in self.required_features):
            raise PredictionModelError("a required input is not one of the model's inputs")
        if not isinstance(model_spec, dict):
            raise PredictionModelError("model part is invalid")
        if self.kind == "logistic":
            self.model = self._check_logistic(model_spec)
        else:
            m = TreeEnsemble.from_dict(model_spec)
            if m.kind != self.kind:
                raise PredictionModelError("model part does not match kind")
            self.model = m
        if list(self.model.names if self.kind != "logistic" else model_spec["names"]) != self.columns:
            raise PredictionModelError("model columns do not match the preprocessor")

    def _check_logistic(self, m: dict) -> dict:
        n = len(self.columns)
        if m.get("type") != "logistic":
            raise PredictionModelError("model part does not match kind")
        for key in ("coef", "column_mean"):
            v = m.get(key)
            if not isinstance(v, list) or len(v) != n or not all(_finite(x) for x in v):
                raise PredictionModelError("logistic model is invalid")
        if not _finite(m.get("bias")):
            raise PredictionModelError("logistic model is invalid")
        return {"names": list(m["names"]), "coef": [float(x) for x in m["coef"]], "bias": float(m["bias"]),
                "column_mean": [float(x) for x in m["column_mean"]]}

    @property
    def simulated(self) -> bool:
        return self.provenance == "simulated"

    # ---- scoring ----
    def raw_output(self, x) -> float:
        """Logit for logistic and gradient boosting, probability for random forest."""
        if self.kind == "logistic":
            return self.model["bias"] + sum(c * v for c, v in zip(self.model["coef"], x))
        return self.model.raw_output(x)

    def _raw_probability(self, x) -> float:
        out = self.raw_output(x)
        if self.kind == "rf_prob":
            return min(1.0, max(0.0, out))
        return sigmoid(out)

    def probability(self, x) -> tuple[float, float]:
        """(raw probability, calibrated probability). Calibration is Platt scaling with a positive slope: order kept."""
        raw = self._raw_probability(x)
        return raw, sigmoid(self.platt_a * logit(raw) + self.platt_b)

    def stratum(self, p: float) -> str | None:
        """'high', 'elevated' or None. None means no extra concern was found, which is NOT the same as low risk."""
        if p >= self.cutoffs["high"]:
            return "high"
        if p >= self.cutoffs["elevated"]:
            return "elevated"
        return None

    def check_inputs(self, features: dict) -> str | None:
        """A not-scored reason code, or None when the row may be scored. Nothing is imputed silently."""
        age = features.get("age_months")
        if age is None or not (self.age_months_range[0] <= age < self.age_months_range[1]):
            return "age_outside_model_range"
        if any(features.get(n) is None for n in self.required_features):
            return "essential_input_unavailable"
        return None

    def vectorise(self, features: dict) -> list[float]:
        """Preprocessed columns for one row. Raises UnseenMissingError for a gap never seen in training."""
        return self.pre.transform({n: features[n] for n in self.pre.names}, strict_missing=True)     # a pathway uses only its own inputs

    def contributions(self, x) -> tuple[float, list[float], str]:
        """(baseline, per-column contribution, unit). baseline + sum(contributions) equals raw_output(x) exactly, for the
        logistic model (against the training mean of each column) and for TreeSHAP. Unit: logit, or probability for the forest."""
        if self.kind == "logistic":
            m = self.model
            parts = [c * (v - mu) for c, v, mu in zip(m["coef"], x, m["column_mean"])]
            return m["bias"] + sum(c * mu for c, mu in zip(m["coef"], m["column_mean"])), parts, "logit"
        base, phi = self.model.contributions(x)
        return base, phi, "logit" if self.kind == "gbm_logit" else "probability"

    def summary(self) -> dict:
        return {"version": self.version, "kind": self.kind, "provenance": self.provenance, "clinical_use": self.clinical_use,
                "target": self.target["name"], "horizon_days": [self.target["horizon_min_days"], self.target["horizon_max_days"]]}


def load_prediction_model(path, allow_simulated: bool = False) -> PredictionModel:
    p = Path(path)
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            raise PredictionModelError("prediction model file is too large")
        spec = json.loads(p.read_text(encoding="utf-8"))
    except PredictionModelError:
        raise
    except (OSError, ValueError):
        raise PredictionModelError("prediction model file missing or unreadable") from None
    model = PredictionModel(spec)
    if model.simulated and not allow_simulated:
        raise PredictionModelError("this prediction model was trained on simulated data: refused (allow simulated models for demonstration only)")
    return model


def load_prediction_models(where: str | None, allow_simulated: bool = False) -> tuple[list[PredictionModel], int]:
    """(models, number refused). `where` is one file, a folder of exported files, or a comma-separated list. Each file stands alone: one
    that is refused or unreadable is counted and skipped, never a failed start. Put the fullest pathway first when covering one target twice."""
    paths: list[Path] = []
    for part in (where or "").split(","):
        if not part.strip():
            continue
        p = Path(part.strip())
        paths += sorted(q for q in p.glob("*.json") if q.name != "results.json") if p.is_dir() else [p]
    # a target's full-pathway file ahead of its other pathways, so it is tried first
    paths.sort(key=lambda q: q.name.count("."))
    models, refused = [], 0
    for q in paths:
        try:
            models.append(load_prediction_model(q, allow_simulated))
        except Exception as exc:        # type only: never the message
            log.warning("Prediction model file refused (%s).", type(exc).__name__)
            refused += 1
    return models, refused


__all__ = ["load_prediction_models", "GOVERNANCE_FIELDS", "KINDS", "NOT_SCORED", "PredictionModel", "SCHEMA", "STRATA", "UnseenMissingError",
           "load_prediction_model"]
