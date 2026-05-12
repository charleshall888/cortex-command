# Specification: trim-cortex-log-invocation-shim-cost-per-call-21ms

## Problem Statement

The `bin/cortex-log-invocation` shim adds ~19ms (per adversarial profiling; ~21ms cited in the #190 spec corrections) to every `bin/cortex-*` invocation. The dominant cost is a `git rev-parse --show-toplevel` subprocess (~6.1ms) plus unconditional `mkdir -p` (~1.5ms warm) and a `basename` fork. The shim consumes most of the per-call envelope for `cortex-lifecycle-state` and similar fast scripts that loops in overnight runner phases and lifecycle skill ceremony invoke repeatedly. Trimming the shim restores the per-call envelope these consumers were designed against, with no behavioral change to fail-open semantics, JSONL schema, or aggregator consumption.

## Phases

- **Phase 1: Shim trim with cooperating-parent env-var fast path** — edit `bin/cortex-log-invocation` to read a pre-resolved `CORTEX_REPO_ROOT` env var (with `.git`-marker validation) before falling back to `git rev-parse`; guard `mkdir -p` behind `[ -d ]`; replace `basename` with builtin parameter expansion. Have the three named producers export `CORTEX_REPO_ROOT` so cooperating-parent path is the default. Update the Python byte-equivalent mirror in lockstep.
- **Phase 2: Perf-budget regression gate** — author a perf test asserting a wall-time budget for the shim's hot path, so future drift cannot silently erase the trim.

## Requirements

1. **Shim consults `CORTEX_REPO_ROOT` before `git rev-parse`**: `bin/cortex-log-invocation` reads `${CORTEX_REPO_ROOT:-}` first. When non-empty AND `[ -d "$CORTEX_REPO_ROOT/.git" ] || [ -f "$CORTEX_REPO_ROOT/.git" ]` succeeds, that value is used as `repo_root` without invoking `git rev-parse`. Otherwise falls back to `git rev-parse --show-toplevel` as today. Acceptance: `CORTEX_REPO_ROOT=/Users/charlie.hall/Workspaces/cortex-command LIFECYCLE_SESSION_ID=test-rrt $(pwd)/bin/cortex-log-invocation /tmp/probe; grep -c '"session_id":"test-rrt"' lifecycle/sessions/test-rrt/bin-invocations.jsonl` ≥ 1 AND the same invocation strace/dtruss output (or visible timing) shows no `git` fork. **Phase**: Phase 1.

2. **Stale `CORTEX_REPO_ROOT` falls back safely**: When `CORTEX_REPO_ROOT` is set but the path contains neither a `.git` directory nor `.git` file (stale env), shim falls back to `git rev-parse --show-toplevel`. Acceptance: `CORTEX_REPO_ROOT=/tmp/nonexistent-stale-root LIFECYCLE_SESSION_ID=test-stale $(pwd)/bin/cortex-log-invocation /tmp/probe; grep -c '"session_id":"test-stale"' lifecycle/sessions/test-stale/bin-invocations.jsonl` = 1 (the write goes to the real repo root, not the stale env). **Phase**: Phase 1.

3. **`mkdir -p` deferred to first-write per session**: Shim replaces unconditional `mkdir -p "$session_dir"` with `[ -d "$session_dir" ] || mkdir -p "$session_dir" 2>/dev/null`. The subsequent `[ ! -d "$session_dir" ]` guard remains so the breadcrumb still emits `session_dir_missing` on failure. Acceptance: `grep -c '\[ -d .*session_dir.* \] || mkdir -p' bin/cortex-log-invocation` ≥ 1 AND `grep -c '\[ ! -d "\$session_dir" \]' bin/cortex-log-invocation` ≥ 1. **Phase**: Phase 1.

4. **`basename` fork replaced with parameter expansion**: Shim replaces `script_name="$(basename "$script_path" 2>/dev/null)"` with `script_name="${script_path##*/}"`. Acceptance: `grep -c 'script_name="${script_path##\*/}"' bin/cortex-log-invocation` = 1 AND `grep -c '^script_name="$(basename' bin/cortex-log-invocation` = 0. **Phase**: Phase 1.

5. **Fail-open contract preserved**: All exit paths still resolve to exit 0. The five breadcrumb categories (`no_session_id|no_repo_root|session_dir_missing|write_denied|other`) are unchanged. The `trap 'exit 0' EXIT` line at top is unchanged. Acceptance: (a) `LIFECYCLE_SESSION_ID= bin/cortex-log-invocation /tmp/x; echo $?` outputs `0` (R3); (b) with a deliberately-unwritable session dir, `bin/cortex-log-invocation /tmp/x; echo $?` outputs `0` (R4); (c) `grep -E "no_session_id\|no_repo_root\|session_dir_missing\|write_denied\|other" bin/cortex-log-invocation` matches one or more lines containing all five tokens; (d) `head -20 bin/cortex-log-invocation | grep -c "trap 'exit 0' EXIT"` = 1. **Phase**: Phase 1.

6. **JSONL byte-equivalence test continues to pass**: The bash shim's emitted line remains byte-identical (after `ts` normalization) to `cortex_command/backlog/_telemetry.py`'s emission. Field order remains `{ts, script, argv_count, session_id}`; JSON separators remain `(",", ":")`; record ends with `\n`. Acceptance: `uv run pytest cortex_command/backlog/tests/test_telemetry_byte_equivalence.py -q` exits 0. **Phase**: Phase 1.

7. **Python helper `_telemetry.py:_resolve_repo_root` updated symmetrically**: `cortex_command/backlog/_telemetry.py` consults `CORTEX_REPO_ROOT` env var with the same `.git`-marker validation before invoking `subprocess.run(["git", "rev-parse", "--show-toplevel"])`. On stale env, falls back identically to today's behavior. Acceptance: `grep -nE 'os\.environ\.get\("CORTEX_REPO_ROOT"\)' cortex_command/backlog/_telemetry.py` ≥ 1 AND `uv run pytest cortex_command/backlog/tests/ -q` exits 0. **Phase**: Phase 1.

8. **Overnight runner exports `CORTEX_REPO_ROOT`**: At the same site that sets `LIFECYCLE_SESSION_ID` (`cortex_command/overnight/runner.py:2014`), the runner additionally sets `os.environ["CORTEX_REPO_ROOT"] = <resolved-project-root>`. Acceptance: `grep -nE 'os\.environ\[.CORTEX_REPO_ROOT.\] = ' cortex_command/overnight/runner.py` ≥ 1 in the same function context as `LIFECYCLE_SESSION_ID`. **Phase**: Phase 1.

9. **SessionStart hook exports `CORTEX_REPO_ROOT` via `CLAUDE_ENV_FILE`**: Both `hooks/cortex-scan-lifecycle.sh` (canonical) and `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` (mirror) write an additional `export CORTEX_REPO_ROOT='…'` line to `CLAUDE_ENV_FILE` alongside `LIFECYCLE_SESSION_ID`. The exported value is the result of resolving the repo root at hook-execution time. Acceptance: `grep -c "export CORTEX_REPO_ROOT=" hooks/cortex-scan-lifecycle.sh plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` reports ≥ 1 match per file. **Phase**: Phase 1.

10. **Dispatch env allowlist includes `CORTEX_REPO_ROOT`**: `cortex_command/pipeline/dispatch.py` (the env-propagation block around line 553-554) propagates `CORTEX_REPO_ROOT` into the dispatched subprocess env when present in the parent. Acceptance: `grep -nE 'CORTEX_REPO_ROOT' cortex_command/pipeline/dispatch.py` ≥ 1 in the env-propagation block. **Phase**: Phase 1.

11. **Plugin distribution byte-identity preserved**: After `just build-plugin`, the regenerated `plugins/cortex-interactive/bin/cortex-log-invocation` (and any other regenerated plugin mirrors) match `bin/cortex-log-invocation` byte-for-byte. Acceptance: `diff bin/cortex-log-invocation plugins/cortex-interactive/bin/cortex-log-invocation; echo $?` = 0 AND `diff bin/cortex-log-invocation plugins/cortex-core/bin/cortex-log-invocation; echo $?` = 0 (R15). **Phase**: Phase 1.

12. **`--check-shims` gate still passes**: The literal string `cortex-log-invocation` remains in the first 50 lines of every `bin/cortex-*` after this work. Acceptance: `bin/cortex-invocation-report --check-shims; echo $?` = 0 (R11). **Phase**: Phase 1.

13. **`--self-test` round-trip still passes**: The shim continues to satisfy the aggregator's probe-write-and-read-back round-trip. Acceptance: `bin/cortex-invocation-report --self-test; echo $?` = 0 (R13). **Phase**: Phase 1.

14. **`just test` continues to pass**: The full test suite passes after the changes land. Acceptance: `just test; echo $?` = 0 (R18). **Phase**: Phase 1.

15. **Perf-budget test asserts a hot-path wall-time ceiling**: A new test file `tests/test_log_invocation_perf.py` exercises the shim with `CORTEX_REPO_ROOT` and `LIFECYCLE_SESSION_ID` both set (the cooperating-parent fast path), runs N ≥ 20 invocations sequentially, measures wall-time per call, and asserts p50 ≤ 15ms. The test uses Python's `time.perf_counter` around `subprocess.run`, skips with `pytest.skip("git not on PATH")` if git is missing, and is unmarked (runs by default in `just test`). Acceptance: `uv run pytest tests/test_log_invocation_perf.py -q; echo $?` = 0 AND `grep -c 'def test_' tests/test_log_invocation_perf.py` ≥ 1. **Phase**: Phase 2.

## Non-Requirements

- Replacing `git rev-parse --show-toplevel` with a pure-bash walk-up loop scanning for `.git`. Rejected per research adversarial review — diverges from `git rev-parse` semantics on worktrees (stale `.git` files pointing to pruned gitdirs), symlinked CWD, `GIT_DIR` pollution, CWD inside `.git/`. Would fragment JSONL writes across orphan paths while still passing the byte-equivalence test.
- Replacing `date -u +%Y-%m-%dT%H:%M:%SZ` with the bash builtin `printf '%(...)T'`. macOS system bash 3.2 raises a hard format error; bash 4.2+ requires an explicit `TZ=UTC` export to match `date -u` output bytes. The ~3.6ms savings is not worth the byte-equivalence-divergence hazard without a value-equivalence test, and the existing byte-equivalence test normalizes `ts` so the regression would be invisible.
- Optimizing the failure-path `_log_breadcrumb` `date -u` call. The breadcrumb runs only when `LIFECYCLE_SESSION_ID` is unset, no repo root resolves, the session dir is unwritable, or the write fails — none of these is the hot path the ticket cares about.
- A file-based repo-root cookie cache under `~/.cache/cortex/repo-roots/`. The cache key is fragile (per-CWD entries) and adds new failure modes for marginal savings beyond env-var cooperation.
- A persistent shim daemon (RAM buffer + flusher, unix-socket listener, or otherwise). Contradicts the shim's one-shot fail-open envelope.
- Per-script tags or expected-frequency taxonomy on the shim output. Out of scope per archived spec Non-Requirements.
- Log rotation, argv-value capture, PreToolUse hook wiring. Out of scope per archived spec Non-Requirements.
- Modifying any caller `bin/cortex-*` scripts. The shim-invocation line in callers is untouched; `--check-shims` semantics are unchanged.

## Edge Cases

- **`CORTEX_REPO_ROOT` set but stale (path no longer has a `.git` marker)**: shim validates via `[ -d "$CORTEX_REPO_ROOT/.git" ] || [ -f "$CORTEX_REPO_ROOT/.git" ]`; on fail, falls back to `git rev-parse --show-toplevel` exactly as if the env var were unset.
- **`CORTEX_REPO_ROOT` unset (no cooperating parent)**: shim invokes `git rev-parse --show-toplevel` exactly as today. No regression vs. baseline behavior on this path; ~6ms still paid.
- **Both `CORTEX_REPO_ROOT` set AND `git rev-parse` available**: env var wins; git is not forked. The validated env value is used.
- **Concurrent shim invocations from parallel overnight worktrees**: Two shims may both pass `[ -d "$session_dir" ]` false simultaneously and both call `mkdir -p`; `mkdir -p` is idempotent on a directory-creation race so the second call is a no-op. Subsequent appends remain atomic under `O_APPEND` for ≤ 4 KB records (spec invariant).
- **Symlinked CWD via cooperating parent**: When the runner / SessionStart hook resolves the repo root, they should pass the canonical (resolved-symlink) path so the shim and `_telemetry.py` agree on path identity. Implementations should use `git rev-parse --show-toplevel` at the producer site (which canonicalizes), not raw `os.getcwd()`.
- **Stale shim-side `LIFECYCLE_SESSION_ID` plus fresh `CORTEX_REPO_ROOT`**: shim writes to `lifecycle/sessions/<stale-id>/bin-invocations.jsonl` under the fresh repo root; this matches today's behavior (env-var staleness in the session id is not introduced by this work).
- **`git rev-parse` fails (CWD inside `.git/`, bare repo, no repo)**: shim writes `no_repo_root` breadcrumb and exits 0 — unchanged from today.
- **`CORTEX_REPO_ROOT` contains whitespace or special chars**: the `[ -d "$CORTEX_REPO_ROOT/.git" ]` test is shell-quoted; whitespace handling matches today's `repo_root` variable usage on the slow path.
- **Plugin regeneration race after shim edit**: pre-commit dual-source hook regenerates `plugins/cortex-core/bin/`; manual `just build-plugin` regenerates `plugins/cortex-interactive/bin/`. The byte-identity diff in Requirement 11 runs after both regenerators complete.
- **Perf test runs on a noisy CI/dev machine**: the p50 ≤ 15ms budget is generous (vs. ~9ms expected on the cooperating-parent path) to absorb machine variance. If the test still flakes, the remediation is to raise the budget with a comment citing the noisy-machine cause, not to delete the test.

## Changes to Existing Behavior

- **MODIFIED**: `bin/cortex-log-invocation` line ~32 (`repo_root="$(git rev-parse ...)"`) — now reads `CORTEX_REPO_ROOT` first with `.git`-marker validation, falls back to `git rev-parse` on absent/invalid env. Same path semantics; same fail-open behavior.
- **MODIFIED**: `bin/cortex-log-invocation` line ~39 (`mkdir -p "$session_dir" 2>/dev/null`) — now guarded by `[ -d "$session_dir" ] || …`; downstream `[ ! -d "$session_dir" ]` check is unchanged.
- **MODIFIED**: `bin/cortex-log-invocation` line ~46 (`script_name="$(basename "$script_path" 2>/dev/null)"`) — now `script_name="${script_path##*/}"`.
- **MODIFIED**: `cortex_command/backlog/_telemetry.py:_resolve_repo_root` — consults `CORTEX_REPO_ROOT` first with `.git`-marker validation (same semantics as the bash shim), falls back to `subprocess.run(["git", "rev-parse", "--show-toplevel"])` on absent/invalid env.
- **MODIFIED**: `cortex_command/overnight/runner.py` near line 2014 — additionally sets `os.environ["CORTEX_REPO_ROOT"]` from the resolved project root, sibling to the `LIFECYCLE_SESSION_ID` export.
- **MODIFIED**: `hooks/cortex-scan-lifecycle.sh` (canonical) and `plugins/cortex-overnight/hooks/cortex-scan-lifecycle.sh` (mirror) — write an additional `export CORTEX_REPO_ROOT='<resolved-root>'` line to `CLAUDE_ENV_FILE`, sibling to the existing `LIFECYCLE_SESSION_ID` export.
- **MODIFIED**: `cortex_command/pipeline/dispatch.py` env-propagation block (near line 553-554) — additionally propagates `CORTEX_REPO_ROOT` when present in the parent.
- **ADDED**: `tests/test_log_invocation_perf.py` — perf-budget test for the shim's cooperating-parent fast path; runs in default `just test`.

## Technical Constraints

- **Spec R5 (archived spec)**: shim must run in `< 0.05s` per invocation with bash + POSIX utilities only — no `jq`, no Python interpreter spawn inside the shim.
- **Spec R2 (archived spec) + `_telemetry.py` byte-equivalence test (`cortex_command/backlog/tests/test_telemetry_byte_equivalence.py:118-121`)**: JSONL line schema is frozen — keys `{ts, script, argv_count, session_id}` in that order; JSON separators `(",", ":")`; ISO 8601 UTC `ts`; trailing `\n`; record ≤ 4 KB.
- **Spec R3/R4 (archived spec)**: fail-open contract preserved — shim exits 0 unconditionally; breadcrumb-category set `{no_session_id, no_repo_root, session_dir_missing, write_denied, other}` is closed.
- **Spec R6/R11/R14 (archived spec)**: `--check-shims` substring grep — literal `cortex-log-invocation` must remain in the first 50 lines of every `bin/cortex-*`. Not affected by this work (no caller edits).
- **Spec R13 (archived spec)**: `--self-test` round-trip — shim must continue to resolve the log path, accept a probe write, and read it back.
- **Spec R15 (archived spec)**: plugin distribution byte-identity — `diff bin/cortex-log-invocation plugins/<plugin>/bin/cortex-log-invocation` exits 0 after `just build-plugin`. Verified post-build by Requirement 11.
- **Existing `CORTEX_REPO_ROOT` convention (`cortex_command/common.py:49-82`)**: the env var is read verbatim with no `.git`-marker validation in `common.py`. The new shim guard (`[ -d "$CORTEX_REPO_ROOT/.git" ] || [ -f …]`) is stricter than `common.py`'s current behavior. The Python mirror update in Requirement 7 mirrors the shim's stricter guard for consistency at the telemetry write sites — `common.py`'s consumers (which need a project root for non-telemetry purposes) are out of scope for this ticket.
- **Dual-source enforcement**: `bin/` is canonical; `plugins/cortex-core/bin/` is auto-regenerated by the pre-commit dual-source hook. Edit `bin/cortex-log-invocation` only; the plugin mirror regenerates automatically.
- **MUST-escalation policy (CLAUDE.md)**: this spec uses soft positive-routing phrasing only — no new MUST/REQUIRED/CRITICAL escalations introduced.

## Open Decisions

(None — all four research-deferred questions were resolved during Spec §2 interview: `_telemetry.py` updates in lockstep [Req 7]; perf-budget test authored inline [Req 15]; all three producers touched [Reqs 8, 9, 10]; breadcrumb-path `date -u` left alone [Non-Requirement].)
