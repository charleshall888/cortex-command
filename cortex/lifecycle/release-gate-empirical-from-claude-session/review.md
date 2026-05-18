# Review: release-gate-empirical-from-claude-session

## Stage 1: Spec Compliance

### Requirement 1: Replace the hallucinated assertion target with paired events that actually exist
- **Expected**: #230 §Procedure step 3 rewritten to assert `dispatch_start` + `dispatch_complete` (paired, with `ts` ordering and matching `feature`) plus zero `EPERM` and zero "Sandbox failed to initialize" against `pipeline-events.log`. Acceptance greps: `feature_dispatched` = 0; `dispatch_start` ≥ 1; `pipeline-events.log` ≥ 1.
- **Actual**: #230:60–67 contains all four assertions against `cortex/lifecycle/smoke-release-gate/pipeline-events.log`. Acceptance greps observed: `feature_dispatched` = 0; `dispatch_start` = 6; `pipeline-events.log` = 11.
- **Verdict**: PASS
- **Notes**: Paired-event proof shape correctly enforces `ts` strictness ("strictly greater than") and matching `feature` field, both load-bearing per spec.

### Requirement 2: Propagate the fix into #228 spec R16
- **Expected**: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` R16 (line 53) removes `feature_dispatched` and `events.log`; replaces with paired `dispatch_start` + `dispatch_complete` against `pipeline-events.log`. Preserves tier-enum rationale, release-tag handshake framing, `[release-type: skip]` → `[release-type: minor]` flow. Acceptance: `feature_dispatched` in spec = 0.
- **Actual**: spec.md:53 rewritten — "paired `dispatch_start` and `dispatch_complete` events in `cortex/lifecycle/<feature>/pipeline-events.log` (matching feature slug; `dispatch_complete.ts > dispatch_start.ts`)". Tier-enum claim ("closed `trivial|simple|complex` enum"), release-tag handshake (`[release-type: skip]` → `[release-type: minor]`), and `feature_complete` framing all preserved. `feature_dispatched` grep returns 0.
- **Verdict**: PASS

### Requirement 3: Add Step 0 version-pinning to the merged #228 SHA
- **Expected**: New Step 0 captures #228 squash-merge SHA, re-installs CLI via `uv tool install --reinstall --no-cache git+...@<sha>`, captures `cortex --version` and `/plugin list`, with §Acceptance gating on SHA + CLI version. Acceptance: `uv tool install --reinstall` ≥ 1 in #230.
- **Actual**: #230:34–50 introduces Step 0 with all four operator actions and a FAIL clause on empty SHA/CLI fields or irreconcilable mismatch. `uv tool install --reinstall` grep returns 1.
- **Verdict**: PASS
- **Notes**: Step 0 also handles plugin install/confirmation via `/plugin list`, matching the spec's edge-case wording about plugin marketplace not exposing SHA-level versions.

### Requirement 4: Codify archive-then-cleanup ordering with wait-and-poll contract
- **Expected**: Step 4 (record proof), Step 4.5 (archive + `git add` before cleanup), Step 5 (`cortex daytime cancel` → poll `cortex daytime status` at 5s intervals up to 30s → only then `git clean -fd`). 5-minute wall-clock timeout on the wait. Acceptance: `cortex daytime status` ≥ 1; `git add` ≥ 1; archive precedes `git clean`.
- **Actual**: #230:69–92 implements Step 4 (record), Step 4.5 (archive + `git add`, line 81), and Step 5 (cancel → poll-status-loop → `git clean`). The 5-minute wall-clock timeout is in Step 2 (#230:58). Acceptance greps: `cortex daytime status` = 1; `git add` = 1. Step ordering verified: line 73 (Step 4.5 archive) precedes line 86 (Step 5) which precedes line 92 (`git clean`).
- **Verdict**: PASS
- **Notes**: Silent-fail FAIL-path ("no PID file within 30s") explicitly named, matching the spec's edge case.

### Requirement 5: Update §Results template to reflect corrected proof shape
- **Expected**: 12 fields, blank values, in the prescribed order, with `dispatch_start:` and `dispatch_complete:` sub-fields under "Paired dispatch event lines".
- **Actual**: #230:121–138 contains exactly the 12 fields in the spec's order, blank, with the paired-events code fence containing `dispatch_start:` and `dispatch_complete:` placeholders.
- **Verdict**: PASS

### Requirement 6: Add a pytest lint that catches future event-name hallucinations
- **Expected**: `tests/test_backlog_grep_targets_resolve.py` walks `cortex/backlog/*.md` (skipping `archive/`), extracts `grep -c "<token>"` patterns, filters to event-name-shape tokens (`^[a-z_]+$`, no spaces), verifies each appears in `bin/.events-registry.md` OR as a literal in `cortex_command/` via `git grep -F`. Fails with `UNREGISTERED_GREP_TARGET: <path>:<line> references "<token>" ...`. Acceptance: `pytest tests/test_backlog_grep_targets_resolve.py -v` exits 0.
- **Actual**: File is 253 lines, three tests: positive fixture (registered token passes), negative fixture (hallucinated token reported with `UNREGISTERED_GREP_TARGET`, line number preserved), and `test_live_backlog_has_no_unregistered_grep_targets` against the real corpus. Ran locally — 3 passed in 0.14s. Regex `_GREP_C_RE` accepts both quote styles; allowlist `{true, false, none, null}` is narrow as spec instructed; archive/ subdir skipped via `_iter_backlog_files`.
- **Verdict**: PASS

### Requirement 7: Wire the lint into the existing test suite without bespoke configuration
- **Expected**: Lint runs under standard pytest discovery; `just test` includes it; no new justfile recipe. Acceptance: `just test 2>&1 | grep -c test_backlog_grep_targets_resolve.py ≥ 1`.
- **Actual**: `pytest tests/ --collect-only -q | grep test_backlog_grep_targets_resolve` returns all 3 tests, confirming standard discovery picks them up. The `just test` recipe at justfile:575 invokes `.venv/bin/pytest tests/ -q` via a `run_test()` wrapper that captures stdout when the test passes, so the literal grep-against-`just test`-output check returns 0 — but that is an artifact of `pytest -q` + `run_test`'s pass-path output suppression, not a wiring defect. The spec's stated mechanism ("inherits the project's existing pytest discovery and `just test` recipe") is satisfied.
- **Verdict**: PARTIAL
- **Notes**: The acceptance literal as written is unachievable against the `just test` recipe's quiet-mode invocation. The substantive intent — "the lint runs as part of `just test`" — is met (3 tests collected and executed under `pytest tests/`). Not a code defect; a defect in the acceptance literal. Treating as PARTIAL because the binary-checkable grep does not return ≥ 1, but the underlying mechanism is wired correctly.

### Requirement 8: Cross-reference the procedure from `docs/release-process.md`
- **Expected**: One paragraph (≤6 sentences) under "Cut a new release" describing the release-gated-ticket pattern (chore + release-gate + manual-verification tags + §Results gate). Acceptance: `230-release-gate-empirical-from-claude-session` ≥ 1 in docs/release-process.md.
- **Actual**: docs/release-process.md:122–124 adds a new "release-gate tickets (manual smoke before push)" subsection. One paragraph, ~5 sentences, names #230 as canonical example, describes the pattern (chore ticket + `release-gate` + `manual-verification` tags + populated §Results gates the empty `[release-type: minor]` commit) without restating the procedure. Acceptance grep = 1.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- The new pytest lint introduces a validation surface (backlog `grep -c` tokens must resolve to registered events or codebase literals) that complements `bin/cortex-check-events-registry` but is not mentioned in project.md's Architectural Constraints. The existing "SKILL.md-to-bin parity enforcement" bullet is the closest precedent; backlog-grep-resolution is a sibling constraint worth surfacing so future authors know this gate exists.
- The release-gate ticket convention (`type: chore` + `release-gate` + `manual-verification` tags + populated §Results gating the release-cut commit) is now documented in docs/release-process.md but is not reflected as a convention in `cortex/requirements/project.md` (Conventions) or pipeline.md. Drift is mild — the convention is captured in the canonical release doc — but a one-bullet acknowledgement under project.md Conventions/Quality Attributes would close the discoverability loop for future ticket authors who don't start by reading the release doc.
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `/Users/charlie.hall/Workspaces/cortex-command/cortex/requirements/project.md`
**Section**: Architectural Constraints
**Content**:
```
- **Backlog `grep -c` resolution**: Backlog tickets that include `grep -c "<token>"` as Done-When/acceptance checks must reference tokens that appear in `bin/.events-registry.md` or as literal strings under `cortex_command/`. Enforced by `tests/test_backlog_grep_targets_resolve.py`. Companion to the events-registry gate; prevents acceptance criteria from passing trivially against hallucinated event names.
```

## Stage 2: Code Quality
- **Naming conventions**: `test_backlog_grep_targets_resolve.py` follows the `tests/test_*.py` pattern; module-level constants (`REPO_ROOT`, `BACKLOG_DIR`, `REGISTRY_PATH`, `_GREP_C_RE`, `_EVENT_SHAPE_RE`, `_ALLOWLIST`) match the underscore-prefix-for-private convention used in `test_check_events_registry.py`. Helper-function names (`_iter_backlog_files`, `_token_emitted_in_codebase`, `_find_unregistered_grep_targets`, `_seed_fake_repo`, `_write_backlog`) are descriptive and consistent. Diagnostic string `UNREGISTERED_GREP_TARGET:` matches the `UNREGISTERED_EVENT` style of the events-registry gate.
- **Error handling**: `_token_emitted_in_codebase` correctly uses `check=False` on `subprocess.run` and inspects `returncode` (git grep exits 1 on no match — that is the "not emitted" signal, not an error). `_find_unregistered_grep_targets` catches `UnicodeDecodeError` on non-UTF8 backlog files via `try/except` and continues. The fixture helper `_seed_fake_repo` uses `check=True` on `git init`/`add`/`commit` (these are setup steps where failure should be loud) and disables GPG signing inline so the test works on operator machines with `commit.gpgsign=true` globally. All appropriate for the context.
- **Test coverage**: Three tests cover positive (registered token passes), negative (hallucinated token surfaces with correct line number and path), and live-corpus (regression guard). Verified locally — `uv run pytest tests/test_backlog_grep_targets_resolve.py -v` exits 0 with 3 passed. All acceptance greps from R1, R2, R3, R4, R8 verified manually and return the required counts. R7's `just test` substring check has an artifact issue noted in the PARTIAL verdict (not a coverage gap; a literal-vs-mechanism mismatch in the acceptance criterion itself).
- **Pattern consistency**: Lint follows the `bin/cortex-check-events-registry` + `tests/test_check_events_registry.py` precedent referenced in the spec. Diagnostic format (`<MARKER>: <path>:<line> references ...`) matches existing scanners. File-based state — registry markdown + git grep — is consistent with ADR-0001 (file-based state). The pytest lint discovery model (no new justfile recipe) matches the project's preference for minimal recipe surface. The #230 procedure prose follows the §Procedure/§Results/§Acceptance/§References sections used by other backlog tickets, and the release-tag handshake framing mirrors `docs/release-process.md` conventions.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
