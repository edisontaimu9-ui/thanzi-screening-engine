"""Deterministic under-five screening: WHO indicators, MUAC, oedema, growth velocity and growth faltering.

Rules only. No machine learning and no import of thanzi_screen.ml or thanzi_screen.prediction (tested). The CMAM
classification comes from thanzi_screen.rules and is never altered here. See docs/modules/under5-screening.md.
"""
from .indicators import IndicatorPanel, compute_panel
from .longitudinal import FalteringConfig, LongitudinalResult, analyse_growth
from .screen import MODULE, MODULE_VERSION, Under5Screening, screen_record

__all__ = ["FalteringConfig", "IndicatorPanel", "LongitudinalResult", "MODULE", "MODULE_VERSION", "Under5Screening",
           "analyse_growth", "compute_panel", "screen_record"]
