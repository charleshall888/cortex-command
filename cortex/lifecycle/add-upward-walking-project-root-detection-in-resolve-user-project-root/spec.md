# Specification: add-upward-walking-project-root-detection-in-resolve-user-project-root

## Problem Statement

`cortex_command/common.py:79-80` resolves the cortex project root with a cwd-only check (`(cwd / "lifecycle").is_dir() or (cwd / "backlog").is_dir()`) — no upward walk. Running any cortex CLI (`cortex backlog list`, `cortex backlog show`, `cortex --print-root`, …) from a subdirectory raises `CortexProjectRootError` until the user `cd`s back to repo root. Every comparable CLI (git, npm, cargo, terraform, kubectl) walks upward. Three sibling modules in `backlog/` and `overnight/daytime_pipeline.py` also bypass the central resolver with their own `Path.cwd() / ...` lookups, so they exhibit the same papercut even though the resolver function itself is central. This ticket switches the central resolver to an upward walk bounded by `.git/` or filesystem root, and reroutes the four sibling callsites through the same resolver — making every cortex CLI usable from inside a project subdirectory.

## Phases

- **Phase 1: Resolver swap** — change `_resolve_user_project_root()` to walk upward and reroute the four sibling callsites through it.

## Requirements

1. **Upward-walking resolver**: `_resolve_user_project_root()` walks upward from `Path.cwd().resolve()`, returning the first ancestor that contains `lifecycle/` OR `backlog/` as a directory. The walk terminates on the first ancestor that contains `.git/` (file or directory) OR on filesystem root (`parent == current`). The `CORTEX_REPO_ROOT` env-var override path is unchanged and short-circuits the walk entirely. **Acceptance**: `python3 -c "from pathlib import Path; from cortex_command.common import _resolve_user_project_root; import os; os.chdir(Path.cwd() / 'lifecycle' / 'add-upward-walking-project-root-detection-in-resolve-user-project-root'); print(_resolve_user_project_root())"` prints the cortex-command repo root (current working directory before the chdir), exit code 0. **Phase**: Resolver swap.

2. **Failure diagnostic on no-match**: When the walk exhausts without finding a marker, `CortexProjectRootError` is raised with a message that lists each directory searched. **Acceptance**: `grep -c "Searched: " cortex_command/common.py` ≥ 1, and the test in R6 below asserts the exception message contains the substring `Searched: ` followed by at least one path. **Phase**: Resolver swap.

3. **daytime_pipeline `_check_cwd` reroute**: `cortex_command/overnight/daytime_pipeline.py:52-64` (function `_check_cwd`) routes through `_resolve_user_project_root()`, catching `CortexProjectRootError` and exiting 1 with the enriched diagnostic instead of its current `Path("lifecycle").is_dir()` check. **Acceptance**: `grep -c 'Path("lifecycle").is_dir()' cortex_command/overnight/daytime_pipeline.py` = 0 (the literal pattern is removed from that file). **Phase**: Resolver swap.

4. **backlog CLI reroute**: `cortex_command/backlog/generate_index.py`, `cortex_command/backlog/update_item.py`, and `cortex_command/backlog/create_item.py` resolve their backlog directory via `_resolve_user_project_root() / "backlog"` (and, for `generate_index.py`, `_resolve_user_project_root() / "lifecycle"` for its `LIFECYCLE_DIR`) instead of `Path.cwd() / "backlog"` / `Path.cwd() / "lifecycle"`. **Acceptance**: `grep -nE 'Path\.cwd\(\) / "(backlog|lifecycle)"' cortex_command/backlog/{generate_index,update_item,create_item}.py` returns 0 matches. **Phase**: Resolver swap.

5. **Indirect callers benefit transparently**: The ~12 sites that already route through `_resolve_user_project_root()` (e.g., `cli.py:117,199`, `dashboard/seed.py`, `overnight/{plan,events,outcome_router,orchestrator}.py`, `dashboard/app.py`) require no edits — they inherit the upward walk for free. **Acceptance**: `cd lifecycle && cortex --print-root` (from anywhere inside the cortex-command repo subtree) emits the repo root in its JSON envelope and exits 0. **Phase**: Resolver swap.

6. **Unit tests for resolver behavior**: Add unit tests (extending `tests/test_common_utils.py`, the existing home for `common.py` unit tests) that cover: (a) resolves from project root with `lifecycle/` marker, (b) resolves from project root with `backlog/` marker only, (c) resolves from a subdirectory two levels below the marker, (d) `.git/` boundary terminates the walk when no marker is found, (e) `.git` as a file (worktree-style) also terminates, (f) `CORTEX_REPO_ROOT` env override is honored verbatim and skips the walk, (g) exception message includes `Searched: ` and lists at least one visited path. **Acceptance**: `just test PATTERN=test_common_utils` exits 0, AND `grep -c "def test_resolve_user_project_root" tests/test_common_utils.py` ≥ 6. **Phase**: Resolver swap.

7. **Full test suite remains green**: No regression in pre-existing tests that depend on `_resolve_user_project_root()` (notably `tests/test_cli_mcp_server_deprecated.py`, `tests/test_no_clone_install.py`, `tests/test_report_sandbox_denials.py`, `tests/test_state_load_failed_event.py`). **Acceptance**: `just test` exits 0. **Phase**: Resolver swap.

## Non-Requirements

