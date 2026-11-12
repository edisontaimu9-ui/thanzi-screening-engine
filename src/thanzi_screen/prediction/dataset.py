"""Longitudinal dataset: one CSV row per visit, plus a SHA-256 manifest. The loader refuses anything unverified,
tampered, carrying an identifier column, inconsistent for a child, or (for real data) lacking governance references.

This is the schema the government data will be mapped into. It holds only what the factor schema holds, a pseudonymous
child_id (splitting only), a coarse district and a visit month (fairness checks only). No names, dates of birth, contacts,
fine geography or facility names. There is no outcome column: labels are built from later visits (see targets.py).
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import fields
from enum import Enum
from pathlib import Path

from ..data.schema import FORBIDDEN_COLUMNS, dec_set, enc_set
from ..factors import Clinical, Demographic, FactorError, Feeding, Maternal, Socioeconomic, Visit
from ..factors.schema import Residence
from ..rules import Appetite, Complication, DangerSign, OedemaGrade
from .records import Child, Observation

CSV_NAME = "visits.csv"
MANIFEST_NAME = "MANIFEST.json"
REAL_MANIFEST_FIELDS = ("ethics_ref", "data_agreement_ref", "extraction_description", "period_covered")


class DatasetError(ValueError):
    pass


# (column, kind). Kinds: str, int, float, bool, residence, education, set_danger, set_comp, oedema, appetite
_STATIC = (
    ("child_id", "str"), ("district", "str"), ("sex", "str"),
    ("residence", "residence"), ("birth_weight_g", "float"), ("gestational_age_weeks", "float"),
    ("multiple_birth", "bool"), ("birth_interval_months", "float"), ("birth_order", "int"),
    ("mother_age_years", "float"), ("mother_education", "str"), ("mother_muac_cm", "float"),
    ("antenatal_visits", "int"), ("mother_is_primary_caregiver", "bool"),
    ("wealth_quintile", "int"), ("household_size", "int"), ("improved_water", "bool"), ("improved_sanitation", "bool"),
    ("food_insecure", "bool"), ("receives_cash_or_food_support", "bool"),
)
_VISIT = (
    ("period", "str"), ("age_days", "int"), ("measure_position", "str"), ("weight_kg", "float"),
    ("length_height_cm", "float"), ("muac_cm", "float"), ("hc_cm", "float"), ("oedema", "oedema"), ("appetite", "appetite"),
    ("danger_signs", "set_danger"), ("complications", "set_comp"), ("clinically_well_and_alert", "bool"),
)
_CLIN = tuple((f.name, "bool") for f in fields(Clinical))
_FEED = (("exclusive_breastfeeding_to_6mo", "bool"), ("currently_breastfed", "bool"),
         ("complementary_start_age_months", "float"), ("food_groups_24h", "int"), ("meals_24h", "int"),
         ("breastmilk_substitute_use", "bool"))
COLUMNS = tuple(c for c, _ in _STATIC + _VISIT + _CLIN + _FEED)
_MATERNAL_MAP = {"age_years": "mother_age_years", "education": "mother_education", "muac_cm": "mother_muac_cm",
                 "antenatal_visits": "antenatal_visits", "mother_is_primary_caregiver": "mother_is_primary_caregiver"}


def _enc(kind: str, v) -> str:
    if kind in ("set_danger", "set_comp"):
        return enc_set(v)
    if v is None:
        return ""
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def _dec(kind: str, s: str):
    if kind == "set_danger":
        return dec_set(s, DangerSign)
    if kind == "set_comp":
        return dec_set(s, Complication)
    if s == "":
        return None
    if kind == "bool":
        if s not in ("true", "false"):
            raise DatasetError(f"bad boolean {s!r}")
        return s == "true"
    if kind == "int":
        return int(s)
    if kind == "float":
        return float(s)
    if kind == "residence":
        return Residence(s)
    if kind == "oedema":
        return OedemaGrade(s)
    if kind == "appetite":
        return Appetite(s)
    return s


def child_rows(child: Child) -> list[dict]:
    d, m, s = child.demographic, child.maternal, child.socioeconomic
    static = {"child_id": child.child_id, "district": child.district, "sex": child.sex,
              "residence": d.residence, "birth_weight_g": d.birth_weight_g, "gestational_age_weeks": d.gestational_age_weeks,
              "multiple_birth": d.multiple_birth, "birth_interval_months": d.birth_interval_months,
              "birth_order": d.birth_order,
              **{col: getattr(m, f) for f, col in _MATERNAL_MAP.items()},
              **{f.name: getattr(s, f.name) for f in fields(s)}}
    rows = []
    for o in child.observations:
        v = o.visit
        row = dict(static)
        row.update({"period": o.period, "age_days": v.age_days, "measure_position": v.measure_position,
                    "weight_kg": v.weight_kg, "length_height_cm": v.length_height_cm, "muac_cm": v.muac_cm,
                    "hc_cm": v.hc_cm, "oedema": v.oedema, "appetite": v.appetite, "danger_signs": v.danger_signs,
                    "complications": v.complications, "clinically_well_and_alert": v.clinically_well_and_alert})
        row.update({f.name: getattr(o.clinical, f.name) for f in fields(Clinical)})
        row.update({f.name: getattr(o.feeding, f.name) for f in fields(Feeding)})
        rows.append(row)
    return rows


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_dataset(children: list[Child], manifest_extra: dict, out_dir) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    kinds = dict(_STATIC + _VISIT + _CLIN + _FEED)
    path = out / CSV_NAME
    n = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for c in children:
            for r in child_rows(c):
                w.writerow([_enc(kinds[col], r[col]) for col in COLUMNS])
                n += 1
    manifest = {"dataset": CSV_NAME, "sha256": _sha(path), "rows": n, "children": len(children), "columns": list(COLUMNS),
                **manifest_extra}
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def load_dataset(csv_path, allow_simulated: bool = False) -> tuple[list[Child], dict]:
    path = Path(csv_path)
    mpath = path.with_name(MANIFEST_NAME)
    if not mpath.exists():
        raise DatasetError("manifest missing: refusing to load an unverified dataset")
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    prov = manifest.get("provenance")
    if prov == "simulated":
        if not allow_simulated:
            raise DatasetError("dataset is simulated: pass allow_simulated to build a non-clinical model")
    elif prov == "real":
        missing = [k for k in REAL_MANIFEST_FIELDS if not str(manifest.get(k, "")).strip()]
        if missing or manifest.get("deidentified") is not True:
            raise DatasetError("real dataset needs a manifest with: " + ", ".join(REAL_MANIFEST_FIELDS) + " and deidentified=true")
    else:
        raise DatasetError("manifest must declare provenance simulated or real")
    if _sha(path) != manifest["sha256"]:
        raise DatasetError("checksum mismatch: dataset was modified")
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = tuple(reader.fieldnames or ())
        bad = sorted(c for c in header if c.lower() in FORBIDDEN_COLUMNS)
        if bad:
            raise DatasetError("identifier column present: " + ", ".join(bad))
        if header != COLUMNS:
            raise DatasetError("columns do not match the longitudinal dataset schema")
        rows = list(reader)
    kinds = dict(_STATIC + _VISIT + _CLIN + _FEED)
    grouped: dict[str, list[dict]] = {}
    for r in rows:
        try:
            grouped.setdefault(r["child_id"], []).append({c: _dec(kinds[c], r[c]) for c in COLUMNS})
        except (ValueError, KeyError) as exc:
            raise DatasetError(f"bad value in row for child {r.get('child_id')}: {exc}") from None
    children = []
    static_cols = [c for c, _ in _STATIC]
    for cid, rs in grouped.items():
        first = rs[0]
        if any(any(r[c] != first[c] for c in static_cols) for r in rs):
            raise DatasetError(f"static fields differ between rows of child {cid}")
        try:
            demo = Demographic(first["residence"], first["birth_weight_g"], first["gestational_age_weeks"],
                               first["multiple_birth"], first["birth_interval_months"], first["birth_order"])
            mat = Maternal(**{f: first[col] for f, col in _MATERNAL_MAP.items()})
            soc = Socioeconomic(*(first[n] for n in ("wealth_quintile", "household_size", "improved_water",
                                                      "improved_sanitation", "food_insecure",
                                                      "receives_cash_or_food_support")))
            obs = []
            for r in rs:
                visit = Visit(r["age_days"], r["weight_kg"], r["length_height_cm"], r["measure_position"], r["muac_cm"],
                              r["oedema"], r["appetite"], r["danger_signs"], r["complications"],
                              r["clinically_well_and_alert"], r["hc_cm"])
                obs.append(Observation(visit, Clinical(**{f.name: r[f.name] for f in fields(Clinical)}),
                                       Feeding(**{f.name: r[f.name] for f in fields(Feeding)}), r["period"]))
            children.append(Child(cid, first["sex"], tuple(obs), demo, mat, soc, first["district"]))
        except (FactorError, TypeError, ValueError) as exc:
            raise DatasetError(f"invalid record for child {cid}: {exc}") from None
    return children, manifest
