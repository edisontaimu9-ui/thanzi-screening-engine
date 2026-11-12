"""Risk dataset: one row per child visit with a later outcome. CSV plus a SHA-256 manifest. Loader refuses anything
unverified, tampered, carrying an identifier column, or (for real data) lacking governance references.

This is the schema the government dataset will be mapped into. It holds only what the API already accepts, a
pseudonymous child ID (used to keep a child in one split, never a feature), and coarse grouping fields for fairness
checks. It never holds names, dates of birth, contacts, fine geography or facility names.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from ...data.schema import FORBIDDEN_COLUMNS, dec_bool, dec_set, enc_bool, enc_set
from ...rules import Appetite, ClinicalInputs, Complication, DangerSign, OedemaGrade
from .errors import RiskModelError
from .features import Prior
from .model import GOVERNANCE_FIELDS

CSV_NAME = "risk_dataset.csv"
MANIFEST_NAME = "MANIFEST.json"
COLUMNS = ("child_id", "district", "period", "sex", "age_days", "measure_position", "weight_kg", "length_height_cm",
           "muac_cm", "oedema", "appetite", "danger_signs", "complications", "clinically_well_and_alert",
           "prev_age_days", "prev_weight_kg", "outcome")
REAL_MANIFEST_FIELDS = ("ethics_ref", "data_agreement_ref", "extraction_description", "period_covered")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fmt(col, v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return format(v, ".2f" if col in ("weight_kg", "prev_weight_kg") else ".1f")
    return str(v)


def write_dataset(rows: list[dict], manifest_extra: dict, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / CSV_NAME
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow([_fmt(c, r.get(c)) for c in COLUMNS])
    manifest = {"dataset": CSV_NAME, "sha256": _sha(path), "rows": len(rows), "columns": list(COLUMNS), **manifest_extra}
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def load_dataset(csv_path, allow_simulated: bool = False) -> tuple[list[dict], dict]:
    path = Path(csv_path)
    mpath = path.with_name(MANIFEST_NAME)
    if not mpath.exists():
        raise RiskModelError("manifest missing: refusing to load an unverified dataset")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    prov = manifest.get("provenance")
    if prov == "simulated":
        if not allow_simulated:
            raise RiskModelError("dataset has simulated outcomes: pass allow_simulated to train a non-clinical model")
    elif prov == "real":
        missing = [k for k in REAL_MANIFEST_FIELDS if not str(manifest.get(k, "")).strip()]
        if missing or manifest.get("deidentified") is not True:
            raise RiskModelError("real dataset needs a manifest with: " + ", ".join(REAL_MANIFEST_FIELDS) + " and deidentified=true")
    else:
        raise RiskModelError("manifest must declare provenance simulated or real")
    if _sha(path) != manifest["sha256"]:
        raise RiskModelError("checksum mismatch: dataset was modified")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        bad = sorted(c for c in header if c.lower() in FORBIDDEN_COLUMNS)
        if bad:
            raise RiskModelError("identifier column present: " + ", ".join(bad))
        if header != COLUMNS:
            raise RiskModelError("columns do not match the risk dataset schema")
        rows = list(reader)
    for r in rows:
        if r["outcome"] not in ("0", "1"):
            raise RiskModelError("outcome must be 0 or 1")
    return rows, manifest


def row_inputs(row: dict):
    """(sex, age_days, weight, length, position, ClinicalInputs, previous visit or None) from a dataset row."""
    muac = row["muac_cm"]
    clinical = ClinicalInputs(
        oedema=OedemaGrade(row["oedema"]), muac_cm=None if muac in ("", None) else float(muac),
        appetite=Appetite(row["appetite"]), danger_signs=dec_set(row["danger_signs"], DangerSign),
        complications=dec_set(row["complications"], Complication),
        clinically_well_and_alert=dec_bool(row["clinically_well_and_alert"]))
    prev = None
    if row["prev_age_days"] not in ("", None) and row["prev_weight_kg"] not in ("", None):
        prev = Prior(int(row["prev_age_days"]), float(row["prev_weight_kg"]))
    return (row["sex"], int(row["age_days"]), float(row["weight_kg"]), float(row["length_height_cm"]),
            row["measure_position"], clinical, prev)


__all__ = ["COLUMNS", "GOVERNANCE_FIELDS", "enc_bool", "enc_set", "load_dataset", "row_inputs", "write_dataset"]
