"""Shared input contract for the under-five screening and prediction modules.

Holds only data types and validation. No screening rules and no machine learning live here, so both modules can depend
on it without depending on each other.
"""
from .schema import (
    ChildRecord, Clinical, Demographic, Feeding, FactorError, Maternal, Socioeconomic, Visit,
    FACTOR_GROUPS, completeness,
)

__all__ = [
    "ChildRecord", "Clinical", "Demographic", "Feeding", "FactorError", "Maternal", "Socioeconomic", "Visit",
    "FACTOR_GROUPS", "completeness",
]
