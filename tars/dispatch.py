"""Language-agnostic build/test dispatch: detect a project's type from
marker files and shell out to the right command. A thin, honest
dispatcher -- if no marker file is recognized, this fails with a clear
error rather than guessing.

Supported markers (checked in this order):
  pyproject.toml or setup.py -> python  (pytest / python -m build)
  package.json                -> node    (npm run <scripts.test|scripts.build>)
  Cargo.toml                  -> rust    (cargo test / cargo build)
  go.mod                      -> go      (go test ./... / go build ./...)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tars.safety import ensure_within_allowed_roots


class DispatchError(Exception):
    """Raised when the project type can't be detected, or a required
    command/script is missing."""


@dataclass
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def detect_project_type(path: Path) -> str | None:
    """Return 'python' | 'node' | 'rust' | 'go' | None (unrecognized)."""
    if (path / "pyproject.toml").is_file() or (path / "setup.py").is_file():
        return "python"
    if (path / "package.json").is_file():
        return "node"
    if (path / "Cargo.toml").is_file():
        return "rust"
    if (path / "go.mod").is_file():
        return "go"
    return None


def _node_script_command(path: Path, script: str) -> list[str]:
    package_json = path / "package.json"
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DispatchError(f"Could not read/parse {package_json}: {exc}") from exc
    scripts = data.get("scripts", {})
    if script not in scripts:
        raise DispatchError(
            f"package.json has no scripts.{script} entry -- nothing to run."
        )
    return ["npm", "run", script]


def resolve_test_command(path: Path) -> list[str]:
    kind = detect_project_type(path)
    if kind == "python":
        return [sys.executable, "-m", "pytest"]
    if kind == "node":
        return _node_script_command(path, "test")
    if kind == "rust":
        return ["cargo", "test"]
    if kind == "go":
        return ["go", "test", "./..."]
    raise DispatchError(
        f"Don't know how to test '{path}': no recognized project marker "
        "(pyproject.toml, setup.py, package.json, Cargo.toml, go.mod)."
    )


def resolve_build_command(path: Path) -> list[str]:
    kind = detect_project_type(path)
    if kind == "python":
        return [sys.executable, "-m", "build"]
    if kind == "node":
        return _node_script_command(path, "build")
    if kind == "rust":
        return ["cargo", "build"]
    if kind == "go":
        return ["go", "build", "./..."]
    raise DispatchError(
        f"Don't know how to build '{path}': no recognized project marker "
        "(pyproject.toml, setup.py, package.json, Cargo.toml, go.mod)."
    )


def _run(command: list[str], cwd: Path) -> CommandResult:
    # On Windows, subprocess/CreateProcess does NOT search PATHEXT the way
    # a shell does, so a bare "npm" fails to resolve (it's really
    # npm.cmd) even though it's on PATH. shutil.which does the same
    # PATH(EXT) search a shell would, so resolve the executable through it
    # first -- a no-op on POSIX / when the command isn't found (the
    # unresolved name is passed through so the real "command not found"
    # error still surfaces).
    resolved = shutil.which(command[0])
    argv = [resolved, *command[1:]] if resolved else command
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise DispatchError(f"'{command[0]}' is not installed or not on PATH: {exc}") from exc
    return CommandResult(
        command=command, returncode=result.returncode,
        stdout=result.stdout, stderr=result.stderr,
    )


def run_test(path: Path, roots=None) -> CommandResult:
    resolved = ensure_within_allowed_roots(path, roots)
    command = resolve_test_command(resolved)
    return _run(command, resolved)


def run_build(path: Path, roots=None) -> CommandResult:
    resolved = ensure_within_allowed_roots(path, roots)
    command = resolve_build_command(resolved)
    return _run(command, resolved)
