# Plan: add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7

## Overview

Implement runtime adoption telemetry as a per-script invocation shim (Alt 5 + DR-5). Two new `bin/cortex-*` scripts are added (a fail-open helper that appends one JSONL record per invocation, and an aggregator CLI with four output modes). Each existing `bin/cortex-*` script gains a single shim-invocation line near the top, dispatched at three different code shapes (bash, plain Python, PEP 723 uv-script). A pre-commit gate enforces the shim line on every staged `bin/cortex-*`. Plugin distribution and dual-source enforcement are inherited automatically from the existing `bin/cortex-` glob in `justfile:481` and the `^bin/cortex-` regex in `.githooks/pre-commit:71` — no `HOOKS=`, regex, or `hooks.json` edits are required.

## Merge Atomicity

**All eleven tasks must land in a single commit or PR** — not as a sequence of independent commits. Rationale: Task 9 wires a pre-commit gate that fires on any staged `bin/cortex-*` path; if Task 9 lands before Tasks 1/6/7/8 are all committed, the gate blocks every subsequent `bin/cortex-*` commit until the inventory is fully shimmed. The `Depends on:` task fields express logical ordering for in-tree work, not commit-graph constraints — atomic merge prevents the bootstrap-deadlock failure mode.

## Sandbox AllowWrite Assumption

Plan verifications write to `lifecycle/sessions/plan-*-sid/bin-invocations.jsonl`. The sandbox `allowWrite` registration produced by `cortex init` (the entry `<repo>/lifecycle/sessions/` with trailing slash) uses **path-prefix matching** — confirmed by direct inspection of `~/.claude/settings.local.json` and by the existing repo precedent that arbitrary `lifecycle/sessions/<session-id>/` writes are routinely produced by the lifecycle skill. Any subdirectory of the registered path is implicitly allowed. This assumption is load-bearing for every Task 1/2/3/5/6 verification command.

## Tasks

