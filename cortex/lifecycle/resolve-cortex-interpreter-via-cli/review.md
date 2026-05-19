# Review: resolve-cortex-interpreter-via-cli (cycle 1)

## Stage 1: Spec Compliance

### Requirement 1 — `cortex hooks scan-lifecycle` subcommand exists, reads stdin JSON — PASS
`cortex_command/cli.py:716-739` registers `cortex hooks` as a top-level subparser with `scan-lifecycle` as its first member; the dispatcher at `cli.py:110-113` lazy-imports `cortex_command.hooks.scan_lifecycle` and calls `main()`. `scan_lifecycle.py:405-484` reads stdin JSON, tolerates absent/malformed payloads (returns 0), and silently exits 0 when the cwd has no `cortex/lifecycle/` dir. `--help` is reachable under both `cortex hooks --help` and `cortex hooks scan-lifecycle --help`.

### Requirement 2 — Golden-file equivalence — PASS
Six fixture pairs are present under `tests/fixtures/hooks/scan_lifecycle/` (`a..f`). `tests/test_hooks_scan_lifecycle.py:285-389` parameterizes six `test_golden_*` cases that stage the lifecycle filesystem state via `tests/_hook_fixture_helpers.py`, replay through `scan_lifecycle.main()`, extract `hookSpecificOutput.additionalContext` from the captured stdout, and assert byte-equivalence against the `*.expected.additionalContext.txt` goldens. The sentinel `__NO_OUTPUT__` handling is correct.

### Requirement 3 — Lazy-load discipline — PASS
Verified directly:
```
python3 -c "import cortex_command.cli; import sys; print([m for m in sys.modules if m.startswith('cortex_command.hooks')])"
=> []
```
The dispatcher body in `cli.py:110-113` imports `cortex_command.hooks.scan_lifecycle` lazily inside the function, and `scan_lifecycle.main()` further defers its intra-package imports (`common`, `_pipeline_state`, `_session_state`, `pipeline.metrics`) to after the cwd/lifecycle early-exit. Matches the overnight precedent at `cli.py:48-66`.

### Requirement 4 — Thin bash wrapper with subcommand-presence probe — PASS
`hooks/cortex-scan-lifecycle.sh` is 9 lines (≤ 15) and matches the spec's prescribed shape exactly: `command -v cortex` guard, stdin capture, cwd `jq` extract, lifecycle-dir guard, `--help` probe with `|| exit 0`, then `printf | exec cortex hooks scan-lifecycle`. The probe-then-exec discipline is preserved.

### Requirement 5 — `CLI_PIN` bumped — PASS
`plugins/cortex-overnight/server.py:106` is now `CLI_PIN = ("v2.2.0", "2.0")`. The acceptance grep `grep -c '^CLI_PIN = ("v2\.1\.2", "2\.0")$'` returns 0 (old pin gone).
Note: per the implementer's note, the `v2.2.0` git tag already exists on a parallel branch unreachable from HEAD; this is a merge-time release-engineering concern that does not affect code correctness in this PR's scope. The release ritual will need to reconcile the tag before/after merge.

### Requirement 6 — Table-driven session-mutation tests — PASS
`grep -c "def test_session_mutation_" tests/test_hooks_scan_lifecycle.py` returns 5 (≥ 4). All four enumerated branches are covered:
- `test_session_mutation_P1` (lines 397-452) asserts both `.session` and `.session-owner` post-call state.
- `test_session_mutation_P2` (lines 455-523) iterates two features and asserts `.session` written + `.session-owner` unchanged.
- `test_session_mutation_SC` (lines 526-571) asserts `.session` written + `.session-owner` not created.
- `test_session_mutation_OR` (lines 574-638) asserts `.session` NOT created when the feature is `complete` with only an orphan `.session-owner` (the documented bash divergence).
The OR-branch suppression is enforced in `scan_lifecycle.py:542-553`: after `migrate_session_p2` writes, the orchestrator runs `detect_lifecycle_phase` and unlinks the just-written `.session` when phase is `complete`. Semantics match the spec; the write-then-unlink approach is stylistically different from a write-prevent gate but functionally equivalent (and the OR test verifies the end-state correctly).

