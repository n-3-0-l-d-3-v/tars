"""Build/test detection: one test per supported language marker, the
unrecognized-project-type failure case, and real end-to-end execution
against the shipped templates (python via pytest, node via `node --test`
-- both toolchains are guaranteed/likely present in this dev environment,
unlike cargo/go which get command-construction-only coverage)."""

import sys
from pathlib import Path

import pytest

from tars.dispatch import (
    DispatchError,
    resolve_build_command,
    detect_project_type,
    run_build,
    run_test,
    resolve_test_command,
)
from tars.safety import SafetyError


def test_detect_python_via_pyproject_toml(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert detect_project_type(tmp_path) == "python"


def test_detect_python_via_setup_py(tmp_path):
    (tmp_path / "setup.py").write_text("", encoding="utf-8")
    assert detect_project_type(tmp_path) == "python"


def test_detect_node_via_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert detect_project_type(tmp_path) == "node"


def test_detect_rust_via_cargo_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    assert detect_project_type(tmp_path) == "rust"


def test_detect_go_via_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert detect_project_type(tmp_path) == "go"


def test_detect_unrecognized_project_type_returns_none(tmp_path):
    (tmp_path / "README.md").write_text("nothing recognizable here", encoding="utf-8")
    assert detect_project_type(tmp_path) is None


def test_resolve_test_command_unrecognized_project_raises_dispatch_error(tmp_path):
    with pytest.raises(DispatchError):
        resolve_test_command(tmp_path)


def test_resolve_build_command_unrecognized_project_raises_dispatch_error(tmp_path):
    with pytest.raises(DispatchError):
        resolve_build_command(tmp_path)


def test_python_test_command_uses_pytest_module(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert resolve_test_command(tmp_path) == [sys.executable, "-m", "pytest"]


def test_python_build_command_uses_build_module(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert resolve_build_command(tmp_path) == [sys.executable, "-m", "build"]


def test_rust_commands(tmp_path):
    (tmp_path / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
    assert resolve_test_command(tmp_path) == ["cargo", "test"]
    assert resolve_build_command(tmp_path) == ["cargo", "build"]


def test_go_commands(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert resolve_test_command(tmp_path) == ["go", "test", "./..."]
    assert resolve_build_command(tmp_path) == ["go", "build", "./..."]


def test_node_test_command_reads_scripts_test(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": {"test": "node --test", "build": "tsc"}}', encoding="utf-8"
    )
    assert resolve_test_command(tmp_path) == ["npm", "run", "test"]
    assert resolve_build_command(tmp_path) == ["npm", "run", "build"]


def test_node_without_test_script_raises_dispatch_error(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {}}', encoding="utf-8")
    with pytest.raises(DispatchError):
        resolve_test_command(tmp_path)


def test_run_test_refuses_path_outside_allowed_roots(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    with pytest.raises(SafetyError):
        run_test(outside, roots=[allowed])


# --- real, non-mocked end-to-end runs against the shipped templates -----

def test_run_test_real_pytest_against_scaffolded_python_cli(tmp_path):
    from tars.scaffold import scaffold_project

    result = scaffold_project("python-cli", "dispatch-demo", tmp_path, roots=[tmp_path])
    outcome = run_test(result.path, roots=[tmp_path])
    assert outcome.ok, outcome.stderr + outcome.stdout
    assert "2 passed" in outcome.stdout or "passed" in outcome.stdout


def test_run_test_real_node_against_scaffolded_node_cli(tmp_path):
    import shutil

    if shutil.which("node") is None:
        pytest.skip("node not on PATH in this environment")

    from tars.scaffold import scaffold_project

    result = scaffold_project("node-cli", "dispatch-node-demo", tmp_path, roots=[tmp_path])
    outcome = run_test(result.path, roots=[tmp_path])
    assert outcome.ok, outcome.stderr + outcome.stdout


def test_run_build_real_node_against_scaffolded_node_cli(tmp_path):
    import shutil

    if shutil.which("node") is None:
        pytest.skip("node not on PATH in this environment")

    from tars.scaffold import scaffold_project

    result = scaffold_project("node-cli", "build-node-demo", tmp_path, roots=[tmp_path])
    outcome = run_build(result.path, roots=[tmp_path])
    assert outcome.ok, outcome.stderr + outcome.stdout
