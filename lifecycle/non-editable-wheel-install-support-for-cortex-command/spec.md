# Specification: No-clone install for cortex CLI via MCP auto-install

## Problem Statement

Today cortex-command is installed by cloning the repo to `~/.cortex` and running `uv tool install -e .`, with `cortex upgrade` doing `git pull` + editable reinstall. This creates a five-step onboarding flow and assumes the user is the maintainer's clone-and-fork audience. As cortex expands to other users, cloning the repo as a precondition is unusual outside developer-native projects. Additionally, lifecycle 115's `Path(__file__)` refactor was validated under editable install only — under non-editable wheel install (which any no-clone path requires), some `Path(__file__)` patterns silently break. This spec migrates the cortex CLI to a non-editable wheel install via tag-pinned git URL, has the cortex-overnight-integration plugin's MCP server auto-install the CLI on first tool call when missing, and ships the `Path(__file__)` audit + conversion as the validation gate. Two distinct surfaces are validated by separate gates: **target state** (the wheel-installed CLI works correctly — gated by R6a/b/c/d) and **transition mechanism** (the MCP first-install hook actually drives the install — gated by R6e). Forkability-primary stance in `requirements/project.md` is deprecated in favor of CLI-first; cloning remains supported as the developer/forker secondary path.

## Requirements

### R1. Tag-based release pipeline

Establish semver-tagged releases of `cortex-command` produced by a GitHub Actions workflow. Tags are the version source of truth for `uv tool install git+<url>@<tag>`.

**Acceptance criteria**:
- (a) `.github/workflows/release.yml` exists and triggers on tag push matching `v[0-9]+.[0-9]+.[0-9]+`. Verify: `test -f .github/workflows/release.yml && grep -c "tags:" .github/workflows/release.yml` ≥ 1.
- (b) Workflow builds the wheel (`uv build`) and creates a GitHub Release with the wheel as a release asset. Verify: `grep -E "uv build|softprops/action-gh-release|gh release create" .github/workflows/release.yml | wc -l` ≥ 2.
- (c) `pyproject.toml` declares `version = "0.1.0"` (or current literal); CHANGELOG.md (or release-notes section) documents v0.1.0 as the first tagged release. Verify: `test -f CHANGELOG.md && grep -c "v0.1.0" CHANGELOG.md` ≥ 1.
- (d) Tag `v0.1.0` is pushed to the repo and a GitHub Release is published. Verify: `git tag -l "v0.1.0" | wc -l` = 1; `gh release list --limit 5 | grep -c "v0.1.0"` ≥ 1.
- (e) Documentation for cutting a release exists at `docs/release-process.md`. Verify: `test -f docs/release-process.md && grep -c "uv build\|tag\|release" docs/release-process.md` ≥ 3.

### R2. No-clone install path; `cortex upgrade` becomes thin advisory wrapper

The cortex CLI is installable via `uv tool install git+https://github.com/charleshall888/cortex-command.git@<tag>` (non-editable wheel) without cloning the repository. `cortex upgrade` is **not** an upgrade verb post-migration — the CLI cannot self-upgrade because the wheel for any version `vN` can only declare "I am vN" and has no way to know about newer tags. The actual upgrade arrow flows plugin → CLI via R4's `_ensure_cortex_installed`. `cortex upgrade` becomes a thin advisory wrapper that prints instructions and exits 0. Bootstrap installer (`install.sh`) is simplified to a `uv` installer + `uv tool install git+<url>@<tag>` for users without `uv`.

