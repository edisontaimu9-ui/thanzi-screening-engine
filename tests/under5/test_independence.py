import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def _modules_after_import(stmt: str) -> set[str]:
    code = f"import sys; {stmt}; print('\\n'.join(sorted(m for m in sys.modules if m.startswith('thanzi_screen'))))"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONPATH": str(SRC)}, check=True)
    return set(out.stdout.split())


def test_screening_imports_no_ml_or_prediction():
    mods = _modules_after_import("import thanzi_screen.under5")
    assert not any(m.startswith(("thanzi_screen.ml", "thanzi_screen.prediction")) for m in mods), mods


def test_report_imports_neither_module():
    mods = _modules_after_import("import thanzi_screen.report")
    assert not any(m.startswith(("thanzi_screen.ml", "thanzi_screen.prediction", "thanzi_screen.under5")) for m in mods), mods


def test_factors_import_no_screening_or_ml():
    mods = _modules_after_import("import thanzi_screen.factors")
    assert not any(m.startswith(("thanzi_screen.ml", "thanzi_screen.prediction", "thanzi_screen.under5")) for m in mods), mods
