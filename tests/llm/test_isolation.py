"""D128: model inference is independent of clinical screening, in both directions, and stays light."""
import ast
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "thanzi_screen"
LLM = SRC / "llm"
# the only two modules outside the package that may know about it: the optional routes and the app that mounts them
ALLOWED_USERS = {SRC / "api" / "app.py", SRC / "api" / "llm_routes.py"}


def imports(path):
    """Yield (level, module, names) for every import in a file."""
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield 0, a.name, []
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or "", [a.name for a in node.names]


def test_llm_package_imports_nothing_from_the_screening_code():
    for path in LLM.rglob("*.py"):
        depth = len(path.relative_to(LLM).parts)                 # 1 for llm/x.py, 2 for llm/providers/x.py
        for level, module, names in imports(path):
            if level == 0:
                assert not module.startswith("thanzi_screen") or module.startswith("thanzi_screen.llm"), (path, module)
            else:
                assert level <= depth, f"{path} reaches outside thanzi_screen.llm with a relative import"


def test_screening_code_never_imports_the_llm_package():
    offenders = []
    for path in SRC.rglob("*.py"):
        if LLM in path.parents or path in ALLOWED_USERS:
            continue
        for level, module, names in imports(path):
            if "llm" in module.split(".") or (not module and "llm" in names):       # `..llm`, `thanzi_screen.llm`, `from .. import llm`
                offenders.append(str(path.relative_to(SRC)))
    assert not offenders, offenders


def test_service_and_engines_have_no_llm_name_at_all():
    for sub in ("anthro", "rules", "ml", "explain", "preterm", "data", "schemas"):
        for path in (SRC / sub).glob("*.py"):
            assert "thanzi_screen.llm" not in path.read_text() and "from ..llm" not in path.read_text(), path
    assert "llm" not in (SRC / "api" / "service.py").read_text().lower()


def test_importing_the_package_is_light():
    code = ("import sys, thanzi_screen.llm as m\n"
            "heavy = [n for n in ('httpx', 'fastapi', 'pydantic', 'starlette', 'thanzi_screen.rules', 'thanzi_screen.anthro',"
            " 'thanzi_screen.ml', 'thanzi_screen.api') if n in sys.modules]\n"
            "print(','.join(heavy))")
    env = {**os.environ, "PYTHONPATH": str(SRC.parent)}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", "importing thanzi_screen.llm pulled in: " + out.stdout.strip()
