"""Longitudinal records for the prediction module: one child, many observations.

Static groups (demographic, maternal, socioeconomic) are held once per child. Clinical history and feeding are asked at
each visit, so they sit on the observation. `district` and `period` are for fairness checks and splitting only and are
never features. None means not assessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..factors import ChildRecord, Clinical, Demographic, FactorError, Feeding, Maternal, Socioeconomic, Visit

_PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass(frozen=True)
class Observation:
    visit: Visit
    clinical: Clinical = field(default_factory=Clinical)
    feeding: Feeding = field(default_factory=Feeding)
    period: str | None = None            # YYYY-MM of the visit. Fairness checks only.

    def __post_init__(self):
        if self.period is not None and not _PERIOD.match(self.period):
            raise FactorError("period must be YYYY-MM")


@dataclass(frozen=True)
class Child:
    child_id: str                        # pseudonymous. Used to keep a child in one split. Never a feature.
    sex: str
    observations: tuple[Observation, ...]
    demographic: Demographic = field(default_factory=Demographic)
    maternal: Maternal = field(default_factory=Maternal)
    socioeconomic: Socioeconomic = field(default_factory=Socioeconomic)
    district: str | None = None          # coarse area only. Fairness checks only.

    def __post_init__(self):
        if not isinstance(self.child_id, str) or not self.child_id.strip():
            raise FactorError("child_id is required")
        if self.sex not in ("male", "female"):
            raise FactorError("sex must be male or female")
        if not self.observations:
            raise FactorError("at least one observation is required")
        ordered = tuple(sorted(self.observations, key=lambda o: o.visit.age_days))
        ages = [o.visit.age_days for o in ordered]
        if len(set(ages)) != len(ages):
            raise FactorError("two observations have the same age_days")
        object.__setattr__(self, "observations", ordered)


def from_child_record(record: ChildRecord, child_id: str, district: str | None = None) -> Child:
    """Bridge from the screening input. The record's clinical and feeding groups describe the latest visit only, so earlier
    observations carry none (not assessed)."""
    obs = [Observation(v) for v in record.visits[:-1]]
    obs.append(Observation(record.visits[-1], record.clinical, record.feeding))
    return Child(child_id, record.sex, tuple(obs), record.demographic, record.maternal, record.socioeconomic, district)
