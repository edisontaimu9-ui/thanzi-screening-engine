"""Injected recording errors. The label `injected_error` is ground truth for ML target A."""
from __future__ import annotations

DAYS_PER_MONTH = 30.4375
ERROR_TYPES = ("weight_decimal_shift", "length_digit_transposition", "muac_unit_error", "age_heaping")


def inject(rng, cfg, rec: dict) -> tuple[dict, str]:
    """Return (recorded values, error label). rec has age_days, weight_kg, length_height_cm, muac_cm."""
    out = dict(rec)
    if rng.random() >= cfg.p_error:
        return out, "none"
    kind = rng.choice(ERROR_TYPES)
    if kind == "weight_decimal_shift":
        out["weight_kg"] = round(rec["weight_kg"] * 10 if rng.random() < 0.5 else rec["weight_kg"] / 10, 2)
    elif kind == "length_digit_transposition":
        whole = int(rec["length_height_cm"])
        s = str(whole)
        if len(s) >= 2:
            swapped = int(s[:-2] + s[-1] + s[-2])
            out["length_height_cm"] = round(swapped + (rec["length_height_cm"] - whole), 1)
    elif kind == "muac_unit_error":
        if rec["muac_cm"] is not None:
            out["muac_cm"] = round(rec["muac_cm"] * 10, 1)
    elif kind == "age_heaping":
        months = rec["age_days"] / DAYS_PER_MONTH
        out["age_days"] = min(1856, max(0, int(round(round(months / 6) * 6 * DAYS_PER_MONTH))))
    if out == rec or out["weight_kg"] <= 0 or out["length_height_cm"] <= 0:
        return dict(rec), "none"
    return out, kind
