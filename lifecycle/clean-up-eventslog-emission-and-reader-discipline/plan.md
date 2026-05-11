# Plan: clean-up-eventslog-emission-and-reader-discipline

## Overview

Apply the per-event remediation table from spec R1 (delete 11 verified-dead skill-prompt emissions; preserve `plan_comparison`; prune `clarify_critic` payload), bump two payload schemas in lockstep (`clarify_critic` v2→v3 inline-only; `aggregate_round_context` v1→v2 with a read-shape index), and ship a CI-time skill-prompt-scoped emission-registry gate (`bin/cortex-check-events-registry` + `bin/.events-registry.md` + a new pre-commit phase + justfile recipes + self-tests) that inverts the cost asymmetry the audit diagnosed. Implementation lands in two waves: cleanup-and-schemas first (R1–R4), then the discipline gate (R5–R7) plus docs (R8). Wave 1 is independently revertable; Wave 2 (the gate) is safely revertable only as long as Wave 1 stays applied — reverting Wave 2 with Wave 1 reverted would re-introduce dead-event literals with no gate to catch them.

**Spec correction (Phase number)**: spec R6 references "Phase 1.7" as the new pre-commit slot, but the repo already has a Phase 1.7 today (`backlog entry-point telemetry-call enforcement` at `.githooks/pre-commit:120`). This plan uses **Phase 1.8** for the new events-registry gate slot, inserted between the existing Phase 1.7 (backlog telemetry) and Phase 2 (dual-source drift). The semantic intent of spec R6 is preserved; only the phase number changes.

## Tasks

### Task 1: Re-verify zero non-test consumers for each DELETE-row event (R2)

- **Files**: `lifecycle/clean-up-eventslog-emission-and-reader-discipline/r2-consumer-grep.md` (new — temporary verification artifact for the PR description)
- **What**: For each DELETE-row event in spec R1, run repo-wide consumer-greps against `cortex_command/`, `bin/`, `hooks/`, `claude/`, `tests/`, `skills/`, `plugins/cortex-core/skills/`, `cortex_command/overnight/prompts/` and record the per-event hit counts. If any DELETE-row event has a real non-test, non-emitter, non-legacy-tolerance consumer, reclassify it (KEEP-AS-AUDIT-AFFORDANCE or PRUNE-PAYLOAD) and update spec.md inline with the reclassification before proceeding.
- **Depends on**: none
- **Complexity**: simple
- **Context**: DELETE-row events from spec R1: `task_complete`, `confidence_check`, `decompose_flag`, `decompose_ack`, `decompose_drop`, `discovery_reference`, `implementation_dispatch`, `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`, `requirements_updated`. KEEP-AS-AUDIT-AFFORDANCE rows (do NOT delete): `plan_comparison`. PRUNE-PAYLOAD: `clarify_critic` (R3). The grep pattern is `grep -rn '"<event_name>"' <scope>`; for skill-prompt scopes also `grep -rn '"event": "<event_name>"'`. Distinguish emitter sites (skill prompts instructing emission) from consumer sites (Python reads, shell substring greps, test fixtures). Legacy-tolerance documentation hits (e.g., `clarify-critic.md:162-166`) are not consumers. Tests-only hits do not block deletion but must be enumerated.
- **Verification**: `lifecycle/clean-up-eventslog-emission-and-reader-discipline/r2-consumer-grep.md` exists and contains an 11-row table with columns `event_name | grep_pattern | scope | hit_count | classification (DELETE | RECLASSIFY: <reason>)`. Pass if file exists and every row has a non-empty classification cell. Fail if any cell is blank or the file is missing.
- **Status**: [ ] pending

### Task 2a: Delete dead-event emission instructions in lifecycle skill prompts (R1)

- **Files**:
  - `skills/lifecycle/SKILL.md` (line ~220, `discovery_reference` emission)
  - `skills/lifecycle/references/orchestrator-review.md` (lines 42, 72, 120 — `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`)
  - `skills/lifecycle/references/specify.md` (lines 65, 76 — `confidence_check`)
  - `skills/lifecycle/references/implement.md` (line 107 — `implementation_dispatch`; lines 185-187 — `task_complete`)
  - `skills/lifecycle/references/review.md` (line 182 — `requirements_updated`)
  - (`plugins/cortex-core/skills/**` mirrors regenerate automatically via the dual-source pre-commit hook; not listed as canonical edits)
