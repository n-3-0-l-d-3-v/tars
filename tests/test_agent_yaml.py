"""agent.yaml validity per the ecosystem contract (matches the fields
Wall-E's own contract_check.py verifies for every sibling agent)."""

from pathlib import Path

import yaml

REQUIRED_FIELDS = {
    "name", "role", "default_sensitivity_tier", "entrypoint",
    "health_check_command", "sandboxed",
}
VALID_TIERS = {"private", "personal-token", "work", "public"}

AGENT_YAML_PATH = Path(__file__).resolve().parents[1] / "agent.yaml"


def _load():
    with AGENT_YAML_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_agent_yaml_exists_and_parses():
    assert AGENT_YAML_PATH.is_file()
    data = _load()
    assert isinstance(data, dict)


def test_agent_yaml_has_all_required_fields():
    data = _load()
    missing = REQUIRED_FIELDS - data.keys()
    assert not missing, f"agent.yaml missing fields: {missing}"


def test_agent_yaml_tier_is_valid():
    data = _load()
    assert data["default_sensitivity_tier"] in VALID_TIERS


def test_agent_yaml_matches_task_spec_values():
    data = _load()
    assert data["name"] == "TARS"
    assert data["role"] == "code-build-test-scaffolding"
    assert data["default_sensitivity_tier"] == "work"
    assert data["entrypoint"] == "tars"
    assert data["health_check_command"] == "tars --health"
    assert data["sandboxed"] is False
