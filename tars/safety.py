"""TARS's hard safety boundary: every scaffold/build/test/git operation
must resolve inside an "allowed roots" list, or TARS refuses.

TARS gets real shell and git access (agent.yaml: `sandboxed: false`), so
this is the actual safety mechanism, not a formality -- see
10x/docs/agents/tars.md: "Shell access scoped to project directories
under an allowed-roots list -- never arbitrary filesystem access."

Default root: `C:\\Users\\<current user>\\Desktop\\Neil` (i.e.
``Path.home() / "Desktop" / "Neil"``), matching the task's stated default
of ``C:\\Users\\Neil Thomas Mathew\\Desktop\\Neil`` on this machine while
staying portable to another account. Override with ``TARS_ALLOWED_ROOTS``,
colon- or semicolon-separated. Windows drive letters ("C:\\...") contain a
colon themselves, so a naive ``str.split(":")`` would mangle them --
``_split_roots`` below treats a colon as a separator UNLESS it immediately
follows a single leading letter (a drive prefix), so both
``C:\\a;D:\\b`` and the more error-prone ``C:\\a:D:\\b`` split correctly.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "TARS_ALLOWED_ROOTS"


class SafetyError(Exception):
    """Raised when a path resolves outside every allowed root."""


def _split_roots(raw: str) -> list[str]:
    """Split a colon- and/or semicolon-separated roots string, without
    breaking apart Windows drive letters (``C:\\...``)."""
    parts: list[str] = []
    current = ""
    for ch in raw:
        if ch == ";":
            parts.append(current)
            current = ""
        elif ch == ":":
            if len(current) == 1 and current.isalpha():
                # Drive-letter colon (e.g. the "C" in "C:\Users\...") --
                # keep it attached to the root being built, not a separator.
                current += ch
            else:
                parts.append(current)
                current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def default_allowed_roots() -> list[Path]:
    """The active allowed-roots list: ``TARS_ALLOWED_ROOTS`` if set,
    otherwise ``~/Desktop/Neil``."""
    raw = os.environ.get(ENV_VAR, "").strip()
    if raw:
        return [Path(p) for p in _split_roots(raw)]
    return [Path.home() / "Desktop" / "Neil"]


def ensure_within_allowed_roots(
    path: os.PathLike | str, roots: list[Path] | None = None
) -> Path:
    """Resolve ``path`` and verify it falls inside one of ``roots``
    (default: :func:`default_allowed_roots`). Returns the resolved path on
    success; raises :class:`SafetyError` (fail closed) otherwise.

    Resolution happens with ``strict=False`` so this works for paths that
    don't exist yet (e.g. a new project directory `tars new` is about to
    create) -- lexical ``..`` traversal is still normalized away by
    ``Path.resolve``, so this cannot be escaped with ``..`` segments.
    """
    roots = roots if roots is not None else default_allowed_roots()
    resolved = Path(path).resolve()
    for root in roots:
        root_resolved = Path(root).resolve()
        if resolved == root_resolved:
            return resolved
        try:
            resolved.relative_to(root_resolved)
            return resolved
        except ValueError:
            continue
    roots_display = ", ".join(str(Path(r).resolve()) for r in roots)
    raise SafetyError(
        f"Refusing: '{resolved}' is outside TARS's allowed roots "
        f"[{roots_display}]. Set {ENV_VAR} to widen this if you really "
        f"mean it."
    )
