"""DHIS2 helpers for the surveillance reports (Phase 10). Needs no extra packages and talks to no server.

    python scripts/export_dhis2.py templates            # write docs/dhis2/mapping.template.json and org-units.template.csv
    python scripts/export_dhis2.py templates --check    # exit 1 if the committed templates are stale (also run by the tests)
    python scripts/export_dhis2.py build request.json mapping.json -o data-value-set.json

`request.json` holds `org_units`, `rows` and optionally `period`, the same as POST /v1/surveillance/dhis2 without the mapping.
`mapping.json` is the mapping the DHIS2 administrators filled in from the template (keys that start with an underscore are ignored).
The output is the body for POST /api/dataValueSets. Import it with dryRun=true first: the parameters are printed.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "dhis2"
MAPPING_FILE, ORG_FILE = OUT / "mapping.template.json", OUT / "org-units.template.csv"


def render_templates() -> dict[Path, str]:
    from thanzi_screen.surveillance import mapping_template

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["code", "name", "level", "parent", "dhis2_org_unit_id"])
    w.writerow(["MW", "Malawi", "national", "", ""])
    w.writerow(["EXAMPLE-D1", "Example District", "district", "MW", ""])
    w.writerow(["EXAMPLE-D1-F1", "Example Health Centre", "facility", "EXAMPLE-D1", ""])
    return {MAPPING_FILE: json.dumps(mapping_template(), indent=2, ensure_ascii=False) + "\n", ORG_FILE: buf.getvalue()}


def _templates(check: bool) -> int:
    files = render_templates()
    if check:
        stale = [p.name for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        print("DHIS2 templates are up to date." if not stale else f"Stale: {', '.join(stale)}. Run scripts/export_dhis2.py templates.")
        return 1 if stale else 0
    OUT.mkdir(parents=True, exist_ok=True)
    for p, text in files.items():
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(ROOT)}")
    return 0


def _build(request: Path, mapping: Path, out: Path) -> int:
    from thanzi_screen.surveillance import Dhis2Mapping, FacilityRow, OrgUnit, SurveillanceInputError, build_data_value_set

    req = json.loads(request.read_text(encoding="utf-8"))
    m = {k: v for k, v in json.loads(mapping.read_text(encoding="utf-8")).items() if not k.startswith("_")}
    try:
        result = build_data_value_set([OrgUnit(**u) for u in req["org_units"]], [FacilityRow(**r) for r in req["rows"]],
                                      Dhis2Mapping(**m), req.get("period"))
    except SurveillanceInputError as exc:
        print(f"Not exported: {exc.code}. {exc.message}", file=sys.stderr)
        return 2
    out.write_text(json.dumps(result["data_value_set"], indent=2) + "\n", encoding="utf-8")
    s = result["summary"]
    print(f"wrote {out} ({s['values']} values, {s['facilities_exported']} facilities, period {s['period']}).")
    print("Import with: POST /api/dataValueSets?" + "&".join(f"{k}={v}" for k, v in result["import_parameters"].items()))
    if s["facilities_with_withheld_counts"]:
        print(f"{s['facilities_with_withheld_counts']} facilities have SAM and MAM withheld (a count of 1 to 4).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("templates")
    t.add_argument("--check", action="store_true")
    b = sub.add_parser("build")
    b.add_argument("request", type=Path)
    b.add_argument("mapping", type=Path)
    b.add_argument("-o", "--out", type=Path, default=Path("data-value-set.json"))
    a = ap.parse_args()
    return _templates(a.check) if a.cmd == "templates" else _build(a.request, a.mapping, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
