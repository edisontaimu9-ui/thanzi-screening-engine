"""Convert WHO Excel tables to CSV and write a checksum manifest.

Dev-only (needs openpyxl). Usage:
    python scripts/build_reference_tables.py <folder-with-xlsx>
Output: src/thanzi_screen/anthro/reference_tables/*.csv and MANIFEST.json
"""
import csv
import hashlib
import json
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parents[1] / "src/thanzi_screen/anthro/reference_tables"

# (source xlsx, output csv, indicator, sex, register id)
SOURCES = [
    ("wfa-boys-zscore-expanded-tables.xlsx", "wfa_boys.csv", "wfa", "male", "R5"),
    ("wfa-girls-zscore-expanded-tables.xlsx", "wfa_girls.csv", "wfa", "female", "R5"),
    ("lhfa-boys-zscore-expanded-tables.xlsx", "lhfa_boys.csv", "lhfa", "male", "R4"),
    ("lhfa-girls-zscore-expanded-tables.xlsx", "lhfa_girls.csv", "lhfa", "female", "R4"),
    ("wfl_boys_0-to-2-years_zscores.xlsx", "wfl_boys.csv", "wfl", "male", "R1"),
    ("wfl_girls_0-to-2-years_zscores__1_.xlsx", "wfl_girls.csv", "wfl", "female", "R1"),
    ("wfh_boys_2-to-5-years_zscores.xlsx", "wfh_boys.csv", "wfh", "male", "R1"),
    ("wfh_girls_2-to-5-years_zscores.xlsx", "wfh_girls.csv", "wfh", "female", "R1"),
    # Head circumference-for-age (R20): weekly 0-13 weeks and monthly 0-60 months, L = 1 throughout
    ("hcfa-boys-0-13-zscores.xlsx", "hcfa_boys_0_13.csv", "hcfa", "male", "R20"),
    ("hcfa-boys-0-5-zscores.xlsx", "hcfa_boys_0_5.csv", "hcfa", "male", "R20"),
    ("hcfa-girls-0-13-zscores.xlsx", "hcfa_girls_0_13.csv", "hcfa", "female", "R20"),
    ("hcfa-girls-0-5-zscores.xlsx", "hcfa_girls_0_5.csv", "hcfa", "female", "R20"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(src_dir: str) -> None:
    src = Path(src_dir)
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for xlsx, name, indicator, sex, ref in SOURCES:
        ws = openpyxl.load_workbook(src / xlsx, read_only=True, data_only=True).active
        rows = list(ws.iter_rows(values_only=True))
        with open(OUT / name, "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            for r in rows:
                w.writerow(["" if v is None else repr(v) if isinstance(v, float) else v for v in r])
        manifest[name] = {
            "indicator": indicator,
            "sex": sex,
            "register_id": ref,
            "source_file": xlsx,
            "source_sha256": sha256(src / xlsx),
            "csv_sha256": sha256(OUT / name),
            "data_rows": len(rows) - 1,
        }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(manifest)} tables to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
