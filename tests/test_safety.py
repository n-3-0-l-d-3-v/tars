from pathlib import Path

import pytest

from tars.safety import (
    ENV_VAR,
    SafetyError,
    _split_roots,
    default_allowed_roots,
    ensure_within_allowed_roots,
)


def test_default_allowed_roots_without_env_var(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    roots = default_allowed_roots()
    assert roots == [Path.home() / "Desktop" / "Neil"]


def test_default_allowed_roots_from_env_var_semicolon(monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv(ENV_VAR, f"{a};{b}")
    assert default_allowed_roots() == [a, b]


def test_split_roots_handles_windows_drive_colons():
    raw = r"C:\Users\me\Desktop\Neil;D:\other\root"
    assert _split_roots(raw) == [r"C:\Users\me\Desktop\Neil", r"D:\other\root"]


def test_split_roots_handles_colon_separated_drive_paths():
    # A user who separates with ':' instead of ';' shouldn't get their
    # drive letters mangled.
    raw = r"C:\Users\me\Desktop\Neil:D:\other\root"
    assert _split_roots(raw) == [r"C:\Users\me\Desktop\Neil", r"D:\other\root"]


def test_path_inside_allowed_root_is_accepted(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    target = root / "some" / "project"
    resolved = ensure_within_allowed_roots(target, roots=[root])
    assert resolved == target.resolve()


def test_path_equal_to_allowed_root_is_accepted(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    resolved = ensure_within_allowed_roots(root, roots=[root])
    assert resolved == root.resolve()


def test_path_outside_allowed_roots_is_refused(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "elsewhere"
    with pytest.raises(SafetyError):
        ensure_within_allowed_roots(outside, roots=[root])


def test_dotdot_traversal_cannot_escape_allowed_root(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    escaping = root / ".." / "elsewhere"
    with pytest.raises(SafetyError):
        ensure_within_allowed_roots(escaping, roots=[root])


def test_windows_system32_style_destination_is_refused(tmp_path):
    """The exact scenario the task calls out: a scaffold destination
    outside the allowed roots must fail closed, not silently succeed."""
    root = tmp_path / "allowed"
    root.mkdir()
    windows_system32_like = tmp_path / "Windows" / "System32"
    with pytest.raises(SafetyError):
        ensure_within_allowed_roots(windows_system32_like, roots=[root])
