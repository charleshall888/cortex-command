# Plan: add-upward-walking-project-root-detection-in-resolve-user-project-root

## Overview

Replace `_resolve_user_project_root()`'s cwd-only marker check with an upward walk bounded by `.git/` (file or directory) or filesystem root, enrich `CortexProjectRootError` with a `Searched: <paths>` diagnostic, then reroute the four sibling callsites that bypass the central resolver (overnight `_check_cwd` + three backlog CLI modules) through the new helper. Indirect callers route through the resolver already and inherit the upward walk transparently.

## Outline

### Phase 1: Resolver replacement (tasks: 1)
**Goal**: New upward-walking `_resolve_user_project_root()` lands with unit-test coverage.
**Checkpoint**: `pytest tests/test_common_utils.py -k test_resolve_user_project_root` is green and includes ≥6 new test functions.

### Phase 2: Callsite reroute and full-suite validation (tasks: 2, 3, 4)
**Goal**: Four direct-cwd callsites route through the new resolver; full repo test suite stays green.
**Checkpoint**: `just test` exits 0, `cd lifecycle && cortex --print-root` exits 0 from inside the lifecycle subdirectory.

## Tasks

### Task 1: Replace `_resolve_user_project_root()` with an upward walk and add unit tests
- **Files**: `cortex_command/common.py`, `tests/test_common_utils.py`
- **What**: Swap the existing cwd-only marker check (`common.py:79-86`) for a loop that walks upward from `Path.cwd().resolve()` collecting each visited parent into a `searched` list, returns the first ancestor whose `lifecycle/` or `backlog/` child is a directory, and terminates on either `(current / ".git").exists()` (file or directory shape — handles git worktrees) or `parent == current` (filesystem root). On termination without a match, raise `CortexProjectRootError` whose message preserves the existing remediation text and appends `Searched: <comma-separated visited paths>`. Preserve the `CORTEX_REPO_ROOT` env-var short-circuit unchanged. Extend `tests/test_common_utils.py` with at least 7 new test functions whose names start with `test_resolve_user_project_root_` (covers `lifecycle/` marker, `backlog/`-only marker, two-level subdirectory walk, `.git/` directory boundary, `.git` file boundary for worktree shape, `CORTEX_REPO_ROOT` env override, and Searched-message contents).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `_resolve_user_project_root` definition lives at `cortex_command/common.py:55-86` and imports `os`, `Path` already.
  - Existing exception class `CortexProjectRootError` at `common.py:46-52`; preserve the docstring and class name.
  - Existing tests in `tests/test_common_utils.py` use pattern `REPO_ROOT = Path(__file__).resolve().parent.parent`, `tmp_path` fixture, `monkeypatch.chdir`, and `monkeypatch.setenv("CORTEX_REPO_ROOT", ...)` — follow the same pattern. Imports already pull from `cortex_command.common`; add `_resolve_user_project_root` and `CortexProjectRootError` to the existing import block.
  - Use `monkeypatch.delenv("CORTEX_REPO_ROOT", raising=False)` in walk-path tests so an ambient env var does not bypass the walk.
  - For the worktree-style test (`.git` as a regular file), create a `tmp_path / "outer" / ".git"` file with `Path.write_text("gitdir: /elsewhere\n", encoding="utf-8")`; that mirrors real worktree shape.
  - For the `Searched:` assertion, use `pytest.raises(CortexProjectRootError) as excinfo` and assert `"Searched: "` appears in `str(excinfo.value)`.
- **Verification**: `just test PATTERN=test_common_utils` exits 0 — pass if exit code = 0; AND `grep -c "^def test_resolve_user_project_root" tests/test_common_utils.py` ≥ 7 — pass if count ≥ 7. (The leading `^` anchors against accidental matches inside comments or docstrings.)
- **Status**: [x] complete

### Task 2: Reroute `daytime_pipeline._check_cwd()` through the resolver
- **Files**: `cortex_command/overnight/daytime_pipeline.py`
- **What**: Replace `_check_cwd`'s `Path("lifecycle").is_dir()` body (lines 52-64) with a `try/except` around `_resolve_user_project_root()`. On `CortexProjectRootError`, write the exception's message (which now includes `Searched: …`) to stderr prefixed with `error: must be run from a cortex project root: ` and `sys.exit(1)`. Add an `_resolve_user_project_root` import to the existing `from cortex_command.…` import block at the top of the file. Leave the function name `_check_cwd` and its callsites unchanged.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Function `_check_cwd` at `cortex_command/overnight/daytime_pipeline.py:52-64`; current body is `if not Path("lifecycle").is_dir(): sys.stderr.write(...); sys.exit(1)`.
  - The module already imports `sys` and `Path` (`pathlib.Path`); only `_resolve_user_project_root` and `CortexProjectRootError` need to be added to the import block from `cortex_command.common`.
  - Call sites of `_check_cwd` live elsewhere in `daytime_pipeline.py` (`_run` / `build_parser` entry points) — confirm signature unchanged (`() -> None`) so callers stay untouched.