### Requirement 7 — uv-tool-topology smoke test — PASS
`tests/smoke_uv_tool_hook.sh` exists, is wired via `justfile:400-404` as `test-smoke-hook`, and exercises both liveness and per-fixture golden equivalence under uv-tool topology. The script includes two guards that skip-with-message rather than emit bogus failures: (a) a topology probe (`cortex` must resolve into `share/uv/tools/cortex-command/`); (b) a subcommand-presence probe (`cortex hooks scan-lifecycle --help`). On a dev-checkout where the installed uv-tool predates this work, the script exits 0 cleanly with a clear setup suggestion — matches the spec's "may be marked skip in CI" allowance, and the recipe+assertion both exist as required.

### Requirement 8 — Plugin mirror refreshed — PASS
`diff hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` returns empty (byte-equivalent). `justfile:646-664` defines `build-plugin` with `cortex-overnight` HOOKS array including `hooks/cortex-scan-lifecycle.sh`, so the mirror regenerates automatically. The pre-commit `dual-source drift` enforcement (Tech Constraints) is honored.

### Requirement 9 — Fail-loud preservation via probe-then-exec — PASS
Two stubs exist under `tests/fixtures/cortex_stubs/`:
- `probe_failure/cortex` exits 1 for any invocation (modeling old CLI without the subcommand) — `test_wrapper_probe_failure_silent_degrade` (lines 894-927) asserts wrapper rc=0.
- `probe_pass_run_fail/cortex` returns 0 from `--help`, 1 otherwise — `test_wrapper_probe_pass_run_fail_propagates` (lines 930-964) asserts wrapper rc=1.
The wrapper's `exec` form propagates the subcommand's exit code on real failures; the probe absorbs skew-window false positives.

### Requirement 10 — statusline.sh parity comment updated — PASS
`grep -c "bash-only mirror" claude/statusline.sh` = 3 (≥ 1). `grep -c "cortex hooks scan-lifecycle" claude/statusline.sh` = 1 (≥ 1). The docstring at `claude/statusline.sh:376-394` explicitly names the canonical entry point (`cortex hooks scan-lifecycle (cortex_command.hooks.scan_lifecycle)`) and documents the structural-exception rationale (statusline render-latency budget). The DR-6 parity surface is preserved (no changes to the bash phase-detection ladder itself).

### Requirement 11 — Session-state writes serialized via `fcntl.flock` — PARTIAL
Semantics: fully met. `cortex_command/hooks/_session_state.py:99-141` defines `feature_lock` as a context manager that opens `{feature_dir}/.lock` and acquires `fcntl.flock(fd, fcntl.LOCK_EX)`; all three mutation helpers (`migrate_session_p1`, `migrate_session_p2`, `claim_single_feature`) wrap their writes in `with feature_lock(...)`. Atomic-rename writes via `tempfile.NamedTemporaryFile` + `os.replace` close the zero-byte-window per the Edge Cases. The concurrent-writes test (`test_session_mutation_concurrent_writes_serialized`, lines 697-816) loops 8 iterations spawning two `multiprocessing` workers synchronized on a `Barrier`, then asserts that `.session` carries exactly one of the candidate ids AND `.session-owner` carries the stale id (the P1 invariant under serialization).

Literal acceptance gap: the spec wrote `grep -c "fcntl.flock" cortex_command/hooks/scan_lifecycle.py >= 1`, but the literal `fcntl.flock` call lives in the helper module `cortex_command/hooks/_session_state.py` (count = 3) — `scan_lifecycle.py` invokes it indirectly via the imported `feature_lock` helper. The semantic requirement (flock serialization + concurrent-write test) is fully discharged; only the strict-text grep target is off. This is a non-blocking acceptance phrasing mismatch — the architectural choice to extract mutation helpers into `_session_state.py` is consistent with the project pattern (cf. `cortex_command/init/settings_merge.py`). Recommended remediation if the literal acceptance must be honored: add a brief comment in `scan_lifecycle.py` referencing `fcntl.flock` (e.g. in the docstring on the P2 block), or update the spec acceptance to grep the `cortex_command/hooks/` subtree.

## Stage 2: Code Quality

### Naming / pattern consistency
- Module layout (`cortex_command/hooks/__init__.py` empty; `_pipeline_state.py`, `_session_state.py` underscore-prefixed as internal helpers; `scan_lifecycle.py` as the public-ish subcommand entry) follows the established pattern in `cortex_command/init/` and `cortex_command/overnight/`.
- Lazy-import discipline in `_dispatch_hooks_scan_lifecycle` mirrors `_dispatch_overnight_*` exactly.
- `_atomic_write` + `feature_lock` follow the precedent in `cortex_command/init/settings_merge.py` (lock on lockfile inode, not data-file inode — explicitly called out in the `feature_lock` docstring).
- Naming of `_encode_phase`, `_phase_label`, `_interrupted_hint`, `_metrics_summary_line` is consistent with the bash helper names they port.

