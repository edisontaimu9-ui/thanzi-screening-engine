"""Synthetic data engineering (Phase 3). Synthetic only; real data is refused."""
from .config import GenConfig
from .generator import generate
from .io import load_dataset, write_dataset
from .schema import COLUMNS, DataError
from .validate import validate_rows

__all__ = ["COLUMNS", "DataError", "GenConfig", "generate", "load_dataset", "validate_rows", "write_dataset"]
