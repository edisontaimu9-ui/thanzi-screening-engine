"""Independent ML prediction module: data, features, labels, preprocessing (Phase 2), comparison and calibration (Phase 3).

Never imports the deterministic screening module (thanzi_screen.under5), the report package or thanzi_screen.ml, and never
uses a CMAM classification as a feature. See docs/modules/prediction-data.md and docs/modules/prediction-models.md.

`evaluate` is standard library and imported here. `candidates` and `compare` are NOT imported here: they load numpy, scikit-learn and
XGBoost lazily and only on a development machine (`from thanzi_screen.prediction import compare`).
"""
from .assemble import Example, build_examples, label_summary, matrix, select
from .dataset import DatasetError, load_dataset, write_dataset
from . import evaluate
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
