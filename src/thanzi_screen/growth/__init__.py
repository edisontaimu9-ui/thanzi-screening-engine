"""Growth monitoring (add-on, not a numbered phase): weight-gain velocity against the ASPEN reference ranges (R19).

Advisory only (D9). Needs an earlier weight from the caller, because the engine stores nothing."""
from .velocity import MIN_INTERVAL_DAYS, GrowthAssessment, assess_weight_velocity

__all__ = ["MIN_INTERVAL_DAYS", "GrowthAssessment", "assess_weight_velocity"]
