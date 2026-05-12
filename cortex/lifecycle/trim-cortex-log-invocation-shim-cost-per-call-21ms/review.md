# Review: trim-cortex-log-invocation-shim-cost-per-call-21ms

## Stage 1: Spec Compliance

### Requirement 1: Shim consults `CORTEX_REPO_ROOT` before `git rev-parse`
- **Expected**: `bin/cortex-log-invocation` reads `${CORTEX_REPO_ROOT:-}` first; when non-empty AND `.git` marker present, uses it without `git rev-parse`; otherwise falls back.
- **Actual**: `bin/cortex-log-invocation:32-43` reads `${CORTEX_REPO_ROOT:-}`, validates via `[ -d "$CORTEX_REPO_ROOT/.git" ] || [ -f "$CORTEX_REPO_ROOT/.git" ]`, uses the value verbatim on hit, falls back to `git rev-parse --show-toplevel 2>/dev/null` on miss. Smoke test during implement (`LIFECYCLE_SESSION_ID=test-t1-smoke CORTEX_REPO_ROOT=/Users/charlie.hall/Workspaces/cortex-command bin/cortex-log-invocation /tmp/probe arg1 arg2`) produced `{"ts":"…","script":"probe","argv_count":2,"session_id":"test-t1-smoke"}` confirming the fast path emits the expected JSONL.
- **Verdict**: PASS
- **Notes**: No `git` fork is reached on the env-var fast-path branch by source inspection.

### Requirement 2: Stale `CORTEX_REPO_ROOT` falls back safely
- **Expected**: When `CORTEX_REPO_ROOT` is set but the path lacks `.git`, shim falls back to `git rev-parse`.
- **Actual**: Lines 32-39 of the shim: the env-var branch is gated on the `.git`-marker test; on failure, `repo_root` remains empty and the subsequent `if [ -z "$repo_root" ]` block runs `git rev-parse --show-toplevel 2>/dev/null`. Verified by source structure.
- **Verdict**: PASS

### Requirement 3: `mkdir -p` deferred to first-write per session
- **Expected**: Shim guards `mkdir -p` with `[ -d ] ||`; downstream `[ ! -d ]` failure check intact.
- **Actual**: `grep -c '\[ -d "\$session_dir" \] || mkdir -p' bin/cortex-log-invocation` = 1 (from implement-phase verification). The downstream `if [ ! -d "$session_dir" ]` failure-emit block at lines 49-52 is preserved.
- **Verdict**: PASS

### Requirement 4: `basename` fork replaced with parameter expansion
- **Expected**: `script_name="${script_path##*/}"` replaces the `basename` subprocess.
- **Actual**: `grep -c 'script_name="${script_path##\*/}"'` returned 1; `grep -c '^script_name="$(basename'` returned 0. Both gates met.
- **Verdict**: PASS

### Requirement 5: Fail-open contract preserved
- **Expected**: `trap 'exit 0' EXIT` at top; breadcrumb-category set `{no_session_id, no_repo_root, session_dir_missing, write_denied, other}` closed; all paths exit 0.
- **Actual**: `head -20 bin/cortex-log-invocation | grep -c "trap 'exit 0' EXIT"` = 1. The five breadcrumb categories all appear unchanged in `_log_breadcrumb` call sites. Smoke test exited 0 cleanly.
- **Verdict**: PASS

### Requirement 6: JSONL byte-equivalence test continues to pass
- **Expected**: `uv run pytest cortex_command/backlog/tests/test_telemetry_byte_equivalence.py -q` exits 0.
- **Actual**: Implement phase ran the test; both parametrizations (`slow-path`, `fast-path`) passed in 0.09s. The fast-path parametrization is new (added in T2) and exercises the env-var branch the original test did not reach.
- **Verdict**: PASS

