# Plan: stabilize-test-no-clone-installtest-target

## Overview
Isolate the uv cache for the two genuine default-run real-`uv` tests by setting `UV_CACHE_DIR` to a `tmp_path`-rooted private directory in each subprocess `env` dict, mirroring the established precedent in `tests/test_mcp_auto_update_real_install.py`. This removes the shared `~/.cache/uv/.lock` contention that makes `just test` non-deterministically red, while preserving every install-regression assertion, skip branch, and subprocess timeout unchanged. A cold-cache measurement gate confirms isolation does not introduce a new timeout failure mode.

## Outline

### Phase 1: Isolate the uv cache for the default-run real-lock tests (tasks: 1, 2, 3)
**Goal**: Point every default-run real-`uv` subprocess at a private, tmp-rooted `UV_CACHE_DIR` so no external `uv` can contend on its lock, then prove determinism and cold-cache cost within budget.
**Checkpoint**: Both isolated targets pass from a cold cache within their subprocess budgets, `just test` exits 0, and no masking branch (timeout-skip) was added.

## Tasks

### Task 1: Isolate the uv cache in `test_no_clone_install.py` (build fixture + install helper)
- **Files**: `tests/test_no_clone_install.py`
- **What**: Point both real-`uv` subprocesses in this file — the `built_wheel` fixture's `uv build --wheel` and `_install_wheel_isolated`'s `uv tool install --reinstall` — at private tmp-rooted uv caches, so neither contends on the shared `~/.cache/uv/.lock`. Satisfies R1 and R2; preserves R4's no-masking constraint.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `built_wheel` (module-scoped fixture, L58-106): currently calls `subprocess.run(["uv", "build", "--wheel", "--out-dir", str(out_dir)], cwd=..., capture_output=True, text=True, timeout=180)` at L71-77 with **no `env=`** (inherits process env → shared cache). Create a module-scoped cache dir via the fixture's existing `tmp_path_factory` (e.g. `tmp_path_factory.mktemp("uv_cache")` — `uv build` tolerates an absent/empty cache dir, uv creates it), build `env = os.environ.copy()`, set `env["UV_CACHE_DIR"] = str(<cache_dir>)`, and pass `env=env` to the `uv build` call. The egress-panic skip block (L78-93) and `pytest.fail` branches must remain byte-unchanged.
  - `_install_wheel_isolated` (L114-145): already builds `env = os.environ.copy()` and sets `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`/`PATH` at L127-130. Add a function-scoped cache dir under the existing `tmp_path` param (e.g. `cache_dir = tmp_path / "uv_cache"; cache_dir.mkdir(parents=True, exist_ok=True)` beside the existing `tool_dir`/`bin_dir` `mkdir` calls at L122-125), and add `env["UV_CACHE_DIR"] = str(cache_dir)` alongside the existing env assignments (between L122 and L132). The `uv tool install` call (L132-138) and its `pytest.fail` branch are otherwise unchanged.
  - Precedent to mirror exactly: `tests/test_mcp_auto_update_real_install.py:165,206,408` (cache dir under tmp, `mkdir(parents=True, exist_ok=True)`, `env["UV_CACHE_DIR"] = str(cache_dir)`, no process-env monkeypatch).
  - Constraint: do NOT add any `except subprocess.TimeoutExpired` or timeout-skip branch; do NOT alter the fixture's module scope, the six `PACKAGE_INTERNAL_SITES` probes, or the install helper's `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR` isolation.
- **Verification**: `grep -c 'UV_CACHE_DIR' tests/test_no_clone_install.py` — pass if count ≥ 2 (one in the build fixture, one in the install helper). AND `grep -c 'TimeoutExpired' tests/test_no_clone_install.py` — pass if count = 0 (no masking branch added).
- **Status**: [ ] pending

