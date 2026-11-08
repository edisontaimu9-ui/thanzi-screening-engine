"""Refresh constraints.txt from a clean virtual environment (Phase 7, D98).

    python scripts/refresh_constraints.py

Creates a temporary venv, installs the project with the dev and api extras at the newest versions that
pyproject.toml allows, and writes every installed package (except this project) to constraints.txt.
Then run the full suite, `python scripts/export_openapi.py --check` and `python scripts/build_case_pack.py --check`
before committing. Needs network access to PyPI. Review the diff: every change is a dependency update.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = """# Pinned versions of every package the project installs, direct and transitive (Phase 7, D98).
# Used by CI, the Docker build and the release build:  pip install -c constraints.txt ".[api]"
# It is a constraints file: it limits versions, it does not add packages. Refresh with:
#   python scripts/refresh_constraints.py
# then run the full suite and `python scripts/export_openapi.py --check` before committing.
# Generated on Python {py} and checked on 3.11 and 3.12.
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        env = Path(tmp) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(env)], check=True)
        py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)
        subprocess.run([str(py), "-m", "pip", "install", "--quiet", f"{ROOT}[dev,api]"], check=True)
        out = subprocess.run([str(py), "-m", "pip", "freeze", "--exclude", "thanzi-screen", "--exclude", "pip"],
                             check=True, capture_output=True, text=True).stdout
    lines = sorted((l for l in out.splitlines() if l.strip()), key=str.lower)
    py_version = ".".join(map(str, sys.version_info[:3]))
    (ROOT / "constraints.txt").write_text(HEADER.format(py=py_version) + "\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote constraints.txt with {len(lines)} pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
