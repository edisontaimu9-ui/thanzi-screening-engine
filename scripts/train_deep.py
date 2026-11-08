#!/usr/bin/env python3
"""Train the deep models from a verified synthetic dataset. Standard library only.

Usage: python scripts/train_deep.py [--data data/synthetic/synthetic_children.csv] [--out models] [--preset small|tiny|base|auto]

`--preset auto` times this machine and picks the largest preset that should train within --budget seconds.
Writes models/recording_error_mlp.json, models/recording_field_mlp.json and models/DL_MODEL_CARD.md.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from thanzi_screen.ml.dl import PRESETS, detect_hardware, estimate_train_seconds, recommend_preset  # noqa: E402
from thanzi_screen.ml.dl.train import train_deep  # noqa: E402
from thanzi_screen.ml.features import FEATURES  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/synthetic/synthetic_children.csv")
    ap.add_argument("--out", default="models")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--preset", default="small", choices=[*PRESETS, "auto"])
    ap.add_argument("--budget", type=float, default=900.0, help="seconds, used by --preset auto")
    ap.add_argument("--dropout", type=float, default=0.0)
    a = ap.parse_args()
    preset = a.preset
    if preset == "auto":
        hw = detect_hardware()
        rows = 35000     # about the size of the training split of the default dataset
        preset = recommend_preset(hw, rows, len(FEATURES), a.epochs, a.budget)
        est = estimate_train_seconds(hw, rows, len(FEATURES), PRESETS[preset], a.epochs)
        print(f"cpus={hw.cpu_count} memory_mb={hw.memory_mb} speed={hw.macs_per_second / 1e6:.0f}M mult-adds/s "
              f"-> preset {preset} (worst-case estimate {est:.0f} s; early stopping usually ends sooner)")
    s = train_deep(a.data, a.out, seed=a.seed, epochs=a.epochs, preset=preset, dropout=a.dropout, baseline_dir=a.out)
    print(json.dumps({"operating_point": s["operating_point"], "test_deep": s["test"]["ml"], "auc": s["test"]["auc"],
                      "ml_recall_on_missed_by_phase1": s["test"]["ml_recall_on_missed_by_phase1"],
                      "field": s["field"], "parameters": s["parameters"], "training": s["training"]}, indent=1))
    print(f"deep models and DL_MODEL_CARD.md written to {a.out}")


if __name__ == "__main__":
    main()
