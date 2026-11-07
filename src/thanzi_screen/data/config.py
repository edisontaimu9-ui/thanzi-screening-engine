"""Generation parameters. Every value is an ASSUMPTION (placeholder) unless stated.

None of these are Malawi prevalence figures. They exist to exercise the engine
and give the rules enough severe, moderate, boundary and error cases to test.
Replace with cited figures (R9) and WHO MUAC-for-age tables (R8) when supplied.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields

# ASSUMPTION: list to be checked by Edison against the official district list.
DISTRICTS = (
    "Balaka", "Blantyre", "Chikwawa", "Chiradzulu", "Chitipa", "Dedza", "Dowa", "Karonga",
    "Kasungu", "Likoma", "Lilongwe", "Machinga", "Mangochi", "Mchinji", "Mulanje", "Mwanza",
    "Neno", "Nkhata Bay", "Nkhotakota", "Nsanje", "Ntcheu", "Ntchisi", "Phalombe", "Rumphi",
    "Salima", "Thyolo", "Zomba", "Mzimba",
)


@dataclass(frozen=True)
class GenConfig:
    seed: int = 42
    n: int = 50_000
    districts: tuple[str, ...] = DISTRICTS          # equal weights, no spatial pattern (ASSUMPTION)
    # Anthropometry targets (ASSUMPTION, placeholders)
    lhfa_mean: float = -0.5
    lhfa_sd: float = 1.1
    wflh_mean: float = -0.4
    wflh_sd: float = 1.1
    hw_corr: float = 0.2
    p_oedema: float = 0.01
    oedema_grade_weights: tuple[float, float, float] = (0.6, 0.3, 0.1)
    # MUAC placeholder (ASSUMPTION): linear in WFL/H z. NOT a WHO MUAC-for-age model (R8 pending)
    muac_at_z0_cm: float = 14.5
    muac_per_z_cm: float = 1.2
    muac_sd_cm: float = 0.6
    # Clinical inputs (ASSUMPTION)
    appetite_fail_sam: float = 0.15
    appetite_fail_other: float = 0.01
    danger_sam: float = 0.20
    danger_other: float = 0.02
    compl_sam: float = 0.20
    compl_other: float = 0.03
    hiv_positive: float = 0.03
    hiv_unknown: float = 0.40
    infant_visible_wasting: float = 0.03
    infant_too_weak: float = 0.02
    infant_no_gain: float = 0.04
    # Missingness, MCAR (ASSUMPTION)
    missing_muac: float = 0.05
    missing_appetite: float = 0.03
    missing_danger: float = 0.03
    missing_compl: float = 0.03
    missing_well_alert: float = 0.03
    missing_infant_items: float = 0.03
    # Injected recording errors (ASSUMPTION); ground truth for ML target A
    p_error: float = 0.04
    # Review (ML target B) margins (ASSUMPTION)
    review_muac_margin_cm: float = 0.2
    review_z_margin: float = 0.1
    # Splits by child (single visit per child)
    split_fractions: tuple[float, float, float] = (0.70, 0.15, 0.15)

    def to_dict(self) -> dict:
        return asdict(self)

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_dict(cls, d: dict) -> "GenConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"unknown config keys: {sorted(unknown)}")
        d = {k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()}
        return cls(**d)
