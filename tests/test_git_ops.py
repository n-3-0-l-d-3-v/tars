"""Git operations against a real scratch git repo (a temp directory --
never one of the real sibling repos)."""

import subprocess
from pathlib import Path

import pytest

from tars.git_ops import GitOpsError, commit_all, create_branch, status
from tars.safety import SafetyError


@pytest.fixture
def scratch_repo(tmp_path):
    repo = tmp_path / "scratch"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.com",
         "commit", "--allow-empty", "-m", "root"],
        cwd=repo, check=True, capture_output=True,
    )
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    return repo


def test_create_branch_switches_to_new_branch(scratch_repo, tmp_path):
    create_branch("feature/x", scratch_repo, roots=[tmp_path])
    out = subprocess.run(
        ["git", "branch", "--show-current"], cwd=scratch_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    assert out == "feature/x"


def test_create_branch_rejects_empty_name(scratch_repo):
    with pytest.raises(GitOpsError):
        create_branch("   ", scratch_repo)


def test_commit_all_stages_and_commits_everything(scratch_repo, tmp_path):
    (scratch_repo / "untracked.txt").write_text("data", encoding="utf-8")
    commit_all("add files", scratch_repo, roots=[tmp_path])

    st = subprocess.run(
        ["git", "status", "--porcelain"], cwd=scratch_repo,
        capture_output=True, text=True,
    ).stdout
    assert st.strip() == ""

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=scratch_repo,
        capture_output=True, text=True,
    ).stdout.strip()
    assert log == "add files"


def test_commit_all_rejects_empty_message(scratch_repo):
    with pytest.raises(GitOpsError):
        commit_all("", scratch_repo)


def test_status_reports_dirty_files(scratch_repo, tmp_path):
    result = status(scratch_repo, roots=[tmp_path])
    assert "file.txt" in result.stdout


def test_ops_reject_non_git_directory(tmp_path):
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    with pytest.raises(GitOpsError):
        status(not_a_repo, roots=[tmp_path])
    with pytest.raises(GitOpsError):
        create_branch("x", not_a_repo, roots=[tmp_path])
    with pytest.raises(GitOpsError):
        commit_all("msg", not_a_repo, roots=[tmp_path])


def test_git_ops_refuse_path_outside_allowed_roots(scratch_repo, tmp_path):
    allowed = tmp_path / "some-other-allowed-dir"
    allowed.mkdir()
    with pytest.raises(SafetyError):
        status(scratch_repo, roots=[allowed])
