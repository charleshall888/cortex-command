# Specification: stabilize-test-no-clone-installtest-target

## Problem Statement

`tests/test_no_clone_install.py::test_target_state` intermittently fails with `subprocess.TimeoutExpired` during full `just test` runs (observed once during #279's overnight Complete gate; green on immediate re-run; passes in isolation in ~5.5s). Root cause: the test runs real `uv build` + `uv tool install --reinstall` against the **shared** uv cache (`~/.cache/uv/`) without isolating `UV_CACHE_DIR`, so under contention from any concurrent `uv` process (notably the cortex-overnight SessionStart/MCP background auto-update installs) it blocks on the per-cache file lock past its 180s subprocess budget. `uv`'s own `UV_LOCK_TIMEOUT` defaults to 300s — longer than the 180s budget — so the subprocess dies before uv surfaces a lock error. The fix isolates the uv cache per-test (the established repo precedent), making `just test` deterministic without weakening the install-regression assertions the gate exists to catch. A developer-facing benefit: `just test` stops being non-deterministically red, unblocking lifecycle Complete gates and CI on sound changes.

## Phases

- **Phase 1: Isolate the uv cache for the genuine default-run real-lock tests** — point each real-`uv` subprocess at a tmp-rooted private `UV_CACHE_DIR`, preserving all existing assertions and timeouts, and verify cold-cache cost stays within budget.

## Requirements

1. **`test_target_state`'s wheel build runs against an isolated uv cache.** The `built_wheel` module-scoped fixture (`tests/test_no_clone_install.py:58-106`) passes an `env` dict to its `uv build` subprocess (currently passes no `env`, L71-77) with `UV_CACHE_DIR` set to a `tmp_path_factory`-rooted directory. Acceptance: `grep -c 'UV_CACHE_DIR' tests/test_no_clone_install.py` ≥ 2, and the `uv build` call at L71-77 passes `env=<dict containing UV_CACHE_DIR>`. **Phase**: Phase 1

2. **`test_target_state`'s install runs against an isolated uv cache.** `_install_wheel_isolated` (`tests/test_no_clone_install.py:114-145`) sets `env["UV_CACHE_DIR"]` to a `tmp_path`-rooted directory `mkdir(parents=True, exist_ok=True)`'d before the `uv tool install` call, alongside the existing `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`/`PATH` (L127-130). Acceptance: the helper's returned/passed `env` contains `UV_CACHE_DIR`; observable as a `UV_CACHE_DIR` assignment between L122 and L132 of the file. **Phase**: Phase 1

3. **`test_mcp_subprocess_contract::test_plugin_path_mismatch_exits_nonzero` runs against an isolated uv cache.** Its `uv run --script` env dict (`tests/test_mcp_subprocess_contract.py:104-114`) includes `"UV_CACHE_DIR": str(tmp_path / "uv_cache")` (created before the call). Acceptance: `grep -c 'UV_CACHE_DIR' tests/test_mcp_subprocess_contract.py` ≥ 1. **Phase**: Phase 1

4. **Install-regression assertions and skip logic are preserved unchanged (no masking).** The egress-panic skip (`tests/test_no_clone_install.py:78-93`) still triggers only on uv's panic signature (`"Tokio executor failed"`/`"system-configuration"`), the six `PACKAGE_INTERNAL_SITES` `importlib.resources` probes and the `"plugin path mismatch"` assertion are unchanged, and **no** `except subprocess.TimeoutExpired`/timeout-skip branch is added. Acceptance: `grep -c 'TimeoutExpired' tests/test_no_clone_install.py tests/test_mcp_subprocess_contract.py` = 0 (no new timeout-handling), and the existing skip/assert blocks are byte-unchanged except for the added `UV_CACHE_DIR` env keys. **Phase**: Phase 1

5. **Both isolated targets pass.** Acceptance: `.venv/bin/pytest "tests/test_no_clone_install.py::test_target_state" "tests/test_mcp_subprocess_contract.py::test_plugin_path_mismatch_exits_nonzero" -q` exits 0 (pass if exit code = 0). **Phase**: Phase 1

6. **Cold-cache cost stays within budget (measured).** With a fresh (empty) `UV_CACHE_DIR`, the contract test's `uv run --script` registry resolve of `mcp`+`pydantic`+`packaging` completes comfortably under its 60s budget (target < 30s) and `test_target_state`'s build+install completes under 180s. Acceptance: run each isolated target from a cold cache, capture wall-clock (e.g. `pytest --durations=0` or a timed run), record it in the implementation notes; pass if the contract test's cold resolve is < 30s and the build/install < 180s. If the contract test's cold resolve is **not** comfortably under 60s, halt and surface it as a blocker — do **not** lengthen the timeout to absorb it. **Phase**: Phase 1

7. **Full default suite is green.** Acceptance: `just test` exits 0 (pass if exit code = 0). **Phase**: Phase 1

## Non-Requirements

- Does **not** modify the `@pytest.mark.slow` real-`uv` tests that share the same failure mode but are opt-in and excluded from the default run: `tests/test_mcp_auto_update_orchestration.py::test_verification_probe_fails_on_corrupt_install` (L1133) and `tests/test_release_artifact_invariants.py::test_wheel_package_version_matches_git_describe` (L197). They are a known latent isolation gap, out of this ticket's default-run scope; do not fix here.
- Does **not** add `@pytest.mark.serial` to the targets. The marker is currently inert (no `pytest-xdist` installed; pytest runs single-process, so it changes no scheduling) and does nothing against the actual trigger (an out-of-process concurrent `uv`). The load-bearing mechanism is `UV_CACHE_DIR`; adding `serial` would be forward-compat speculation against the project's "simpler wins" default.
- Does **not** gate, disable, or add a test-detection signal to the cortex-overnight MCP auto-update (`plugins/cortex-overnight/server.py`) or SessionStart background-install hook (`hooks/cortex-cli-background-install.sh`). Per-test cache isolation makes the targets immune to **every** external `uv` contender regardless, so hook-gating would be a fragile, partial, redundant mitigation.
- Does **not** lengthen subprocess timeouts or add retries as the de-flake mechanism — that masks a correctness gate (research-flagged anti-pattern). (R6's measured fallback for the 2nd target is a blocker, not a timeout bump.)
- Does **not** add `pytest-xdist` or convert the runner to parallel execution.
- Does **not** alter the `built_wheel` fixture's module scope, the install helper's isolation of `UV_TOOL_DIR`/`UV_TOOL_BIN_DIR`, or any of the `importlib.resources` probe sites.

## Edge Cases

- **Cold `uv run --script` resolve approaches/exceeds 60s on a slow network** (the contract test): surfaced as an explicit blocker per R6; do not bump the timeout. This is the one scenario where isolation could introduce a new failure mode, hence the measured gate.
- **`uv` not on PATH**: existing skip guards (`test_no_clone_install.py:67-68`, `test_mcp_subprocess_contract.py:96-97`) still fire first; adding `UV_CACHE_DIR` to the env does not change skip behavior.
- **Sandbox blocks PyPI/GitHub egress**: the `built_wheel` egress-panic skip (L78-93) still catches uv's panic signature; an isolated (empty) cache does not alter the panic path. Note: a cold isolated cache *requires* network for the first population, so an egress-blocked sandbox that previously rode a warm shared cache will now hit the skip/failure path earlier — acceptable, and consistent with the test's existing "requires network access" skip semantics.
- **`built_wheel` is module-scoped**: its `UV_CACHE_DIR` must be created at fixture (module) scope via `tmp_path_factory`; the install helper's cache is function-scoped via `tmp_path`. They need not share — each just needs to be off `~/.cache/uv/`.

## Changes to Existing Behavior

- **MODIFIED**: `built_wheel` fixture and `_install_wheel_isolated` (`tests/test_no_clone_install.py`) now run `uv build`/`uv tool install` against a tmp-rooted private cache (`UV_CACHE_DIR`) instead of the shared `~/.cache/uv/` → removes shared-lock contention; first run per suite is a cold (network-populated) cache.
- **MODIFIED**: `test_plugin_path_mismatch_exits_nonzero` (`tests/test_mcp_subprocess_contract.py`) now runs `uv run --script` against a tmp-rooted private cache → immune to external lock contention; cold-resolves PEP 723 deps per suite run.

## Technical Constraints

- **Isolation mechanism (precedent-bound)**: set `UV_CACHE_DIR` in the subprocess `env` dict pointing at a `tmp_path`/`tmp_path_factory` directory; `mkdir(parents=True, exist_ok=True)` before the install call (`uv build` tolerates an absent cache dir, uv creates it). Mirror `tests/test_mcp_auto_update_real_install.py:165,206,408` exactly — no process-env monkeypatch, no shared fixture required.
- **uv lock model**: the cache lock is per-cache-directory (`$UV_CACHE_DIR/.lock`); a unique tmp cache gives each process its own lock, eliminating cross-process contention. `UV_LOCK_TIMEOUT` defaults to 300s (> the 180s/60s subprocess budgets), which is why the subprocess timeout fires first.
- **Preserve all existing timeouts**: 180s (build), 180s (install), 60s (`uv run --script`), 30s/15s (probes). Isolation removes the contention that made them insufficient; the budgets themselves do not change.
- **Pre-commit gates on `tests/*`**: `.githooks/pre-commit` runs `just check-parity --staged` (Phase 1.5) and `just check-contract --staged` on staged `tests/*` paths; both pass for a tests-only edit (no SKILL/CLI surface touched). Keep all changes within `tests/`. No `pyproject.toml` change is needed (no new marker added).
- **Scope/upkeep**: confined to test files; no shipped-code or cross-cutting behavioral effects; none of the lifecycle-gated paths (`skills/`, `hooks/`, `bin/cortex-*`, `cortex_command/common.py`, plugins) are touched.

## Open Decisions

None. Approach (per-test `UV_CACHE_DIR` isolation) and the second-target handling (isolate both, with a measured cold-cache gate) are resolved during Clarify and the Spec interview. Cold-cache timing is a measured acceptance criterion (R6), not an unresolved design choice.

## Proposed ADR

None considered.
