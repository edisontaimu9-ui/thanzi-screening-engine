"""Target B ground truth for the synthetic data. Delegates to the rules-based review (D45)."""
from __future__ import annotations

from ..rules.review import review


def review_reasons(anthro, result, muac, oedema: bool, cfg) -> list[str]:
    return list(review(anthro, result, muac, oedema, cfg.review_muac_margin_cm, cfg.review_z_margin).reasons)
