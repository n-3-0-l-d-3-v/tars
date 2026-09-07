"""`tars new <template> <project-name>`: copy a template into a real
project directory, substitute the project name, `git init`, initial
commit.

Placeholders substituted in file contents AND path components:
  __TARS_PROJECT_NAME__  -> the project name as given (e.g. "demo-project")
  __TARS_PACKAGE_NAME__  -> a Python-identifier-safe form (e.g. "demo_project")
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tars.safety import ensure_within_allowed_roots

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

PROJECT_NAME_TOKEN = "__TARS_PROJECT_NAME__"
PACKAGE_NAME_TOKEN = "__TARS_PACKAGE_NAME__"

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")

# Extensions/files we know are text and safe to substitute into. Anything
# else is copied byte-for-byte untouched (defensive default: don't
# corrupt binaries the templates might one day include).
_TEXT_SUFFIXES = {
    ".py", ".toml", ".md", ".txt", ".json", ".js", ".ts", ".cfg", ".ini",
    ".yaml", ".yml", ".gitignore", "",
}


class ScaffoldError(Exception):
    """Raised for any user-facing scaffold failure (bad name, unknown
    template, existing destination, git failure)."""


@dataclass
class ScaffoldResult:
    template: str
    project_name: str
    package_name: str
    path: Path
    initial_commit: str


def list_templates() -> list[str]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return sorted(
        p.name for p in TEMPLATES_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def _validate_project_name(name: str) -> None:
    if not name or not _NAME_RE.match(name):
        raise ScaffoldError(
            f"Invalid project name '{name}': must start with a letter and "
            "contain only letters, digits, '-' or '_'."
        )


def _package_name(project_name: str) -> str:
    """A Python-identifier-safe form of the project name."""
    return project_name.replace("-", "_")


def _is_text_file(path: Path) -> bool:
    return path.suffix in _TEXT_SUFFIXES or path.name == ".gitignore"


def _substitute_in_tree(root: Path, project_name: str, package_name: str) -> None:
    """Replace placeholder tokens in file contents, then rename any path
    components containing a placeholder token. Contents first, so renaming
    doesn't affect the walk order in confusing ways."""
    for path in root.rglob("*"):
        if path.is_file() and _is_text_file(path):
            text = path.read_text(encoding="utf-8")
            if PROJECT_NAME_TOKEN in text or PACKAGE_NAME_TOKEN in text:
                text = text.replace(PROJECT_NAME_TOKEN, project_name)
                text = text.replace(PACKAGE_NAME_TOKEN, package_name)
                path.write_text(text, encoding="utf-8")

    # Rename path components deepest-first so renaming a parent doesn't
    # invalidate a child Path object we still need to visit.
    all_paths = sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True)
    for path in all_paths:
        name = path.name
        if PROJECT_NAME_TOKEN in name or PACKAGE_NAME_TOKEN in name:
            new_name = name.replace(PROJECT_NAME_TOKEN, project_name)
            new_name = new_name.replace(PACKAGE_NAME_TOKEN, package_name)
            path.rename(path.with_name(new_name))


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ScaffoldError(
            f"git {' '.join(args)} failed in {cwd}: {result.stderr.strip()}"
        )
    return result


def scaffold_project(
    template: str,
    project_name: str,
    dest_dir: Path,
    roots: list[Path] | None = None,
) -> ScaffoldResult:
    """Copy `template` into `dest_dir/project_name`, substitute the
    project name, `git init` + initial commit. Raises ScaffoldError or
    tars.safety.SafetyError (allowed-roots refusal) on failure."""
    _validate_project_name(project_name)

    template_dir = TEMPLATES_DIR / template
    if not template_dir.is_dir():
        available = ", ".join(list_templates()) or "(none)"
        raise ScaffoldError(
            f"Unknown template '{template}'. Available: {available}"
        )

    target = Path(dest_dir) / project_name
    # Fail-closed safety boundary FIRST, before touching the filesystem.
    ensure_within_allowed_roots(target, roots)

    if target.exists():
        if any(target.iterdir()):
            raise ScaffoldError(f"Destination '{target}' already exists and is not empty.")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)

    shutil.copytree(template_dir, target, dirs_exist_ok=True)

    package_name = _package_name(project_name)
    _substitute_in_tree(target, project_name, package_name)

    _run_git(["init", "-b", "main"], cwd=target)
    _run_git(["add", "-A"], cwd=target)
    _run_git(
        [
            "-c", "user.name=TARS",
            "-c", "user.email=tars@localhost",
            "commit", "--allow-empty", "-m",
            f"Initial commit: scaffolded from tars template '{template}'\n\n"
            "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>",
        ],
        cwd=target,
    )
    commit_hash = _run_git(["rev-parse", "HEAD"], cwd=target).stdout.strip()

    return ScaffoldResult(
        template=template,
        project_name=project_name,
        package_name=package_name,
        path=target,
        initial_commit=commit_hash,
    )
