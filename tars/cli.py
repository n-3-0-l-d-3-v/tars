"""TARS CLI.

`tars --health` is an eager top-level flag (not a subcommand), matching
Friday (`friday --health`), Ultron (`ultron --health`), Jarvis
(`jarvis --health`), and Wall-E (`wall-e --health`) -- see README.md and
agent.yaml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from tars import __version__
from tars.dispatch import DispatchError, run_build, run_test
from tars.git_ops import GitOpsError, commit_all, create_branch, status
from tars.guard import GuardError, install_hook, scan_repo, uninstall_hook
from tars.guard import report as guard_report
from tars.safety import SafetyError, default_allowed_roots
from tars.scaffold import ScaffoldError, list_templates, scaffold_project


def _print_json(data: dict) -> None:
    click.echo(json.dumps(data, indent=2, default=str))


def _self_health() -> dict:
    """TARS's own health: are templates present and readable, and is the
    allowed-roots config resolvable. Does NOT run git/build/test -- that's
    what `tars test`/`tars build`/`tars new` are for, matching the same
    "own status only" contract every sibling agent's `--health` follows."""
    templates = list_templates()
    roots = [str(r) for r in default_allowed_roots()]
    healthy = len(templates) > 0
    return {
        "version": __version__,
        "healthy": healthy,
        "templates_found": templates,
        "allowed_roots": roots,
    }


@click.group(invoke_without_command=True)
@click.option(
    "--health",
    "show_health",
    is_flag=True,
    default=False,
    help="Print TARS's own JSON health report and exit. This is the "
    "ecosystem agent contract's health_check_command -- see agent.yaml.",
)
@click.version_option(__version__, prog_name="tars")
@click.pass_context
def cli(ctx: click.Context, show_health: bool) -> None:
    """TARS: code / build / test / scaffolding agent."""
    if show_health:
        payload = _self_health()
        _print_json(payload)
        ctx.exit(0 if payload["healthy"] else 1)
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="templates")
def templates_cmd() -> None:
    """List available scaffold templates."""
    names = list_templates()
    if not names:
        click.echo("No templates found.")
        return
    for name in names:
        click.echo(name)


@cli.command(name="new")
@click.argument("template")
@click.argument("name")
@click.option(
    "--dest", "dest_raw", default=None,
    help="Destination directory to create the project in "
    "(default: the first allowed root).",
)
def new_cmd(template: str, name: str, dest_raw: Optional[str]) -> None:
    """Scaffold a new project: `tars new <template> <name>`."""
    dest = Path(dest_raw) if dest_raw else default_allowed_roots()[0]
    try:
        result = scaffold_project(template, name, dest)
    except (ScaffoldError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Created '{result.project_name}' from template '{result.template}' at {result.path}")
    click.echo(f"Initial commit: {result.initial_commit}")


@cli.command(name="test")
@click.option("--path", "path_raw", default=".", help="Project directory (default: cwd).")
def test_cmd(path_raw: str) -> None:
    """Detect the project type and run its test command."""
    try:
        result = run_test(Path(path_raw))
    except (DispatchError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)
    sys.exit(result.returncode)


@cli.command(name="build")
@click.option("--path", "path_raw", default=".", help="Project directory (default: cwd).")
def build_cmd(path_raw: str) -> None:
    """Detect the project type and run its build command."""
    try:
        result = run_build(Path(path_raw))
    except (DispatchError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"$ {' '.join(result.command)}")
    if result.stdout:
        click.echo(result.stdout)
    if result.stderr:
        click.echo(result.stderr, err=True)
    sys.exit(result.returncode)


@cli.command(name="branch")
@click.argument("name")
@click.option("--path", "path_raw", default=".", help="Repo directory (default: cwd).")
def branch_cmd(name: str, path_raw: str) -> None:
    """Create and switch to a new git branch."""
    try:
        result = create_branch(name, Path(path_raw))
    except (GitOpsError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(result.stdout or f"Switched to a new branch '{name}'")


@cli.command(name="commit")
@click.option("-m", "--message", "message", required=True, help="Commit message.")
@click.option("--path", "path_raw", default=".", help="Repo directory (default: cwd).")
def commit_cmd(message: str, path_raw: str) -> None:
    """Stage everything and commit in the given repo directory."""
    try:
        result = commit_all(message, Path(path_raw))
    except (GitOpsError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(result.stdout)


@cli.command(name="status")
@click.option("--path", "path_raw", default=".", help="Repo directory (default: cwd).")
def status_cmd(path_raw: str) -> None:
    """`git status --porcelain` for the given repo directory."""
    try:
        result = status(Path(path_raw))
    except (GitOpsError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(result.stdout or "(clean)")


@cli.group(name="guard")
def guard_group() -> None:
    """Pre-commit secret guard: install/uninstall the hook, or scan now."""


@guard_group.command(name="install")
@click.option("--path", "path_raw", default=".", help="Repo directory (default: cwd).")
@click.option("--force", is_flag=True, default=False,
              help="Replace an existing non-TARS pre-commit hook (kept as pre-commit.bak).")
def guard_install_cmd(path_raw: str, force: bool) -> None:
    """Install the secret-blocking pre-commit hook into a repo."""
    try:
        hook = install_hook(Path(path_raw), force=force)
    except (GuardError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Installed tars-guard pre-commit hook: {hook}")


@guard_group.command(name="uninstall")
@click.option("--path", "path_raw", default=".", help="Repo directory (default: cwd).")
def guard_uninstall_cmd(path_raw: str) -> None:
    """Remove TARS's pre-commit hook (restores a backed-up hook if any)."""
    try:
        removed = uninstall_hook(Path(path_raw))
    except (GuardError, SafetyError) as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo("Removed tars-guard hook." if removed else "No tars-guard hook installed.")


@guard_group.command(name="scan")
@click.option("--path", "path_raw", default=".", help="Repo directory (default: cwd).")
@click.option("--all", "all_files", is_flag=True, default=False,
              help="Scan every tracked file instead of only staged changes.")
def guard_scan_cmd(path_raw: str, all_files: bool) -> None:
    """Scan staged changes (or all tracked files) for secrets. Exit 1 on findings."""
    try:
        findings = scan_repo(Path(path_raw), staged=not all_files)
    except GuardError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    if findings:
        click.echo(guard_report(findings), err=True)
        sys.exit(1)
    click.echo("tars-guard: no secrets found.")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