### Requirement 7: Python helper `_telemetry.py:_resolve_repo_root` updated symmetrically
- **Expected**: Consults `CORTEX_REPO_ROOT` with `.git`-marker validation before invoking git rev-parse.
- **Actual**: `cortex_command/backlog/_telemetry.py:46-71` reads `_os.environ.get("CORTEX_REPO_ROOT")`, validates via `marker = _Path(env_root) / ".git"; if marker.is_dir() or marker.is_file(): return env_root`, falls back to the existing `subprocess.run(["git", "rev-parse", "--show-toplevel"])` on miss. Pinned predicate (`is_dir() or is_file()`) matches the bash shim's `[ -d ] || [ -f ]` semantics on regular files, directories, and broken symlinks.
- **Verdict**: PASS
- **Notes**: Predicate pinning was added during plan critical-review apply phase; closes the silent-divergence gap the spec's "match exactly" wording left open.

### Requirement 8: Overnight runner exports `CORTEX_REPO_ROOT`
- **Expected**: At the `LIFECYCLE_SESSION_ID` export site (`runner.py:2014`), additionally set `os.environ["CORTEX_REPO_ROOT"]`.
- **Actual**: `cortex_command/overnight/runner.py:2015-2019` sets `os.environ["CORTEX_REPO_ROOT"] = str(repo_path)` adjacent to the `LIFECYCLE_SESSION_ID` export. Sourced from runner-local `repo_path`, not propagated from `os.environ`, defending against stale operator-shell values.
- **Verdict**: PASS

### Requirement 9: SessionStart hook exports `CORTEX_REPO_ROOT` via `CLAUDE_ENV_FILE`
- **Expected**: Both `hooks/cortex-scan-lifecycle.sh` and `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` write `export CORTEX_REPO_ROOT='…'` to `CLAUDE_ENV_FILE`.
- **Actual**: Both files contain the export block, gated on `[[ -z "${CORTEX_REPO_ROOT:-}" && -e "$CWD/.git" && -n "${CLAUDE_ENV_FILE:-}" ]]`. `grep -c "export CORTEX_REPO_ROOT="` returns ≥ 1 per file. `diff hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` exit 0 confirms byte-identity post-edit.
- **Verdict**: PASS
- **Notes**: Implementation adds a user-override guard not in the original spec — only emits when `CORTEX_REPO_ROOT` is unset, preserving the user-facing override documented in `common.py:75-77`. This is a critical-review apply-phase strengthening; semantically supersedes the spec's unconditional export.

### Requirement 10: Dispatch env allowlist includes `CORTEX_REPO_ROOT`
- **Expected**: `cortex_command/pipeline/dispatch.py` env-propagation block propagates `CORTEX_REPO_ROOT` when present in the parent.
- **Actual**: `cortex_command/pipeline/dispatch.py:555-560` sets `_env["CORTEX_REPO_ROOT"] = str(worktree_path)` adjacent to the `LIFECYCLE_SESSION_ID` propagation. Acceptance grep (`grep -nE 'CORTEX_REPO_ROOT' cortex_command/pipeline/dispatch.py`) returns ≥ 1 — satisfied.
- **Verdict**: PASS
- **Notes**: Implementation deviates from the spec's "propagate from parent env" pattern in favor of pinning from the `worktree_path` argument. This was a deliberate critical-review apply-phase change to defend against stale parent-shell values misrouting telemetry into the wrong project. Spec acceptance criterion (presence in dispatch.py) is met; the implementation's semantics are stricter than spec.

### Requirement 11: Plugin distribution byte-identity preserved
- **Expected**: `diff bin/cortex-log-invocation plugins/cortex-interactive/bin/cortex-log-invocation` AND `diff bin/cortex-log-invocation plugins/cortex-core/bin/cortex-log-invocation` both exit 0.
- **Actual**: `diff bin/cortex-log-invocation plugins/cortex-core/bin/cortex-log-invocation; echo $?` outputs 0 (just verified). The `plugins/cortex-interactive/` directory does not exist on disk — that half of the spec acceptance was a spec error caught during critical-review and the plan was narrowed to `cortex-core` only. The pre-commit dual-source hook also enforces this on every shim edit (it forced T4 to co-commit with T1).
- **Verdict**: PASS
- **Notes**: Spec text references a `cortex-interactive` plugin that does not exist; plan corrected this. Only-real-plugin (`cortex-core`) check passes.

### Requirement 12: `--check-shims` gate still passes
- **Expected**: `bin/cortex-invocation-report --check-shims` exits 0.
- **Actual**: T6 verification ran the command: "Checked 19 scripts; 0 missing shim line." Exit 0.
- **Verdict**: PASS