### Task 1: Create `bin/cortex-log-invocation` shim helper
- **Files**: `bin/cortex-log-invocation`
- **What**: New executable bash helper that resolves the per-session JSONL log path under `lifecycle/sessions/<LIFECYCLE_SESSION_ID>/bin-invocations.jsonl` (relative to `git rev-parse --show-toplevel`) and appends one ≤4KB JSON record per invocation. Fails open silently on every error class.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Path: `bin/cortex-log-invocation` (executable, `#!/usr/bin/env bash`).
  - Mirror leaf-bash precedent at `bin/cortex-git-sync-rebase` for shebang and style.
  - Output schema (R5/Technical Constraints): one JSON object per line, ≤4KB, fields `{"ts": <ISO 8601 UTC>, "script": <basename of $1>, "argv_count": <int>, "session_id": <string>}`. **Argv values are NEVER recorded** — only `argv_count`. Use `date -u +%Y-%m-%dT%H:%M:%SZ` for `ts`. Compute `argv_count` as `$# - 1` (caller passes `$0` first, then `$@`).
  - Fail-open contract (R3, R4): exit 0 unconditionally; never propagate errors to caller. Any failure path writes a one-line entry to `~/.cache/cortex/log-invocation-errors.log` (`mkdir -p` the parent; redirect that mkdir's stderr; the breadcrumb write itself is `>> ... 2>/dev/null || true`).
  - Failure classes to record (each as a single category token in the breadcrumb line, plus ISO timestamp and resolved-path snippet): `no_session_id`, `no_repo_root`, `session_dir_missing`, `write_denied`, `other`.
  - Performance budget (R5): pure bash + POSIX utilities. Forbidden: `jq`, `python3`, any subshell-heavy idioms. Allowed: `date`, `basename`, `git rev-parse`, `printf`, `mkdir`, `>>` redirection. JSON construction via a single `printf '{"ts":"%s","script":"%s","argv_count":%d,"session_id":"%s"}\n' ...` line.
  - JSON-string escaping: `script` is a basename and `session_id` is a UUID-shaped value — neither requires escaping in practice. Document the assumption in a 1-line comment; if either contains `"` or `\`, emit no record (treat as failure class `other`).
  - Caller pattern (informational; established by Tasks 6/7/8): bash callers pass `"$0" "$@"`; Python callers pass `sys.argv[0], *sys.argv[1:]`. Helper uses positional `$1` as the script-path source for `basename`.
  - **No production-side fault-injection hooks**: do NOT add a `LOG_INVOCATION_FORCE_FAIL` env-var-check or other test scaffolding to the helper. Fault simulation for R4 testing is done via a chmod-write-denied probe directory at verification time (see verification 4 below) — production code stays free of testability seams.
- **Verification**:
  1. `test -x bin/cortex-log-invocation && echo OK` — pass if output is `OK` (R1).
  2. `LIFECYCLE_SESSION_ID=plan-test-sid bin/cortex-log-invocation /tmp/fake-script a b c; wc -l < lifecycle/sessions/plan-test-sid/bin-invocations.jsonl` — pass if output is `1`. Then `python3 -c 'import json,sys; d=json.loads(open("lifecycle/sessions/plan-test-sid/bin-invocations.jsonl").readline()); assert set(d.keys())>={"ts","script","argv_count","session_id"}, d; print("OK")'` — pass if output is `OK` (R2).
  3. `LIFECYCLE_SESSION_ID= bin/cortex-log-invocation /tmp/x; echo $?` — pass if output is `0` and no log file is created in a fresh `lifecycle/sessions/` (R3).
  4. **Real write-denial fault injection** for R4: `mkdir -p lifecycle/sessions/plan-deny-sid && chmod 000 lifecycle/sessions/plan-deny-sid && LIFECYCLE_SESSION_ID=plan-deny-sid bin/cortex-log-invocation /tmp/x; rc=$?; chmod 755 lifecycle/sessions/plan-deny-sid; rm -rf lifecycle/sessions/plan-deny-sid; echo $rc` — pass if final output is `0` (helper fails open silently). Then `[ -f ~/.cache/cortex/log-invocation-errors.log ] && grep -q write_denied ~/.cache/cortex/log-invocation-errors.log; echo $?` — pass if final output is `0` (breadcrumb recorded the failure class).
  5. `time (for i in $(seq 1 10); do bin/cortex-log-invocation /tmp/x; done) 2>&1 | awk '/real/{print $2}'` — pass if real time < 0.5s for 10 invocations (R5; budget is <50ms each, leaving slack).
  6. **Cleanup**: `rm -rf lifecycle/sessions/plan-test-sid` after verifications 2 and 5 complete (avoid test-session-dir leakage).
- **Status**: [ ] pending

### Task 2: Create `bin/cortex-invocation-report` aggregator (default mode)
- **Files**: `bin/cortex-invocation-report`
- **What**: New executable bash aggregator that globs `bin/cortex-*` from repo root, reads every `lifecycle/sessions/*/bin-invocations.jsonl`, counts invocations per basename, and emits a human-readable report including per-script counts and a `CANDIDATES FOR REVIEW` section listing inventory items with zero counts.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Path: `bin/cortex-invocation-report` (executable, `#!/usr/bin/env bash`).
  - Mirror bash + jq precedent at `bin/overnight-status`. `jq` is OPTIONAL (only required by `--json` mode in Task 3); the default mode must work without `jq`.
  - Inventory source: `for f in "$(git rev-parse --show-toplevel)"/bin/cortex-*; do basename "$f"; done`. Exclude `cortex-log-invocation` and `cortex-invocation-report` themselves. Exclude paths that are not regular files (some users may have stale symlinks).
  - Counting: `awk` over each `bin-invocations.jsonl`. The match needle MUST anchor the closing quote — use the literal four-character pattern `"script":"<name>"` including the trailing `"` so that `cortex-archive` cannot substring-match `cortex-archive-rewrite-paths` or `cortex-archive-sample-select`. Awk-based parsing avoids the `jq` dependency.
  - Filter scope: the per-script counter only increments for script names present in the inventory. Records whose `script` field is not in inventory (e.g., `cortex-self-test-probe` from Task 5's `--self-test`) are skipped silently — they do NOT count toward `Records:` or per-script tallies. The default report's `Records:` shows the count of inventory-matched records only.
  - Glob-handling guard: enable `shopt -s nullglob` once at script entry so the `lifecycle/sessions/*/bin-invocations.jsonl` expansion returns empty (rather than the literal pattern) when no logs exist. This makes the no-data path (verification 4) deterministic regardless of bash version or how the implementer iterates.
  - Recent-window semantics: v1 default window is "all retained sessions" — there is no time-based filter. Spec R9 says "in the recent window"; the recent window is implicitly defined by lifecycle session retention (whatever sessions still exist on disk). Document this in a `--help` line.
  - No-data path (R12): if no `lifecycle/sessions/*/bin-invocations.jsonl` files are present, emit `No invocations logged.` then the full `CANDIDATES FOR REVIEW` section listing every inventory item, then exit 0.
  - Output structure (default mode, plain text):
    ```
    Runtime Adoption Telemetry — bin/cortex-* invocations
    Sessions scanned: <N>      Records: <M>      Errors recorded: <K>

    PER-SCRIPT INVOCATION COUNTS
      <script>           <count>
      ...

    CANDIDATES FOR REVIEW
      <script>           (zero invocations in retained sessions)
      ...
    ```
  - `Errors recorded` reads `~/.cache/cortex/log-invocation-errors.log` line count if the file exists, else `0`.
  - Argument dispatch: a single `case "${1:-}" in --json) ... ;; --check-shims) ... ;; --self-test) ... ;; --help|-h) ... ;; *) default ;; esac`. Tasks 3, 4, 5 fill in the non-default cases.
- **Verification**:
  1. `test -x bin/cortex-invocation-report && echo OK` — pass if output is `OK` (R7).
  2. From a clean state (`rm -rf lifecycle/sessions/plan-*-sid`), populate one record: `LIFECYCLE_SESSION_ID=plan-r8-sid bin/cortex-log-invocation bin/cortex-update-item`. Then `bin/cortex-invocation-report | grep -E '^[[:space:]]*cortex-update-item[[:space:]]+1[[:space:]]*$'; echo $?` — pass if final output is `0` (end-of-line anchor `$` prevents `\s+1` from matching `\s+11` or `\s+100`) (R8).
  3. With the same single record from (2): `bin/cortex-invocation-report | awk '/CANDIDATES FOR REVIEW/{found=1; next} found && /cortex-audit-doc/{count++} END {exit !(count>=1)}'` — pass if exit is 0 (R9).
  4. From a fully clean state (no `lifecycle/sessions/*/bin-invocations.jsonl`): `rm -rf lifecycle/sessions/plan-*-sid && bin/cortex-invocation-report; echo $?` — pass if output ends with `0` and report contains `No invocations logged` (R12).
  5. **Cleanup**: `rm -rf lifecycle/sessions/plan-r8-sid` after verifications 2 and 3 complete.
- **Status**: [ ] pending

### Task 3: Add `--json` flag to aggregator
- **Files**: `bin/cortex-invocation-report`
- **What**: Extend the aggregator's `--json` branch to emit a single structured JSON document with `inventory`, `scripts`, `candidates_for_review`, and `metadata` fields. Output goes to stdout; exit 0 on success.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Schema:
    ```json
    {
      "metadata": {"sessions_scanned": <int>, "records": <int>, "errors_recorded": <int>, "skipped_malformed_lines": <int>},
      "inventory": ["cortex-archive-rewrite-paths", "..."],
      "scripts": [{"script": "<name>", "count": <int>}],
      "candidates_for_review": ["<name>", "..."]
    }
    ```
  - Implementation: `jq -n --argjson scripts '...' --argjson inventory '...' '{metadata: ..., inventory: $inventory, scripts: $scripts, candidates_for_review: ...}'`. `jq` IS required for `--json` mode; if `jq` is missing, exit non-zero with stderr message `--json mode requires jq` (a documented dependency hint, not a silent failure).
  - `errors_recorded` is computed with an explicit existence guard: `if [ -f ~/.cache/cortex/log-invocation-errors.log ]; then errors_recorded=$(wc -l < ~/.cache/cortex/log-invocation-errors.log | tr -d ' '); else errors_recorded=0; fi`. The bash redirection `wc -l < missing-file` errors at shell level (no `wc` invocation; empty substitution); the explicit `[ -f ]` guard is what makes "or 0 if absent" actually behave as documented and prevents `jq --argjson` from receiving an empty string.
  - `skipped_malformed_lines` is a population-level counter incremented inside the awk parser whenever a line cannot be matched to the expected JSONL pattern. Aggregation is per-file: each awk invocation emits its file-local count via the END block, and the bash caller sums them across all files before passing the total to `jq --argjson skipped_malformed_lines $TOTAL`. Use a per-file loop (`for f in lifecycle/sessions/*/bin-invocations.jsonl; do ... done`) to keep ARG_MAX safe for large session counts.
  - `scripts` array semantics: includes EVERY inventory item, even those with zero invocations (count = 0). Order is alphabetical by `script` name. The `candidates_for_review` array is a redundant-but-distinct surface listing zero-count items (matches the human-readable report's section). Consumers iterating `scripts` get the full inventory; consumers iterating `candidates_for_review` get the triage subset. Both views agree.
- **Verification**:
  1. **jq presence precondition**: `command -v jq >/dev/null 2>&1 || { echo 'jq required for --json verifications' >&2; exit 1; }` — abort the verification block with a clear error if `jq` is missing.
  2. `LIFECYCLE_SESSION_ID=plan-r10-sid bin/cortex-log-invocation bin/cortex-update-item` then `bin/cortex-invocation-report --json | jq -e '.scripts | type == "array"'; echo $?` — pass if output ends with `0` (R10).
  3. `bin/cortex-invocation-report --json | jq -e 'has("inventory") and has("scripts") and has("candidates_for_review") and has("metadata")'; echo $?` — pass if output ends with `0` (R10).
  4. **Fresh-install path** (errors_recorded guard): `rm -f ~/.cache/cortex/log-invocation-errors.log && bin/cortex-invocation-report --json | jq -e '.metadata.errors_recorded == 0'; echo $?` — pass if output ends with `0` (proves the absent-file guard returns 0, not empty string crashing `jq`).
  5. **Cleanup**: `rm -rf lifecycle/sessions/plan-r10-sid` after verifications 2/3 complete.
- **Status**: [ ] pending

### Task 4: Add `--check-shims` flag to aggregator
- **Files**: `bin/cortex-invocation-report`
- **What**: Extend the aggregator's `--check-shims` branch to grep the first 50 lines of every `bin/cortex-*` (excluding `cortex-log-invocation`) for the literal string `cortex-log-invocation`. Exit 0 if all match; exit non-zero and write missing names to stderr otherwise.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Logic: `for f in "$(git rev-parse --show-toplevel)"/bin/cortex-*; do n="$(basename "$f")"; [ "$n" = "cortex-log-invocation" ] && continue; [ "$n" = "cortex-invocation-report" ] && continue; head -50 "$f" | grep -q "cortex-log-invocation" || echo "$n" >&2; done`. Track missing count via a counter; final `exit $missing_count`.
  - Stderr format: one missing-script basename per line. Reserve stdout for any human-readable summary (`Checked N scripts; M missing shim line.`).
  - Why exclude both helper and aggregator: the helper invokes itself trivially via name; the aggregator does not need a shim line because it is a developer-facing report tool, not a target of adoption-failure detection.
- **Verification**:
  1. After Tasks 6, 7, 8 complete (downstream verification): `bin/cortex-invocation-report --check-shims; echo $?` — pass if output ends with `0` (R11 happy path).
  2. **Sandbox-friendly negative test** (executes during this task): create a temporary `bin/cortex-test-no-shim`, then run `chmod +x bin/cortex-test-no-shim && bin/cortex-invocation-report --check-shims 2>&1 1>/dev/null | grep -q 'cortex-test-no-shim' && bin/cortex-invocation-report --check-shims; echo $?; rm bin/cortex-test-no-shim` — pass if intermediate stderr contains `cortex-test-no-shim` AND the second `echo $?` shows non-zero (verifies the missing-shim detection logic; cleanup deletes the probe file before any commit) (R11 negative path).
- **Status**: [ ] pending

### Task 5: Add `--self-test` flag to aggregator
- **Files**: `bin/cortex-invocation-report`
- **What**: Extend the aggregator's `--self-test` branch to verify end-to-end telemetry: helper resolves the log path, a probe write succeeds, the probe record is read back. Exit 0 on success; exit non-zero with a remediation hint to stderr on any step failure.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**:
  - Steps:
    1. Verify `LIFECYCLE_SESSION_ID` is set; if not, stderr `step 1 (LIFECYCLE_SESSION_ID resolution): unset — run from inside a Claude Code session`, exit non-zero.
    2. Verify `git rev-parse --show-toplevel` resolves; otherwise stderr `step 2 (repo root resolution): not in a git tree`, exit non-zero.
    3. Compute target log path. `mkdir -p` the session dir; if mkdir fails, stderr `step 3 (session dir create): permission denied — run \`cortex init\` to register the log path in sandbox.filesystem.allowWrite`, exit non-zero.
    4. Invoke `bin/cortex-log-invocation /tmp/cortex-self-test-probe`. Helper itself is fail-open, but the probe verifies via reading: `tail -1 "$logfile" | grep -q '"script":"cortex-self-test-probe"'`. If the read-back fails: stderr `step 4 (probe write/read): probe record not found in log — run \`cortex init\` to register the log path in sandbox.filesystem.allowWrite`, exit non-zero.
    5. Print `Self-test passed.` to stdout; exit 0.
  - Probe records ARE written to the real session log. Document in `--help` that running `--self-test` adds one record. This is acceptable because the script name (`cortex-self-test-probe`) is distinct from any inventory script and never appears in inventory globs.
- **Verification**:
  1. `LIFECYCLE_SESSION_ID=plan-selftest-sid bin/cortex-invocation-report --self-test; echo $?` — pass if output ends with `0` and stdout contains `Self-test passed.` (R13 happy path).
  2. `LIFECYCLE_SESSION_ID= bin/cortex-invocation-report --self-test; echo $?` — pass if output ends with non-zero AND stderr contains `step 1` (R13 failure path).
  3. **Cleanup**: `rm -rf lifecycle/sessions/plan-selftest-sid` after verifications complete.
- **Status**: [ ] pending

### Task 6: Add shim invocation to bash scripts
- **Files**: `bin/cortex-create-backlog-item`, `bin/cortex-generate-backlog-index`, `bin/cortex-git-sync-rebase`, `bin/cortex-jcc`, `bin/cortex-update-item`
- **What**: Insert one shim-invocation line near the top of each of the five bash scripts: `"$(dirname "$0")/cortex-log-invocation" "$0" "$@" || true`. Insertion point is immediately after the shebang and any leading comment block, before the first executable line.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - All five files are bash (verified at plan time via `head -5` reads).
  - Insertion semantics: between the leading comment block and the first executable line. For files using `set -euo pipefail` as their first executable line, the shim line goes ABOVE that — running the shim before `set -e` is engaged is part of the fail-open contract. The `|| true` is belt-and-suspenders.
  - Absolute path via `dirname "$0"` avoids reliance on `bin/` being on PATH (e.g., `cortex-jcc` is invoked via PATH lookup; `cortex-update-item` is invoked from inside the repo by skills that reference the absolute path).
  - Do NOT modify any other behavior in these scripts. The diff per file is exactly +1 line.
- **Verification**:
  1. For each f in the Files list: `head -10 "$f" | grep -c "cortex-log-invocation"` — pass if output is `1` for each. Run as: `for f in bin/cortex-create-backlog-item bin/cortex-generate-backlog-index bin/cortex-git-sync-rebase bin/cortex-jcc bin/cortex-update-item; do echo "$f: $(head -10 "$f" | grep -c "cortex-log-invocation")"; done` — pass if every line ends with `: 1`.
  2. Round-trip: ensure `CORTEX_COMMAND_ROOT="$(git rev-parse --show-toplevel)" LIFECYCLE_SESSION_ID=plan-rt-sid bin/cortex-jcc --list 2>/dev/null; tail -1 lifecycle/sessions/plan-rt-sid/bin-invocations.jsonl | grep -q '"script":"cortex-jcc"'; echo $?` — pass if output ends with `0` (proves the shim line actually invokes the helper at runtime, not just that the literal exists in the file). `--list` is the documented `just` recipe-listing flag and exits 0 cleanly without requiring a specific recipe; explicitly setting `CORTEX_COMMAND_ROOT` removes env-state dependency.
  3. **Cleanup**: `rm -rf lifecycle/sessions/plan-rt-sid` after verification 2 completes.
- **Status**: [ ] pending

### Task 7: Add shim invocation to plain Python scripts
- **Files**: `bin/cortex-archive-rewrite-paths`, `bin/cortex-archive-sample-select`
- **What**: Insert one shim-invocation block near the top of each of the two plain Python scripts: `import os, subprocess, sys; subprocess.run([os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortex-log-invocation"), sys.argv[0], *sys.argv[1:]], check=False)`. Insertion point is **after any `from __future__ import …` lines** and before the first non-`__future__` import.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Both files verified at plan time as plain Python (`#!/usr/bin/env python3`, NOT PEP 723 uv-script — verified by `head -5` showing `python3` shebang and no `# /// script` block).
  - **`__future__` ordering constraint (PEP 236)**: both files DO contain `from __future__ import annotations` — at line 44 in `cortex-archive-rewrite-paths` and at line 47 in `cortex-archive-sample-select` (verified at plan time via `grep -n "from __future__"`). PEP 236 mandates that `from __future__` imports be the first non-docstring/non-comment statements in a Python module. Inserting the shim block ABOVE a `__future__` import raises `SyntaxError: from __future__ imports must occur at the beginning of the file`.
  - **Correct insertion ordering**: shebang → module docstring → ALL `from __future__ import …` statements → shim block → existing non-`__future__` imports. The shim block goes IMMEDIATELY AFTER the last `__future__` import, BEFORE the first non-`__future__` import.
  - **Single-line form is intentional** to keep the diff minimal and the visual footprint small. `os` and `subprocess` are imported on the same statement as `sys` to guarantee no NameError if the existing script does not import all three. Same-line semicolons are valid Python.
  - `check=False` ensures Python does not raise on non-zero helper exit (the helper is fail-open and exits 0, but this is defense-in-depth).
  - Spec note (Changes to Existing Behavior): the spec listed `cortex-archive-sample-select` as bash; verified at plan time it is Python. This task corrects the spec's classification.
- **Verification**:
  1. `for f in bin/cortex-archive-rewrite-paths bin/cortex-archive-sample-select; do head -20 "$f" | grep -c "cortex-log-invocation"; done` — pass if both lines output `1`.
  2. `python3 -c 'import ast; ast.parse(open("bin/cortex-archive-rewrite-paths").read()); ast.parse(open("bin/cortex-archive-sample-select").read()); print("OK")'` — pass if output is `OK` (proves valid Python syntax after edit).
- **Status**: [ ] pending

### Task 8: Add shim invocation to PEP 723 uv-script Python
- **Files**: `bin/cortex-audit-doc`, `bin/cortex-count-tokens`
- **What**: Insert the same Python shim-invocation block as Task 7 into each of the two PEP 723 uv-script files, immediately AFTER the `# ///` close marker and before the first `import` statement.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Both files verified at plan time as PEP 723 uv-script (`#!/usr/bin/env -S uv run --script` shebang, followed by `# /// script` ... `# ///` block).
  - **Insertion ordering**: shebang → `# /// script` ... `# ///` block → module docstring (if present) → shim block → existing imports. The shim must NOT go inside the metadata block — uv parses that block as TOML-like config and any free-form Python would break parsing.
  - uv parses metadata first, runs the script body second, so the shim runs after dependency resolve. The "negligible overhead" framing in spec R5 is acknowledged as weakened on these two scripts; the shim itself remains <50ms.
  - Same single-line Python form as Task 7.
- **Verification**:
  1. `for f in bin/cortex-audit-doc bin/cortex-count-tokens; do head -25 "$f" | grep -c "cortex-log-invocation"; done` — pass if both lines output `1`.
  2. `python3 -c 'import ast; ast.parse(open("bin/cortex-audit-doc").read()); ast.parse(open("bin/cortex-count-tokens").read()); print("OK")'` — pass if output is `OK`.
  3. **Cross-task acceptance gate** (full R6 verified after this task is the last to land): `for f in bin/cortex-*; do n="$(basename "$f")"; [ "$n" = "cortex-log-invocation" ] && continue; [ "$n" = "cortex-invocation-report" ] && continue; head -50 "$f" | grep -q "cortex-log-invocation" || echo "MISSING: $n"; done` — pass if there is no output (R6).
- **Status**: [ ] pending

### Task 9: Wire `--check-shims` into `.githooks/pre-commit`
- **Files**: `.githooks/pre-commit`
- **What**: Add a pre-commit gate that, when any staged path matches `^bin/cortex-`, runs `bin/cortex-invocation-report --check-shims` and rejects the commit with stderr message and missing-script names if the check fails.
- **Depends on**: [4, 6, 7, 8]
- **Complexity**: simple
- **Context**:
  - **Insertion point**: a new "Phase 1.5" block between Phase 1 (name validation, line 62) and Phase 2 (build short-circuit, line 67). Rationale: shim check is cheap; running it before the conditional `just build-plugin` invocation in Phase 3 reduces the cost of a guaranteed-fail commit.
  - **`staged` variable hoist**: the existing Phase 2 computes `staged=$(git diff --cached --name-only --diff-filter=ACMR)` at line 68. Move this assignment above the new Phase 1.5 so both phases can read it. No semantic change.
  - **Phase 1.5 logic**: if `staged` contains any path matching `^bin/cortex-`, invoke `bin/cortex-invocation-report --check-shims`. The aggregator's stderr (one missing-script basename per line, per Task 4) is what should reach the user. On non-zero exit: emit a one-line `pre-commit:` prefix to stderr explaining the rejection, relay the missing names from the aggregator, then `exit 1`. On zero exit: continue to Phase 2.
  - **Pattern reference**: existing Phase 2 short-circuit (lines 67-83) demonstrates the `echo "$staged" | grep -qE` idiom and how to handle multi-step bash logic in this hook.
  - **Bash 3.2 compatibility constraint**: file uses `#!/bin/bash` (macOS system bash). Allowed idioms — `read -r` patterns, `grep -qE`, `[ ... ]` test brackets. Forbidden — `mapfile`, `readarray`, `[[ =~ ]]` regex when `grep -qE` suffices.
  - **Out-of-scope**: `.githooks/pre-commit` is hand-maintained (not in the dual-source plugin tree). No mirroring updates required.
- **Verification**:
  1. **Setup-githooks precondition**: `[ "$(git config core.hooksPath 2>/dev/null)" = ".githooks" ] || just setup-githooks` — ensures the hook is wired so that subsequent verifications actually exercise the gate. Without this, a fresh-clone run would silently pass for the wrong reason (gate never fires because hook isn't installed).
  2. **Negative gate fires (R14)**: create a probe `bin/cortex-test-no-shim` with the shebang `#!/bin/bash` and no shim line, `chmod +x bin/cortex-test-no-shim`, then attempt to commit it: `git add bin/cortex-test-no-shim && git commit -m "should fail"; commit_rc=$?; git diff --cached --quiet -- bin/cortex-test-no-shim; staged_present=$?; git restore --staged bin/cortex-test-no-shim 2>/dev/null; rm -f bin/cortex-test-no-shim plugins/cortex-interactive/bin/cortex-test-no-shim; [ "$commit_rc" -ne 0 ] && [ "$staged_present" -eq 0 ] && echo OK` — pass if final output is `OK`. The two assertions verify (a) the commit was rejected (`commit_rc != 0`, stronger than checking only that stderr contained the script name) and (b) the file remained staged after rejection (proving the gate ran). Cleanup also removes the plugin-mirror artifact in case `just build-plugin` ran.
  3. **Idempotent probe-name reuse**: prior to verification 2, `rm -f bin/cortex-test-no-shim plugins/cortex-interactive/bin/cortex-test-no-shim` — defensively clean up any artifact left by an interrupted prior run (Task 4's negative test uses the same probe name).
  > Verification 1 of an earlier draft created a real commit and rewound via `git reset --soft HEAD^` + `git checkout --`; this was destructive on dirty trees and has been replaced by the precondition check above. The negative-gate test (verification 2) is sufficient to prove the gate fires on missing shims; a positive-gate "valid commit succeeds" test is left to the standard `just test` run after all tasks land.
- **Status**: [ ] pending

### Task 10: Amend backlog item 103 to reflect the shim mechanism
- **Files**: `backlog/103-add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7.md`
- **What**: Rewrite the backlog item's `title:` frontmatter, `# Heading`, and the `## Scope` / `## Out of scope` / 2026-04-27 amendment sections to describe the per-script invocation shim approach in place of the originally-proposed PreToolUse Bash hook matcher. Filename is NOT renamed (preserves backlog index links).
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Suggested title (per spec R16): `"Add runtime adoption telemetry via per-script invocation shim (DR-7)"`.
  - Update the `# Heading` to match the new title.
  - Replace `## Scope` body to enumerate: helper script, aggregator CLI, four flags, shim insertion across 9 scripts, pre-commit gate, observability doc update.
  - Replace `## Out of scope` body to enumerate the spec's Non-Requirements section essentials: agent-intent classification, pipeline integration, non-cortex Bash, log rotation policy, historical backfill.
  - Replace the 2026-04-27 amendment section with a new 2026-04-28 amendment section recording the alternative-mechanism pivot driven by the lifecycle research's Adversarial F7 sandbox finding and Alt 5 + DR-5 composition rationale.
  - Do NOT modify the YAML frontmatter beyond `title:`. Do not touch `lifecycle_phase`, `session_id`, `status` — those are managed by the lifecycle skill via `cortex-update-item`.
- **Verification**:
  1. `grep -c "PreToolUse Bash hook matcher" backlog/103-add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7.md` — pass if output is `0` (R16 negative).
  2. `grep -c "invocation shim" backlog/103-add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7.md` — pass if output is `≥ 2` (R16 positive).
  3. `awk '/^---$/{c++; next} c==1' backlog/103-add-runtime-adoption-telemetry-via-pretooluse-bash-hook-matcher-dr-7.md | grep -c "^title:"` — pass if output is `1` (frontmatter intact).
- **Status**: [ ] pending

### Task 11: Add 6th observability subsystem section to `requirements/observability.md`
- **Files**: `requirements/observability.md`
- **What**: Add a new `### Runtime Adoption Telemetry` subsection under `## Functional Requirements` documenting the shim + aggregator subsystem (Description, Inputs, Outputs, Acceptance criteria, Priority). Insertion point is between the existing `### Notifications` and `### In-Session Status CLI` subsections.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Mirror the existing five subsystems' structure exactly. Read `requirements/observability.md` first to confirm the exact heading conventions and field ordering used by the other five.
  - Subsection contents (one paragraph each):
    - **Description**: per-script invocation shim writes one JSONL record per `bin/cortex-*` invocation to `lifecycle/sessions/<id>/bin-invocations.jsonl`; aggregator reads the logs and reports adoption. Composed with DR-5 static parity lint (ticket 102) for full coverage.
    - **Inputs**: helper invocation calls from each `bin/cortex-*` script's shim line; environment variables `LIFECYCLE_SESSION_ID`.
    - **Outputs**: per-session JSONL log file; aggregator stdout (default + `--json` modes); error breadcrumb at `~/.cache/cortex/log-invocation-errors.log`.
    - **Acceptance**: Spec R1–R18 acceptance criteria from `lifecycle/.../spec.md`.
    - **Priority**: P1 (closes the runtime-adoption-failure detection gap that DR-5 cannot reach).
  - Insertion order positions this AFTER notifications (which is also a runtime telemetry subsystem) and BEFORE the in-session status CLI (which is a developer-facing query interface) — the new subsystem is closer to notifications in nature.
- **Verification**:
  1. `grep -c "Runtime Adoption Telemetry" requirements/observability.md` — pass if output is `≥ 1` (R17 positive).
  2. `awk '/### Notifications/,/### In-Session Status CLI/' requirements/observability.md | grep -c "Runtime Adoption Telemetry"` — pass if output is `≥ 1` (R17 ordering).
- **Status**: [ ] pending

## Verification Strategy

After all tasks complete, the feature is end-to-end verified by:

1. **Telemetry round-trip**: `LIFECYCLE_SESSION_ID=verify-sid bin/cortex-jcc --version 2>/dev/null; tail -1 lifecycle/sessions/verify-sid/bin-invocations.jsonl | jq -e '.script == "cortex-jcc"'` exits 0 — proves a real script invocation flows through the shim into the log.
2. **Report renders correctly**: `bin/cortex-invocation-report` shows `cortex-jcc` with count ≥ 1 in the per-script section and inventory items unused this session in `CANDIDATES FOR REVIEW`.
3. **Pre-commit gate is active**: attempting to commit a `bin/cortex-test-probe` script without the shim line is rejected by the pre-commit hook with the script name in stderr.
4. **Self-test passes**: `bin/cortex-invocation-report --self-test` exits 0 with `Self-test passed.` on stdout.
5. **All static acceptance criteria from spec R1–R18 pass when run in sequence.**
6. **`just test` exits 0** after all per-task verifications pass — `just test; echo $?` ends with `0` (R18).
7. **Plugin distribution mirror is byte-identical**: `just build-plugin && diff bin/cortex-log-invocation plugins/cortex-interactive/bin/cortex-log-invocation; echo $?` ends with `0`, and `diff bin/cortex-invocation-report plugins/cortex-interactive/bin/cortex-invocation-report; echo $?` ends with `0` (R15). Mirroring is automatic via the existing `BIN=(cortex-)` glob in `justfile:481`; no justfile edits needed.

## Veto Surface

- **Sandbox-friendly write target chosen**: `lifecycle/sessions/<id>/bin-invocations.jsonl` (research M2) instead of `~/.claude/bin-invocations.jsonl`. Trade-off: per-session retention semantics inherit from lifecycle session cleanup; aggregator must merge across N session dirs. Resolved in spec; flagging here in case implementer wants to revisit before committing 9 file edits.
- **Bash + POSIX implementation language**: chosen over Python helper. Trade-off: simpler dependency surface; ~50ms budget achievable; harder to extend later if the helper grows. Resolved in spec; flagging here.
- **No log rotation in v1**: aggregator does not rotate. Trade-off: ~70 KB/day maximum across all session dirs; deferrable for years per spec. Flagging here in case implementer reads the volume estimate differently.
- **Probe records written by `--self-test` enter the real log**: documented in `--help`. Trade-off: `cortex-self-test-probe` will appear in invocation counts for users who run self-test frequently. Could pollute reports if self-test is run by automation; v1 accepts this since self-test is manual.
- **Shim insertion ordering for bash scripts (above `set -euo pipefail`)**: ensures shim runs before strict mode engages, preserving fail-open even if `set -e` is configured. Trade-off: the shim line is technically outside strict-mode protection, but the helper itself is fail-open and the trailing `|| true` is belt-and-suspenders. Flagging in case implementer prefers below-`set` placement.
- **Helper performance verification uses 10 runs / <0.5s wall-clock budget**: rather than direct <50ms-per-run measurement. Trade-off: easier to verify across machines without dependence on `time` precision. Flagging in case spec R5 needs literal 50ms verification.

## Scope Boundaries

Mirrors spec Non-Requirements:
- No agent-intent classification (Alt 3's "Read+Grep instead of script" is explicitly out of scope).
- No pipeline `agent-activity.jsonl` / `pipeline-events.log` integration.
- No non-`bin/cortex-*` Bash invocation tracking.
- No PreToolUse hook (the original ticket 103 mechanism is rejected).
- No script classification by expected frequency or agent-facing-vs-utility taxonomy in v1.
- No "sandbox-denied write" vs "successful no-op" distinction in v1 helper failure handling.
- No agent-worktree telemetry bridge (overnight isolation under `/private/tmp/...`).
- No `cortex-jcc` recipe-level telemetry (only the dispatcher itself).
- No log rotation policy.
- No historical backfill from existing Claude Code session JSONL.
- No automatic aggregator triggers (manual run or weekly only).
