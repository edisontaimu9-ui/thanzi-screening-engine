"""ML feature row for preterm / low-birth-weight babies: the preterm engine's `features()` (Fenton 2025 z-scores).

Kept apart from `features.FEATURES` on purpose: `load_models()` refuses any model whose feature list differs from
`FEATURES`, so adding columns there would put every existing model into degraded mode. No model uses these columns yet.

Two rules for whoever trains on them:
- `rule_level` is the rule engine's own referral level. It is never a training label, and it is left out of the
  numeric vector (`PRETERM_FEATURES`) so it cannot leak in as a feature either. Labels must come from reviewed
  clinical outcomes or recording-error annotations, never from `screen()`.
- Missing values: `features()` gives NaN. Like the under-5 pipeline, `preterm_vector` turns NaN into 0.0 and adds a
  `*_missing` indicator so the plain-Python models never see NaN.
"""
from __future__ import annotations

import math

from ..preterm import PretermInput, features as _features

RULE_DERIVED = ("rule_level",)                     # context only; never a label, never in the vector
_SAMPLE = PretermInput(sex="female", ga_weeks=30.0, birth_weight_g=1300, age_days=10, weight_g=1300)
ROW_COLUMNS = tuple(_features(_SAMPLE))             # every column features() returns, in its order
PRETERM_FEATURES = tuple(c for c in ROW_COLUMNS if c not in RULE_DERIVED)
_MAYBE_MISSING = tuple(c for c in PRETERM_FEATURES if c.startswith(("z_", "dz_")) or c == "weight_g")
PRETERM_VECTOR_COLUMNS = PRETERM_FEATURES + tuple(f"{c}_missing" for c in _MAYBE_MISSING)
FORBIDDEN_LABEL_COLUMNS = RULE_DERIVED + ("referral_level", "preterm_level", "tier")


def preterm_row(i: PretermInput) -> dict:
    """The engine's own feature row, unchanged (NaN where unavailable)."""
    return _features(i)


def preterm_vector(row: dict) -> list[float]:
    """Numeric vector in `PRETERM_VECTOR_COLUMNS` order. NaN becomes 0.0 plus a missing indicator."""
    isnan = lambda v: isinstance(v, float) and math.isnan(v)
    base = [0.0 if isnan(row[c]) else float(row[c]) for c in PRETERM_FEATURES]
    return base + [float(isnan(row[c])) for c in _MAYBE_MISSING]


def assert_valid_label(name: str) -> None:
    """Call before training: refuses a label that is the rule engine's referral level."""
    if name in FORBIDDEN_LABEL_COLUMNS:
        raise ValueError(f"{name} is derived from the clinical rules and must not be used as a training label")