- **What**: Remove the JSONL-emit instruction block (template + surrounding "Append/Emit/Log this event" prose) for each DELETE-row event in these five files whose Task 1 classification confirmed DELETE. Preserve all surrounding non-emission prose (instruction context, decision rules, etc.). Do NOT touch `plan_comparison`, `phase_transition`, `feature_complete`, `lifecycle_start`, `criticality_override`, `review_verdict`, or `batch_dispatch` emissions present in adjacent locations — these are live-consumer events.
- **Depends on**: [1]
- **Complexity**: complex
- **Context**: Each skill-prompt JSONL emit block typically reads: prose "Append/Emit this event..." + fenced code block with `{"ts": "...", "event": "<name>", ...}` + occasional trailing rationale prose. Delete the prose + fenced block; do not leave dangling lead-ins. The lifecycle reference files contain emit blocks for both live and dead events at adjacent lines — delete only the dead-event block(s) and leave surrounding live-event blocks intact. Pre-commit Phase 2 (dual-source drift) regenerates `plugins/cortex-core/skills/**` mirrors; do not skip the hook.
- **Verification**: `grep -rn '"event":\s*"\(confidence_check\|discovery_reference\|implementation_dispatch\|orchestrator_review\|orchestrator_dispatch_fix\|orchestrator_escalate\|requirements_updated\|task_complete\)"' skills/lifecycle/ plugins/cortex-core/skills/lifecycle/` returns 0 non-legacy-tolerance-comment hits — pass.
- **Status**: [ ] pending

### Task 2b: Delete dead-event emission instructions in discovery skill prompts (R1)

- **Files**:
  - `skills/discovery/references/decompose.md` (lines 49-51 — `decompose_flag`, `decompose_ack`, `decompose_drop`)
  - `skills/discovery/references/orchestrator-review.md` (lines 27, 55, 98 — `orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`)
  - (`plugins/cortex-core/skills/discovery/**` mirrors regenerate automatically via the dual-source pre-commit hook; not listed as canonical edits)
- **What**: Remove the JSONL-emit instruction block (template + surrounding "Append/Emit/Log this event" prose) for each DELETE-row event in these two files. Preserve all surrounding non-emission prose.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Same edit shape as Task 2a — prose + fenced code block per event. The discovery `orchestrator-review.md` mirrors the lifecycle `orchestrator-review.md` structure; the three events (`orchestrator_review`, `orchestrator_dispatch_fix`, `orchestrator_escalate`) are emitted at parallel line positions.
- **Verification**: `grep -rn '"event":\s*"\(decompose_flag\|decompose_ack\|decompose_drop\|orchestrator_review\|orchestrator_dispatch_fix\|orchestrator_escalate\)"' skills/discovery/ plugins/cortex-core/skills/discovery/` returns 0 non-legacy-tolerance-comment hits — pass.
- **Status**: [ ] pending

### Task 3: Delete the `requirements_updated` consumer scan section in walkthrough.md (R1)

- **Files**: `skills/morning-review/references/walkthrough.md` (lines 301-320 — Section 2c "Requirements Drift Updates")
- **What**: Remove the entire `## Section 2c — Requirements Drift Updates` block (header, prose, code fragment that greps for `requirements_updated`). Renumber any subsequent sections (e.g., a current `Section 2d` becomes `Section 2c`) so numbering is consistent.
- **Depends on**: [2a]
- **Complexity**: simple
- **Context**: The block instructs the morning-review skill to grep `events.log` files for `requirements_updated` rows. With Task 2 removing the emit instruction, the consumer scan is also dead. Check for subsequent sections that need renumber (search for `## Section 2[a-z]` and `## Section 3` in the same file).
- **Verification**: `grep -n 'requirements_updated' skills/morning-review/references/walkthrough.md` — pass if zero hits. `grep -n '## Section 2c' skills/morning-review/references/walkthrough.md` — pass if zero hits (or, if Section 2c remains, it is a renumbered successor with different content).
- **Status**: [ ] pending

