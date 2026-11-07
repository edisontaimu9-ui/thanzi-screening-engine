"""Record schema, encoding and decoding."""
from __future__ import annotations

from ..rules import Appetite, ClinicalInputs, Complication, DangerSign, OedemaGrade


class DataError(ValueError):
    """Dataset failed validation, or is not synthetic."""


COLUMNS = (
    "child_id", "is_synthetic", "record_type", "split", "district", "sex", "age_days", "measure_position",
    "weight_kg", "length_height_cm", "muac_cm", "oedema", "appetite", "danger_signs", "complications",
    "clinically_well_and_alert", "hiv_positive", "visible_severe_wasting", "too_weak_to_suckle",
    "failure_to_gain_weight",
    # ground truth (before injected errors)
    "true_age_days", "true_weight_kg", "true_length_height_cm", "true_muac_cm", "true_lhfa_z", "true_wflh_z",
    "injected_error",
    # engine outputs computed from the recorded values (Phase 1 and Phase 2, never re-implemented)
    "wfa_z", "lhfa_z", "wflh_z", "cmam_class", "tier", "programme", "rules_fired",
    # ML target B: constructed from the engine outputs, see docs/modules/data.md
    "review_needed", "review_reasons",
)

# Column names that must never appear (identifiers, dates of birth, fine geography)
FORBIDDEN_COLUMNS = frozenset({
    "name", "first_name", "last_name", "dob", "date_of_birth", "birth_date", "phone", "address", "village",
    "gps", "latitude", "longitude", "lat", "lon", "facility", "community", "nrc", "national_id", "email",
})

FLOAT_FORMATS = {
    "weight_kg": ".2f", "true_weight_kg": ".2f", "length_height_cm": ".1f", "true_length_height_cm": ".1f",
    "muac_cm": ".1f", "true_muac_cm": ".1f", "true_lhfa_z": ".4f", "true_wflh_z": ".4f",
    "wfa_z": ".4f", "lhfa_z": ".4f", "wflh_z": ".4f",
}
SPLITS = ("train", "val", "test", "boundary")


def enc_bool(v: bool | None, na: bool = False) -> str:
    """true/false; 'unknown' when not assessed; '' when not applicable."""
    if na:
        return ""
    return "unknown" if v is None else ("true" if v else "false")


def dec_bool(s: str) -> bool | None:
    return None if s in ("", "unknown") else s == "true"


def enc_set(v) -> str:
    if v is None:
        return "unknown"
    return "none" if not v else ";".join(sorted(x.value for x in v))


def dec_set(s: str, enum):
    if s == "unknown":
        return None
    return frozenset() if s == "none" else frozenset(enum(x) for x in s.split(";"))


def row_to_inputs(row: dict) -> ClinicalInputs:
    muac = row["muac_cm"]
    return ClinicalInputs(
        oedema=OedemaGrade(row["oedema"]),
        muac_cm=None if muac in (None, "") else float(muac),
        appetite=Appetite(row["appetite"]),
        danger_signs=dec_set(row["danger_signs"], DangerSign),
        complications=dec_set(row["complications"], Complication),
        clinically_well_and_alert=dec_bool(row["clinically_well_and_alert"]),
        hiv_positive=dec_bool(row["hiv_positive"]),
        visible_severe_wasting=dec_bool(row["visible_severe_wasting"]),
        too_weak_to_suckle=dec_bool(row["too_weak_to_suckle"]),
        failure_to_gain_weight=dec_bool(row["failure_to_gain_weight"]),
    )
