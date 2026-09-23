"""TARS guard: a git pre-commit hook that blocks secrets before they land
in history.

Two kinds of rule:

* **File rules** -- the staged path itself is a secret-bearing file
  (``.env``, SSH private keys, ``*.pem``/``*.key``/``*.p12`` ...).
  ``.env.example``/``.env.sample``/``.env.template`` are allowed.
* **Content rules** -- a staged line matches a known credential shape
  (private-key header, AWS/GitHub/Slack/Google/OpenAI/Anthropic/Groq/
  Hugging Face tokens) or a generic ``api_key = "..."`` assignment whose
  value looks random (entropy floor, placeholder words skipped).

Content is read from the **index** (``git show :<path>``), not the
working tree, so what gets scanned is exactly what would be committed.
Binary and very large blobs are skipped.

Escape hatches, all explicit: a ``tars:allow`` marker on the offending
line, glob patterns in a ``.tars-guard-allow`` file at the repo root, or
git's own ``git commit --no-verify`` (the user's call, never TARS's).

Installing the hook writes to ``<repo>/.git/hooks`` and so goes through
the allowed-roots boundary (tars/safety.py). Scanning is read-only. The
hook fails closed: if TARS can't be found it blocks the commit and says
how to fix or remove the hook.
"""

from __future__ import annotations

import fnmatch
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tars.safety import ensure_within_allowed_roots

HOOK_MARKER = "# tars-guard"
ALLOW_MARKER = "tars:allow"
ALLOW_FILE = ".tars-guard-allow"
MAX_BYTES = 1_000_000


class GuardError(Exception):
    """Raised for any user-facing guard failure (not a repo, foreign hook...)."""


@dataclass(frozen=True)
class Finding:
    path: str
    line: int  # 0 = the file itself (file rule)
    rule: str

    def render(self) -> str:
        where = self.path if self.line == 0 else f"{self.path}:{self.line}"
        return f"{where}: {self.rule}"


# --- rules -----------------------------------------------------------------

_SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist")
_KEY_FILENAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".pypirc",
                  "credentials.json", "service-account.json"}
_KEY_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".ppk"}

CONTENT_RULES: list[tuple[str, re.Pattern]] = [
    ("private key block", re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}T3BlbkFJ[A-Za-z0-9_-]{20,}")),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{40,}\b")),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    ("Stripe secret key", re.compile(r"\b[rs]k_live_[A-Za-z0-9]{20,}\b")),
]

_GENERIC = re.compile(
    r"""(?ix)
    (?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?token|auth[_-]?token|password|passwd|client[_-]?secret)
    ["']?\s*[:=]\s*
    ["']([^"'\s]{16,})["']
    """
)
_PLACEHOLDER_WORDS = ("your", "xxx", "example", "changeme", "placeholder", "dummy",
                      "fake", "test", "sample", "redacted", "<", "${", "{{", "***")


def _entropy(s: str) -> float:
    counts = Counter(s)
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


def _looks_random(value: str) -> bool:
    low = value.lower()
    if any(w in low for w in _PLACEHOLDER_WORDS):
        return False
    return _entropy(value) >= 3.5


def check_path(path: str) -> str | None:
    """Return a rule name if the path itself is a secret-bearing file."""
    name = PurePosixPath(path).name
    low = name.lower()
    if low == ".env" or (low.startswith(".env.") and not low.endswith(_SAFE_ENV_SUFFIXES)):
        return "environment file (.env)"
    if low in _KEY_FILENAMES:
        return f"credential file ({name})"
    if PurePosixPath(low).suffix in _KEY_EXTENSIONS:
        return f"key/certificate store ({PurePosixPath(name).suffix})"
    return None


def scan_text(path: str, text: str) -> list[Finding]:
    """Content findings for one file's text (one finding per line max)."""
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for rule, pattern in CONTENT_RULES:
            m = pattern.search(line)
            # Vendors' documented dummy keys (AWS's ...EXAMPLE) aren't secrets.
            if m and "example" not in m.group(0).lower():
                findings.append(Finding(path, lineno, rule))
                break
        else:
            m = _GENERIC.search(line)
            if m and _looks_random(m.group(1)):
                findings.append(Finding(path, lineno, "hard-coded credential assignment"))
    return findings


# --- git plumbing ----------------------------------------------------------

def _git(args: list[str], cwd: Path, *, binary: bool = False):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", "replace").strip()
        raise GuardError(f"git {' '.join(args)} failed in {cwd}: {err}")
    return result.stdout if binary else result.stdout.decode("utf-8", "replace")


