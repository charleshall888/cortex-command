---
schema_version: "1"
uuid: b70b19f9-3325-44a6-987e-cd938f244f4a
title: "Stabilize test_no_clone_install::test_target_state against uv-cache-lock timeout flake"
status: backlog
priority: medium
type: bug
created: 2026-06-02
updated: 2026-06-02
---
**Why:** `tests/test_no_clone_install.py::test_target_state` intermittently fails with `subprocess.Timeout` during the full `just test` run. Observed during #279's Complete gate (1 failed / 1729 passed), then green on immediate re-run (6/6). It passes in isolation in ~5.5s. The flake makes `just test` non-deterministically red, which can block lifecycle Complete gates and CI on changes that are actually sound.

**Root cause (diagnosed during #279):** The test runs real `uv build` + `uv tool install --reinstall` (each guarded by a 180s `subprocess` timeout) plus several `python -c importlib.resources` probes (15–30s timeouts). pytest runs single-process (no xdist installed), but the suite contains ~17 uv-invoking tests, `just test` also runs `test-install` (`tests/test_install.sh`), and the cortex-overnight MCP server can fire a background `uv tool install --reinstall git+…` auto-update hook. All of these serialize on the shared uv cache lock (`~/.cache/uv/.lock`). Under contention, `test_target_state`'s uv operations block on the lock past their subprocess timeout and raise `TimeoutExpired` — which falls past the test's own egress-block skip (that skip only triggers on uv's immediate panic signature, not a timeout).

**Role / fix options (decide during refine):**
- Isolate the uv cache per-test via `UV_CACHE_DIR=<tmpdir>` so the test does not contend on the shared lock (trades a cold-cache slowdown for determinism), or
- Add a bounded retry / longer timeout calibrated to realistic lock-wait, or
- Quarantine/serialize the uv-invoking integration tests (own group or marker) so they never overlap a background `uv tool install`.

**Edges:** Must not mask a genuine install regression — do not blanket-skip on timeout. If the fix is cache isolation, confirm the sibling uv-invoking tests that share this failure mode are covered too. Background MCP auto-update firing mid-suite is part of the trigger; consider gating it during tests.

**Touch-points:** `tests/test_no_clone_install.py` (`built_wheel` module fixture, `_install_wheel_isolated`, `test_target_state`); possibly the `justfile` `test` recipe; the ~17 other uv-invoking tests under `tests/` that share the shared-cache-lock exposure.