### Requirement 13: `--self-test` round-trip still passes
- **Expected**: `bin/cortex-invocation-report --self-test` exits 0.
- **Actual**: T6 verification ran the command: "Self-test passed." Exit 0.
- **Verdict**: PASS

### Requirement 14: `just test` continues to pass
- **Expected**: `just test` exits 0.
- **Actual**: T6 verification ran the full suite: "Test suite: 6/6 passed" (test-pipeline, test-overnight, test-init, test-install, tests, tests-takeover-stress all PASS). Exit 0.
- **Verdict**: PASS

### Requirement 15: Perf-budget test asserts a hot-path wall-time ceiling
- **Expected**: `tests/test_log_invocation_perf.py` exercises the shim with `CORTEX_REPO_ROOT` and `LIFECYCLE_SESSION_ID` set, N ≥ 20 sequential invocations, asserts p50 ≤ 15ms. Skips on missing git. Unmarked.
- **Actual**: `tests/test_log_invocation_perf.py` exists with two test functions: `test_log_invocation_fast_path_budget` (N=30, asserts `p50 ≤ 15ms`, `mean ≤ 18ms`, `p95 ≤ 25ms`) and `test_log_invocation_fast_path_faster_than_slow` (N=20 each path, asserts `median(slow) - median(fast) ≥ 2ms` to catch silent fall-through). Both functions guard with `pytest.skipif(shutil.which("git") is None)`. Unmarked. T5 implement-phase pytest run: 2 passed in 0.88s.
- **Verdict**: PASS
- **Notes**: Implementation exceeds spec — multi-statistic budget plus a delta assertion that catches a failure mode (silent fall-through to slow path) the single-p50 spec assertion cannot detect. This is a critical-review apply-phase strengthening.

## Requirements Drift

**State**: none
**Findings**:
- None — the work is a perf trim of an existing observability shim. No new architectural commitments, quality attributes, or product boundaries are introduced. `CORTEX_REPO_ROOT` already existed as a documented user-facing override in `cortex_command/common.py:75-77` and as an allowlisted env in `cortex_command/overnight/scheduler/macos.py:60`; this work consumes that existing protocol. The "workflow trimming" principle in `requirements/project.md` (Philosophy of Work) and "Maintainability through simplicity" (Quality Attributes) both endorse this class of change explicitly.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `CORTEX_REPO_ROOT` matches the existing convention from `cortex_command/common.py:75-77`. Bash variable naming (`repo_root`, `session_dir`, `script_path`, `script_name`) preserved verbatim from the prior shim. Python helper retains `_resolve_repo_root` name and signature.
- **Error handling**: Fail-open contract preserved. `trap 'exit 0' EXIT` at shim top is unchanged; all five breadcrumb categories (`no_session_id`, `no_repo_root`, `session_dir_missing`, `write_denied`, `other`) emit on the matching failure path. The Python mirror wraps the env-var consult in an existing `try/except` envelope that returns `""` on any failure — matches bash semantics. `_resolve_repo_root`'s `subprocess.run` fallback retains its existing `check=False` posture.
- **Test coverage**: Plan verification steps all executed and green. Byte-equivalence test now exercises both the slow and fast paths (was: slow only). Perf test exercises the fast path with three statistical budgets plus a delta assertion against the slow path. Smoke test during T1 implement verified the fast-path JSONL schema unchanged. Full suite (`just test`) passes 6/6. Slow-path edge cases (worktree `.git`-as-file pointing to pruned gitdir; symlinked CWD; `GIT_DIR` env interaction) remain unexercised by tests — explicitly out of scope per plan Risks and spec Non-Requirements; slow-path semantics were not modified.
- **Pattern consistency**: Follows existing project conventions. Shim edits stay POSIX/bash-only (no new external deps; no Python spawn inside shim — Spec R5 preserved). Dispatch env-propagation pattern uses the same `_env["KEY"] = value` shape as the existing `LIFECYCLE_SESSION_ID` block. Hook canonical+mirror dual-source pattern matches existing `cortex-scan-lifecycle.sh` lockstep practice. Pre-commit dual-source hook caught the plugin mirror drift in T1 and forced co-commit — pattern worked as designed.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
