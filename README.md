# TARS

Code / build / test / scaffolding agent for the personal multi-agent
developer ecosystem. Built from `10x/docs/agents/tars.md` in the
ecosystem's umbrella repo -- read that for the design intent this
implements. Only prior art was a throwaway 15-line `dev` script described
in `alfredOS` (folder-copy from a template + `git init`); its ergonomics
("one short command, sensible defaults") are kept, the code itself is
written fresh here.

## What's actually built (v1)

1. **Project scaffolding** (`tars/scaffold.py`) -- `tars new <template>
   <name> [--dest <dir>]` copies a template, substitutes the project name
   into the relevant files (`pyproject.toml`'s `name`, `package.json`'s
   `name`, source/test files, and a placeholder package directory name),
   runs `git init -b main`, and makes a real initial commit. Two shipped
   templates (`tars/templates/`):
   - **`python-cli`** -- `pyproject.toml` (src layout, console-script
     entry point), a minimal `argparse` CLI, one real pytest test, a
     `.gitignore`. A `tests/conftest.py` puts `src/` on `sys.path` so
     `pytest` works immediately with no install step.
   - **`node-cli`** -- `package.json`, a minimal ESM CLI, one real test
     using Node's built-in test runner (`node --test`) and `node --check`
     as a dependency-free "build" step. Zero npm dependencies, so it runs
     immediately with no `npm install`.
2. **The allowed-roots safety boundary** (`tars/safety.py`) -- every
   scaffold/build/test/git operation resolves the target path and
   verifies it falls inside an allowed-roots list (default:
   `~/Desktop/Neil`, i.e. `C:\Users\<you>\Desktop\Neil` on this machine;
   override with `TARS_ALLOWED_ROOTS`, colon- or semicolon-separated).
   Anything outside refuses with `SafetyError` -- fail closed, checked
   *before* any filesystem/git/subprocess work happens. `Path.resolve()`
   normalizes `..` traversal first, so a path can't escape via `../..`
   tricks either.
3. **Language-agnostic build/test dispatch** (`tars/dispatch.py`) --
   `tars test [--path <dir>]` / `tars build [--path <dir>]` detect the
   project type from marker files and shell out to the right command:
   - `pyproject.toml` / `setup.py` -> `python -m pytest` / `python -m build`
   - `package.json` -> `npm run <scripts.test|scripts.build>` (reads the
     script name out of the file; errors clearly if the script isn't
     defined, rather than guessing one)
   - `Cargo.toml` -> `cargo test` / `cargo build`
   - `go.mod` -> `go test ./...` / `go build ./...`
   - anything else -> a clear "don't know how to test/build this" error.
   This is a thin, honest dispatcher, not a build system -- it does not
   invent commands for a marker it doesn't recognize.
4. **Git operations** (`tars/git_ops.py`), scoped to the same
   allowed-roots boundary -- `tars branch <name>`, `tars commit -m
   "<message>"` (stages and commits everything), `tars status`. **No
   `tars push`** -- see below.