### Error handling
- `scan_lifecycle.main()` is appropriately defensive: stdin read failure, JSON parse failure, non-dict payload, missing `cwd`, malformed `.session` reads all return 0 with no output (matches bash precedent). Metrics regen swallows `SystemExit` and bare `Exception` consistent with bash `|| true`.
- `_atomic_write` (`_session_state.py:52-96`) is correct: same-dir tempfile, fsync before replace, `BaseException`-clause cleanup with double-try for both `close` and `unlink` (handles edge cases where close was already attempted). The `BaseException` catch is the right call here — covers KeyboardInterrupt/SystemExit during the write window.
- `feature_lock` opens with `O_CLOEXEC` (correct for fork-safety in the multiprocessing concurrent test), and explicitly unlocks before closing in the finally block.
- `_read_id` matches bash's `tr -d '[:space:]'` semantics via `"".join(raw.split())` — correctly removes ALL whitespace, not just leading/trailing.
- The OR-branch write-then-unlink in `scan_lifecycle.py:542-553` swallows `OSError` on `unlink`, which is correct (race where the file disappears between write and unlink is benign).

### Test coverage
- 15 test functions in `tests/test_hooks_scan_lifecycle.py`: 6 golden-replay + 4 session-mutation + 1 concurrent-serialization + 2 fixture-meta + 2 wrapper-probe.
- The wrapper-probe tests use real bash invocation against stub `cortex` shell scripts on PATH — exercises the actual wrapper shape end-to-end, not a mock.
- The concurrent test uses `spawn` start method explicitly (correct for parity across macOS/Linux) and loops 8 iterations to surface race windows, with defensive cleanup of leaked workers.
- Fixture-staging via `_hook_fixture_helpers.py` (StageSpec/FeatureSpec dataclasses) is clean and reused across smoke test, golden replay, and mutation tests — single source of truth.

### Pattern consistency
- Argparse subparser registration mirrors the overnight surface precisely (description, help, lazy dispatcher).
- Plugin-mirror enforcement and bin/parity-exception entry (`cortex-pipeline-metrics` moved to library-internal allowlist with the 2026-05-18 dated note) are both correctly handled.
- `.gitignore` entry for `cortex/lifecycle/*/.lock` keeps the new per-feature lockfile out of git — appropriate.

### Notable strengths
- The smoke test's two-tier skip guards (topology probe + subcommand-presence probe) are a notably thoughtful defense against bogus failures on dev-checkout — exits cleanly when assertions can't be meaningfully evaluated.
- The OR-branch divergence from bash is documented in three places (`_session_state.py` module docstring, the `skip_orphan_session_owner` function docstring, and the orchestrator comment block at `scan_lifecycle.py:542-553`) — the latent-bug rationale is fully traceable.
- `ensure_ascii=False` on the final `json.dump` (line 723) is correctly applied — preserves emoji-bearing pipeline-context bytes per the Morning Review fixture (☀️).
- `_dispatch_print_root` and unrelated subcommands continue to pay zero import cost for the new hooks subtree (Req #3 lazy discipline).

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Verdict
```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```

### Reviewer notes (non-blocking)
- The implementer correctly fixed the `ensure_ascii=False` divergence flagged in Task 9 (verified at `scan_lifecycle.py:723`).
- The OR-branch write-then-unlink is semantically equivalent to the spec's write-prevent intent; the OR test verifies the end-state (`.session` absent), not the write path. No defect.
- The `v2.2.0` git-tag collision on parallel history is a merge-time release-engineering concern, not a code defect. Recommend reconciling the existing tag (e.g., re-cut as `v2.2.1` or fast-forward main) before publishing the release artifact that consumers will reference for `CLI_PIN`.
- Spec Req #11's literal acceptance `grep -c "fcntl.flock" cortex_command/hooks/scan_lifecycle.py >= 1` is not satisfied by current text layout (count = 0), but the semantic requirement is met. The architectural choice to keep `fcntl.flock` in `_session_state.py` is the right one. Either a docstring mention in `scan_lifecycle.py` or a small spec-acceptance amendment would close the literal gap without affecting correctness.
- The defensive uv-tool smoke-test subcommand-presence probe is correctly implemented and exits 0 cleanly on the current dev checkout (verified `tests/smoke_uv_tool_hook.sh:48-60`).
