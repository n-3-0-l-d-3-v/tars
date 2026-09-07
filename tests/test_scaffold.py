"""Real end-to-end scaffolding tests: actual filesystem, actual `git
init`/commit -- not mocked. One test per shipped template, plus the
safety-boundary refusal and a few error-path tests."""

import subprocess
from pathlib import Path

import pytest

from tars.safety import SafetyError
from tars.scaffold import ScaffoldError, list_templates, scaffold_project


def test_list_templates_finds_both_shipped_templates():
    names = list_templates()
    assert "python-cli" in names
    assert "node-cli" in names


def test_scaffold_python_cli_end_to_end(tmp_path):
    result = scaffold_project("python-cli", "demo-project", tmp_path, roots=[tmp_path])

    project = tmp_path / "demo-project"
    assert result.path == project
    assert project.is_dir()

    # Name substitution landed in the right places.
    pyproject_text = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "demo-project"' in pyproject_text
    assert "demo_project.cli:main" in pyproject_text

    package_dir = project / "src" / "demo_project"
    assert package_dir.is_dir()
    assert (package_dir / "cli.py").is_file()
    cli_text = (package_dir / "cli.py").read_text(encoding="utf-8")
    assert "__TARS_PROJECT_NAME__" not in cli_text
    assert "demo-project" in cli_text

    # No leftover placeholder directories.
    assert not (project / "src" / "__TARS_PACKAGE_NAME__").exists()

    # git init + initial commit really happened.
    assert (project / ".git").is_dir()
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=project, capture_output=True, text=True,
    )
    assert log.returncode == 0
    assert log.stdout.strip() != ""
    assert result.initial_commit and len(result.initial_commit) >= 7

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True,
    )
    assert status.stdout.strip() == ""  # everything committed, tree clean


def test_scaffold_node_cli_end_to_end(tmp_path):
    result = scaffold_project("node-cli", "demo-node-app", tmp_path, roots=[tmp_path])

    project = tmp_path / "demo-node-app"
    assert project.is_dir()

    package_json = (project / "package.json").read_text(encoding="utf-8")
    assert '"name": "demo-node-app"' in package_json

    index_js = (project / "src" / "index.js").read_text(encoding="utf-8")
    assert "demo-node-app" in index_js
    assert "__TARS_PROJECT_NAME__" not in index_js

    assert (project / ".git").is_dir()
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=project, capture_output=True, text=True,
    )
    assert log.stdout.strip() != ""
    assert result.initial_commit


def test_scaffold_refuses_destination_outside_allowed_roots(tmp_path):
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside = tmp_path / "Windows" / "System32"

    with pytest.raises(SafetyError):
        scaffold_project(
            "python-cli", "myproj", outside, roots=[allowed_root]
        )
    # And it must genuinely not have created anything.
    assert not (outside / "myproj").exists()


def test_scaffold_unknown_template_raises_scaffold_error(tmp_path):
    with pytest.raises(ScaffoldError):
        scaffold_project("does-not-exist", "myproj", tmp_path)


def test_scaffold_invalid_project_name_raises_scaffold_error(tmp_path):
    with pytest.raises(ScaffoldError):
        scaffold_project("python-cli", "../escape", tmp_path)


def test_scaffold_refuses_nonempty_existing_destination(tmp_path):
    target = tmp_path / "demo-project"
    target.mkdir()
    (target / "existing.txt").write_text("hi", encoding="utf-8")
    with pytest.raises(ScaffoldError):
        scaffold_project("python-cli", "demo-project", tmp_path, roots=[tmp_path])