def _repo_root(path: Path) -> Path:
    try:
        top = _git(["rev-parse", "--show-toplevel"], path).strip()
    except GuardError:
        raise GuardError(f"'{path}' is not inside a git repository.") from None
    return Path(top)


def _allow_globs(root: Path) -> list[str]:
    f = root / ALLOW_FILE
    if not f.is_file():
        return []
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _allowed(path: str, globs: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(PurePosixPath(path).name, g) for g in globs)


def _scan_blob(path: str, data: bytes) -> list[Finding]:
    if len(data) > MAX_BYTES or b"\x00" in data[:8192]:
        return []
    return scan_text(path, data.decode("utf-8", "replace"))


def scan_repo(path: Path, *, staged: bool = True) -> list[Finding]:
    """Scan the staged changes (default) or every tracked file (``staged=False``)."""
    root = _repo_root(Path(path))
    globs = _allow_globs(root)
    if staged:
        out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], root)
    else:
        out = _git(["ls-files", "-z"], root)
    findings: list[Finding] = []
    for rel in filter(None, out.split("\0")):
        if rel == ALLOW_FILE or _allowed(rel, globs):
            continue
        rule = check_path(rel)
        if rule:
            findings.append(Finding(rel, 0, rule))
            continue
        if staged:
            data = _git(["show", f":{rel}"], root, binary=True)
        else:
            try:
                data = (root / rel).read_bytes()
            except OSError:
                continue
        findings.extend(_scan_blob(rel, data))
    return findings


def report(findings: list[Finding]) -> str:
    lines = [f"tars-guard: blocked {len(findings)} possible secret(s):"]
    lines += [f"  {f.render()}" for f in findings]
    lines += [
        "",
        "Remove the secret (use an env var or an untracked .env), then re-stage.",
        f"False positive? add '{ALLOW_MARKER}' to the line, or a glob to {ALLOW_FILE}.",
    ]
    return "\n".join(lines)


# --- hook install ----------------------------------------------------------

def _hooks_dir(root: Path) -> Path:
    p = Path(_git(["rev-parse", "--git-path", "hooks"], root).strip())
    return p if p.is_absolute() else root / p


def hook_script(python: str | None = None) -> str:
    py = (python or sys.executable).replace(chr(92), "/")
    return (
        "#!/bin/sh\n"
        f"{HOOK_MARKER} pre-commit hook (installed by `tars guard install`)\n"
        f'PY="{py}"\n'
        'if [ -x "$PY" ]; then exec "$PY" -m tars.guard; fi\n'
        "if command -v tars >/dev/null 2>&1; then exec tars guard scan; fi\n"
        'echo "tars-guard: TARS not found; reinstall it or run: tars guard uninstall" >&2\n'
        "exit 1\n"
    )


def install_hook(path: Path, *, force: bool = False, roots=None) -> Path:
    """Write the pre-commit hook. Refuses to clobber a foreign hook unless
    ``force``, in which case the old one is kept as ``pre-commit.bak``."""
    root = _repo_root(ensure_within_allowed_roots(path, roots))
    ensure_within_allowed_roots(root, roots)
    hooks = _hooks_dir(root)
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    if hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8", errors="replace"):
        if not force:
            raise GuardError(f"{hook} already exists and isn't TARS's; use --force to replace it (a .bak copy is kept).")
        hook.replace(hooks / "pre-commit.bak")
    hook.write_text(hook_script(), encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    return hook


def uninstall_hook(path: Path, roots=None) -> bool:
    """Remove TARS's hook (restoring a .bak if one exists). False if none was installed."""
    root = _repo_root(ensure_within_allowed_roots(path, roots))
    hooks = _hooks_dir(root)
    hook = hooks / "pre-commit"
    if not hook.exists() or HOOK_MARKER not in hook.read_text(encoding="utf-8", errors="replace"):
        return False
    hook.unlink()
    bak = hooks / "pre-commit.bak"
    if bak.exists():
        bak.replace(hook)
    return True


def hook_installed(path: Path) -> bool:
    try:
        hook = _hooks_dir(_repo_root(Path(path))) / "pre-commit"
    except GuardError:
        return False
    return hook.exists() and HOOK_MARKER in hook.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    """Hook entry point: scan the index of the repo in the cwd."""
    try:
        findings = scan_repo(Path.cwd())
    except GuardError as exc:
        print(f"tars-guard: {exc}", file=sys.stderr)
        return 1
    if findings:
        print(report(findings), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