### Task 4: Bump `clarify_critic` schema v2→v3 in clarify-critic.md (R3)

- **Files**:
  - `skills/refine/references/clarify-critic.md` (lines ~113-220, including the legacy-tolerance table at 162-166 and the event-emit template at 175)
  - `plugins/cortex-core/skills/refine/references/clarify-critic.md` (auto-regenerated)
- **What**: Replace the v2 event-emit template at the canonical site with the v3 inline-only shape from spec R3: drop `findings[]`, `dismissals[]`, `applied_fixes[]` arrays; replace with `findings_count`, `dismissals_count`, `applied_fixes_count` integer fields. Bump `schema_version: 3`. Update the legacy-tolerance table at lines 162-166 to enumerate v3 (canonical write shape) plus v1, v1+dismissals, v2, YAML-block all read-tolerated indefinitely. No sibling artifact is introduced — do NOT add a `findings_path` reference.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Use the v3 shape from spec.md:46-48 verbatim. The legacy-tolerance table is a markdown table at 162-166; extend it with a row for v3 as the current write shape and ensure each prior shape's row carries an "indefinite read-tolerance" annotation. The prose around the template should explain that the per-finding text is intentionally not preserved (audit-verified zero non-test consumers; preserving prose without a reader would re-create the dead-emission pattern). The mirror at `plugins/cortex-core/skills/refine/references/clarify-critic.md` regenerates via the dual-source pre-commit hook.
- **Verification**: `grep -c '"schema_version": 3' skills/refine/references/clarify-critic.md` ≥ 1 — pass. `grep -c '"findings":' skills/refine/references/clarify-critic.md` = 0 in event-emit template context (legacy-tolerance examples may still show `findings:` as historical shape) — pass if no template-level reference. `grep -c '"findings_count":' skills/refine/references/clarify-critic.md` ≥ 1 — pass.
- **Status**: [ ] pending

### Task 5: Verify `tests/test_clarify_critic_alignment_integration.py` passes unchanged under v3 (R3)

- **Files**: `tests/test_clarify_critic_alignment_integration.py` (read-only check; no edits expected unless the test breaks)
- **What**: Run the integration test against the post-Task-4 tree. The test's `detections >= 1` invariant at lines 666-669 should continue to pass because (a) archived v2 rows in `lifecycle/archive/` are not rewritten and remain readable, (b) the `_JSONL_RE` / `_YAML_EVENT_LINE_RE` regexes at lines 579-581 do not depend on the inner `findings` field, (c) new v3 emissions add count fields without altering row identification. Additionally synthesize a v3-shape row in a tmp fixture directory and assert the test passes against a v3-only corpus (not just the archive's mixed/legacy rows), so a v3-emission-path bug is not masked by archived v2 rows still satisfying the invariant. If the test fails, diagnose whether the failure is in legacy-tolerance handling, row-counting, or v3 shape parsing and fix the test minimally (do not weaken the invariant).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: The test walks `lifecycle/*/events.log` for `clarify_critic` rows and asserts at least one detection. It is a schema-conformance gate, not a content assertion against the inner payload. The fixtures at `tests/fixtures/clarify_critic_v1.json` and `tests/fixtures/jsonl_emission_cutoff.txt` are referenced for legacy-tolerance verification and should not need changes for v1/v2 paths. For the v3 path: construct an in-test `tmp_path` events.log containing one synthetic v3 row matching the Task 4 template literal and rerun the detection-count assertion against it. If the test module doesn't already support a parameterized fixture-corpus path, add the v3 case as a new test function rather than weakening the existing one.
- **Verification**: `just test -- tests/test_clarify_critic_alignment_integration.py` — pass if exit 0. A v3-only synthetic fixture is detected with `detections >= 1` — pass (asserted by the added test function).
- **Status**: [ ] pending

