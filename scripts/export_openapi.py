"""Write or check the committed API contract, docs/api/openapi.json (Phase 6, D84).

    python scripts/export_openapi.py            # regenerate the file
    python scripts/export_openapi.py --check    # exit 1 if the file is stale (CI)

Needs the api extra: pip install -e ".[api]"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "docs" / "api" / "openapi.json"


def render() -> str:
    from thanzi_screen.api.app import create_app
    app = create_app(gateway_key="x" * 32, models_dir=ROOT / "models")
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if docs/api/openapi.json differs from the live app")
    args = ap.parse_args()
    text = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("docs/api/openapi.json is stale. Run: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        print("docs/api/openapi.json is up to date.")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
