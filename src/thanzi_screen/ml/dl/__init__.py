"""Lightweight deep learning (add-on, not a numbered phase). Advisory only, never changes a clinical classification (D9).

Plain-Python neural networks that train and run on modest hardware, beside the Phase 4 logistic and tree models.
"""
from .hardware import HardwareProfile, detect_hardware, estimate_train_seconds, measure_speed, recommend_preset
from .network import MAX_PARAMS, PRESETS, Network, parameter_count
from .predict import DeepModels, ModelComparison, compare_record, flag_record_deep, load_deep_models

__all__ = ["DeepModels", "HardwareProfile", "MAX_PARAMS", "ModelComparison", "Network", "PRESETS", "compare_record",
           "detect_hardware", "estimate_train_seconds", "flag_record_deep", "load_deep_models", "measure_speed",
           "parameter_count", "recommend_preset"]