### Task 6: Rewrite `aggregate_round_context` to emit `prior_resolutions_by_feature` (R4)

- **Files**:
  - `cortex_command/overnight/orchestrator_context.py` (lines 20, 60-110, 105, 115-116 specifically — `_EXPECTED_SCHEMA_VERSION`, the aggregation logic, the inline payload literal, and the strict-equality guard)
- **What**: Remove the `all_entries: list[dict]` field from the `escalations` sub-dict returned by `aggregate_round_context`. Add `prior_resolutions_by_feature: dict[str, list[dict]]` keyed by feature slug, containing only entries with `type == "resolution"`. Preserve the existing `unresolved` field as-is. Bump `_EXPECTED_SCHEMA_VERSION` (line 20) from `1` to `2`. Bump the inline `"schema_version"` literal in the returned dict (line 105) from `1` to `2` in lockstep. Update the drift-guard `RuntimeError(...)` message at lines 115-116 to reference the new shape (e.g., mention `prior_resolutions_by_feature` so a future drift error is self-documenting).
- **Depends on**: none
- **Complexity**: complex
- **Context**: The aggregator currently builds `all_entries` by concatenating all `escalations.jsonl` rows; replace this with a dict-comprehension that buckets by `feature` for entries where `type == "resolution"`. `unresolved` is computed at lines 79-94 and is independent of this change. The two schema_version sites (`_EXPECTED_SCHEMA_VERSION` and the inline literal) MUST move together — the strict-equality guard at 115-116 fails if they drift. Function signature: `aggregate_round_context(session_dir: Path, round_number: int) -> dict` (verified at `cortex_command/overnight/orchestrator_context.py:23`; do not drop the `round_number` arg). The returned `escalations` sub-dict shape becomes `{"unresolved": list[dict], "prior_resolutions_by_feature": dict[str, list[dict]]}`. Per spec R4 acceptance and Edge Cases line 178: the producer (this file) and the consumer prompt (Task 7) MUST ship in the same PR.
- **Verification**: `grep -n '_EXPECTED_SCHEMA_VERSION = 2' cortex_command/overnight/orchestrator_context.py` returns exactly one hit — pass. `grep -n '"schema_version": 2' cortex_command/overnight/orchestrator_context.py` returns ≥ 1 hit (the inline literal) — pass. `grep -n 'all_entries' cortex_command/overnight/orchestrator_context.py` returns 0 hits in non-comment code — pass. `grep -n 'prior_resolutions_by_feature' cortex_command/overnight/orchestrator_context.py` returns ≥ 1 hit — pass.
- **Status**: [ ] pending

### Task 7: Update orchestrator-round.md prompt to consume the new dict (R4)

- **Files**: `cortex_command/overnight/prompts/orchestrator-round.md` (lines 54-61)
- **What**: Replace the inline per-feature filter over `all_entries` with a dict lookup: `ctx["escalations"]["prior_resolutions_by_feature"].get(entry["feature"], [])`. Remove any prose that references `all_entries` or the filter pattern; the new shape is a direct dict-key access.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Co-deployed with Task 6 in the same PR per spec R4 (Edge Cases line 178: the producer and consumer revert must be coupled). The reader prompt is consumed by the orchestrator agent at round time. The `.get(entry["feature"], [])` fallback handles features absent from the dict (no prior resolutions) — this is the dict-equivalent of the previous filter returning an empty list.
- **Verification**: `grep -n 'all_entries' cortex_command/overnight/prompts/orchestrator-round.md` returns 0 hits — pass. `grep -n 'prior_resolutions_by_feature' cortex_command/overnight/prompts/orchestrator-round.md` returns ≥ 1 hit — pass.
- **Status**: [ ] pending

### Task 8: Add round-trip schema-lockstep test for `aggregate_round_context` (R4)