- **No `cortex/` marker**: The helper does NOT look for a `cortex/` directory. Adding it is epic #200, ticket #202's job (the atomic relocation commit that also creates the directory). Adding it pre-emptively here would be dead code today (the directory does not exist) and would risk masking incomplete state during the relocation transition.
- **No change to `discovery.py`**: `cortex_command/discovery.py:62-74` (`_default_repo_root`) already walks upward via `git rev-parse --show-toplevel`. DR-10 listed it for completeness but it has no cwd-only bug. Leave untouched.
- **No subprocess-based fallback**: The resolver remains pure-Python — no `git rev-parse` call. Subprocess fallback was considered in research §Tradeoffs and rejected (silent-failure risk + library-vs-CLI separation).
- **No walking past `.git/`**: When a `.git/` ancestor exists without a cortex marker inside it, the walk stops there and raises. This prevents leaking into ancestor cortex projects that live above an unrelated nested git repo.
- **No new public API**: The function name stays `_resolve_user_project_root()` (single leading underscore). No companion `_with_walk()` variant — the existing function is replaced in place.

## Edge Cases

- **CWD is exactly the marker directory (`lifecycle/` or `backlog/`)**: First walk iteration tests the cwd itself; the cwd is the marker, not the parent, so the check moves up one level. The parent (repo root) contains the marker → returns parent. Correct.
- **Worktree (`.git` is a file)**: `(current / ".git").exists()` is true for both file and directory shapes. The walk terminates at the worktree's own root. If the worktree contains `lifecycle/` or `backlog/`, the marker check succeeds first and the walk returns the worktree root. Correct.
- **Nested cortex inside an unrelated git repo**: walking up from a cortex subdirectory finds the cortex marker before the unrelated `.git/`. If the cortex project itself has no `.git/`, the walk stops at the unrelated `.git/` and raises — user must set `CORTEX_REPO_ROOT` or run `cortex init`.
- **`$CORTEX_REPO_ROOT` set**: Returns `Path(env)` verbatim without resolving, without walking, without checking the marker. Backwards-compatible with all existing tests that rely on this override.
- **CWD on a non-git tree (e.g., tmp_path test fixture without `git init`)**: walk reaches filesystem root (`parent == current`) and raises with the searched-paths diagnostic.
- **Symlinked cwd**: `Path.cwd().resolve()` collapses symlinks at the start of the walk, so the walk traverses the canonical path. This matches the existing function's `.resolve()` semantics.
- **Permissions error on a parent dir**: `is_dir()` and `exists()` return False on `PermissionError`-shadowed paths; the walk silently moves past them. Acceptable — surfacing a permissions error mid-walk would change the failure shape from a single `CortexProjectRootError` to a leaked `OSError`. Standing on the existing function's "if any check fails, keep going" tolerance.

## Changes to Existing Behavior

- **MODIFIED: `_resolve_user_project_root()` cwd-only check** → walks upward from cwd to the first marker (`lifecycle/` OR `backlog/` directory), bounded by `.git/` or filesystem root. The env-var override short-circuit is preserved.
- **MODIFIED: `CortexProjectRootError` message** → includes a `Searched: <paths>` suffix listing each directory the walk visited. Existing callers that catch and print the exception (e.g., `cli.py:201`) automatically display the enrichment.
- **MODIFIED: `cortex_command/overnight/daytime_pipeline.py:_check_cwd()`** → routes through the central resolver and catches `CortexProjectRootError` instead of its own `Path("lifecycle").is_dir()` check.
- **MODIFIED: `cortex_command/backlog/{generate_index,update_item,create_item}.py`** → resolves `BACKLOG_DIR` (and, in `generate_index.py`, `LIFECYCLE_DIR`) via the central resolver instead of `Path.cwd()`.
- **ADDED: ~12 indirect callers** (cli, dashboard, overnight pipeline modules) become usable from inside any cortex subdirectory without an edit at the callsite. This is a transparent behavior expansion.

## Technical Constraints

- **Pure-Python resolver**: no subprocess shell-outs in `_resolve_user_project_root()`. Research §Tradeoffs alternative B was rejected on this basis.
- **`.git` shape tolerance**: use `Path.exists()` (not `is_dir()`) for the `.git/` boundary check so that git worktrees (where `.git` is a regular file pointing at the main checkout) terminate the walk correctly.
- **Idempotency under `monkeypatch.chdir`**: the function is invoked at call time (existing constraint at `common.py:63-66`). The walk happens fresh on every call, so worker subprocesses and pytest fixtures that chdir mid-test resolve correctly without caching.
- **Backwards-compatibility with `CORTEX_REPO_ROOT`**: env-var override path returns `Path(env)` unchanged. Pre-existing tests rely on this — see `tests/test_report_sandbox_denials.py:186-189`, `tests/test_no_clone_install.py:214`, `tests/test_state_load_failed_event.py:48`, `tests/test_cli_mcp_server_deprecated.py:93`.
- **`backlog/generate_index.py` module-level constants**: today `BACKLOG_DIR` and `LIFECYCLE_DIR` are evaluated at import time (line 24-25). Moving to the resolver requires either making them functions/properties or evaluating them at the first use inside `main()`. Function-local evaluation (matching the existing pattern at `update_item.py:444` and `create_item.py:162`) is the simpler choice — no import-time side effects, no breaking change to the existing call shape.
- **No dual-source plugin mirror impact**: the changes touch only `cortex_command/` Python sources; the plugin-mirrored `bin/` directory is unaffected.

## Open Decisions

(none — all design questions were resolved during Clarify Q1/Q2/Q3 and research.)
