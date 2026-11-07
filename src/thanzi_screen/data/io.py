"""CSV writing, SHA-256 manifest, and a loader that refuses anything not synthetic or tampered."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

from ..anthro import tables
from .config import GenConfig
from .schema import COLUMNS, FLOAT_FORMATS, DataError
from .validate import validate_rows

CSV_NAME = "synthetic_children.csv"
MANIFEST_NAME = "MANIFEST.json"


def _fmt(col: str, v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return format(v, FLOAT_FORMATS.get(col, ".4f"))
    return str(v)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_dataset(rows: list[dict], cfg: GenConfig, out_dir: str | Path) -> dict:
    problems = validate_rows(rows, cfg.districts)
    if problems:
        raise DataError("; ".join(problems[:5]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([_fmt(c, r[c]) for c in COLUMNS])
    manifest = {
        "dataset": CSV_NAME, "is_synthetic": True, "sha256": _sha256(csv_path), "rows": len(rows),
        "random_rows": sum(r["record_type"] == "random" for r in rows),
        "boundary_rows": sum(r["record_type"] == "boundary" for r in rows),
        "columns": list(COLUMNS), "seed": cfg.seed, "config_sha256": cfg.sha256(), "config": cfg.to_dict(),
        "reference_tables_manifest_sha256": hashlib.sha256(json.dumps(tables.manifest(), sort_keys=True).encode()).hexdigest(),
        "python": ".".join(map(str, sys.version_info[:3])),
        "note": "Synthetic data. Parameters are assumptions, not Malawi prevalence. No real or identifiable data.",
    }
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def load_dataset(csv_path: str | Path, districts=None) -> list[dict]:
    """Load a dataset only if its manifest exists, the checksum matches, and every row is synthetic."""
    path = Path(csv_path)
    mpath = path.with_name(MANIFEST_NAME)
    if not mpath.exists():
        raise DataError("manifest missing: refusing to load an unverified dataset")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    if manifest.get("is_synthetic") is not True:
        raise DataError("manifest does not declare the dataset synthetic: refused")
    if _sha256(path) != manifest["sha256"]:
        raise DataError("checksum mismatch: dataset was modified")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    problems = validate_rows(rows, tuple(districts or manifest["config"]["districts"]))
    if problems:
        raise DataError("; ".join(problems[:5]))
    return rows
