"""TARS's MCP server: tool registration and one real end-to-end pass
through each tool, exercised via `server.list_tools()`/`server.call_tool`
-- the same path a real MCP client uses -- following the pattern in
alfred/apps/api/tests/test_mcp_server.py."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _call(server, name, args):
    result = asyncio.run(server.call_tool(name, args))
    return result


def test_all_tools_are_registered():
    from tars import mcp_server

    tools = asyncio.run(mcp_server.server.list_tools())
    names = {t.name for t in tools}
    assert names == {"scaffold", "test", "build", "git_status", "tars_templates", "guard_scan"}


def test_tars_templates_tool_lists_shipped_templates():
    from tars import mcp_server

    result = _call(mcp_server.server, "tars_templates", {})
    text = result.content[0].text
    assert "python-cli" in text
    assert "node-cli" in text


def test_scaffold_tool_real_end_to_end(tmp_path, monkeypatch):
    from tars import mcp_server

    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(tmp_path))
    result = _call(
        mcp_server.server, "scaffold",
        {"template": "python-cli", "name": "mcp-demo", "dest": str(tmp_path)},
    )
    text = result.content[0].text
    assert "Created 'mcp-demo'" in text
    assert (tmp_path / "mcp-demo" / ".git").is_dir()


def test_scaffold_tool_refuses_path_outside_allowed_roots(tmp_path, monkeypatch):
    from tars import mcp_server

    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(allowed))

    result = _call(
        mcp_server.server, "scaffold",
        {"template": "python-cli", "name": "x", "dest": str(outside)},
    )
    text = result.content[0].text
    assert "Error" in text
    assert not (outside / "x").exists()


def test_git_status_tool_on_real_scratch_repo(tmp_path, monkeypatch):
    import subprocess

    from tars import mcp_server

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "new.txt").write_text("x", encoding="utf-8")

    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(tmp_path))
    result = _call(mcp_server.server, "git_status", {"path": str(repo)})
    assert "new.txt" in result.content[0].text


def test_test_tool_real_end_to_end_against_scaffolded_project(tmp_path, monkeypatch):
    from tars import mcp_server
    from tars.scaffold import scaffold_project

    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(tmp_path))
    scaffolded = scaffold_project("python-cli", "mcp-test-demo", tmp_path)

    result = _call(mcp_server.server, "test", {"path": str(scaffolded.path)})
    text = result.content[0].text
    assert "PASSED" in text
