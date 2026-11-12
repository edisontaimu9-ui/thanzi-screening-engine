"""SIMULATED outcomes for building and testing the risk pipeline before real data arrives.

NOT CLINICAL. The outcome is drawn from the explicit, assumed formula below, so any model trained on it can only learn
this formula: its accuracy says nothing about real children. Its purpose is to exercise the code (features, training,
calibration, validation, export, explanation, API) end to end. Models trained on it are marked `provenance: simulated`
and are refused by the service unless simulated models are explicitly allowed.
"""
from __future__ import annotations

import math
import random

from ...data import GenConfig
from ...data.generator import generate
from .data import enc_bool, enc_set  # noqa: F401  (re-exported helpers keep the CSV encoding in one place)

PERIODS = ("2025Q1", "2025Q2", "2025Q3", "2025Q4", "2026Q1", "2026Q2")
TARGET = {"name": "simulated_adverse_outcome_8w", "horizon_weeks": 8,
          "plain": "an adverse outcome (simulated, not a real prediction)",
          "definition": "SIMULATED. Bernoulli draw from the assumed formula in thanzi_screen.ml.risk.simulate."}
P_HAS_PREVIOUS = 0.6
TARGET_PREVALENCE = 0.10

# ASSUMED effects in logit units (placeholders, not estimates from any data).
ASSUMPTIONS = {
    "wasting_per_z": 0.8, "stunting_per_z": 0.3, "muac_below_12_5": 0.9, "muac_below_11_5": 0.8, "oedema": 1.2,
    "failed_appetite": 0.9, "failed_appetite_with_low_muac": 0.9, "per_danger_sign": 0.7, "per_complication": 0.5,
    "weight_loss_since_last_visit": 0.8, "gain_per_g_per_day": -0.12, "age_under_12_months": 0.3, "noise_sd": 0.5,
}


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _logit_no_intercept(row: dict, rate: float | None, rng: random.Random) -> float:
    a = ASSUMPTIONS
    zw, zh = row["true_wflh_z"], row["true_lhfa_z"]
    muac = row["true_muac_cm"]
    z = a["wasting_per_z"] * _clip(-zw, -2.0, 4.0) + a["stunting_per_z"] * _clip(-zh, -2.0, 4.0)
    low12 = muac is not None and muac < 12.5
    if muac is not None:
        z += a["muac_below_12_5"] * low12 + a["muac_below_11_5"] * (muac < 11.5)
    z += a["oedema"] * (row["oedema"] != "none")
    failed = row["appetite"] == "failed"
    z += a["failed_appetite"] * failed + a["failed_appetite_with_low_muac"] * (failed and low12)
    signs = row["danger_signs"]
    z += a["per_danger_sign"] * (0 if signs in ("none", "unknown") else len(signs.split(";")))
    comps = row["complications"]
    z += a["per_complication"] * (0 if comps in ("none", "unknown") else len(comps.split(";")))
    if rate is not None:
        z += a["gain_per_g_per_day"] * (rate - 4.5) + a["weight_loss_since_last_visit"] * (rate < 0)
    z += a["age_under_12_months"] * (row["age_days"] < 365)
    return z + rng.gauss(0.0, a["noise_sd"])


def _solve_intercept(base_logits: list[float], target: float) -> float:
    lo, hi = -15.0, 5.0
    for _ in range(60):
        mid = (lo + hi) / 2
        mean = sum(1 / (1 + math.exp(-(mid + z))) for z in base_logits) / len(base_logits)
        lo, hi = (mid, hi) if mean < target else (lo, mid)
    return (lo + hi) / 2


def simulate_rows(n: int = 20_000, seed: int = 7) -> tuple[list[dict], dict]:
    """Return (dataset rows, manifest extras). Deterministic for a given (n, seed)."""
    rows_in = [r for r in generate(GenConfig(n=n, seed=seed)) if r["record_type"] == "random"]
    rng = random.Random(seed + 101)
    staged = []
    for r in rows_in:
        has_prev = rng.random() < P_HAS_PREVIOUS
        rate = prev_age = prev_w = None
        if has_prev:
            interval = rng.randint(21, 56)
            rate = rng.gauss(4.5 + 1.0 * _clip(r["true_wflh_z"], -3.0, 3.0), 3.0)
            prev_age = r["age_days"] - interval
            prev_w = round(r["true_weight_kg"] - rate * interval / 1000.0 + rng.gauss(0, 0.05), 2)
            if prev_age < 0 or prev_w <= 1.0:
                has_prev, rate, prev_age, prev_w = False, None, None, None
        staged.append((r, rate, prev_age, prev_w, _logit_no_intercept(r, rate, rng)))
    intercept = _solve_intercept([s[4] for s in staged], TARGET_PREVALENCE)
    out = []
    for r, rate, prev_age, prev_w, z in staged:
        p = 1 / (1 + math.exp(-(intercept + z)))
        out.append({"child_id": r["child_id"], "district": r["district"], "period": rng.choice(PERIODS), "sex": r["sex"],
                    "age_days": r["age_days"], "measure_position": r["measure_position"], "weight_kg": r["weight_kg"],
                    "length_height_cm": r["length_height_cm"], "muac_cm": r["muac_cm"], "oedema": r["oedema"],
                    "appetite": r["appetite"], "danger_signs": r["danger_signs"], "complications": r["complications"],
                    "clinically_well_and_alert": r["clinically_well_and_alert"], "prev_age_days": prev_age,
                    "prev_weight_kg": prev_w, "outcome": int(rng.random() < p)})
    prevalence = sum(o["outcome"] for o in out) / len(out)
    extra = {"provenance": "simulated", "non_clinical": True, "outcome_simulated": True, "seed": seed, "n_requested": n,
             "target": TARGET, "assumptions": ASSUMPTIONS, "assumed_intercept": round(intercept, 4),
             "observed_prevalence": round(prevalence, 4),
             "note": "SIMULATED outcomes from an assumed formula. For pipeline testing only. Says nothing about real children."}
    return out, extra
