#!/usr/bin/env python3
"""Generate the synthetic dataset. Same seed and config give a byte-identical CSV and SHA-256.

Usage: python scripts/generate_synthetic.py [--seed 42] [--n 50000] [--config cfg.json] [--out data/synthetic]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from thanzi_screen.data import GenConfig, generate, write_dataset  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--n", type=int)
    ap.add_argument("--config", help="JSON file of GenConfig overrides")
    ap.add_argument("--out", default="data/synthetic")
    a = ap.parse_args()
    d = json.loads(Path(a.config).read_text()) if a.config else {}
    if a.seed is not None:
        d["seed"] = a.seed
    if a.n is not None:
        d["n"] = a.n
    cfg = GenConfig.from_dict(d)
    m = write_dataset(generate(cfg), cfg, a.out)
    print(f"rows={m['rows']} (random {m['random_rows']}, boundary {m['boundary_rows']})")
    print(f"sha256={m['sha256']}")
    print(f"written to {a.out}")


if __name__ == "__main__":
    main()
