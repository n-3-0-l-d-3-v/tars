"""TARS MCP server -- exposes scaffold/test/build/git_status as MCP tools,
following the same pattern Friday (friday/mcp_server.py) and Alfred
(apps/api/alfred/mcp_server.py) use: the standard `mcp` PyPI package,
stdio transport, one `MCPServer` instance with `@server.tool()`-decorated
functions returning plain strings.

Register it once:
    claude mcp add --transport stdio -s user tars -- python -m tars.mcp_server

Every tool call goes through the same allowed-roots safety boundary as
the CLI (tars/safety.py) -- an MCP client gets no more filesystem reach
than a human running the `tars` command directly.
"""

from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from tars.dispatch import DispatchError, run_build, run_test
from tars.git_ops import GitOpsError, status as git_status_op
from tars.guard import GuardError, scan_repo
from tars.guard import report as guard_report
from tars.safety import SafetyError, ensure_within_allowed_roots
from tars.scaffold import ScaffoldError, list_templates, scaffold_project

server = MCPServer(
    name="tars",
    instructions=(
        "TARS is the user's code/build/test/scaffolding agent. It has real "
        "shell and git access, scoped to an allowed-roots directory list "
        "(never arbitrary filesystem access) -- every tool call that "
        "touches a path can refuse with a safety error if the path falls "
        "outside those roots.\n\n"
        "Use `scaffold` to create a new project from a template "
        "(`tars_templates` in the description below, or call `scaffold` "
        "with an unknown template name to get the list back in the error "
        "message). Use `test`/`build` to detect and run a project's own "
        "test/build command. Use `git_status` to check a repo's working "
        "tree.\n\n"
        "TARS deliberately has NO push/publish tool -- that stays a "
        "user-confirmed action, never something an agent does "
        "autonomously."
    ),
)


@server.tool(
    description=(
        "Scaffold a new project from a template into a directory. Copies "
        "the template, substitutes the project name, runs `git init` and "
        "makes an initial commit. `dest` is optional (defaults to the "
        "first allowed root). Refuses if the destination falls outside "
        "TARS's allowed-roots safety boundary, or if the template name is "
        "unknown (the error lists what's available)."
    )
)
def scaffold(template: str, name: str, dest: str = "") -> str:
    from tars.safety import default_allowed_roots

    dest_path = Path(dest) if dest.strip() else default_allowed_roots()[0]
    try:
        result = scaffold_project(template, name, dest_path)
    except (ScaffoldError, SafetyError) as exc:
        return f"Error: {exc}"
    return (
        f"Created '{result.project_name}' from template '{result.template}' "
        f"at {result.path}. Initial commit: {result.initial_commit}"
    )


@server.tool(
    description=(
        "Detect a project's type (Python/Node/Rust/Go, from its marker "
        "file) and run its test command. `path` defaults to the current "
        "directory. Fails with a clear error if the project type isn't "
        "recognized, rather than guessing."
    )
)
def test(path: str = ".") -> str:
    try:
        result = run_test(Path(path))
    except (DispatchError, SafetyError) as exc:
        return f"Error: {exc}"
    outcome = "PASSED" if result.ok else f"FAILED (exit {result.returncode})"
    return f"$ {' '.join(result.command)}\n{outcome}\n\n{result.stdout}\n{result.stderr}".strip()


@server.tool(
    description=(
        "Detect a project's type (Python/Node/Rust/Go, from its marker "
        "file) and run its build command. `path` defaults to the current "
        "directory. Fails with a clear error if the project type isn't "
        "recognized, rather than guessing."
    )
)
def build(path: str = ".") -> str:
    try:
        result = run_build(Path(path))
    except (DispatchError, SafetyError) as exc:
        return f"Error: {exc}"
    outcome = "SUCCEEDED" if result.ok else f"FAILED (exit {result.returncode})"
    return f"$ {' '.join(result.command)}\n{outcome}\n\n{result.stdout}\n{result.stderr}".strip()


@server.tool(
    description=(
        "`git status --porcelain` for a repository directory. `path` "
        "defaults to the current directory. Read-only."
    )
)
def git_status(path: str = ".") -> str:
    try:
        result = git_status_op(Path(path))
    except (GitOpsError, SafetyError) as exc:
        return f"Error: {exc}"
    return result.stdout or "(clean)"


@server.tool(
    description=(
        "Scan a git repo for secrets (keys, tokens, .env/private-key files). "
        "Scans staged changes by default; `all_files=true` scans every "
        "tracked file. Read-only: reports findings (path:line + rule), never "
        "prints the secret itself."
    )
)
def guard_scan(path: str = ".", all_files: bool = False) -> str:
    try:
        resolved = ensure_within_allowed_roots(Path(path))
        findings = scan_repo(resolved, staged=not all_files)
    except (GuardError, SafetyError) as exc:
        return f"Error: {exc}"
    return guard_report(findings) if findings else "No secrets found."


@server.tool(
    description="List TARS's available scaffold templates."
)
def tars_templates() -> str:
    names = list_templates()
    return "\n".join(names) if names else "No templates found."


def main():
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
