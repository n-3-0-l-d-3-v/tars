"""CLI: --health output shape, `templates` listing, and a `new` +
safety-refusal smoke test through the actual Click entry point."""

import json
from pathlib import Path

from click.testing import CliRunner

from tars.cli import cli


def test_health_flag_prints_json_and_exits_zero_when_templates_present():
    runner = CliRunner()
    result = runner.invoke(cli, ["--health"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["healthy"] is True
    assert "python-cli" in payload["templates_found"]
    assert "node-cli" in payload["templates_found"]
    assert "version" in payload
    assert "allowed_roots" in payload


def test_templates_command_lists_shipped_templates():
    runner = CliRunner()
    result = runner.invoke(cli, ["templates"])
    assert result.exit_code == 0
    assert "python-cli" in result.output
    assert "node-cli" in result.output


def test_new_command_scaffolds_a_real_project(tmp_path, monkeypatch):
    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(tmp_path))
    runner = CliRunner()
    result = runner.invoke(
        cli, ["new", "python-cli", "cli-demo", "--dest", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    project = tmp_path / "cli-demo"
    assert project.is_dir()
    assert (project / ".git").is_dir()


def test_new_command_fails_closed_outside_allowed_roots(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(allowed))

    outside = tmp_path / "Windows" / "System32"
    runner = CliRunner()
    result = runner.invoke(
        cli, ["new", "python-cli", "myproj", "--dest", str(outside)]
    )
    assert result.exit_code == 1
    assert not (outside / "myproj").exists()


def test_test_command_reports_error_for_unrecognized_project(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["test", "--path", str(tmp_path)])
    assert result.exit_code == 1
    assert "Error" in result.output
