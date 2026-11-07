"""Input and output types for the rules module."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OedemaGrade(str, Enum):
    NONE = "none"
    PLUS = "+"
    PLUS_PLUS = "++"
    PLUS_PLUS_PLUS = "+++"


class Appetite(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_DONE = "not_done"


class DangerSign(str, Enum):
    """CMAM 2016 Table 5, p.16."""
    ANOREXIA = "anorexia"
    INTRACTABLE_VOMITING = "intractable_vomiting"
    CONVULSIONS = "convulsions"
    LETHARGY_NOT_ALERT = "lethargy_not_alert"
    UNCONSCIOUSNESS = "unconsciousness"
    UNABLE_TO_DRINK_OR_BREASTFEED = "unable_to_drink_or_breastfeed"
    HIGH_FEVER = "high_fever"  # >39 C rectal or >38.5 C axillary


class Complication(str, Enum):
    """CMAM 2016 Table 5, p.16."""
    HYPOGLYCAEMIA = "hypoglycaemia"
    HYPOTHERMIA = "hypothermia"  # <35 C axillary or <35.5 C rectal
    INFECTIONS = "infections"
    SEVERE_DEHYDRATION = "severe_dehydration"
    SHOCK = "shock"
    VERY_SEVERE_ANAEMIA = "very_severe_anaemia"
    CARDIAC_FAILURE = "cardiac_failure"
    SEVERE_DERMATOSIS = "severe_dermatosis"
    VITAMIN_A_DEFICIENCY_SIGNS = "vitamin_a_deficiency_signs"
    DIARRHOEA = "diarrhoea"
    MALARIA = "malaria"


class Classification(str, Enum):
    LOW_RISK = "low_risk"
    MAM = "MAM"
    SAM_OTP = "SAM_OTP"
    SAM_INPATIENT = "SAM_INPATIENT"
    SAM_ASSESS = "SAM_ASSESS"  # urgent assessment: determine OTP vs inpatient
    UNABLE_TO_CLASSIFY = "UNABLE_TO_CLASSIFY"  # recheck measurements / missing inputs


class Tier(str, Enum):
    LOW_RISK = "low_risk"
    MAM = "mam"
    URGENT = "urgent"
    RECHECK = "recheck"


@dataclass(frozen=True)
class ClinicalInputs:
    """Clinical findings entered by the user. None means unknown / not assessed.

    danger_signs / complications: empty frozenset = assessed, none present; None = not assessed.
    """
    oedema: OedemaGrade = OedemaGrade.NONE
    muac_cm: float | None = None  # 6-59 months only (D2)
    appetite: Appetite = Appetite.NOT_DONE
    danger_signs: frozenset[DangerSign] | None = None
    complications: frozenset[Complication] | None = None
    clinically_well_and_alert: bool | None = None
    hiv_positive: bool | None = None  # optional, sensitive (D7)
    # Infants under 6 months (CMAM 2016 Table 5 column B)
    visible_severe_wasting: bool | None = None
    too_weak_to_suckle: bool | None = None
    failure_to_gain_weight: bool | None = None


@dataclass(frozen=True)
class ClassificationResult:
    classification: Classification
    tier: Tier
    programme: str | None  # "NRU", "OTP", "SFP" or None
    rules_fired: tuple[str, ...]
    reasons: tuple[str, ...]  # why unable to classify / assessment needed
    warnings: tuple[str, ...]
    referral_text: str
    rule_set_version: str
    disclaimer: str
