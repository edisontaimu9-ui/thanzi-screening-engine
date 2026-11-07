#!/usr/bin/env python3
"""Train Phase 4 models from a verified synthetic dataset.

Usage: python scripts/train_models.py [--data data/synthetic/synthetic_children.csv] [--out models] [--seed 0]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from thanzi_screen.ml.train import train_all  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/synthetic/synthetic_children.csv")
    ap.add_argument("--out", default="models")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--epochs", type=int, default=12)
    a = ap.parse_args()
    s = train_all(a.data, a.out, seed=a.seed, epochs=a.epochs)
    print(json.dumps({"operating_point": s["operating_point"], "test_ml": s["test"]["ml"],
                      "ml_recall_on_missed_by_phase1": s["test"]["ml_recall_on_missed_by_phase1"],
                      "field": s["field"]}, indent=1))
    print(f"models and MODEL_CARD.md written to {a.out}")


if __name__ == "__main__":
    main()