- **Files**: `cortex_command/overnight/tests/test_orchestrator_context_schema_roundtrip.py` (new)
- **What**: Add a pytest module that calls `aggregate_round_context` on a fixture session directory and asserts: (a) the call does not raise `RuntimeError("schema_version drift")`; (b) `escalations` contains exactly the keys `{"unresolved", "prior_resolutions_by_feature"}`; (c) `all_entries` is absent. This locks the inline literal and `_EXPECTED_SCHEMA_VERSION` together — any future drift between them will surface in CI before merge.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**: Existing pattern: see other `cortex_command/overnight/tests/test_*.py` modules for fixture-session-dir setup. The fixture session can be a `tmp_path`-built directory with a minimal `escalations.jsonl` containing one resolution entry and one promotion entry, plus any other files `aggregate_round_context` requires (check the function's read surface). Call signature is `aggregate_round_context(session_dir, round_number=1)` — pass a plausible round number. The assertion on key-set is `set(result["escalations"].keys()) == {"unresolved", "prior_resolutions_by_feature"}`.
- **Verification**: `just test -- cortex_command/overnight/tests/test_orchestrator_context_schema_roundtrip.py` — pass if exit 0.
- **Status**: [ ] pending

### Task 9: Create `bin/cortex-check-events-registry` script + justfile recipes (R5/R6 wiring)

- **Files**:
  - `bin/cortex-check-events-registry` (new, executable, stdlib-only)
  - `justfile` (add two recipes: `check-events-registry` and `check-events-registry-audit`)
- **What**: Create the static-analysis gate modeled on `bin/cortex-check-parity`. Three flags: `--staged` (pre-commit critical path), `--audit` (off-critical-path deprecation review), and `--root <path>` (testability override — when set, scan the directory tree under `<path>` instead of running `git diff --cached --name-only`). `--staged` (without `--root`) scans `git diff --cached --name-only` filtered to `skills/**/*.md` and `cortex_command/overnight/prompts/*.md`. `--staged --root <path>` scans the matching files under `<path>` as if they were all staged (test-only mode). In all modes, the script extracts emitted `event_name` literals via regex and fails if any name is not present in `bin/.events-registry.md`. `--audit` scans the registry itself and fails if any `category=deprecated-pending-removal` row has a `deprecation_date` in the past or a missing `owner` field. Fails closed on missing registry (`MISSING_REGISTRY` error). Error messages in positive-routing form. Include the `cortex-log-invocation` shim in the script's first 50 lines per `.githooks/pre-commit` Phase 1.6. Add justfile recipes that invoke the script in the two modes; reference the script by its path-qualified token so the parity check (W003) is satisfied.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Precedent: `bin/cortex-check-parity` (lines 34, 51, 69, 117 for top-level constants; line 386 for fail-open behavior to OVERRIDE). The new script uses similar SCAN_GLOBS but narrower: `("skills/**/*.md", "cortex_command/overnight/prompts/*.md")`. Event-name extraction regex: `r'"event":\s*"([a-z_]+)"'` against markdown content (skill prompts embed JSONL emit templates in fenced code blocks). Registry parsing: markdown table at `bin/.events-registry.md` with header row defining columns from spec R5; parse with stdlib `csv` after stripping `|` delimiters, or use plain-line splitting. CLI shape: `argparse` with `--staged` / `--audit` mutually-exclusive flags. Exit code 0 on pass, non-zero on any error; print human-readable diagnostics to stderr. The `cortex-log-invocation` shim is a 5-10 line block copied from existing `bin/cortex-*` scripts (e.g., `bin/cortex-check-parity` first 50 lines). stdlib-only — no third-party imports. Justfile recipes: `check-events-registry` runs `bin/cortex-check-events-registry --staged`; `check-events-registry-audit` runs `bin/cortex-check-events-registry --audit`. The justfile reference + the Task-11 test file together satisfy the dual-source parity contract for the new script.
- **Verification**: `test -x bin/cortex-check-events-registry` — pass if exit 0 (script is executable). `bin/cortex-check-events-registry --help` exits 0 with usage text — pass. `head -50 bin/cortex-check-events-registry | grep -c cortex-log-invocation` ≥ 1 — pass. `grep -n '^check-events-registry:' justfile` ≥ 1 — pass. `grep -n '^check-events-registry-audit:' justfile` ≥ 1 — pass.
- **Status**: [ ] pending

### Task 10: Populate `bin/.events-registry.md` with initial rows (R7)

- **Files**: `bin/.events-registry.md` (new)
- **What**: Create the registry file with a header row matching spec R5's schema (`event_name | target | scan_coverage | producers | consumers | category | added_date | deprecation_date | rationale | owner`). Populate rows for: (a) every live skill-prompt / orchestrator-template event surviving Task 2 deletions: `phase_transition`, `feature_complete`, `lifecycle_start`, `batch_dispatch`, `review_verdict`, `dispatch_complete`, `criticality_override`, `clarify_critic` (post-R3), `plan_comparison` — all `scan_coverage: gate-enforced, target: per-feature-events-log, category: live`; (b) every constant in `cortex_command/overnight/events.py:90-148` `EVENT_TYPES` — `scan_coverage: manual, target: overnight-events-log, category: live`, consumers enumerated from research.md's Codebase Analysis; (c) Python emission sites in `cortex_command/pipeline/dispatch.py` (lines 654-808), `cortex_command/pipeline/merge.py` (lines 205-326), `cortex_command/pipeline/conflict.py` (lines 257-442), `bin/cortex-complexity-escalator` — `scan_coverage: manual, category: live`; (d) every event being deleted by Task 2 — `category: deprecated-pending-removal`, `scan_coverage: gate-enforced` (or `manual` if Python), `deprecation_date: 2026-06-10` (today + 30 days per spec R7), `owner: charliemhall@gmail.com`, `rationale` ≥30 chars explaining the deletion.
- **Depends on**: [2a, 2b, 6]
- **Complexity**: complex
- **Context**: The registry's column order must match spec R5. The markdown table format is `| col1 | col2 | ... |` with a separator row `|---|---|...|` after the header. For consumer pointers, prefer `path:line` form (e.g., `cortex_command/pipeline/metrics.py:232`). `human-skim` is allowed as a consumer value only for `category: audit-affordance` rows with a ≥30-char rationale (the post-Task-2 surviving set has no audit-affordance rows; `plan_comparison` has test consumers and qualifies as `live` — record it as `category: live, consumers: tests/<path>:<line> (tests-only)` per spec R5's `tests-only` annotation convention). The `deprecated-pending-removal` rows exist so in-flight features that emit a deleted name during a transitional period don't trigger the gate — these rows are pruned by a follow-up cleanup PR after the 30-day grace period.
- **Verification**: `test -f bin/.events-registry.md` — pass if exit 0. `grep -c '^|' bin/.events-registry.md` ≥ 20 (header + separator + at least 18 data rows covering the live + deprecated event set) — pass. `bin/cortex-check-events-registry --staged` exit code 0 against a clean working tree — pass.
- **Status**: [ ] pending

