"""Clinical review pack and deployment gates (Phase 11).

    python scripts/review_pack.py write            # write the reviewer checklist and the unsigned sign-off templates
    python scripts/review_pack.py check            # exit 1 if those committed files are stale (CI runs this as a test)
    python scripts/review_pack.py gate [--dir D]   # exit 1 if a feature that is switched on has no valid sign-off (deploy preflight)
    python scripts/review_pack.py gate --all       # check every feature, switched on or not (prints the reasons)

`gate` reads the same switches as the service (THANZI_CHILD_REPORT_ENABLED, THANZI_SURVEILLANCE_REPORTS_ENABLED) and the folder
THANZI_REVIEW_SIGNOFF_DIR (or --dir). It prints reason codes only, never a reviewer's name. Standard library only.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from thanzi_screen.review import SUBJECTS, check_subject, signoff_dir  # noqa: E402
from thanzi_screen.review.pack import checklist_markdown, template_text  # noqa: E402

REVIEW = ROOT / "docs" / "review"
SIGNOFF = REVIEW / "signoff"


def expected_files() -> dict[Path, str]:
    files = {REVIEW / "reviewer-checklist.md": checklist_markdown()}
    for s in SUBJECTS.values():
        files[SIGNOFF / s.filename.replace(".signoff.json", ".signoff.template.json")] = template_text(s)
    return files


def stale() -> list[Path]:
    return [p for p, text in expected_files().items() if not p.is_file() or p.read_text(encoding="utf-8") != text]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("write", "check", "gate"))
    ap.add_argument("--dir", help="folder with the signed files (default: THANZI_REVIEW_SIGNOFF_DIR)")
    ap.add_argument("--all", action="store_true", help="gate: check every feature, not only the ones switched on")
    args = ap.parse_args(argv)

    if args.command == "write":
        for path, text in expected_files().items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print("wrote", path.relative_to(ROOT))
        return 0
    if args.command == "check":
        bad = stale()
        for p in bad:
            print(f"{p.relative_to(ROOT)} is stale. Run: python scripts/review_pack.py write", file=sys.stderr)
        return 1 if bad else 0

    directory = args.dir or signoff_dir()
    blocked = False
    for s in SUBJECTS.values():
        wanted = os.environ.get(s.flag, "").strip().lower() in ("1", "true", "yes", "on")
        if not wanted and not args.all:
            print(f"{s.key}: off ({s.flag} is not 1)")
            continue
        result = check_subject(s.key, directory)
        print(f"{s.key}: {'OK' if result.ok else 'BLOCKED'}" + ("" if result.ok else " - " + ", ".join(result.reasons)))
        blocked = blocked or (wanted and not result.ok)
    return 1 if blocked else 0


if __name__ == "__main__":
    sys.exit(main())
