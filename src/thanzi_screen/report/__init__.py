"""Unified report: the deterministic screening and the ML prediction side by side, never merged.

This package imports neither module's internals. It receives their output dictionaries and lays them out. Nothing in the
prediction block can change the screening block (tested).
"""
from .build import REPORT_VERSION, build_report

__all__ = ["REPORT_VERSION", "build_report"]
