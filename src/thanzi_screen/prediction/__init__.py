"""Independent ML prediction module: data, features, labels and preprocessing (Phase 2).

Never imports the deterministic screening module (thanzi_screen.under5), the report package or thanzi_screen.ml, and never
uses a CMAM classification as a feature. See docs/modules/prediction-data.md.
"""
from .assemble import Example, build_examples, label_summary, matrix, select
from .dataset import DatasetError, load_dataset, write_dataset
from .features import FEATURE_NAMES, FEATURES, GROUPS, MONOTONE, build_features
from .preprocess import PreprocessError, Preprocessor, UnseenMissingError, split_children
from .records import Child, Observation, from_child_record
from .simulate import SimConfig, simulate_children
from .targets import TARGETS, TargetConfig, label_targets

MODULE = "ml_prediction"

__all__ = ["Child", "DatasetError", "Example", "FEATURES", "FEATURE_NAMES", "GROUPS", "MODULE", "MONOTONE", "Observation",
           "PreprocessError", "Preprocessor", "SimConfig", "TARGETS", "TargetConfig", "build_examples", "build_features", "from_child_record",
           "label_summary", "label_targets", "load_dataset", "matrix", "select", "simulate_children", "split_children", "UnseenMissingError",
           "write_dataset"]
