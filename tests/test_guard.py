"""tars guard: rules, staged-index scanning, and a real hook blocking a
real `git commit`.

Fake credentials are assembled at runtime (prefix + filler) so this file
never contains a literal token shape -- it must pass its own hook and
GitHub push protection.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from tars import guard
from tars.cli import cli

AWS = "AKIA" + "Q" * 16
GH = "ghp" + "_" + "a1B2c3D4e5" * 4
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----"
RANDOM_VALUE = "9fK2xQ7LmZp4Rt8Vw1Ns6Yb3"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(tmp_path))
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    (r / "README.md").write_text("hello\n")
    _git(r, "add", "README.md")
    _git(r, "commit", "-q", "-m", "init")
    return r


# --- rules -------------------------------------------------------------------

@pytest.mark.parametrize("path", [".env", "app/.env", ".env.local", "id_rsa", "certs/server.pem",
                                  "keys/prod.key", "store.p12", "credentials.json", ".pypirc"])
def test_check_path_flags_secret_files(path):
    assert guard.check_path(path)


@pytest.mark.parametrize("path", [".env.example", ".env.sample", "id_rsa.pub", "src/app.py",
                                  "keyboard.py", "README.md"])
def test_check_path_allows_normal_files(path):
    assert guard.check_path(path) is None


@pytest.mark.parametrize("line,rule", [
    (f"aws = '{AWS}'", "AWS access key id"),
    (f"token: {GH}", "GitHub token"),
    (PEM, "private key block"),
    ("GROQ=gsk" + "_" + "x" * 44, "Groq API key"),
    (f'api_key = "{RANDOM_VALUE}"', "hard-coded credential assignment"),
])
def test_scan_text_detects(line, rule):
    findings = guard.scan_text("f.py", f"ok\n{line}\n")
    assert [(f.line, f.rule) for f in findings] == [(2, rule)]


@pytest.mark.parametrize("line", [
    'api_key = "your-api-key-here-please"',
    'password = "aaaaaaaaaaaaaaaaaaaa"',
    "api_key = os.environ['API_KEY']",
    'secret = "${SECRET_FROM_ENV_VAR}"',
    f"aws = '{AWS}'  # tars:allow",
    "aws = 'AKIA" + "IOSFODNN7EXAMPLE'",  # AWS's documented dummy key
])
def test_scan_text_ignores_placeholders_env_lookups_and_allow_marker(line):
    assert guard.scan_text("f.py", line) == []


# --- staged scanning -------------------------------------------------------

def test_scan_reads_the_index_not_the_working_tree(repo):
    f = repo / "config.py"
    f.write_text(f"KEY = '{AWS}'\n")
    _git(repo, "add", "config.py")
    f.write_text("KEY = None\n")  # fixed in the tree, but the secret is still staged
    findings = guard.scan_repo(repo)
    assert [(x.path, x.line) for x in findings] == [("config.py", 1)]


def test_scan_ignores_unstaged_and_binary(repo):
    (repo / "loose.py").write_text(f"KEY = '{AWS}'\n")  # never staged
    (repo / "blob.bin").write_bytes(b"\x00\x01" + AWS.encode())
    _git(repo, "add", "blob.bin")
    assert guard.scan_repo(repo) == []


def test_allow_file_globs_skip_paths(repo):
    (repo / "fixtures").mkdir()
    (repo / "fixtures" / "k.py").write_text(f"{PEM}\n")
    (repo / guard.ALLOW_FILE).write_text("# test fixtures\nfixtures/*\n")
    _git(repo, "add", "-A")
    assert guard.scan_repo(repo) == []


def test_scan_all_covers_tracked_files(repo):
    (repo / "old.py").write_text(f"t = '{GH}'\n")
    _git(repo, "add", "old.py")
    _git(repo, "commit", "-q", "--no-verify", "-m", "oops")
    assert guard.scan_repo(repo) == []  # nothing staged
    assert [f.path for f in guard.scan_repo(repo, staged=False)] == ["old.py"]


def test_scan_outside_repo_raises(tmp_path):
    with pytest.raises(guard.GuardError):
        guard.scan_repo(tmp_path)


# --- hook install + real commit ---------------------------------------------

def test_installed_hook_blocks_a_real_commit_and_allows_a_clean_one(repo):
    hook = guard.install_hook(repo)
    assert guard.HOOK_MARKER in hook.read_text()
    assert guard.hook_installed(repo)

    (repo / ".env").write_text("X=1\n")
    _git(repo, "add", ".env")
    blocked = _git(repo, "commit", "-m", "add env")
    assert blocked.returncode != 0
    assert "tars-guard: blocked" in blocked.stderr
    assert _git(repo, "log", "--oneline").stdout.count("\n") == 1

    _git(repo, "rm", "-q", "--cached", ".env")
    (repo / "app.py").write_text("print('hi')\n")
    _git(repo, "add", "app.py")
    ok = _git(repo, "commit", "-m", "clean")
    assert ok.returncode == 0, ok.stderr


def test_install_refuses_foreign_hook_unless_forced_and_uninstall_restores(repo):
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "pre-commit").write_text("#!/bin/sh\necho mine\n")
    with pytest.raises(guard.GuardError):
        guard.install_hook(repo)
    guard.install_hook(repo, force=True)
    assert (hooks / "pre-commit.bak").exists()
    assert guard.uninstall_hook(repo) is True
    assert (hooks / "pre-commit").read_text() == "#!/bin/sh\necho mine\n"
    assert guard.uninstall_hook(repo) is False


def test_install_refuses_outside_allowed_roots(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("TARS_ALLOWED_ROOTS", str(tmp_path / "elsewhere"))
    from tars.safety import SafetyError
    with pytest.raises(SafetyError):
        guard.install_hook(repo)


def test_hook_script_uses_forward_slashes_and_fails_closed():
    script = guard.hook_script("C:" + chr(92) + "py" + chr(92) + "python.exe")
    assert 'PY="C:/py/python.exe"' in script
    assert script.rstrip().endswith("exit 1")


def test_module_entry_point_matches_hook(repo):
    (repo / "k.pem").write_text("x\n")
    _git(repo, "add", "k.pem")
    r = subprocess.run([sys.executable, "-m", "tars.guard"], cwd=repo, capture_output=True, text=True)
    assert r.returncode == 1 and "k.pem" in r.stderr


# --- CLI + MCP -------------------------------------------------------------

def test_cli_guard_scan_install_uninstall(repo):
    runner = CliRunner()
    assert runner.invoke(cli, ["guard", "scan", "--path", str(repo)]).exit_code == 0
    (repo / "id_rsa").write_text("x\n")
    _git(repo, "add", "id_rsa")
    res = runner.invoke(cli, ["guard", "scan", "--path", str(repo)])
    assert res.exit_code == 1 and "id_rsa" in res.output
    assert runner.invoke(cli, ["guard", "install", "--path", str(repo)]).exit_code == 0
    res = runner.invoke(cli, ["guard", "uninstall", "--path", str(repo)])
    assert "Removed" in res.output


def test_mcp_guard_scan_reports_without_echoing_secret(repo):
    from tars import mcp_server

    (repo / "c.py").write_text(f"t = '{GH}'\n")
    _git(repo, "add", "c.py")
    result = asyncio.run(mcp_server.server.call_tool("guard_scan", {"path": str(repo)}))
    text = result.content[0].text
    assert "c.py:1: GitHub token" in text
    assert GH not in text
