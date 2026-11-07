"""Explainability (Phase 5). Plain-language and audit explanations of Phase 2 and Phase 4 outputs.

Explanations describe. They never change a classification, tier, referral, warning or flag (D9).
"""
from .compose import Explanation, explain, explain_parts

__all__ = ["Explanation", "explain", "explain_parts"]
