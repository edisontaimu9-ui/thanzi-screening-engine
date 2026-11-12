"""Deterministic under-five screening of one child record: classification, indicator panel, longitudinal growth.

Independent of machine learning: this module never imports or reads any prediction output. The CMAM classification
is produced by thanzi_screen.rules exactly as the API produces it, from the latest visit.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from ..anthro import compute_anthropometry
from ..factors import ChildRecord, completeness
from ..rules import OedemaGrade, classify
from ..rules.models import ClinicalInputs
from .indicators import IndicatorPanel, compute_panel
from .longitudinal import FalteringConfig, LongitudinalResult, analyse_growth

MODULE = "deterministic_screening"
MODULE_VERSION = "under5_screening_0.1"
WARN_PRETERM = ("Preterm or low birth weight is recorded. This module uses chronological age and does not apply "
                "corrected age. Use the preterm routing of POST /v1/screen for babies under 50 weeks post-menstrual age.")
WARN_NO_HISTORY = "Only one usable visit: growth velocity and faltering cannot be assessed."


@dataclass(frozen=True)
class Under5Screening:
    module: str
    version: str
    status: str                       # ok | recheck_measurements
    classification: dict
    indicators: IndicatorPanel
    longitudinal: LongitudinalResult
    factor_completeness: dict
    warnings: tuple[str, ...]
    advisory: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["warnings"] = list(self.warnings)
        return d


def _clinical(record: ChildRecord) -> ClinicalInputs:
    v = record.latest
    return ClinicalInputs(oedema=v.oedema, muac_cm=v.muac_cm, appetite=v.appetite, danger_signs=v.danger_signs,
                          complications=v.complications, clinically_well_and_alert=v.clinically_well_and_alert)


def screen_record(record: ChildRecord, config: FalteringConfig | None = None) -> Under5Screening:
    v = record.latest
    cl = _clinical(record)
    anthro = compute_anthropometry(sex=record.sex, weight_kg=v.weight_kg, length_height_cm=v.length_height_cm,
                                   measure_position=v.measure_position, age_days=v.age_days,
                                   oedema=v.oedema is not OedemaGrade.NONE)
    result = classify(anthro, cl)
    panel = compute_panel(record.sex, v)
    growth = analyse_growth(record, config)
    warnings = list(result.warnings)
    d = record.demographic
    if (d.gestational_age_weeks is not None and d.gestational_age_weeks < 37) or (
            d.birth_weight_g is not None and d.birth_weight_g < 2500):
        warnings.append(WARN_PRETERM)
    if growth.visits_used < 2:
        warnings.append(WARN_NO_HISTORY)
    classification = {
        "classification": result.classification.value, "tier": result.tier.value, "programme": result.programme,
        "rules_fired": list(result.rules_fired), "reasons": list(result.reasons), "referral_text": result.referral_text,
        "rule_set_version": result.rule_set_version, "disclaimer": result.disclaimer,
    }
    status = "recheck_measurements" if (panel.any_implausible or result.tier.value == "recheck") else "ok"
    return Under5Screening(MODULE, MODULE_VERSION, status, classification, panel, growth, completeness(record),
                           tuple(warnings), result.disclaimer)
