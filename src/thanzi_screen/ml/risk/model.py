"""The risk model as shipped: one JSON file holding the model, its calibration, operating point, eligibility range,
target definition and provenance. Refused (fail closed) unless every part is present and valid.

A model trained on simulated outcomes is marked `provenance: simulated` and `clinical_use: false`. It is refused
unless the caller explicitly allows simulated models. A model trained on real data is refused unless its governance
fields (ethics approval, data agreement, clinical sign-off) are filled in.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..models import LogisticModel
from .errors import RiskModelError
from .features import RISK_FEATURES
from .trees import TreeEnsemble, logit, sigmoid

SCHEMA = "thanzi-risk-model/1"
MODEL_FILE = "risk_model.json"
DEFAULT_DIR = Path(__file__).resolve().parents[4] / "models" / "risk"
GOVERNANCE_FIELDS = ("ethics_ref", "data_agreement_ref", "clinical_signoff")
KINDS = ("logistic", "gbm_logit", "rf_prob")


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


class RiskModel:
    def __init__(self, spec: dict):
        if not isinstance(spec, dict) or spec.get("schema") != SCHEMA:
            raise RiskModelError("not a risk model file")
        try:
            self.version = str(spec["version"])
            self.kind = spec["kind"]
            self.provenance = spec["provenance"]
            self.clinical_use = spec["clinical_use"]
            self.target = dict(spec["target"])
            cal, self.threshold = spec["calibration"], spec["threshold"]
            self.platt_a, self.platt_b = cal["a"], cal["b"]
            self.age_months_range = (float(spec["eligibility"]["age_months_min"]), float(spec["eligibility"]["age_months_max"]))
            model_spec = spec["model"]
        except (KeyError, TypeError, ValueError):
            raise RiskModelError("risk model file is missing a required part") from None
        self.spec = spec
        if self.kind not in KINDS:
            raise RiskModelError("unknown model kind")
        if self.provenance not in ("simulated", "real") or not isinstance(self.clinical_use, bool):
            raise RiskModelError("provenance or clinical_use is invalid")
        if self.provenance == "simulated" and self.clinical_use:
            raise RiskModelError("a model trained on simulated outcomes can never be marked for clinical use")
        if self.provenance == "real":
            gov = spec.get("governance") or {}
            if not all(isinstance(gov.get(k), str) and gov[k].strip() for k in GOVERNANCE_FIELDS):
                raise RiskModelError("a model trained on real data needs ethics, data agreement and clinical sign-off references")
            acc = spec.get("acceptance") or {}
            if acc.get("set") is not True or acc.get("passed") is not True:
                raise RiskModelError("a model trained on real data needs acceptance thresholds that were set in advance and passed")
        for k in ("name", "plain"):
            if not isinstance(self.target.get(k), str) or not self.target[k]:
                raise RiskModelError("target needs a name and a plain-language description")
        if not isinstance(self.target.get("horizon_weeks"), int) or self.target["horizon_weeks"] <= 0:
            raise RiskModelError("target needs a horizon in whole weeks")
        if not (_finite(self.platt_a) and _finite(self.platt_b)) or self.platt_a <= 0:
            raise RiskModelError("calibration must be finite with a positive slope (it must keep the order of the risks)")
        if not _finite(self.threshold) or not (0.0 < self.threshold < 1.0):
            raise RiskModelError("threshold must be between 0 and 1")
        if not (0.0 <= self.age_months_range[0] < self.age_months_range[1] <= 60.0):
            raise RiskModelError("eligibility age range is invalid")
        if not isinstance(model_spec, dict):
            raise RiskModelError("model part is invalid")
        if self.kind == "logistic":
            if model_spec.get("type") != "logistic":
                raise RiskModelError("model part does not match kind")
            m = LogisticModel.from_dict(model_spec)
            if m.names != list(RISK_FEATURES) or not all(_finite(v) for v in (*m.mean, *m.std, *m.coef, m.bias)) or min(m.std) <= 0:
                raise RiskModelError("logistic model is invalid")
            self.model = m
        else:
            m = TreeEnsemble.from_dict(model_spec)
            if m.kind != self.kind:
                raise RiskModelError("model part does not match kind")
            self.model = m
        if list(self.model.names) != list(RISK_FEATURES):
            raise RiskModelError("model features do not match this version of the service")

    @property
    def simulated(self) -> bool:
        return self.provenance == "simulated"

    def _raw(self, x) -> float:
        """Raw probability from the model before calibration."""
        if self.kind == "logistic":
            return self.model.predict_proba(x)
        return self.model.probability(x)

    def probability(self, x) -> tuple[float, float]:
        """(raw probability, calibrated probability). Calibration is Platt scaling with a positive slope: order kept."""
        raw = self._raw(x)
        return raw, sigmoid(self.platt_a * logit(raw) + self.platt_b)

    def elevated(self, x) -> tuple[bool, float, float]:
        raw, p = self.probability(x)
        return p >= self.threshold, raw, p

    def contributions(self, x) -> tuple[float, list[float], str]:
        """(baseline, per-feature contribution, unit). baseline + sum(contributions) equals the raw model output
        (a logit for logistic and gradient boosting, a probability for random forest). Exact for these models."""
        if self.kind == "logistic":
            parts = [c * (v - m) / s for c, v, m, s in zip(self.model.coef, x, self.model.mean, self.model.std)]
            return self.model.bias, parts, "logit"
        base, phi = self.model.contributions(x)
        return base, phi, "logit" if self.kind == "gbm_logit" else "probability"

    def summary(self) -> dict:
        return {"version": self.version, "kind": self.kind, "provenance": self.provenance,
                "clinical_use": self.clinical_use, "target": self.target["name"], "horizon_weeks": self.target["horizon_weeks"]}


def load_risk_model(directory=None, allow_simulated: bool = False) -> RiskModel:
    path = Path(directory or DEFAULT_DIR) / MODEL_FILE
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise RiskModelError("risk model file missing or unreadable") from None
    model = RiskModel(spec)
    if model.simulated and not allow_simulated:
        raise RiskModelError("this risk model was trained on simulated outcomes: refused (set THANZI_RISK_ALLOW_SIMULATED=1 for demonstration only)")
    return model