5. **`agent.yaml`** -- `default_sensitivity_tier: work` per
   `10x/docs/agents/tars.md` ("`work` unless the target repo is explicitly
   private/personal"). v1 does not auto-detect a private/personal target
   repo; see "What's NOT completed" below.
6. **MCP server** (`tars/mcp_server.py`) -- exposes `scaffold`, `test`,
   `build`, `git_status` (plus `tars_templates`, for discoverability) as
   MCP tools, following the same pattern Friday
   (`friday/friday/mcp_server.py`) and Alfred
   (`alfred/apps/api/alfred/mcp_server.py`) use: the standard `mcp` PyPI
   package (v2.x -- `mcp.server.mcpserver.MCPServer`, not the renamed-away
   `fastmcp`), stdio transport, `@server.tool()`-decorated functions
   returning plain strings. Every tool call goes through the same
   allowed-roots check as the CLI.
7. **CLI** (`tars/cli.py`, `click`-based, matching every sibling agent's
   CLI framework choice): `tars new`, `tars templates`, `tars test`,
   `tars build`, `tars branch`, `tars commit`, `tars status`, `tars
   --health`.

## Why there's no `tars push`

Per `10x/docs/agents/tars.md`: "PR creation/push still needs your
confirmation per the standing action-confirmation rules, TARS doesn't get
an exception." Every sibling agent's own `agent.yaml`/README documents the
same rule for its own write-adjacent actions -- publishing/pushing is a
user-confirmed action across this whole ecosystem, never something an
agent does autonomously. This is not a missing feature to add later; it's
a deliberate, permanent omission. `tars commit` stops at a local commit;
getting it to a remote is a step you take yourself.

## Package vs. command name

Both the importable package and the console script are `tars` -- no
hyphen to work around (unlike Wall-E's `wall-e` command / `walle`
package).

## Install

```powershell
cd tars
pip install -e ".[dev]"
```

## Configuration

```powershell
# Widen (or change) the allowed-roots boundary. Semicolons are the safe
# separator on Windows (colons collide with drive letters); a bare colon
# is still accepted between two drive-letter paths (tars/safety.py splits
# on it correctly), but semicolon is recommended.
$env:TARS_ALLOWED_ROOTS = "C:\Users\me\Desktop\Neil;D:\other\allowed\root"
```

## Usage

```powershell
# List available templates
tars templates

# Scaffold a new project (destination defaults to the first allowed root)
tars new python-cli my-cli-tool
tars new node-cli my-node-tool --dest "C:\Users\me\Desktop\Neil\projects"

# This refuses -- outside the allowed roots -- rather than silently succeeding
tars new python-cli oops --dest C:\Windows\System32

# Detect project type and run its test/build command
tars test --path C:\Users\me\Desktop\Neil\my-cli-tool
tars build --path C:\Users\me\Desktop\Neil\my-cli-tool

# Git ops, scoped to the same safety boundary
tars branch feature/x --path C:\Users\me\Desktop\Neil\my-cli-tool
tars commit -m "message" --path C:\Users\me\Desktop\Neil\my-cli-tool
tars status --path C:\Users\me\Desktop\Neil\my-cli-tool

# TARS's own status (ecosystem agent.yaml contract's health_check_command)
tars --health
```

Register the MCP server:

```powershell
claude mcp add --transport stdio -s user tars -- python -m tars.mcp_server
```

## Test discipline

```powershell
cd tars
pip install -e ".[dev]"
python -m pytest -q
```

56 tests, all passing on this machine:

- **Safety boundary** (`tests/test_safety.py`) -- default-root resolution,
  `TARS_ALLOWED_ROOTS` parsing (including the Windows-drive-letter-colon
  edge case, both semicolon- and colon-separated), inside/outside/equal
  cases, `..`-traversal can't escape, and the exact scenario the task
  calls out: a `C:\Windows\System32`-style destination is refused.
- **Scaffolding** (`tests/test_scaffold.py`) -- real filesystem, real `git
  init`/commit, no mocking: one end-to-end test per shipped template
  (files exist, name substitution landed correctly in both file contents
  and the package directory name, `.git` exists, the working tree is
  clean after the initial commit), plus the allowed-roots refusal,
  unknown-template, invalid-name, and existing-nonempty-destination error
  paths.
- **Build/test dispatch** (`tests/test_dispatch.py`) -- one detection test
  per marker file (`pyproject.toml`, `setup.py`, `package.json`,
  `Cargo.toml`, `go.mod`), the unrecognized-project-type failure case, one
  command-construction test per language, the node "no test script
  defined" failure case, the allowed-roots refusal, **and real end-to-end
  execution** of `tars test`/`tars build` against a just-scaffolded
  `python-cli` project (via `python -m pytest`, guaranteed present as a
  dev dependency) and a just-scaffolded `node-cli` project (via `node
  --test`/`node --check`, skipped cleanly if `node` isn't on PATH --
  present on this machine, so it actually ran). Rust/Go got
  command-construction coverage only (no scaffold template ships for
  them, and Go's toolchain isn't installed on this machine) -- see "What's
  NOT completed" below.
- **Git operations** (`tests/test_git_ops.py`) -- against a real scratch
  git repo built fresh in a temp directory for each test (never one of
  the real sibling repos): branch creation, commit-all (stages and
  commits everything, tree is clean after), status reporting, the
  non-git-directory refusal, and the allowed-roots refusal.
- **MCP server** (`tests/test_mcp_server.py`) -- tool registration
  (`server.list_tools()` returns exactly the five expected tools) and one
  real end-to-end pass through `scaffold`, `test`, `git_status`, and
  `tars_templates` via `server.call_tool(...)` (the same path a real MCP
  client uses), following the pattern in
  `alfred/apps/api/tests/test_mcp_server.py`. Includes the allowed-roots
  refusal through the MCP tool, not just the CLI.
- **`agent.yaml`** (`tests/test_agent_yaml.py`) -- parses as valid YAML,
  has every field Wall-E's own `contract_check.py` verifies for the other
  sibling agents, a valid tier value, and matches the task spec's exact
  values.
- **CLI** (`tests/test_cli.py`) -- `--health` output shape (JSON,
  `healthy`/`version`/`templates_found`/`allowed_roots` keys), `templates`
  listing, a real `tars new` invocation through the actual Click entry
  point, the safety-refusal scenario through the CLI (not just the
  library function), and the unrecognized-project error path.

Manually verified against this machine after the automated suite passed:
`tars --health` (healthy, both templates found), `tars templates`, `tars
new python-cli demo-project --dest <scratch dir under the allowed root>`
(real project created, real git commit), `tars new python-cli badproj
--dest C:\Windows\System32` (refused, exit code 1, nothing created), and
`tars test --path <the scaffolded project>` (ran the real `pytest`, 2
passed).

## Judgment calls

- **`TARS_ALLOWED_ROOTS` separator.** The task says "colon/semicolon-
  separated." A plain `str.split(":")` would mangle Windows drive letters
  (`C:\...`). `tars/safety.py`'s `_split_roots` treats a colon as a
  separator UNLESS it immediately follows a single leading letter (i.e.
  it's a drive prefix), so both `C:\a;D:\b` and `C:\a:D:\b` split
  correctly. Semicolon is still the recommended separator in practice.
- **Windows + `npm`/`cargo`/`go` via `subprocess`.** Python's
  `subprocess.run(["npm", ...])` fails on Windows with `FileNotFoundError`
  even when `npm` is on `PATH`, because `npm` actually resolves to
  `npm.cmd` and `CreateProcess` (unlike a shell) doesn't search `PATHEXT`.
  `tars/dispatch.py`'s `_run` resolves the executable through
  `shutil.which` first (the same PATH(EXT) search a shell performs) before
  calling `subprocess.run` -- a no-op on POSIX or when the command
  genuinely isn't found. This was caught by running the node-cli
  end-to-end test for real, not assumed.
- **`node-cli` over `node-ts`.** The task allowed "Node/TS or FastAPI" as
  the second template, "your choice, pick what's genuinely useful." Chose
  plain Node (ESM, no TypeScript) over both alternatives so the template
  needs zero dependency installation to actually build/test (`node --test`
  + `node --check` are stdlib) -- genuinely runnable end-to-end offline,
  immediately after `tars new`, which a TypeScript template (needing
  `tsc`) or a FastAPI template (needing `pip install fastapi`, not present
  on this machine) would not be. Also gives the build/test dispatcher a
  second, genuinely different marker type (`package.json` vs.
  `pyproject.toml`) to prove against for real, rather than two Python
  templates.
- **Scaffold commit identity.** The initial commit inside a newly
  scaffolded project is made as `TARS <tars@localhost>` (via `git -c
  user.name=... -c user.email=...`), not whatever global git identity
  happens to be configured on the machine -- TARS is the actual author of
  that specific commit, and this makes `tars new` work unmodified on a
  machine with no git identity configured at all.
- **`tars status` and `tars_templates`.** Not explicitly requested by the
  task, but added for symmetry: the MCP tool list names `git_status`, so
  the CLI got a matching `tars status`; the MCP server got a
  `tars_templates` tool so an MCP client can discover template names
  without shelling out to the CLI.

## What's NOT completed, and why

- **Auto-detecting a private/personal target repo** to override
  `default_sensitivity_tier`. `10x/docs/agents/tars.md` explicitly flags
  this as future work ("`work` unless the target repo is explicitly
  private/personal, which v1 doesn't need to auto-detect"); not attempted.
- **Code generation / refactoring / test *authoring*.** The umbrella doc's
  "Job" section also lists "Code generation, refactoring, test
  authoring/running" and a "GitHub Actions / local CI helper (Layer 9
  concept)." Both are explicitly deferred there to a local-model choice
  ("Open questions... decide at Phase 5 (Local AI Foundation) once
  hardware specs are locked") that hasn't landed in this ecosystem yet --
  v1 here is the scaffold/build/test/git-ops foundation those features
  would sit on top of, not those features themselves.
- **Rust/Go end-to-end dispatch tests.** Detection and command
  construction are tested for both; real subprocess execution is only
  exercised for Python (guaranteed present) and Node (present on this
  build machine, verified). No scaffold template ships for Rust or Go
  (only 2 templates were required), and Go's toolchain isn't installed on
  this machine, so a real Go dispatch run couldn't be verified here.
- **PR creation.** `10x/docs/agents/tars.md` mentions "PR draft" as a
  possible git capability; not built in v1 -- `tars commit` is the extent
  of the git surface, and PR creation would itself need to push first,
  which this agent deliberately never does.
