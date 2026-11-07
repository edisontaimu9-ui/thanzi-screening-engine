"""CI and Docker files, checked as text so this runs without Docker or PyYAML (D84)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github/workflows/ci.yml").read_text()
DOCKER = (ROOT / "Dockerfile").read_text()


def test_ci_runs_on_push_and_pr_to_main():
    assert re.search(r"push:\s*\n\s*branches: \[main\]", CI) and re.search(r"pull_request:\s*\n\s*branches: \[main\]", CI)


def test_ci_matrix_and_full_suite():
    assert '"3.11"' in CI and '"3.12"' in CI
    assert 'pip install -e ".[dev,api]"' in CI
    assert re.search(r"python -m pytest -q\s*$", CI, re.M)
    assert 'THANZI_REQUIRE_API_TESTS: "1"' in CI


def test_ci_checks_the_openapi_file():
    assert "python scripts/export_openapi.py --check" in CI


def test_ci_docker_job_builds_starts_and_checks():
    assert re.search(r"^  docker:", CI, re.M)
    for needle in ("docker build", "docker run", "/health", "/v1/screen", "id -u", "X-Gateway-Key"):
        assert needle in CI, needle


def test_ci_actions_are_pinned_to_major_versions():
    uses = re.findall(r"uses:\s*(\S+)", CI)
    assert uses and all(re.search(r"@v\d+$", u) for u in uses), uses


def test_ci_has_read_only_permissions():
    assert re.search(r"permissions:\s*\n\s*contents: read", CI)


def test_dockerfile_is_non_root_with_healthcheck_and_no_dev_deps():
    assert re.search(r"^USER thanzi$", DOCKER, re.M) and "useradd" in DOCKER
    assert "HEALTHCHECK" in DOCKER and "/health" in DOCKER
    assert '".[api]"' in DOCKER and "dev" not in re.sub(r"#.*", "", DOCKER).replace("development", "")
    assert "pytest" not in DOCKER and "httpx" not in DOCKER


def test_dockerfile_bakes_in_no_secrets_and_publishes_no_port():
    code = re.sub(r"#.*", "", DOCKER)
    assert "EXPOSE" not in code
    assert not re.search(r"(GATEWAY|AUDIT)_KEY\s*=", code) and "THANZI_DEV_MODE" not in code
    assert "--factory thanzi_screen.api.app:create_app_from_env" in DOCKER


def test_dockerignore_keeps_secrets_and_data_out():
    ignore = (ROOT / ".dockerignore").read_text().split()
    for item in (".env", "data", ".git", "tests"):
        assert item in ignore


def test_pyproject_declares_the_api_extra_and_dev_httpx():
    text = (ROOT / "pyproject.toml").read_text()
    assert re.search(r"^api = \[.*fastapi.*pydantic.*uvicorn.*\]", text, re.M)
    assert re.search(r"^dev = \[.*httpx", text, re.M)
    assert re.search(r"^dependencies = \[\]", text, re.M)           # the engine stays standard library


def test_api_tests_cannot_be_skipped_when_required(monkeypatch):
    import importlib.util
    import pytest
    from tests.api._support import need_api
    monkeypatch.setenv("THANZI_REQUIRE_API_TESTS", "1")
    if importlib.util.find_spec("fastapi") is None:
        with pytest.raises(pytest.fail.Exception):
            need_api()
    else:
        need_api()                                                  # present: returns quietly


def test_ci_file_is_valid_yaml_with_the_expected_jobs():
    """The text checks above cannot see a YAML syntax error, which GitHub reports as an invalid workflow."""
    import pytest
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(CI)
    assert set(doc["jobs"]) == {"test", "docker"}
    assert doc["jobs"]["test"]["strategy"]["matrix"]["python-version"] == ["3.11", "3.12"]
    assert doc["jobs"]["test"]["env"]["THANZI_REQUIRE_API_TESTS"] == "1"
    steps = doc["jobs"]["docker"]["steps"]
    assert all("uses" in s or "run" in s for s in steps)
    assert doc["jobs"]["docker"]["needs"] == "test"
