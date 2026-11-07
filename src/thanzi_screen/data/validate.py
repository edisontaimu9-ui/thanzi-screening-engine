"""Dataset validation: schema, ranges, synthetic marker, no identifiers."""
from __future__ import annotations

from .config import DISTRICTS
from .schema import COLUMNS, FORBIDDEN_COLUMNS, SPLITS


def validate_rows(rows: list[dict], districts=DISTRICTS) -> list[str]:
    """Return a list of problems (empty = valid). Works on rows with python types or CSV strings."""
    problems: list[str] = []
    if not rows:
        return ["no rows"]
    cols = set(rows[0])
    bad = cols & FORBIDDEN_COLUMNS
    if bad:
        problems.append(f"forbidden identifier columns: {sorted(bad)}")
    if cols != set(COLUMNS):
        problems.append(f"columns differ from schema: missing {sorted(set(COLUMNS) - cols)}, extra {sorted(cols - set(COLUMNS))}")
        return problems
    seen = set()
    for i, r in enumerate(rows):
        if str(r["is_synthetic"]).lower() != "true":
            problems.append(f"row {i}: is_synthetic is not true")
        cid = r["child_id"]
        if cid in seen:
            problems.append(f"row {i}: duplicate child_id")
        seen.add(cid)
        if not 0 <= int(r["age_days"]) <= 1856:
            problems.append(f"row {i}: age_days out of range")
        if float(r["weight_kg"]) <= 0 or float(r["length_height_cm"]) <= 0:
            problems.append(f"row {i}: non-positive measurement")
        if r["muac_cm"] not in (None, "") and float(r["muac_cm"]) <= 0:
            problems.append(f"row {i}: non-positive muac")
        if r["sex"] not in ("male", "female"):
            problems.append(f"row {i}: bad sex")
        if r["district"] not in districts:
            problems.append(f"row {i}: unknown district")
        if r["split"] not in SPLITS:
            problems.append(f"row {i}: bad split")
        if len(problems) > 50:
            problems.append("too many problems, stopping")
            break
    return problems
