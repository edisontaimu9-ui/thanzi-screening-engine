"""Leak-free splits. One visit per child, so splitting rows by child_id is splitting children."""
from __future__ import annotations

import random
from collections import defaultdict


def assign_splits(rows: list[dict], fractions: tuple[float, float, float], seed: int) -> None:
    """Stratify by cmam_class. Boundary rows get split 'boundary' and are excluded from training."""
    rng = random.Random(seed + 1)
    strata: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r["record_type"] == "boundary":
            r["split"] = "boundary"
        else:
            strata[r["cmam_class"]].append(r)
    f_train, f_val, _ = fractions
    for cls in sorted(strata):
        group = strata[cls]
        rng.shuffle(group)
        n = len(group)
        a, b = round(n * f_train), round(n * (f_train + f_val))
        for i, r in enumerate(group):
            r["split"] = "train" if i < a else ("val" if i < b else "test")
