"""Input pathways. A pathway names the groups of inputs a model is built from and the inputs it cannot run without.

`anthropometric` uses only measurements (this visit and earlier visits). Clinical history, feeding, birth, maternal and household
inputs are not part of it, so they can be empty without stopping a score and are never filled in. Because new children often have no
earlier visit, training also withholds the earlier-visit inputs from a share of rows (`withhold_history`), so the model has learned what
"no earlier visit" looks like and a missing history never has to be guessed. Standard library only.
"""
from __future__ import annotations

import zlib
from dataclasses import replace

from .assemble import Example
from .features import FEATURES

PATHWAYS = {
    "full": {"groups": tuple(sorted({s.group for s in FEATURES.values()})),
             "required": ("age_months", "sex_male", "waz", "haz", "whz", "oedema_present")},
    "anthropometric": {"groups": ("anthropometric", "longitudinal"),
                       "required": ("age_months", "sex_male", "waz", "haz", "whz", "oedema_present")},
}
HISTORY_WITHHELD_PCT = 30


def feature_names(pathway: str) -> tuple[str, ...]:
    groups = PATHWAYS[pathway]["groups"]
    return tuple(n for n, s in FEATURES.items() if s.group in groups)


def withhold_history(features: dict) -> dict:
    """What build_features gives for a child with no earlier visit: zero prior visits, every other earlier-visit input empty."""
    return {n: (0.0 if n == "n_prior_visits" else None) if FEATURES.get(n) and FEATURES[n].group == "longitudinal" else v
            for n, v in features.items()}


def _withheld(e: Example, pct: int) -> bool:
    return zlib.crc32(f"{e.child_id}|{e.index_age_days}".encode()) % 100 < pct


def apply_pathway(examples: list[Example], pathway: str, history_withheld_pct: int = HISTORY_WITHHELD_PCT) -> list[Example]:
    """Keep only the pathway's inputs. For a pathway that uses earlier visits, a fixed, repeatable share of rows has them withheld."""
    keep = set(feature_names(pathway))
    uses_history = "longitudinal" in PATHWAYS[pathway]["groups"] and pathway != "full"
    out = []
    for e in examples:
        f = {n: v for n, v in e.features.items() if n in keep}
        if uses_history and _withheld(e, history_withheld_pct):
            f = withhold_history(f)
        out.append(replace(e, features=f))
    return out