### Task 11: Self-tests for `bin/cortex-check-events-registry` (R5)

- **Files**: `tests/test_check_events_registry.py` (new)
- **What**: Add ≥ 8 self-test cases per spec R5 acceptance: (1) unregistered skill-prompt name fails pre-commit; (2) registered name with valid consumer passes; (3) audit-mode finding a stale deprecation date errors; (4) pre-commit path NOT firing the date check (passes even with stale rows); (5) audit-mode finding `deprecated-pending-removal` row missing `owner` errors; (6) missing registry file errors with `MISSING_REGISTRY`; (7) `category != live` row missing `rationale` errors; (8) pre-commit path passing a commit unrelated to skill prompts even with stale rows present. Each test sets up a temp directory with `bin/.events-registry.md` fixture content + a staged-files fixture, invokes the script via `subprocess`, and asserts exit code + stderr substring.
- **Depends on**: [9, 10]
- **Complexity**: complex
- **Context**: Use `pytest` with `tmp_path` fixture. Invoke via `subprocess.run(["bin/cortex-check-events-registry", "--staged", "--root", str(tmp_path)], ...)` — the script needs a `--root` flag for testability (or alternatively, invoke with `cwd=tmp_path`). Each test's fixture registry should be the minimal content needed to exercise that case. Assertion form: `assert result.returncode == expected_code` and `assert "<expected substring>" in result.stderr.decode()`.
- **Verification**: `just test -- tests/test_check_events_registry.py` — pass if exit 0 and ≥ 8 test cases collected (`pytest -v` output shows 8+ test ids).
- **Status**: [ ] pending

