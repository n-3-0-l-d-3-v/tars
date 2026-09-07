"""Git operations, scoped to the safety boundary in tars/safety.py.

`tars branch` and `tars commit` only. Deliberately **no `tars push`** --
pushing/publishing is a user-confirmed action across this ecosystem (every
sibling agent's own agent.yaml notes, and 10x's own conventions), not
something an agent does autonomously. See README.md.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tars.safety import ensure_within_allowed_roots


class GitOpsError(Exception):
    """Raised for any user-facing git-operation failure."""


@dataclass
class GitResult:
    command: list[str]
    stdout: str
    stderr: str


def _run_git(args: list[str], cwd: Path) -> GitResult:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GitOpsError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}"
        )
    return GitResult(command=["git", *args], stdout=result.stdout, stderr=result.stderr)


def _ensure_git_repo(path: Path) -> None:
    if not (path / ".git").exists():
        raise GitOpsError(f"'{path}' is not a git repository (no .git found).")


def create_branch(name: str, path: Path, roots=None) -> GitResult:
    """Create and switch to a new branch `name` in the repo at `path`."""
    if not name or not name.strip():
        raise GitOpsError("Branch name must not be empty.")
    resolved = ensure_within_allowed_roots(path, roots)
    _ensure_git_repo(resolved)
    return _run_git(["checkout", "-b", name], cwd=resolved)


def commit_all(message: str, path: Path, roots=None) -> GitResult:
    """Stage everything and commit in the repo at `path`."""
    if not message or not message.strip():
        raise GitOpsError("Commit message must not be empty.")
    resolved = ensure_within_allowed_roots(path, roots)
    _ensure_git_repo(resolved)
    _run_git(["add", "-A"], cwd=resolved)
    return _run_git(["commit", "-m", message], cwd=resolved)


def status(path: Path, roots=None) -> GitResult:
    """`git status --porcelain` in the repo at `path` -- used by both the
    CLI's implicit checks and the MCP server's `git_status` tool."""
    resolved = ensure_within_allowed_roots(path, roots)
    _ensure_git_repo(resolved)
    return _run_git(["status", "--porcelain"], cwd=resolved)
