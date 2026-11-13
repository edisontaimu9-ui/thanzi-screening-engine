"""Phase 7 files: workflows, constraints, compose example, tooling configs (D93-D100). Checked without Docker or GitHub."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))


def _yaml(path):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def test_workflows_parse_and_have_the_expected_jobs():
    names = {p.name: set(_yaml(p)["jobs"]) for p in WORKFLOWS}
    assert names == {"ci.yml": {"test", "dependencies", "secrets", "docker"}, "release.yml": {"verify", "release"}}


def test_every_job_has_a_timeout_and_every_action_is_pinned_to_a_sha():
    for p in WORKFLOWS:
        doc = _yaml(p)
        assert all("timeout-minutes" in j for j in doc["jobs"].values()), p.name
        for use in re.findall(r"uses:\s*(\S+)", p.read_text(encoding="utf-8")):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", use), (p.name, use)


def test_ci_cancels_superseded_runs_and_release_alone_may_write():
    ci, rel = _yaml(ROOT / ".github/workflows/ci.yml"), _yaml(ROOT / ".github/workflows/release.yml")
    assert ci["concurrency"]["cancel-in-progress"] is True
    assert ci["permissions"] == {"contents": "read"} and rel["permissions"] == {"contents": "read"}
    assert rel["jobs"]["release"]["permissions"] == {"contents": "write"}
    assert "contents" not in ci["jobs"]["test"].get("permissions", {})


def test_release_is_always_a_prerelease_and_needs_notes_and_matching_tag():
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "--prerelease" in text and "Release Candidate, Not Validated" in text and "--verify-tag" in text
    assert 'test "v$version" = "$GITHUB_REF_NAME"' in text and "docs/release/${GITHUB_REF_NAME}.md" in text
    assert "ghcr.io" not in text and "docker push" not in text            # publishing to a registry is Hope's (Q6)


def test_dependabot_watches_actions_docker_and_pip():
    doc = _yaml(ROOT / ".github/dependabot.yml")
    assert {u["package-ecosystem"] for u in doc["updates"]} == {"github-actions", "docker", "pip"}


def test_ci_smoke_uses_generated_keys_not_literals():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "openssl rand -hex 24" in ci and "ci-gateway-key" not in ci and "ci-audit-key" not in ci


def test_gitleaks_allowlist_is_only_the_known_throwaway_test_keys():
    text = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    assert re.findall(r"'''([^']+)'''", text) == [
        "ci-gateway-key-0123456789",    # historical Phase 6 CI smoke keys (D99)
        "ci-audit-key-0123456789ab",
        "wrong-key-0123456789",         # deliberately wrong key that tests send to prove a bad key is refused
    ]


def test_constraints_pin_everything_and_match_what_is_installed():
    from importlib import metadata
    from packaging.utils import canonicalize_name
    pins = {}
    for line in (ROOT / "constraints.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            m = re.fullmatch(r"([A-Za-z0-9_.-]+)==([\w.!+-]+)", line.strip())
            assert m, f"not an exact pin: {line}"
            pins[canonicalize_name(m.group(1))] = m.group(2)
    for name in ("fastapi", "pydantic", "uvicorn", "starlette", "pydantic-core"):
        assert name in pins, name
    for name, version in pins.items():
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        assert installed == version, f"{name}: installed {installed}, constraints.txt pins {version}"


def test_constraints_satisfy_the_ranges_in_pyproject():
    import tomllib
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    pins = {canonicalize_name(a): b for a, b in re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)$", (ROOT / "constraints.txt").read_text(), re.M)}
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    for spec in extras["api"] + extras["dev"]:
        req = Requirement(spec)
        name = canonicalize_name(req.name)
        assert name in pins, f"{req.name} is not pinned in constraints.txt"
        assert req.specifier.contains(pins[name], prereleases=True), f"{spec} not satisfied by pin {pins[name]}"


def test_dockerfile_and_ci_install_with_the_constraints_file():
    assert 'pip install -c constraints.txt ".[api]"' in (ROOT / "Dockerfile").read_text()
    ignore = (ROOT / ".dockerignore").read_text().split()
    assert "constraints.txt" not in ignore


def test_version_is_consistent_everywhere():
    import tomllib
    import thanzi_screen
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert py == thanzi_screen.__version__ == "0.7.0"
    assert f'"version": "{py}"' in (ROOT / "docs/api/openapi.json").read_text()
    assert f"## {py}" in (ROOT / "CHANGELOG.md").read_text()
    assert (ROOT / f"docs/release/v{py}.md").exists()


def test_compose_example_is_private_and_uses_secret_files():
    doc = _yaml(ROOT / "deploy/docker-compose.example.yml")
    svc = doc["services"]["thanzi"]
    assert "ports" not in svc                                                   # no published port (I21)
    assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"] and "no-new-privileges:true" in svc["security_opt"]
    assert doc["networks"]["thanzi_private"]["internal"] is True
    env = svc["environment"]
    assert all(v.startswith("${") for k, v in env.items() if k.endswith("_KEY"))    # keys never written in the file


def test_traceability_file_lists_every_rule_and_none_untested():
    from thanzi_screen.rules.rules_v2016 import RULES
    text = (ROOT / "docs/testing/traceability.md").read_text(encoding="utf-8")
    assert set(re.findall(r"^\| `([A-Z0-9_.]+)` \|", text, re.M)) == set(RULES)
    assert "Rules with no test: none." in text


@pytest.mark.parametrize("script", ["smoke_api.py", "load_probe.py", "build_traceability.py", "build_case_pack.py",
                                    "refresh_constraints.py"])
def test_scripts_show_help(script):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"] if script != "refresh_constraints.py"
                       else [sys.executable, "-c", f"import ast,sys;ast.parse(open(r'{ROOT / 'scripts' / script}').read())"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_case_pack_matches_a_fresh_run():
    pytest.importorskip("openpyxl")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/build_case_pack.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