### Task 12: Wire pre-commit Phase 1.8 (R6)

- **Files**: `.githooks/pre-commit`
- **What**: Add a new "Phase 1.8 — Events-registry enforcement" block between the existing Phase 1.7 (backlog entry-point telemetry-call enforcement, `.githooks/pre-commit:120`) and Phase 2 (dual-source drift). The phase invokes `just check-events-registry --staged` (or equivalent direct invocation). Triggers narrowly on staged paths matching `skills/*`, `cortex_command/overnight/prompts/*`, `bin/cortex-check-events-registry`, `bin/.events-registry.md`. Does NOT include `cortex_command/**/*.py` — Python-only commits do not invoke this phase, so unrelated backend work is never blocked by registry staleness. Failure output points the committer at `bin/.events-registry.md` and the script's error message; no MUST/CRITICAL/REQUIRED phrasing. This task lands last in Wave 2 so that earlier commits in Wave 1 (Tasks 2a/2b deletions) and earlier in Wave 2 (Tasks 9, 10) are not gated by a half-installed registry.
- **Depends on**: [9, 10, 11]
- **Complexity**: simple
- **Context**: Existing Phase 1.5 (SKILL.md-to-bin parity) is the structural precedent in the same file; mirror its trigger-on-paths shape. The trigger-path matching uses the existing `git diff --cached --name-only` pattern from earlier phases. The phase is gated by staged-paths so a commit that touches none of the trigger paths short-circuits (exit 0 without invoking the gate).
- **Verification**: `grep -n 'Phase 1.8' .githooks/pre-commit` ≥ 1 — pass. `grep -n 'check-events-registry' .githooks/pre-commit` ≥ 1 — pass. After installing the hook (`just setup-githooks`), staging a skill-prompt edit that adds an unregistered event name and attempting `git commit -m test --dry-run` fails non-zero with the registry error message — pass (manual verification step recorded in PR description).
- **Status**: [ ] pending

### Task 13: CHANGELOG entry + `docs/internals/events-registry.md` (R8)

- **Files**:
  - `CHANGELOG.md` (append a new entry)
  - `docs/internals/events-registry.md` (new)
  - `docs/internals/pipeline.md` (add link to the new registry doc near its events.log discussion)
  - `docs/overnight-operations.md` (add link to the new registry doc near its events.log discussion)
- **What**: Append a CHANGELOG entry summarizing: events removed (R1 DELETE rows by name), `clarify_critic` schema bump v2→v3 (R3), `aggregate_round_context` schema bump v1→v2 (R4), new `bin/cortex-check-events-registry` gate (R5/R6). Create `docs/internals/events-registry.md` describing the registry schema (column-by-column), the `gate-enforced` vs `manual` scope split, the two-mode (`--staged` pre-commit critical-path vs `--audit` off-critical-path) design, the deprecation lifecycle, and the stale-row recovery path (`--audit` surfaces stale rows; `owner` field identifies who runs the cleanup PR; rows can be bumped with a rationale update). Add one-line cross-reference links from `docs/internals/pipeline.md` and `docs/overnight-operations.md` where they discuss events.log to the new registry doc.
- **Depends on**: [2a, 2b, 4, 6, 9, 10, 12]
- **Complexity**: simple
- **Context**: Existing CHANGELOG.md format: scan the last 3-5 entries to match style (date header, bulleted change list). The new docs/internals/ file follows the existing pattern of `docs/internals/pipeline.md` and `docs/internals/mcp-contract.md` — markdown, no frontmatter required, headed sections for Schema / Scope / Modes / Deprecation Lifecycle / Recovery. No user-side cleanup paths required per spec R8 acceptance (deletions affect emission only; archived rows remain parseable via Tolerant-Reader semantics).
- **Verification**: `grep -n 'cortex-check-events-registry' CHANGELOG.md` ≥ 1 — pass. `test -f docs/internals/events-registry.md` — pass. `grep -n 'events-registry' docs/internals/pipeline.md` ≥ 1 — pass. `grep -n 'events-registry' docs/overnight-operations.md` ≥ 1 — pass.
- **Status**: [ ] pending

