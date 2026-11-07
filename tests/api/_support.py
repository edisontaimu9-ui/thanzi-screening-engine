"""Shared helpers for the API tests. Framework-free except `need_api`."""
from __future__ import annotations

import importlib.util
import os

import pytest

from thanzi_screen.rules import ClinicalInputs


def need_api() -> None:
    """Call at the top of a module that needs FastAPI. In CI (THANZI_REQUIRE_API_TESTS=1) a missing
    dependency fails the run instead of skipping (D84)."""
    missing = [m for m in ("fastapi", "pydantic", "httpx") if importlib.util.find_spec(m) is None]
    if not missing:
        return
    if os.environ.get("THANZI_REQUIRE_API_TESTS") == "1":
        pytest.fail("API tests are required but not installed: " + ", ".join(missing), pytrace=False)
    pytest.skip("FastAPI test dependencies not installed: " + ", ".join(missing), allow_module_level=True)


def clinical_payload(c: ClinicalInputs) -> dict:
    return {
        "oedema": c.oedema.value, "muac_cm": c.muac_cm, "appetite": c.appetite.value,
        "danger_signs": None if c.danger_signs is None else sorted(d.value for d in c.danger_signs),
        "complications": None if c.complications is None else sorted(d.value for d in c.complications),
        "clinically_well_and_alert": c.clinically_well_and_alert, "hiv_positive": c.hiv_positive,
        "visible_severe_wasting": c.visible_severe_wasting, "too_weak_to_suckle": c.too_weak_to_suckle,
        "failure_to_gain_weight": c.failure_to_gain_weight,
    }


def record_payload(sex, age_days, weight_kg, length_height_cm, position, clinical: ClinicalInputs) -> dict:
    return {"sex": sex, "age_days": age_days, "weight_kg": weight_kg, "length_height_cm": length_height_cm,
            "measure_position": position, **clinical_payload(clinical)}


READY = dict(appetite="passed", danger_signs=[], complications=[], clinically_well_and_alert=True)
# Child pathway, MUAC in the moderate band, everything else normal: MAM by MUAC.
MAM_BASE = {"sex": "male", "age_days": 500, "weight_kg": 11.0, "length_height_cm": 80.0,
            "measure_position": "length", "oedema": "none", "muac_cm": 12.0, **READY}
SAM_BASE = {**MAM_BASE, "muac_cm": 11.0}
LOW_BASE = {**MAM_BASE, "muac_cm": 14.0}