**Acceptance criteria**:
- (a) `uv tool install git+https://github.com/charleshall888/cortex-command.git@v0.1.0` succeeds in a fresh environment and produces a working `cortex` console script. Verify (in `tests/test_no_clone_install.py`): subprocess exits 0; `cortex --help` runs successfully under the installed wheel.
- (b) `cortex_command/cli.py:_dispatch_upgrade` no longer references `git pull`, `git status`, `~/.cortex`, or any `subprocess.run(["uv", "tool", "install"...])` invocation. Verify: `grep -E "git pull|git status|~/\\.cortex|CORTEX_COMMAND_ROOT|subprocess.*uv.*tool.*install" cortex_command/cli.py` returns 0 matches.
- (c) `_dispatch_upgrade` prints an advisory message to stdout pointing users at (1) `/plugin update cortex-overnight-integration@cortex-command` for the MCP-driven path, and (2) `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<tag>` with a pointer to https://github.com/charleshall888/cortex-command/releases for the bare-shell path; exits 0. Verify: `grep -E "/plugin update|uv tool install --reinstall" cortex_command/cli.py | wc -l` ≥ 2; `cortex upgrade` exits 0 (smoke-tested in `tests/test_cli_upgrade.py`).
- (d) `cortex_command/cli.py:_resolve_cortex_root` is deleted; `--print-root` returns the package install location (via `Path(cortex_command.__file__).parent`) or an explicit `CORTEX_REPO_ROOT` override. Verify: `grep -c "_resolve_cortex_root" cortex_command/cli.py` = 0.
- (e) `install.sh` no longer clones the repo or runs `uv tool install -e`; instead it ensures `uv` is installed, then runs `uv tool install git+<url>@<tag>`. Verify: `grep -E "git clone|uv tool install -e" install.sh` returns 0; `grep -E "uv tool install git\\+" install.sh` returns ≥ 1.

### R3. Path(__file__) audit + conversion (call-time resolution mandated)

