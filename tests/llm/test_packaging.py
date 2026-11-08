"""Packaging of the optional feature: extra, pins, example files. The release image and its install line are unchanged."""
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_llm_extra_is_pinned_and_the_engine_stays_dependency_free():
    from packaging.requirements import Requirement
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == []
    extra = project["optional-dependencies"]["llm"]
    pins = dict(re.findall(r"^([A-Za-z0-9_.-]+)==(\S+)$", (ROOT / "constraints.txt").read_text(), re.M))
    for spec in extra:
        req = Requirement(spec)
        assert req.specifier.contains(pins[req.name], prereleases=True), spec


def test_release_dockerfile_is_unchanged_in_what_it_installs():
    text = (ROOT / "Dockerfile").read_text()
    assert 'pip install -c constraints.txt ".[api]"' in text and "httpx" not in text


def test_derived_dockerfile_adds_only_httpx_with_the_constraints():
    text = (ROOT / "deploy" / "Dockerfile.llm").read_text()
    assert "constraints.txt" in text and 'httpx~=0.28.1' in text and text.rstrip().endswith("USER thanzi")


def test_example_files_parse_and_hold_no_secret_values():
    yaml = pytest.importorskip("yaml")
    compose = yaml.safe_load((ROOT / "deploy" / "docker-compose.llm.example.yml").read_text())
    assert compose["networks"]["llm_private"]["internal"] is True
    assert "ports" not in compose["services"]["ollama"] and "ports" not in compose["services"]["thanzi"]
    env = (ROOT / "deploy" / "llm.env.example").read_text()
    assert re.search(r"^THANZI_LLM_API_KEY=$", env, re.M) and re.search(r"^THANZI_LLM_ALLOW_REMOTE=0$", env, re.M)


def test_every_variable_in_the_env_example_is_one_the_loader_reads():
    from thanzi_screen.llm import LLMConfig
    from thanzi_screen.llm.config import ENV_PREFIX, ENV_SETTINGS
    known = {ENV_PREFIX + name for _, name, _ in ENV_SETTINGS} | {"THANZI_LLM_ENABLED"}
    lines = (ROOT / "deploy" / "llm.env.example").read_text().splitlines()
    env = {}
    for line in lines:
        m = re.match(r"^#?\s*(THANZI_LLM_[A-Z_]+)=(\S*)", line)
        if m and m.group(2) and m.group(1) not in ("THANZI_LLM_ENABLED", "THANZI_LLM_ENDPOINT"):
            env[m.group(1)] = m.group(2)
    assert len(env) > 12 and set(env) <= known, sorted(set(env) - known)
    assert {ENV_PREFIX + n for _, n, _ in ENV_SETTINGS} - {"THANZI_LLM_STOP"} <= set(re.findall(r"THANZI_LLM_[A-Z_]+", "\n".join(lines)))
    LLMConfig.from_env({**env, "THANZI_LLM_ENDPOINT": "http://ollama:11434"})        # raises if any value or name is wrong
