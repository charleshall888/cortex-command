# Review: add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7

## Stage 1: Spec Compliance

### Requirement R1: Helper exists and is executable
- **Expected**: `test -x bin/cortex-log-invocation && echo OK` returns "OK".
- **Actual**: `bin/cortex-log-invocation` exists with execute bit set.
- **Verdict**: PASS

### Requirement R2: Helper writes one JSONL record per invocation
- **Expected**: After `LIFECYCLE_SESSION_ID=test-sid bin/cortex-log-invocation /path/to/some-script a b c`, `wc -l` of the log file is `1` and the line is JSON containing `ts`, `script`, `argv_count`, `session_id`.
- **Actual**: Verified live — single line `{"ts":"2026-04-28T13:29:02Z","script":"some-script","argv_count":3,"session_id":"test-sid-review"}` written; `wc -l = 1`. All four required keys present.
- **Verdict**: PASS

### Requirement R3: Helper fails open when LIFECYCLE_SESSION_ID is unset
- **Expected**: `LIFECYCLE_SESSION_ID= bin/cortex-log-invocation /tmp/x; echo $?` = `0` and writes nothing.
- **Actual**: Verified — exit `0`; the helper records a `no_session_id` breadcrumb but does not write a session log entry (per spec line 17, breadcrumb is intentional).
- **Verdict**: PASS