## Verification Strategy

End-to-end verification after all tasks:

1. `just test` — full test suite passes (covers Tasks 5, 8, 11 plus regression against existing tests; Tolerant-Reader behavior for in-flight features with pre-cut events).
2. `just check-events-registry` — pre-commit-mode gate passes against a clean working tree (Tasks 9, 10 wired).
3. `just check-events-registry-audit` — audit-mode gate passes (no stale `deprecation_date` at implementation time; all `deprecated-pending-removal` rows have `owner`).
4. Manual: stage a skill-prompt edit that introduces a hypothetical new event name not in `bin/.events-registry.md`, attempt `git commit`; commit is rejected with the positive-routing registry error message (Task 12).
5. Manual: read three recent archived features' `events.log` files to confirm legacy v2 `clarify_critic` rows parse cleanly under the v3 reader (Tolerant-Reader; legacy-tolerance table extension in Task 4).
6. Manual: run a one-round overnight session against a fixture feature, confirm `aggregate_round_context` returns the new shape without raising `RuntimeError("schema_version drift")` and the `orchestrator-round.md` consumer reads `prior_resolutions_by_feature` (Tasks 6, 7).

## Veto Surface

- **30-day deprecation grace window vs the 25-day batch cadence**: spec R7 sets `deprecation_date: today + 30 days` for deleted events to leave headroom over the observed ~25-day batch cadence. If a shorter window is preferred (e.g., 14 days to match the parity-linter precedent), the plan downstreams a single date-string change in Task 10. Recommend keeping 30 days for the larger safety margin given this is the first deprecation cycle for this gate.
- **`bin/.events-registry.md` location vs `events/events-registry.md`**: spec chose `bin/.events-registry.md` for `.parity-exceptions.md` precedent fit. If the user prefers a top-level `events/` directory for discoverability, the plan changes the path in Tasks 9, 10, 12, 13 (single string find-and-replace). Recommend keeping `bin/.events-registry.md` per spec.
- **Task 1 reclassification scope**: if Task 1's re-grep surfaces a real consumer for any DELETE-row event (e.g., a forgotten `hooks/` shell script greps for one of them), that event is reclassified inline in spec.md and excluded from Task 2's deletion list. The plan tolerates up to ~3 reclassifications without restructuring; more than that suggests the audit's "verified-dead" claim was less reliable than asserted and the user may want to pause for re-research.
- **No consumer-side runtime drift detector** (D1 deferred per spec Non-Requirements). The producer-side static gate cannot catch a runtime invention where Claude emits a name not in any source file. The user may want to pull this in scope; spec marks it explicitly deferred.
- **No CODEOWNERS protection on `bin/.events-registry.md`** (Non-Requirements). Anyone with repo write access can add rows; this is the same trust model as `.parity-exceptions.md` today.

## Scope Boundaries

Per spec Non-Requirements:
- No consumer-side runtime drift detector (`cortex-validate-events`); deferred D1.
- No automatic detection of new Python emission sites by the CI gate; Python sites are documented manually in the registry.
- No retroactive rewrite of `lifecycle/archive/` events.log files.
- No 2-tier `events.log` + `events-detail.log` split (deferred per epic #172).
- No OpenTelemetry-style structured tracing.
- No changes to live-consumer parsing logic (`extract_feature_metrics`, `parse_feature_events`, statusline) beyond what R3/R4 strictly require.
- No runtime emission registry for skill-prompt path; CI-time gate is the discipline mechanism.
- No CODEOWNERS protection on `bin/.events-registry.md` for v1.
- No new `CLAUDE.md` policy entry; gate error messages use positive-routing form.
- No `clarify-critic-findings.json` sibling artifact; R3 is inline-only payload pruning.
- No pre-commit-path `deprecation_date` enforcement; stale rows surface only via `--audit`.