Every `Path(__file__)` site in `cortex_command/` (excluding tests) is classified and converted: package-internal lookups use `importlib.resources.files()`; user-data lookups use a new `_resolve_user_project_root()` helper invoked **at call time, not at module load**; the vestigial `sys.path.insert` in `outcome_router.py` is deleted. The new helper is named distinctly from `cortex_command.init.handler:_resolve_repo_root` (which uses `git rev-parse --show-toplevel` and is reserved for `cortex init`'s own dispatch path) to prevent future conflation.

**Acceptance criteria**:
- (a) All 6 package-internal sites use `importlib.resources.files()`. Verify: `grep -rn "importlib.resources" cortex_command/ --include='*.py' | grep -v tests | wc -l` ≥ 6 AND `grep -rn "Path(__file__)" cortex_command/ --include='*.py' | grep -v tests | grep -E "prompts|templates" | wc -l` = 0.
- (b) `cortex_command/common.py` defines `_resolve_user_project_root()` returning `CORTEX_REPO_ROOT` env var if set (Path), else `Path.cwd()`. Verify: `grep -E "_resolve_user_project_root|CORTEX_REPO_ROOT" cortex_command/common.py | wc -l` ≥ 2; the function is defined as a regular `def`, not a module-level constant.
- (c) **Call-time invocation mandated.** All 7 user-data sites invoke `_resolve_user_project_root()` inside function bodies (or as the default value of a function parameter computed each call), never as a module-level constant assignment. Verify: `python3 -c "import ast, sys; from pathlib import Path; failures = []; [(*[failures.append(f'{p}:{node.lineno}') for node in ast.walk(ast.parse(p.read_text())) if isinstance(node, ast.Assign) and any(isinstance(v, ast.Call) and getattr(v.func, 'attr', getattr(v.func, 'id', '')) == '_resolve_user_project_root' for v in ast.walk(node))],) for p in Path('cortex_command').rglob('*.py') if 'tests' not in str(p)]; sys.exit(0 if not failures else 1)"` exits 0 (no module-level call sites). Plus `grep -rn "Path(__file__).resolve().parents\\[2\\]" cortex_command/ --include='*.py' | grep -v tests | wc -l` = 0.
- (d) `outcome_router.py:307-309` (`_PROJECT_ROOT = Path(__file__)... sys.path.insert(0, str(_PROJECT_ROOT))`) is deleted. Verify: `grep -c "sys.path.insert" cortex_command/overnight/outcome_router.py` = 0.
- (e) `outcome_router.py` lines 360 and 417 use `_resolve_user_project_root() / "backlog"` (called inside the function, not at module load) instead of `_PROJECT_ROOT / "backlog"`. Verify: `grep -c "_PROJECT_ROOT" cortex_command/overnight/outcome_router.py` = 0.
- (f) Helper raises a clear error when neither `CORTEX_REPO_ROOT` is set nor a recognizable cortex project is at `Path.cwd()` (no `lifecycle/` AND no `backlog/`). Error message includes both the project-root remedy AND the git-repo precondition: "Run from your cortex project root, set CORTEX_REPO_ROOT, or create a new project here with `git init && cortex init` (cortex init requires a git repository)." Verify: `grep -E "git init && cortex init|requires a git repository" cortex_command/common.py` returns ≥ 1.
- (g) Existing test suite (`just test`) passes against the converted code under both editable and non-editable installs. Verify: `just test` exits 0.

### R4. MCP first-install hook

`plugins/cortex-overnight-integration/server.py` auto-installs the cortex CLI on first tool call when missing. Reuses 146's flock + NDJSON + skip-predicate patterns, adapted for the pre-install context. Probes `uv` availability at startup. Uses `cortex --print-root --format json` (not `--help`) as post-install verification.

**Acceptance criteria**:
- (a) New `_ensure_cortex_installed()` function in `server.py` runs before each tool handler delegates to a `cortex` subprocess. Verify: `grep -c "_ensure_cortex_installed" plugins/cortex-overnight-integration/server.py` ≥ 2 (definition + call site). **Plus runtime test** (in R6e) confirms the function fires on cortex-absent.
- (b) Function detects missing CLI via `shutil.which("cortex") is None` and runs `subprocess.run(["uv", "tool", "install", "--reinstall", f"git+https://github.com/charleshall888/cortex-command.git@{CLI_PIN[0]}"], timeout=300)` where `CLI_PIN[0]` is the tag from R5a's tuple constant. Verify: `grep -E "shutil.which.*cortex|uv.*tool.*install.*reinstall" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 2 AND R6e runtime test exercises this path.
- (c) Flock at `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/install.lock` with 60s timeout serializes concurrent first-install attempts across MCP sessions. Verify: `grep -E "install.lock|XDG_STATE_HOME" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1.
- (d) On install failure, a sentinel file `${XDG_STATE_HOME}/cortex-command/install-failed.<ts>` is written; subsequent first-install attempts within 60s read the sentinel and surface the prior failure to the user instead of retrying on partial state. **Runtime assertion** in R6e exercises a single-process write-sentinel-then-read-sentinel cycle (mock the install subprocess to fail, then call `_ensure_cortex_installed()` again and assert it surfaces the sentinel rather than re-attempting). Verify: `grep -E "install-failed|sentinel" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 AND R6e covers the sentinel-read happy path.
- (e) Failure log appended to `${XDG_STATE_HOME}/cortex-command/last-error.log` with `stage: "first_install"`. Verify: `grep -E "first_install" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1.
- (f) Post-install verification calls `cortex --print-root --format json` (not `--help`) and parses the JSON envelope; non-zero exit or unparseable JSON is treated as install failure. Verify: `grep -E "cortex.*--print-root|print-root.*--format" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1; runtime test in R6e asserts a successful install produces parseable JSON.
- (g) MCP server startup probes `shutil.which("uv")`; on miss, emits structured stderr error pointing at the macOS GUI-app + Homebrew + `~/.zshenv` fix and refuses to start. Verify: `grep -E "shutil.which.*uv|zshenv|GUI" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 2.
- (h) Skip predicate: `CORTEX_AUTO_INSTALL=0` env var disables auto-install (falls back to 146 R19's notice-only path). The 146 R9 dirty-tree and non-main-branch predicates are NOT applied pre-install (no clone exists). Verify: `grep -E "CORTEX_AUTO_INSTALL" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1.

### R5. Plugin/CLI version coupling via embedded tag (CLI_PIN tuple)

The cortex-overnight-integration plugin embeds the matching CLI git tag and schema version in a single `CLI_PIN` constant in `server.py`. Plugin auto-update drives CLI auto-update via tag bump. The CLI does NOT consume `CLI_PIN` — the constant is plugin-only; the CLI cannot import from the plugin tree because the plugin lives at `~/.claude/plugins/<name>/` (outside the CLI's import path).

**Acceptance criteria**:
- (a) `CLI_PIN` constant in `plugins/cortex-overnight-integration/server.py` is a tuple `(tag: str, schema_version: str)` — for example `CLI_PIN = ("v0.1.0", "1.0")`. The first element is the git tag (matches `v[0-9]+.[0-9]+.[0-9]+` per R1a); the second element is the schema floor (matches `[0-9]+.[0-9]+`). `MCP_REQUIRED_CLI_VERSION` is derived as `CLI_PIN[1]`. The auto-install URL embeds `CLI_PIN[0]`. Verify: `grep -E "^CLI_PIN = \\(" plugins/cortex-overnight-integration/server.py` returns ≥ 1; `grep -E "MCP_REQUIRED_CLI_VERSION = CLI_PIN\\[1\\]" plugins/cortex-overnight-integration/server.py` returns ≥ 1; `grep -E "CLI_PIN\\[0\\]" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1 (used in install URL).
- (b) Schema-mismatch error message includes "downgrade plugin OR run `uv tool install --reinstall git+<url>@<expected-tag>` to upgrade cortex CLI to the matching version." Verify: `grep -E "downgrade plugin|--reinstall" plugins/cortex-overnight-integration/server.py | wc -l` ≥ 1.
- (c) Documentation (`docs/install.md`) explicitly addresses users with plugin auto-update disabled — they get a stable plugin/CLI pair until they explicitly update either side. Verify: `grep -E "auto-update|stale plugin" docs/install.md` returns ≥ 1.
- (d) `cortex_command/cli.py` does NOT reference `CLI_PIN` or `MCP_REQUIRED_CLI_VERSION` (the CLI cannot reach the plugin's namespace). Verify: `grep -E "CLI_PIN|MCP_REQUIRED_CLI_VERSION" cortex_command/cli.py` returns 0.

### R6. Validation gate (smoke tests for both target state and transition mechanism)

Tests verify (1) the wheel-installed CLI works correctly under non-editable install — **target state**; and (2) the MCP first-install hook actually drives the install end-to-end — **transition mechanism**. These are distinct surfaces with distinct test gates.

**Acceptance criteria**:
- (a) `tests/test_no_clone_install.py` exists. Verify: `test -f tests/test_no_clone_install.py`.
- (b) **Target-state test**: builds the wheel (`uv build`), installs in a tmpdir-isolated `uv` env via `uv tool install <wheel>`, and asserts:
  - `cortex --print-root --format json` exits 0 and returns parseable JSON.
  - `importlib.resources.files("cortex_command.overnight.prompts").joinpath("orchestrator-round.md").read_text()` returns non-empty content (verified inside the installed env via subprocess).
  - All 6 package-internal `importlib.resources` sites resolve under the wheel install (parameterized test).
  Verify: `pytest tests/test_no_clone_install.py::test_target_state -v` exits 0.
- (c) Tag-based release smoke test: a CI step builds the wheel from tag `v0.1.0` and asserts `uv tool install <wheel-url>` produces a working `cortex --version` output. Verify: workflow file in `.github/workflows/` references `tag` and runs `uv tool install`. (Interactive/session-dependent: GitHub Actions execution requires an actual tag push; the test file's expected behavior under tag-trigger is documented in workflow comments.)
- (d) Existing test suite (`just test`) passes after the migration. Verify: `just test` exits 0.
- (e) **Transition-mechanism test**: `tests/test_no_clone_install.py::test_mcp_first_install_hook` exercises `_ensure_cortex_installed()` end-to-end:
  - Creates a tmpdir-isolated env with `cortex` absent from PATH (`shutil.which("cortex")` returns None inside the test fixture).
  - Imports the plugin's `server.py` and invokes `_ensure_cortex_installed()` directly (or invokes one MCP tool handler via subprocess that triggers the hook).
  - Asserts: (1) the hook fires (detectable via NDJSON `last-error.log` having a `first_install` start entry, OR via mock-subprocess capture confirming `uv tool install --reinstall` was invoked with the correct tag); (2) post-install verification (`cortex --print-root --format json`) is invoked; (3) on simulated install failure, a sentinel file is written at `${XDG_STATE_HOME}/cortex-command/install-failed.*`; (4) a second invocation within 60s reads the sentinel and surfaces the prior failure rather than re-attempting the install.
  - This test may use `unittest.mock.patch("subprocess.run", ...)` to avoid the real `uv tool install` cost; the goal is to verify the hook's control flow, not the network round-trip.
  Verify: `pytest tests/test_no_clone_install.py::test_mcp_first_install_hook -v` exits 0.

### R7. Documentation updates

Update `requirements/project.md`, `CLAUDE.md`, `docs/install.md`, and migration runbook to reflect the no-clone install model and deprecate the forkability-primary stance.

**Acceptance criteria**:
- (a) `requirements/project.md` L7-8 (in Project Boundaries / Out of Scope) updated: removes "uv tool install -e ." and "publishing to PyPI is out of scope" framing; adds non-editable wheel install via git URL as the primary install model. Verify: `grep -E "uv tool install -e \\." requirements/project.md` returns 0; `grep -E "uv tool install git\\+" requirements/project.md` returns ≥ 1.
- (b) `requirements/project.md` Overview / philosophy section updated to remove "shared publicly for others to clone or fork" as primary identity. Verify: `grep -E "clone or fork" requirements/project.md` returns 0 OR appears only in a "secondary forker path" context.
- (c) `CLAUDE.md` L5 and L22 updated: install command no longer references `-e`. Verify: `grep -E "uv tool install -e" CLAUDE.md` returns 0; `grep -E "uv tool install git\\+" CLAUDE.md` returns ≥ 1.
- (d) `docs/install.md` leads with `uv tool install git+<url>@<tag>` as the primary install path; documents `curl | sh` (`install.sh`) as fallback for users without `uv`; documents the bare-shell `cortex` access pattern. Verify: `grep -c "uv tool install git\\+" docs/install.md` ≥ 1; first non-heading content paragraph references the git URL install (not clone).
- (e) `docs/migration-no-clone-install.md` exists and documents the runbook for existing maintainer install: `uv tool uninstall cortex-command && uv tool install git+<url>@<tag>`. Verify: `test -f docs/migration-no-clone-install.md && grep -c "uv tool uninstall" docs/migration-no-clone-install.md` ≥ 1.
- (f) `requirements/observability.md` install-mutation classification (L139-142) updated: replaces `-e` flag references and adds the new MCP first-install hook as a tracked install-mutation orchestrator. Verify: `grep -E "uv tool install -e" requirements/observability.md` returns 0; `grep -E "first_install|first install hook" requirements/observability.md` returns ≥ 1.

## Non-Requirements

- **PyPI publication.** Once tag-based releases land, `pip install cortex-command` from PyPI is purely additive — it doesn't break the git URL path. Filed as deferred follow-up if/when version-pinning becomes a real requirement for users.
- **Homebrew tap.** Ticket 125 stays wontfix.
- **`cortex migrate` subcommand.** A documented runbook (R7e) is sufficient for the current user count (effectively 1 maintainer).
- **Audit and conversion of dev-only `Path(__file__)` sites.** The 4 sites in test files are kept as-is; tests are not shipped in the wheel.
- **Concurrent first-install fault-injection tests.** Half-failed install via real-network fault injection + concurrent two-session race tests are deferred to slow-tier opt-in tests. R6e's basic-happy-path and sentinel-read coverage are required for merge; concurrent-process and real-network-failure tests are not.
- **`.pid` file relocation in dashboard.** `dashboard/app.py:184` is dev-only runtime state; out of scope.
- **Eliminating `~/.cortex` references entirely from the codebase.** Some references remain in test fixtures, documentation, and 146-era code paths.
- **Self-upgrade via `cortex upgrade` from the CLI.** The CLI cannot self-upgrade (architectural — wheel for vN can only declare "I am vN"). The upgrade arrow flows plugin → CLI via R4; `cortex upgrade` is downgraded to an advisory wrapper (R2c). Users who want to upgrade independently of the plugin run `uv tool install --reinstall git+<url>@<tag>` themselves.

## Edge Cases

- **First-install offline (network unreachable).** `subprocess.run(["uv", "tool", "install", ...])` exits non-zero with a network error. Auto-install fails; sentinel file written; MCP returns "cortex CLI install failed: network error. Retry when online or run `uv tool install git+<url>@<tag>` manually." Tool calls fail until install succeeds.
- **First-install partial wheel (network drop mid-download).** uv leaves a partial state in `~/.cache/uv/`; `uv tool install --reinstall` (always used for cortex auto-install) overwrites cleanly on retry. Sentinel file from R4d ensures the second concurrent session sees the failure and surfaces it.
- **Concurrent first-install across two MCP sessions.** Session A acquires `install.lock`; Session B blocks for up to 60s. If A succeeds, B re-checks `shutil.which("cortex")` after acquiring lock — finds CLI present and skips the install. If A fails, A writes the sentinel + releases the lock; B reads the sentinel and surfaces the failure without re-attempting.
- **Stale plugin (auto-update disabled).** Plugin's embedded `CLI_PIN[0]` is `v0.1.0`; CLI installed at v0.1.0; user runs without updating. Schema versions match; everything works. When user manually runs `/plugin update cortex-overnight-integration@cortex-command`, plugin's `CLI_PIN` bumps to (e.g.) `("v0.2.0", "2.0")`; on next MCP tool call, schema-mismatch detection fires; auto-install re-runs with the new tag; CLI bumps to v0.2.0; tool call succeeds.
- **User invokes cortex from a non-project directory and not in a git repo.** `Path.cwd()` doesn't contain `lifecycle/` or `backlog/`. The `_resolve_user_project_root()` helper raises with the documented error including the git-repo precondition: "Run from your cortex project root, set CORTEX_REPO_ROOT, or create a new project here with `git init && cortex init` (cortex init requires a git repository)." User sees a clear error with a self-contained remedy; no silent corruption.
- **macOS GUI-app launches Claude Code; `uv` not on PATH.** `shutil.which("uv")` returns None at MCP startup. Server emits structured stderr error pointing at the `~/.zshenv` fix and refuses to start.
- **Existing maintainer's editable install collides with `uv tool install`.** Auto-install path uses `uv tool install --reinstall` unconditionally, which idempotently overwrites any prior install state. First MCP tool call after the migration silently transitions the maintainer's install. Manual migration runbook (R7e) provides explicit steps for users who prefer to do it themselves first.
- **Plugin embeds a tag that doesn't exist in the cortex repo.** uv install fails with "ref not found"; sentinel + last-error.log capture the failure; user sees "cortex CLI install failed: tag v0.X.Y not found at <url>. Plugin may be ahead of cortex repo; check that all required cortex tags are pushed."
- **`CORTEX_REPO_ROOT` set but points at a directory that isn't a cortex project.** `_resolve_user_project_root()` returns the env-var value verbatim (trust the user's explicit override). Subsequent operations fail with "lifecycle/ not found at <CORTEX_REPO_ROOT>" — the user's responsibility.
- **`cortex upgrade` invoked from a bare shell.** Prints advisory message pointing at `/plugin update` (MCP path) and `uv tool install --reinstall` (manual path). Exits 0. No `git pull`, no install attempt.
- **`cortex init` invoked from a non-git directory.** `init/handler.py:67`'s git-rev-parse precondition raises "not inside a git repository." User must `git init` first. The R3f error message in `_resolve_user_project_root()` already references `git init && cortex init` for users hitting it from a different code path.
- **Module-level import of overnight modules from a worker subprocess with wrong CWD.** `_resolve_user_project_root()` is only called inside function bodies (R3c), never at module level — so worker imports do not bind `_LIFECYCLE_ROOT` (or any user-data path) to the wrong directory at import time. The first call inside the worker that actually needs the lifecycle path resolves CWD-or-env at that point.

## Changes to Existing Behavior

- **MODIFIED**: `cortex_command/cli.py:_dispatch_upgrade` (lines 251-296). Was: `git status --porcelain` + `git pull --ff-only` + `uv tool install -e $cortex_root --force`. Now: prints advisory message pointing users at `/plugin update cortex-overnight-integration@cortex-command` (MCP path) and `uv tool install --reinstall git+https://github.com/charleshall888/cortex-command.git@<tag>` (bare-shell path). No subprocess, no install attempt, exits 0.
- **MODIFIED**: `install.sh`. Was: clones repo to `~/.cortex` + `uv tool install -e <target> --force`. Now: ensures `uv` is installed; runs `uv tool install git+<url>@<tag>`. No clone.
- **MODIFIED**: `requirements/project.md` (Project Boundaries Out of Scope, Architecture Constraints, identity). Forkability-primary stance deprecated; CLI-as-primary install model adopted.
- **MODIFIED**: `CLAUDE.md` (L5, L22). Install command no longer references `-e`.
- **MODIFIED**: `requirements/observability.md` (L139-142). Install-mutation classification updated.
- **MODIFIED**: All 6 package-internal `Path(__file__)` lookups (init/scaffold.py, pipeline/conflict.py, pipeline/review_dispatch.py, overnight/brain.py, overnight/feature_executor.py, dashboard/app.py:49). Now use `importlib.resources.files()`.
- **MODIFIED**: All 7 user-data `Path(__file__)` lookups (overnight/plan.py:25, events.py:25, orchestrator.py:25, state.py:28, report.py:493, dashboard/seed.py:25, dashboard/app.py:42, outcome_router.py:360+417). Now invoke `_resolve_user_project_root()` **inside function bodies** (not at module level).
- **REMOVED**: `cortex_command/cli.py:_resolve_cortex_root()` (lines 168-209) and all `CORTEX_COMMAND_ROOT` consumers in cli.py + install_guard.py.
- **REMOVED**: `cortex_command/overnight/outcome_router.py:307-309` (vestigial `sys.path.insert`).
- **REMOVED**: `cortex_command/cli.py:_dispatch_print_root`'s `CORTEX_COMMAND_ROOT`-based discovery; replaced with `Path(cortex_command.__file__).parent` + optional `CORTEX_REPO_ROOT` override.
- **REMOVED**: `cortex_command/cli.py:_dispatch_upgrade`'s install-mutation logic (subprocess + git operations). The function is retained as an advisory printer only.
- **ADDED**: `.github/workflows/release.yml` — tag-on-push triggers wheel build + GitHub Release.
- **ADDED**: `CHANGELOG.md` — first entry documents v0.1.0.
- **ADDED**: `docs/release-process.md` — version-bump and tag-push workflow.
- **ADDED**: `docs/install.md` — `uv tool install git+<url>@<tag>` as primary path.
- **ADDED**: `docs/migration-no-clone-install.md` — runbook for existing maintainer install.
- **ADDED**: `cortex_command/common.py:_resolve_user_project_root()` — single source of truth for "where does the user's cortex project live?" Distinct name from `cortex_command/init/handler.py:_resolve_repo_root` (which uses `git rev-parse --show-toplevel` and is reserved for `cortex init`'s dispatch).
- **ADDED**: `plugins/cortex-overnight-integration/server.py:_ensure_cortex_installed()` — first-install hook.
- **ADDED**: `plugins/cortex-overnight-integration/server.py:CLI_PIN` constant — tuple `(tag, schema_version)` shared between the install URL and `MCP_REQUIRED_CLI_VERSION`.
- **ADDED**: `shutil.which("uv")` startup probe in `server.py` with structured PATH-fix error.
- **ADDED**: `tests/test_no_clone_install.py::test_target_state` — wheel-install + `importlib.resources` smoke test.
- **ADDED**: `tests/test_no_clone_install.py::test_mcp_first_install_hook` — runtime test of `_ensure_cortex_installed()` and the sentinel-read fallback.

## Technical Constraints

- **Composes with 146's auto-update orchestration.** First-install reuses 146's flock pattern, NDJSON failure surface (`${XDG_STATE_HOME}/cortex-command/last-error.log`), and skip-predicate latch. Differences: lock path is `install.lock` (not `update.lock`); only `CORTEX_AUTO_INSTALL=0` predicate applies pre-install (R9 dirty-tree and non-main-branch predicates assume a clone).
- **Plugin/CLI version coupling: `CLI_PIN` is plugin-only.** The plugin's `server.py` holds `CLI_PIN = (tag, schema)`. The CLI cannot import from the plugin tree (plugin lives at `~/.claude/plugins/`, outside the CLI's import path). The CLI must NOT reference `CLI_PIN` or `MCP_REQUIRED_CLI_VERSION` directly. Updates flow plugin → CLI via R4's `_ensure_cortex_installed`; the CLI never self-upgrades.
- **CLI surfaces that bypass `_resolve_user_project_root()`.** The following must NOT call the helper (because they need to run before any cortex project exists, or because their own resolution semantics are independent): `cortex init` (uses `cortex_command.init.handler:_resolve_repo_root`, a git-based resolver), `cortex --help` and `cortex --version` (argparse pre-dispatch, never reach handler code), `cortex --print-root` (uses `Path(cortex_command.__file__).parent` for the package install location), `cortex upgrade` (the new advisory wrapper, prints + exits 0). All other dispatch paths are free to invoke `_resolve_user_project_root()` inside their function bodies.
- **Call-time resolution mandated for `_resolve_user_project_root()`.** The helper must be invoked inside function bodies, never at module load. R3c enforces this via an AST-level acceptance check. Module-level invocation would capture `Path.cwd()` at import time, which silently breaks worker subprocesses, pytest fixtures that `monkeypatch.chdir`, and users who chdir between cortex invocations in a long-running shell.
- **`hatchling` default wheel build is correct as-is.** No `pyproject.toml` change needed for package data.
- **`importlib.resources` Traversable API only.** Conversions use `.read_text()`, `.is_file()`, `.iterdir()`, `.joinpath()`. Use `importlib.resources.as_file()` only when a real `pathlib.Path` is required by an external API.
- **`Path.cwd()` semantic for user-data lookups.** Design intent: most users invoke `cortex` from inside their own project repo. CWD = project root = where `lifecycle/` and `backlog/` live. The `_resolve_user_project_root()` helper enforces this with a sanity check at call time.
- **Branch refs are not safe for `uv tool upgrade`.** Verified (uv issues #4317, #9146, #14954). The migration depends on tag discipline (R1).
- **Auto-RCE expansion accepted as documented trade-off.** First-install has no equivalent of 146's R9 skip predicates. Mitigations: NDJSON audit trail, schema-version gate, plugin SHA pinning (epic 122). Trust model: same as 146 — single-maintainer GitHub repo trusted by users who installed the plugin.
- **MCP servers are not subject to Claude Code's Bash sandbox.** `uv tool install` from the MCP writes to `~/.local/share/uv/tools/`, `~/.local/bin/`, etc. without permission prompts. This is an asymmetry vs. the Bash tool path; documented per `requirements/project.md` L34.
- **PATH inheritance for MCP-spawned subprocesses follows Claude Code's MCP-launch env.** R4g's startup probe catches the macOS GUI-app + Homebrew + `~/.zshrc`-only misconfiguration.
- **Hatch wheel build does NOT include `tests/`.** Test fixtures with `Path(__file__)` are safe to leave unconverted.

## Open Decisions

(none — all 9 research-phase Open Questions resolved or deferred-with-default before spec write; critical-review fix-invalidating findings were resolved by the spec rewrite; no implementation-level questions remain.)