### Task 2: Isolate the uv cache in `test_mcp_subprocess_contract.py` (`uv run --script`)
- **Files**: `tests/test_mcp_subprocess_contract.py`
- **What**: Point the `uv run --script` subprocess in `test_plugin_path_mismatch_exits_nonzero` at a private tmp-rooted uv cache so its PEP 723 dependency resolution does not contend on the shared `~/.cache/uv/.lock`. Satisfies R3; preserves R4's no-masking constraint.
- **Depends on**: none
- **Context**:
  - `test_plugin_path_mismatch_exits_nonzero` (L87-124): the `subprocess.run(["uv", "run", "--script", str(SERVER_PATH)], ..., timeout=60, env={...})` call at L104-114 passes a **literal** env dict (`PATH`, `HOME`, `CLAUDE_PLUGIN_ROOT`) — not `os.environ.copy()`. Add a key `"UV_CACHE_DIR": str(tmp_path / "uv_cache")` to that dict, and create the directory before the call (e.g. `(tmp_path / "uv_cache").mkdir(parents=True, exist_ok=True)` after `attacker_root.mkdir()` at L102). The `tmp_path` fixture param is already in scope (L87).
  - The existing `uv`-not-on-PATH skip (L96-97), the `SERVER_PATH.exists()` assert (L99), and both downstream assertions (L116-124) are unchanged.
  - Constraint: do NOT add any timeout-handling/`TimeoutExpired` branch; do NOT lengthen the 60s timeout.
- **Verification**: `grep -c 'UV_CACHE_DIR' tests/test_mcp_subprocess_contract.py` — pass if count ≥ 1. AND `grep -c 'TimeoutExpired' tests/test_mcp_subprocess_contract.py` — pass if count = 0.
- **Status**: [ ] pending

### Task 3: Verify isolated targets pass cold, measure cold-cache cost, and confirm full suite green
- **Files**: `cortex/lifecycle/stabilize-test-no-clone-installtest-target/plan.md` (implementation-notes append only — record measured timings)
- **What**: Prove the two isolated targets pass from a cold (empty) cache within their subprocess budgets, measure and record the cold-cache wall-clock (R6 gate), and confirm the full default suite is green (R5, R6, R7). Surfaces a blocker — rather than bumping a timeout — if the contract test's cold resolve is not comfortably under 60s.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - Cold-cache run of the two targets (force an empty cache so the measurement reflects the worst case): `.venv/bin/pytest "tests/test_no_clone_install.py::test_target_state" "tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero" -q --durations=0`. Because each target now roots `UV_CACHE_DIR` under a fresh pytest `tmp_path`, every run is already cold by construction — no need to clear `~/.cache/uv/`.
  - R6 thresholds (from spec): the contract test's cold `uv run --script` registry resolve of `mcp`+`pydantic`+`packaging` must complete comfortably under its 60s budget (target < 30s); `test_target_state`'s build+install must complete under 180s. Capture the per-test durations from `--durations=0` and append them to this plan's implementation notes.
  - R6 blocker rule: if the contract test's cold resolve is NOT comfortably under 60s, HALT and surface it as a blocker — do NOT lengthen the timeout to absorb it.
  - Full default suite: `just test` (runs sub-suites + hermetic `bash tests/test_install.sh` + `.venv/bin/pytest tests/ -q`; `@slow` excluded).
- **Verification**: `.venv/bin/pytest "tests/test_no_clone_install.py::test_target_state" "tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero" -q` — pass if exit code = 0 (R5). AND `just test` — pass if exit code = 0 (R7). AND the contract test's recorded cold resolve is < 30s and `test_target_state`'s build+install < 180s, recorded in the implementation-notes append (R6).
- **Status**: [ ] pending

## Risks
- **Cold-cache cost is the one new failure mode isolation could introduce.** Research rates a cold `UV_CACHE_DIR` build+install of this small pure-Python wheel at seconds (well under 180s), but found no published number for this exact operation — hence R6's measured gate (Task 3). If the contract test's cold `uv run --script` resolve approaches 60s on a slow network, the spec mandates surfacing it as a blocker, not bumping the timeout. This is a deliberate, accepted gate, not an open design choice.
- **Scope deliberately excludes the two `@slow` latent-gap tests** (`test_mcp_auto_update_orchestration.py::test_verification_probe_fails_on_corrupt_install`, `test_release_artifact_invariants.py::test_wheel_package_version_matches_git_describe`). They share the failure mode but are opt-in and excluded from the default run — documented as a known latent gap, intentionally not fixed here.
- **`@pytest.mark.serial` deliberately not added.** It is inert today (no `pytest-xdist`) and does nothing against the out-of-process trigger; `UV_CACHE_DIR` is the load-bearing mechanism. Adding `serial` would be forward-compat speculation against the project's "simpler wins" default.
