"""Case pack for clinical review (Phase 7, D95): scenarios run through the engine, with blank columns for Maria.

    python scripts/build_case_pack.py            # write docs/testing/case-pack.xlsx
    python scripts/build_case_pack.py --check    # exit 1 if the committed workbook differs from a fresh run

Every result in the workbook is what the engine returned under rule set rules_v2016, with the rule and printed page
from the register. It shows what the engine does, not what is clinically right. The agreement columns are for the
reviewer. Synthetic scenarios only; no real child data. The ML flag is not part of this pack (rules only).

Needs openpyxl (dev extra).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "testing" / "case-pack.xlsx"

FULL = dict(appetite="passed", danger_signs=[], complications=[], clinically_well_and_alert=True)
INFANT_FULL = dict(danger_signs=[], complications=[], clinically_well_and_alert=True,
                   visible_severe_wasting=False, too_weak_to_suckle=False, failure_to_gain_weight=False)
BOYS_300 = dict(sex="male", age_days=300, length_height_cm=70.0, measure_position="length")
GIRLS_900 = dict(sex="female", age_days=900, length_height_cm=90.0, measure_position="height")
BOYS_100 = dict(sex="male", age_days=100, length_height_cm=60.0, measure_position="length")


def _z(base: dict, weight: float) -> float:
    from thanzi_screen.anthro import compute_anthropometry
    a = compute_anthropometry(sex=base["sex"], weight_kg=weight, length_height_cm=base["length_height_cm"],
                              measure_position=base["measure_position"], age_days=base["age_days"], oedema=False)
    return a.wflh.z


def weight_at(base: dict, threshold: float, side: str) -> float:
    """Closest weight (0.01 kg steps) just below (`below`) or at or above (`at_or_above`) a WFL/H z threshold."""
    w = 3.0
    prev = None
    while w < 25.0:
        z = _z(base, round(w, 2))
        if z is not None and z >= threshold:
            return round(w, 2) if side == "at_or_above" else prev
        prev = round(w, 2)
        w += 0.01
    raise ValueError("threshold not reached")


def _case(label: str, base: dict, weight: float, **clinical) -> dict:
    p = {**base, "weight_kg": weight, "oedema": "none", **clinical}
    return {"label": label, "payload": p}


def scenarios() -> list[dict]:
    b, g = BOYS_300, GIRLS_900
    w_norm, w_norm_g = 8.6, 13.0
    sev_b, mod_b, ok_b = weight_at(b, -3.0, "below"), weight_at(b, -3.0, "at_or_above"), weight_at(b, -2.0, "at_or_above")
    mod_edge_b = weight_at(b, -2.0, "below")
    sev_g, mod_g = weight_at(g, -3.0, "below"), weight_at(g, -2.0, "below")
    c = []
    # ---- MUAC (Table 4 p.14; Table 5 pp.16-17)
    for m in (11.4, 11.5, 12.4, 12.5):
        c.append(_case(f"MUAC {m} cm, normal weight, full assessment", b, w_norm, muac_cm=m, **FULL))
    c.append(_case("MUAC 11.0 cm, girl 30 months, full assessment", g, w_norm_g, muac_cm=11.0, **FULL))
    # ---- WFL/H
    c.append(_case("WFL/H just below -3, normal MUAC, full assessment", b, sev_b, muac_cm=13.5, **FULL))
    c.append(_case("WFL/H just at or above -3, normal MUAC", b, mod_b, muac_cm=13.5, **FULL))
    c.append(_case("WFL/H just below -2, normal MUAC", b, mod_edge_b, muac_cm=13.5, **FULL))
    c.append(_case("WFL/H just at or above -2, normal MUAC", b, ok_b, muac_cm=13.5, **FULL))
    c.append(_case("Girl 30 months, WFL/H just below -3, no MUAC taken", g, sev_g, **FULL))
    c.append(_case("Girl 30 months, WFL/H just below -2, no MUAC taken", g, mod_g, **FULL))
    # ---- Oedema
    for grade in ("+", "++", "+++"):
        c.append(_case(f"Oedema {grade}, normal MUAC, full assessment", b, w_norm, muac_cm=13.5, oedema=grade, **FULL))
    c.append(_case("Oedema ++ with MUAC 11.0 (severe wasting)", b, w_norm, muac_cm=11.0, oedema="++", **FULL))
    c.append(_case("Oedema + with danger sign (high fever)", b, w_norm, muac_cm=13.5, oedema="+",
                   **{**FULL, "danger_signs": ["high_fever"]}))
    c.append(_case("Oedema ++ with complication (malaria)", b, w_norm, muac_cm=13.5, oedema="++",
                   **{**FULL, "complications": ["malaria"]}))
    # ---- SAM pathway: OTP versus inpatient versus assess
    c.append(_case("SAM by MUAC 11.0, full assessment, appetite passed", b, w_norm, muac_cm=11.0, **FULL))
    c.append(_case("SAM by MUAC 11.0, appetite test failed", b, w_norm, muac_cm=11.0, **{**FULL, "appetite": "failed"}))
    c.append(_case("SAM by MUAC 11.0, appetite test not done", b, w_norm, muac_cm=11.0, **{**FULL, "appetite": "not_done"}))
    for ds in ("anorexia", "intractable_vomiting", "convulsions", "lethargy_not_alert", "unconsciousness",
               "unable_to_drink_or_breastfeed", "high_fever"):
        c.append(_case(f"SAM by MUAC 11.0 with danger sign: {ds}", b, w_norm, muac_cm=11.0, **{**FULL, "danger_signs": [ds]}))
    for cp in ("hypoglycaemia", "hypothermia", "infections", "severe_dehydration", "shock", "very_severe_anaemia",
               "cardiac_failure", "severe_dermatosis", "vitamin_a_deficiency_signs", "diarrhoea", "malaria"):
        c.append(_case(f"SAM by MUAC 11.0 with complication: {cp}", b, w_norm, muac_cm=11.0, **{**FULL, "complications": [cp]}))
    c.append(_case("SAM by MUAC 11.0, not clinically well and alert", b, w_norm, muac_cm=11.0, **{**FULL, "clinically_well_and_alert": False}))
    c.append(_case("SAM by MUAC 11.0, danger signs not assessed", b, w_norm, muac_cm=11.0, **{**FULL, "danger_signs": None}))
    c.append(_case("SAM by MUAC 11.0, complications not assessed", b, w_norm, muac_cm=11.0, **{**FULL, "complications": None}))
    c.append(_case("SAM by MUAC 11.0, well-and-alert not assessed", b, w_norm, muac_cm=11.0, **{**FULL, "clinically_well_and_alert": None}))
    # ---- MAM, HIV (Table 5 p.17)
    c.append(_case("MAM by MUAC 12.0, full assessment, HIV status not given", b, w_norm, muac_cm=12.0, **FULL))
    c.append(_case("MAM by MUAC 12.0, full assessment, HIV negative", b, w_norm, muac_cm=12.0, hiv_positive=False, **FULL))
    c.append(_case("MAM by MUAC 12.0, full assessment, HIV positive", b, w_norm, muac_cm=12.0, hiv_positive=True, **FULL))
    c.append(_case("MAM by MUAC 12.0, HIV positive, appetite failed", b, w_norm, muac_cm=12.0, hiv_positive=True, **{**FULL, "appetite": "failed"}))
    c.append(_case("MAM by MUAC 12.0, HIV positive, complication (diarrhoea)", b, w_norm, muac_cm=12.0, hiv_positive=True,
                   **{**FULL, "complications": ["diarrhoea"]}))
    c.append(_case("MAM by WFL/H just below -2, HIV positive, full assessment", b, mod_edge_b, muac_cm=13.5, hiv_positive=True, **FULL))
    # ---- Low risk, missing information
    c.append(_case("Normal measurements, MUAC 13.5, full assessment", b, w_norm, muac_cm=13.5, **FULL))
    c.append(_case("Normal measurements, no MUAC, nothing else assessed", b, w_norm))
    c.append(_case("Normal measurements, MUAC 13.5, nothing else assessed", b, w_norm, muac_cm=13.5))
    # ---- Implausible measurements (D12, D23)
    c.append(_case("Implausibly low weight (3.0 kg at 10 months), normal MUAC", b, 3.0, muac_cm=13.5, **FULL))
    c.append(_case("Implausibly low weight (3.0 kg at 10 months), MUAC 11.0", b, 3.0, muac_cm=11.0, **FULL))
    # ---- Age boundary (D-Q5)
    inf = {"sex": "male", "length_height_cm": 55.0, "measure_position": "length"}
    edge = {"sex": "male", "length_height_cm": 66.0, "measure_position": "length"}
    c.append(_case("Age 182 days (just under 6 months), normal measurements, infant signs assessed absent", {**edge, "age_days": 182}, 7.8, muac_cm=13.5, **INFANT_FULL))
    c.append(_case("Age 183 days (just over 6 months), same measurements, child assessment complete", {**edge, "age_days": 183}, 7.8, muac_cm=13.5, **FULL))
    # ---- Infants under 6 months (Table 5 p.16)
    i = BOYS_100
    c.append(_case("Infant 100 days, normal weight, all infant signs assessed absent", i, 5.8, **INFANT_FULL))
    c.append(_case("Infant 100 days, WFL z below -3 (length 60 cm), signs absent", i, weight_at(i, -3.0, "below"), **INFANT_FULL))
    c.append(_case("Infant 100 days, WFL/H just at or above -3, signs absent", i, weight_at(i, -3.0, "at_or_above"), **INFANT_FULL))
    c.append(_case("Infant 100 days, oedema +", i, 5.8, **{**INFANT_FULL, "oedema": "+"}))
    c.append(_case("Infant 100 days, visible severe wasting", i, 5.8, **{**INFANT_FULL, "visible_severe_wasting": True}))
    c.append(_case("Infant 100 days, too weak to suckle", i, 5.8, **{**INFANT_FULL, "too_weak_to_suckle": True}))
    c.append(_case("Infant 100 days, failure to gain weight", i, 5.8, **{**INFANT_FULL, "failure_to_gain_weight": True}))
    c.append(_case("Infant 100 days, infant signs not assessed", i, 5.8))
    c.append(_case("Infant 100 days, weight-for-age z below -3, WFL normal", {**i, "length_height_cm": 55.0}, 4.0, **INFANT_FULL))
    c.append(_case("Age 190 days, weight 2.9 kg (below 3.0 kg)", {**inf, "age_days": 190, "length_height_cm": 50.0}, 2.9, muac_cm=None, **FULL))
    return c


def build_cases() -> list[dict]:
    from thanzi_screen.anthro import compute_anthropometry
    from thanzi_screen.api import service
    from thanzi_screen.rules.rules_v2016 import RULES
    rows = []
    for n, sc in enumerate(scenarios(), start=1):
        p = sc["payload"]
        a = compute_anthropometry(sex=p["sex"], weight_kg=p["weight_kg"], length_height_cm=p["length_height_cm"],
                                  measure_position=p["measure_position"], age_days=p["age_days"], oedema=p["oedema"] != "none")
        audit = service.screen(p, "audit", None)
        worker = service.screen(p, "worker", None)
        fired = audit["rules_fired"]
        rows.append({
            "id": f"C{n:03d}", "scenario": sc["label"], "payload": p,
            "wflh_z": None if a.wflh.z is None else round(a.wflh.z, 3),
            "wfa_z": None if a.wfa.z is None else round(a.wfa.z, 3),
            "classification": audit["classification"], "tier": audit["tier"], "programme": audit["programme"],
            "rules": ", ".join(fired),
            "rule_pages": "; ".join(f"{r}: {RULES[r].source} {RULES[r].page}" for r in fired if r in RULES),
            "reasons": ", ".join(x["code"] if isinstance(x, dict) else str(x) for x in audit["reasons"]),
            "warnings": " | ".join(audit["warnings"]),
            "worker_summary": " ".join(worker["worker_summary"]),
        })
    return rows


COLS = [
    ("Case", "id", 8), ("Scenario (intended)", "scenario", 46), ("Sex", "sex", 8), ("Age (days)", "age_days", 10),
    ("Weight (kg)", "weight_kg", 10), ("Length/height (cm)", "length_height_cm", 12), ("Position", "measure_position", 10),
    ("Oedema", "oedema", 8), ("MUAC (cm)", "muac_cm", 9), ("Appetite", "appetite", 10), ("Danger signs", "danger_signs", 22),
    ("Complications", "complications", 22), ("Well and alert", "clinically_well_and_alert", 10), ("HIV positive", "hiv_positive", 9),
    ("Visible severe wasting", "visible_severe_wasting", 10), ("Too weak to suckle", "too_weak_to_suckle", 10),
    ("Failure to gain weight", "failure_to_gain_weight", 10),
    ("WFL/H z", "wflh_z", 9), ("WFA z", "wfa_z", 9),
    ("Engine classification", "classification", 20), ("Tier", "tier", 9), ("Programme (engine)", "programme", 11),
    ("Rules fired", "rules", 28), ("Rule source and page", "rule_pages", 44), ("Reasons (if any)", "reasons", 30),
    ("Warnings", "warnings", 44), ("Worker sees (summary)", "worker_summary", 60),
]


def _cell(value):
    if value is None:
        return "not assessed"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(value) if value else "none"
    return value


def rows_as_cells(rows: list[dict]) -> list[list]:
    out = []
    for r in rows:
        flat = {**r["payload"], **{k: v for k, v in r.items() if k != "payload"}}
        out.append([_cell(flat.get(key)) if key in flat else "not given" for _, key, _ in COLS] + ["", ""])
    return out


def build_workbook(rows: list[dict]):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from thanzi_screen import __version__
    from thanzi_screen.rules.rules_v2016 import DISCLAIMER, RULES, RULE_SET_VERSION

    f, bold = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
    head_fill, input_fill = PatternFill("solid", fgColor="D9E2F3"), PatternFill("solid", fgColor="FFF2CC")
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    lines = [
        ("Thanzi screening engine: case pack for clinical review", bold),
        (f"Engine {__version__}, rule set {RULE_SET_VERSION}. Release candidate, not validated.", f),
        (DISCLAIMER, f),
        ("", f),
        ("What this is", bold),
        ("Synthetic scenarios run through the engine. 'Engine classification' and the columns after it are what the engine returned, "
         "with the rule and the printed page of the CMAM 2016 guideline (R3) it is based on. They are not clinically verified.", f),
        ("What to fill in", bold),
        ("Only the two yellow columns at the end of the Cases sheet: 'Clinician agrees?' (Yes, No or Unsure) and "
         "'Comment or expected result if different'. Do not edit any other cell.", f),
        ("Example of a filled row", bold),
        ("Case C000 | Clinician agrees? = No | Comment = Expected inpatient care because the child cannot drink. Checked against Table 5, p.16.", f),
        ("(C000 is an example only. It is not one of the cases.)", f),
        ("Notes", bold),
        ("The worker view never shows the programme for a moderate case, and never shows HIV information (D86). "
         "The 'Programme (engine)' column shows the real programme for review. Anthropometric z-scores are computed from the WHO 2006 tables. "
         "Measurements marked 'implausible' are ignored by the rules (D12, D23). The 'Rules' sheet lists every rule and its source page. "
         "Open wording items: I10 (referral slip text, placeholder), I18 and I23 (worker wording).", f),
    ]
    for r, (text, font) in enumerate(lines, start=1):
        cell = ws.cell(row=r, column=1, value=text)
        cell.font, cell.alignment = font, Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 120

    cs = wb.create_sheet("Cases")
    headers = [h for h, _, _ in COLS] + ["Clinician agrees?", "Comment or expected result if different"]
    cs.append(headers)
    for row in rows_as_cells(rows):
        cs.append(row)
    for col, (_, _, width) in enumerate(COLS, start=1):
        cs.column_dimensions[cs.cell(row=1, column=col).column_letter].width = width
    for extra in (len(COLS) + 1, len(COLS) + 2):
        cs.column_dimensions[cs.cell(row=1, column=extra).column_letter].width = 22 if extra == len(COLS) + 1 else 50
    for row in cs.iter_rows():
        for cell in row:
            cell.font = f
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in cs[1]:
        cell.font, cell.fill = bold, head_fill
    last = cs.max_row
    for col in (len(COLS) + 1, len(COLS) + 2):
        for r in range(2, last + 1):
            cs.cell(row=r, column=col).fill = input_fill
    dv = DataValidation(type="list", formula1='"Yes,No,Unsure"', allow_blank=True)
    cs.add_data_validation(dv)
    letter = cs.cell(row=1, column=len(COLS) + 1).column_letter
    dv.add(f"{letter}2:{letter}{last}")
    cs.freeze_panes = "C2"

    rs = wb.create_sheet("Rules")
    rs.append(["Rule", "Rule text", "Source", "Printed page", "Tag"])
    for rid, rule in RULES.items():
        rs.append([rid, rule.description, rule.source, rule.page, rule.tag])
    for row in rs.iter_rows():
        for cell in row:
            cell.font, cell.alignment = f, Alignment(wrap_text=True, vertical="top")
    for cell in rs[1]:
        cell.font, cell.fill = bold, head_fill
    for letter, width in zip("ABCDE", (28, 80, 10, 28, 16)):
        rs.column_dimensions[letter].width = width
    return wb


def sheet_values(wb) -> dict:
    norm = lambda v: None if v == "" else v          # openpyxl reads an empty string back as None
    return {ws.title: [[norm(v) for v in r] for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the committed workbook differs from a fresh run")
    args = ap.parse_args()
    from openpyxl import load_workbook
    fresh = build_workbook(build_cases())
    if args.check:
        if not OUT.exists():
            print("docs/testing/case-pack.xlsx is missing. Run: python scripts/build_case_pack.py", file=sys.stderr)
            return 1
        committed = sheet_values(load_workbook(OUT))
        wanted = sheet_values(fresh)
        # The two reviewer columns may be filled in the committed copy; everything else must match.
        n = len(COLS)
        for name, rows in wanted.items():
            got = committed.get(name)
            if got is None or len(got) != len(rows):
                print(f"sheet {name} differs in size. Run: python scripts/build_case_pack.py", file=sys.stderr)
                return 1
            for a, b in zip(rows, got):
                if name == "Cases":
                    a, b = a[:n], b[:n]
                if a != b:
                    print(f"sheet {name} differs. Run: python scripts/build_case_pack.py", file=sys.stderr)
                    return 1
        print("case pack matches a fresh run of the engine.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fresh.save(OUT)
    print(f"wrote {OUT.relative_to(ROOT)} ({fresh['Cases'].max_row - 1} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
