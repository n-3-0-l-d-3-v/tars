

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _git_identity(monkeypatch):
    """CI runners have no global git identity; tests that commit need one."""
    for var, val in (("GIT_AUTHOR_NAME", "TARS Test"), ("GIT_AUTHOR_EMAIL", "tars@test.invalid"),
                     ("GIT_COMMITTER_NAME", "TARS Test"), ("GIT_COMMITTER_EMAIL", "tars@test.invalid")):
        monkeypatch.setenv(var, val)