- **Verification**: `grep -c 'Path("lifecycle").is_dir()' cortex_command/overnight/daytime_pipeline.py` = 0 — pass if count = 0; AND `python3 -c "import cortex_command.overnight.daytime_pipeline"` exits 0 — pass if exit 0 (no import-time syntax error).
- **Status**: [x] complete

### Task 3: Reroute backlog CLIs through the resolver
- **Files**: `cortex_command/backlog/generate_index.py`, `cortex_command/backlog/update_item.py`, `cortex_command/backlog/create_item.py`
- **What**: Replace `Path.cwd() / "backlog"` (and, in `generate_index.py`, `Path.cwd() / "lifecycle"`) with `_resolve_user_project_root() / "backlog"` / `_resolve_user_project_root() / "lifecycle"`. In `generate_index.py:24-25` the constants are evaluated at module import time — move them to function-local evaluation inside `main()` (the same pattern already used at `update_item.py:444` and `create_item.py:162`), or convert them to lazy getters; the function-local pattern is the simpler change. Add `_resolve_user_project_root` to the existing `from cortex_command.common import …` lines in each module.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `cortex_command/backlog/generate_index.py:22` already imports from `cortex_command.common`; extend the import. Lines 24-25 hold module-level `BACKLOG_DIR` and `LIFECYCLE_DIR` — move them into `main()` and pass through to downstream helpers as function args if they're referenced elsewhere in the module (grep `BACKLOG_DIR`/`LIFECYCLE_DIR` first to enumerate all references).
  - `cortex_command/backlog/update_item.py:442-444` and `cortex_command/backlog/create_item.py:160-162` already evaluate `BACKLOG_DIR = Path.cwd() / "backlog"` inside `main()` — a one-line swap each.
  - Internal callers (functions inside these modules that take `backlog_dir` as a parameter) are unaffected — the spec explicitly excludes "callsites that already accept a `lifecycle_base` parameter."
- **Verification**: `grep -nE 'Path\.cwd\(\) / "(backlog|lifecycle)"' cortex_command/backlog/generate_index.py cortex_command/backlog/update_item.py cortex_command/backlog/create_item.py` returns 0 matches — pass if no output; AND `python3 -c "import cortex_command.backlog.generate_index, cortex_command.backlog.update_item, cortex_command.backlog.create_item"` exits 0 — pass if exit 0.
- **Status**: [x] complete

### Task 4: Full-suite validation and subdirectory smoke test
- **Files**: (none — validation only)
- **What**: Run the full test suite to confirm no regressions in the indirect-caller integration tests (`tests/test_cli_mcp_server_deprecated.py`, `tests/test_no_clone_install.py`, `tests/test_report_sandbox_denials.py`, `tests/test_state_load_failed_event.py`). Then smoke-test the from-subdirectory user flow by `cd`ing into `lifecycle/` and invoking `cortex --print-root` to confirm it resolves the repo root via the new walk rather than failing on cwd-only.
- **Depends on**: [2, 3]
- **Complexity**: simple
- **Context**:
  - `just test` is the canonical test runner.
  - `cortex --print-root` lives at `cortex_command/cli.py:163-202` and routes through `_resolve_user_project_root()` (line 199); a successful resolve emits versioned JSON with the `root` field.
  - The smoke test must be run from inside a subdirectory of the cortex-command repo (e.g., `lifecycle/`), not from the repo root, to actually exercise the walk.
- **Verification**: `just test` exits 0 — pass if exit code = 0; AND `(cd lifecycle && cortex --print-root)` exits 0 and emits JSON whose `.root` field equals the absolute path of the cortex-command repo root — pass if both hold. (Check with `(cd lifecycle && cortex --print-root | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["root"])')` matches `git rev-parse --show-toplevel`. Note: the literal `cortex` binary points at the pinned `uv tool install` wheel; the new resolver is verified via `.venv/bin/python -m cortex_command.cli --print-root`, which packages the working tree.)
- **Status**: [x] complete

## Risks

- **`.git` shape detection** (`exists()` vs `is_dir()`): the walk treats `.git` as a boundary regardless of whether it is a directory (normal checkout) or a file (worktree). If a user has a non-standard `.git`-named regular file at a parent for unrelated reasons, the walk would stop there. This is the same risk git itself accepts; the user would set `CORTEX_REPO_ROOT` to override.
- **Marker-set hardcoding**: `lifecycle/`/`backlog/` are baked into the resolver. When epic #200 lands and the relocation introduces `cortex/`, this function will be rewritten by ticket #202 to look for `cortex/` instead (Q3 decision). No coordination needed inside this ticket.
- **Performance**: bounded loop; depth typically <10. No measurable cost.