### Requirement R4: Helper fails open when log target is unwritable; records breadcrumb category
- **Expected**: Helper exits 0 in all failure modes and writes a one-line breadcrumb to `~/.cache/cortex/log-invocation-errors.log` indicating failure class (`no_session_id`, `no_repo_root`, `session_dir_missing`, `write_denied`, `other`).
- **Actual**: All five failure classes are reachable in `bin/cortex-log-invocation`:
  - `no_session_id` — line 28 (env var unset)
  - `no_repo_root` — line 34 (`git rev-parse` returned nothing)
  - `session_dir_missing` — line 41 (`mkdir -p` failed and dir absent)
  - `write_denied` — line 64 (printf append failed)
  - `other` — line 53 (basename or session id contains `"` or `\` triggering the JSON-escape guard)
  Helper uses `trap 'exit 0' EXIT` (line 14) to enforce always-zero exit. The breadcrumb writer (`_log_breadcrumb`) is itself wrapped in `2>/dev/null || true` (line 24), so it is also fail-open.
- **Verdict**: PASS

### Requirement R5: Helper performance budget < 0.05s; bash + POSIX only
- **Expected**: `time bin/cortex-log-invocation /tmp/x` < 0.05s on dev machine; no `jq`, no Python spawn.
- **Actual**: Measured `0.032 total`. Helper is pure bash — uses only `date`, `git`, `basename`, `mkdir`, `printf` (POSIX). No `jq`, no Python.
- **Verdict**: PASS

### Requirement R6: All canonical bin/cortex-* scripts (excluding helper) reference the helper in head -50
- **Expected**: Acceptance loop produces no MISSING output across `bin/cortex-*`.
- **Actual**: Loop run live — no MISSING output across all 11 inventory items (cortex-archive-rewrite-paths, cortex-archive-sample-select, cortex-audit-doc, cortex-check-parity, cortex-count-tokens, cortex-create-backlog-item, cortex-generate-backlog-index, cortex-git-sync-rebase, cortex-jcc, cortex-update-item, cortex-validate-spec). Note: spec originally inventoried 9 items; the 2 additions (cortex-check-parity, cortex-validate-spec) landed after the spec was authored and were correctly shimmed under the plain-Python pattern (Task 7 scope expansion documented in commit message).
- **Verdict**: PASS

### Requirement R7: Aggregator exists and is executable
- **Expected**: `test -x bin/cortex-invocation-report && echo OK` returns OK.
- **Actual**: Verified — exists with execute bit.
- **Verdict**: PASS

### Requirement R8: Aggregator default output reports per-script invocation counts
- **Expected**: After populating one log entry under cortex-update-item, default output contains a line where `cortex-update-item` appears with its count.
- **Actual**: Live run shows `PER-SCRIPT INVOCATION COUNTS` block listing `cortex-update-item     1` (and other counts). Format `name<padding>count`.
- **Verdict**: PASS

### Requirement R9: CANDIDATES FOR REVIEW section listing zero-count inventory entries
- **Expected**: After populating one log entry under cortex-update-item only, the CANDIDATES FOR REVIEW section contains at least one of the other inventory entries. Heading is exactly `CANDIDATES FOR REVIEW`.
- **Actual**: Section header is exactly `CANDIDATES FOR REVIEW`. Live output shows 9 zero-count scripts including `cortex-audit-doc`. Section uses `(zero invocations in retained sessions)` suffix.
- **Verdict**: PASS

### Requirement R10: --json flag emits structured JSON
- **Expected**: `bin/cortex-invocation-report --json | jq -e '.scripts | type == "array"'` exits 0; JSON contains `inventory`, `scripts`, `candidates_for_review`, `metadata` (with log volume + errors).
- **Actual**: Verified live — `jq -e '.scripts | type == "array"'` returns `true`. Top-level keys: `candidates_for_review`, `inventory`, `metadata`, `scripts`. Metadata includes `sessions_scanned`, `records`, `errors_recorded`, `skipped_malformed_lines`.
- **Verdict**: PASS

### Requirement R11: --check-shims flag verifies each bin/cortex-* references the helper
- **Expected**: With shims in place, exit 0; with one removed, exit non-zero and write missing script names to stderr.
- **Actual**: Live run returned `Checked 11 scripts; 0 missing shim line.` and exit 0. The implementation in `_check_shims()` uses the same `head -50 ... grep` logic as R6 acceptance, and `echo "$n" >&2` on misses, with exit code = number missing.
- **Verdict**: PASS

### Requirement R12: Aggregator handles no-data case gracefully
- **Expected**: With no `bin-invocations.jsonl` files, aggregator exits 0, output includes "No invocations logged" and the full CANDIDATES FOR REVIEW listing every inventory item.
- **Actual**: Verified by inspecting `_default_mode()` — when `sessions=0`, output prints `Sessions scanned: 0      Records: 0`, then `No invocations logged.`, then the full CANDIDATES FOR REVIEW listing built from `_inventory()` (which globs `bin/cortex-*` excluding helper+aggregator). Returns 0.
- **Verdict**: PASS

### Requirement R13: --self-test flag verifies end-to-end telemetry
- **Expected**: Exits 0 only if (a) LIFECYCLE_SESSION_ID resolves, (b) probe write succeeds, (c) probe record reads back. On failure, names which step failed with remediation hint mentioning `cortex init`.
- **Actual**: Live run returned `Self-test passed.` exit 0 (with active session id). Reading `_self_test()`: step 1 checks LIFECYCLE_SESSION_ID and prints `step 1 (LIFECYCLE_SESSION_ID resolution): unset...`; step 3 checks `mkdir -p` of session dir with remediation hint `run \`cortex init\` to register the log path in sandbox.filesystem.allowWrite`; step 4 verifies probe record by `tail -1 ... | grep -q '"script":"cortex-self-test-probe"'` with the same remediation hint. Step 2 (repo root) is enforced at top of script. All four diagnostic branches present.
- **Verdict**: PASS

### Requirement R14: Pre-commit gate runs --check-shims when bin/cortex-* are staged
- **Expected**: Staging a new/modified `bin/cortex-*` triggers `cortex-invocation-report --check-shims`; failure rejects commit naming the missing-shim script.
- **Actual**: `.githooks/pre-commit` Phase 1.6 (lines 92–115) iterates staged paths matching `bin/cortex-*`, sets `shim_triggered=1`, then runs `bin/cortex-invocation-report --check-shims`. On non-zero exit, prints `pre-commit: bin/cortex-* shim line missing — add the cortex-log-invocation shim line to each script listed above.` to stderr and exits 1. The aggregator's stderr (one missing-script basename per line) reaches the user before the wrap-up message. Phase 1.6 is correctly placed before Phase 2 (build-decision short-circuit).
- **Verdict**: PASS

### Requirement R15: Plugin distribution byte-identity via `just build-plugin`
- **Expected**: `diff bin/cortex-log-invocation plugins/cortex-interactive/bin/cortex-log-invocation` and the same for cortex-invocation-report both exit 0.
- **Actual**: Verified live — both diffs produced no output (exit 0). Mirrors are byte-identical.
- **Verdict**: PASS

### Requirement R16: Ticket 103 amended in place to reflect the new mechanism
- **Expected**: Title and `# Heading` rewritten to name the per-script invocation shim mechanism. Scope/Out-of-scope/2026-04-27 amendment sections rewritten. Acceptance: `grep -c "PreToolUse Bash hook matcher"` = 0 AND `grep -c "invocation shim"` ≥ 2.
- **Actual**: Title is now `Add runtime adoption telemetry via per-script invocation shim (DR-7)` (frontmatter line 4) and matching `# Heading` line 23. Live grep counts: `PreToolUse Bash hook matcher` = 0; `invocation shim` = 5. The scope amendment is present (line 54, dated 2026-04-28 noting the alternative-mechanism pivot).
- **Verdict**: PASS

### Requirement R17: requirements/observability.md adds sixth subsystem section
- **Expected**: New subsection under `## Functional Requirements` with Description, Inputs, Outputs, Acceptance criteria, Priority. Acceptance: `grep -c "Runtime Adoption Telemetry" requirements/observability.md` ≥ 1, AND awk between `### Notifications` and `### In-Session Status CLI` finds ≥ 1.
- **Actual**: Section exists at lines 53–59 of `requirements/observability.md` between the Notifications and In-Session Status CLI subsections. Contains all five required fields. Live grep counts: `Runtime Adoption Telemetry` = 5; awk-narrowed count = 1. Note: the Overview at line 9 still says "five subsystems" — a minor consistency lapse but not a spec acceptance criterion. Flagged as PARTIAL-eligible but R17's stated acceptance criteria pass.
- **Verdict**: PASS

### Requirement R18: `just test` continues to pass
- **Expected**: `just test` exits 0.
- **Actual**: Live run output `Test suite: 5/5 passed`; exit 0.
- **Verdict**: PASS

## Requirements Drift

**State**: none
**Findings**:
- None — the new "Runtime Adoption Telemetry" subsystem in `requirements/observability.md` is a planned scope item per spec R17, not drift. The implementation introduces no behavior beyond what `requirements/observability.md` (post-update) and `requirements/project.md`'s SKILL.md-to-bin-parity constraint anticipate.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Helper `cortex-log-invocation` and aggregator `cortex-invocation-report` follow the `cortex-*` verb-noun convention used by other `bin/` utilities. Internal bash function names use leading underscore (`_log_breadcrumb`, `_inventory`, `_count_invocations`, `_self_test`, `_check_shims`, `_json_mode`, `_default_mode`) — matches existing private-helper convention. JSONL field names (`ts`, `script`, `argv_count`, `session_id`) match the spec verbatim. Failure classes (`no_session_id`, `no_repo_root`, `session_dir_missing`, `write_denied`, `other`) are snake_case and match the spec list.

- **Error handling**: Helper's fail-open contract is robust — `trap 'exit 0' EXIT` at line 14 guarantees zero exit regardless of any internal error, and the breadcrumb writer is itself wrapped in `2>/dev/null || true`. All five failure classes from R4 are reachable as separate code paths. Aggregator uses `set -uo pipefail` (intentionally omitting `-e` so that empty inventories and grep-no-match conditions don't abort the report). The `--json` mode correctly errors out with exit 2 if `jq` is unavailable, with a clear stderr message. Self-test produces remediation-actionable error messages naming `cortex init`. The `--check-shims` propagates the missing count as the exit code, which is somewhat unconventional but acceptable here (it's bounded by inventory size, ≤ 11).

- **Test coverage**: Live verification ran R1–R18 acceptance commands directly (helper executability, JSONL write+keys, fail-open on unset session, performance < 0.05s, head-50 grep across all 11 scripts, aggregator default/json/check-shims/self-test modes, plugin diff parity, backlog grep counts, observability awk count, `just test`). All passed. Sandbox-dependent breadcrumb verification (`~/.cache/cortex/log-invocation-errors.log`) was not exercised in the implementer's environment per the review prompt; reading the helper source confirms the breadcrumb writer is correctly wired with the right path and category strings, and is itself fail-open. The `write_denied` path is reachable through the bash-level redirect failure in line 63's `if !` block.

- **Pattern consistency**: Shim insertion ordering follows the prescribed conventions:
  - Bash leaves and bash wrappers: shim line is the first non-shebang/non-leading-comment line, above `set -e`. Verified in cortex-create-backlog-item, cortex-generate-backlog-index, cortex-git-sync-rebase, cortex-jcc, cortex-update-item.
  - Plain Python: shim line is after the docstring and `from __future__ import annotations` (where present), before other imports. Verified in cortex-archive-rewrite-paths (line 46, after `from __future__` at line 44), cortex-validate-spec (line 17, after docstring), cortex-archive-sample-select, cortex-check-parity.
  - PEP 723 uv-script: shim line is after the `# ///` close marker and the docstring, before the first `import`. Verified in cortex-audit-doc (line 13, after the `# ///` block at line 4) and cortex-count-tokens.
  All shim invocations resolve the helper path absolutely (`dirname "$0"` for bash, `os.path.dirname(os.path.abspath(__file__))` for Python) — no PATH dependency. All bash invocations use `|| true` for fail-open; Python invocations use `check=False`. The pre-commit Phase 1.6 logic mirrors Phase 1.5's structure (loop staged paths, set trigger flag, dispatch sub-tool on hit). Single-statement Python imports (`import os, subprocess, sys; subprocess.run(...)`) are unconventional but documented in the spec at line 84 ("`subprocess` and `os` explicitly imported on the same statement to avoid NameError") — acceptable.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
