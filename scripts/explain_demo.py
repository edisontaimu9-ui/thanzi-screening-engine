#!/usr/bin/env python3
"""Print the worker summary (and, with --audit, the full trace) for sample records. Synthetic examples only.

Usage: python scripts/explain_demo.py [--audit] [--json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from thanzi_screen.explain import explain  # noqa: E402
from thanzi_screen.ml import load_models  # noqa: E402
from thanzi_screen.rules import Appetite, ClinicalInputs, OedemaGrade  # noqa: E402

FULL = dict(appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset(), clinically_well_and_alert=True)
SAMPLES = {
    "Low risk, child 16 months": ("male", 500, 11.0, 80.0, "length", ClinicalInputs(muac_cm=14.0, **FULL)),
    "MUAC just under 11.5, all assessed (OTP)": ("male", 400, 8.0, 72.0, "length", ClinicalInputs(muac_cm=11.4, **FULL)),
    "MUAC just under 11.5, assessments missing": ("male", 400, 8.0, 72.0, "length", ClinicalInputs(muac_cm=11.4)),
    "MUAC recorded in mm (135)": ("female", 360, 9.5, 75.0, "length", ClinicalInputs(muac_cm=135.0, **FULL)),
    "Infant, nothing assessed": ("male", 90, 5.5, 58.0, "length", ClinicalInputs()),
    "Infant with oedema": ("female", 120, 4.0, 56.0, "length", ClinicalInputs(oedema=OedemaGrade.PLUS)),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="also print rules, criteria, flag and review traces")
    ap.add_argument("--json", action="store_true", help="print the full Explanation as JSON")
    args = ap.parse_args()
    models = load_models()
    for title, case in SAMPLES.items():
        e = explain(*case, models)
        print(f"== {title}")
        if args.json:
            print(e.to_json(indent=2))
            continue
        for line in e.summary:
            print(" ", line)
        if args.audit:
            t = e.classification_trace
            print("  [rules]", ", ".join(f"{r.id} ({r.source} {r.page}, {r.tag})" for r in t.rules))
            for c in t.criteria:
                print("  [criterion]", c.text)
            for n in t.audit_notes:
                print("  [audit note]", n)
            f = e.flag_trace
            print(f"  [ml] p={f.probability:.3f} threshold={f.threshold:.3f} flagged={f.flagged}")
            for c in f.contributions[:5]:
                print(f"    {c.contribution:+.2f} {c.text}")
            for r in e.review_trace.reasons:
                print("  [review]", r.code, "-", r.evidence)
        print()


if __name__ == "__main__":
    main()
