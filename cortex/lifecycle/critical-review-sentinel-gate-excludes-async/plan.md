# Plan: critical-review-sentinel-gate-excludes-async

## Overview

Layer a gate-time re-hash into the critical-review CLI command wrappers so a missing `READ_OK` sentinel is disambiguated against the pinned artifact: stable → advisory pass, drifted → hard-fail. The pure verifier text-parsers stay untouched; a new `sentinel_advisory` event keeps exclusion telemetry meaningful and is registered with its phantom-lifecycle consumer. Then delete the doc/prompt language that caused and would re-seed the bug, and record the contract change as ADR-0028.
**Architectural Pattern**: layered

## Outline

<!-- Phases below are a narrative grouping. The overnight executor schedules by `Depends on` only (compute_dependency_batches), ignoring phase headings: Batch 0 = tasks 1, 2, 5, 6 (no deps); Batch 1 = tasks 3, 4 (depend on [2]). Task verifications are therefore self-contained per task and do not assume a phase boundary; no per-task verification runs the full `just test` suite (which would race concurrent siblings in the shared worktree). Whole-suite green is the Acceptance/checkpoint contract, established once all batches merge. -->

### Phase 1: Re-hash gate + advisory telemetry (tasks: 1, 2, 3, 4)
**Goal**: an absent sentinel with a provably-stable pinned artifact passes (exit 0, `sentinel_advisory`) instead of tripping total-failure; genuine drift still hard-fails (exit 3, `sentinel_absence`); the phantom-lifecycle consumer and gate docs stay in lock-step.
**Checkpoint**: `just test` green; a sentinel-free reviewer output whose `--artifact-path` re-hashes to the pinned SHA yields CLI exit 0 with a `sentinel_advisory` row, and a drifted path yields exit 3.

### Phase 2: Doc/prompt correction + ADR (tasks: 5, 6)
**Goal**: remove the "raw stdout" / "preamble prose before it is fine" language that seeds the bug, reframe the sentinel as advisory, and record the contract change.
**Checkpoint**: `grep -c "raw stdout" verification-gates.md` = 0, `grep -c "preamble prose before it is fine" reviewer-prompt.md` = 0, `cortex/adr/0028-*.md` present, mirror parity green.

## Tasks

### Task 1: Register `sentinel_advisory` with the phantom-lifecycle consumer
- **Files**: `cortex_command/common.py`, `tests/test_phantom_dir_discriminator.py`
- **What**: Add `"sentinel_advisory"` to the `_TELEMETRY_ONLY_EVENT_TYPES` frozenset so `is_phantom_lifecycle_dir` still classifies a telemetry-only dir carrying the new event; add a discriminator test for it.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `cortex_command/common.py:604` `_TELEMETRY_ONLY_EVENT_TYPES: frozenset[str] = frozenset({"synthesizer_drift", "sentinel_absence"})`; consumer `is_phantom_lifecycle_dir` at `common.py:610`, subset test `event_types <= _TELEMETRY_ONLY_EVENT_TYPES` at `common.py:672`. Existing discriminator tests live in `tests/test_phantom_dir_discriminator.py` — mirror their fixture pattern (a lifecycle dir whose events.log holds only telemetry events and no research/spec/plan artifact).
- **Verification**: `grep -c '"sentinel_advisory"' cortex_command/common.py` = 1; `python3 -m pytest tests/test_phantom_dir_discriminator.py -q` exits 0 with a new case asserting `is_phantom_lifecycle_dir` returns `True` for a dir whose only events are `sentinel_advisory`.
- **Status**: [ ] pending

### Task 2: Wrapper re-hash + `sentinel_advisory` emission + events-registry
- **Files**: `cortex_command/critical_review/__init__.py`, `bin/.events-registry.md`
- **What**: Add an **optional** `--artifact-path` argument to the `check-artifact-stable` and `check-synth-stable` subparsers; in `_cmd_check_artifact_stable` and `_cmd_check_synth_stable`, when the pure verifier returns `absent` AND `--artifact-path` was provided, re-hash it with `sha256_of_path` — match → exit 0 emitting a `sentinel_advisory` event; mismatch/unreadable → today's exit 3 + `sentinel_absence`. When `--artifact-path` is omitted, keep today's exact behavior (`absent` → exit 3 + `sentinel_absence`) so existing callers/tests are unaffected. Register `sentinel_advisory` in `bin/.events-registry.md` and add a dated rebaseline note recording `sentinel_absence`'s narrowed post-fix meaning.
- **Depends on**: none
- **Complexity**: complex
- **Context**: Pure verifiers `check_artifact_stable` (`__init__.py:398-456`, returns `("absent", None)` on no sentinel — leave unchanged) and `check_synth_stable` (`:350-386`); CLI wrappers `_cmd_check_artifact_stable` (`:677-748`) and `_cmd_check_synth_stable` (`:613-674`); argparse for the subcommands at `:840-894`; `sha256_of_path` helper at `:287`; exit-code constants (exit 0 pass, 3 exclude, 4 telemetry-skip). The re-hash + advisory decision must sit **before** the exit-4 telemetry write-guard so an advisory-clean result returns exit 0 (not exit 4). The advisory event must NOT be a new `reason` value on `sentinel_absence` (that still emits a `sentinel_absence` row); it is a new event *name*. Do not add a new pure-verifier return literal (keeps `_VERIFIER_SITE_RE` and gate-class parity unaffected). Any new annotated decision site in the wrapper carries a `# gate-class: advisory` comment (note: the gate-class parity test scans only the pure verifiers, not the `_cmd_*` wrappers, so this annotation is convention, not test-enforced). `bin/.events-registry.md:103` holds the `sentinel_absence` row (mirror its prior #229 rebaseline-note style). Register `sentinel_advisory` per the project's "new events register in `bin/.events-registry.md`" convention — note this is NOT enforced by the events-registry pre-commit gate, which scans only `skills/**/*.md` and `cortex_command/overnight/prompts/*.md`, never the Python emission site.
- **Verification**: create a throwaway lifecycle dir `cortex/lifecycle/_probe376/` and a temp file F (SHA S) plus a sentinel-free input file; `cortex-critical-review check-artifact-stable --feature _probe376 --reviewer-angle probe --expected-sha S --model-tier sonnet --input-file <sentinel-free> --artifact-path F` exits 0 and appends a `sentinel_advisory` row to `cortex/lifecycle/_probe376/events.log`; re-running after mutating F exits 3 with `sentinel_absence`; invoking the same command WITHOUT `--artifact-path` exits 3 (backward-compat). Remove the throwaway dir after. `grep -c "sentinel_advisory" bin/.events-registry.md` ≥ 1.
- **Status**: [ ] pending

### Task 3: Wrapper-level tests and fixtures (both artifact AND synth paths)
- **Files**: `tests/test_critical_review_sentinel_window.py`, `tests/fixtures/critical-review/reviewer-outputs/`
- **What**: Add wrapper-level tests for the three new outcomes on **both** `_cmd_check_artifact_stable` AND `_cmd_check_synth_stable` (absent+`--artifact-path`-stable→exit 0+`sentinel_advisory`; absent+drift→exit 3+`sentinel_absence`; absent+unreadable→exit 3; and absent+no-`--artifact-path`→exit 3 backward-compat); add a new fixture (sentinel-absent-but-stable) with a sibling `.meta.json`. Because `--artifact-path` is optional, no existing CLI-invoking test needs modification — confirm they and the three pure-verifier `("absent", None)` tests remain unchanged and green.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: Pure-verifier tests that MUST stay green unmodified: `test_sentinel_absent_returns_absent` (`test_critical_review_sentinel_window.py:91`), `test_sentinel_in_evidence_quote_past_window_returns_absent` (`:127`), `test_window_size_default_is_50` (`:228`). The synth wrapper `_cmd_check_synth_stable` (`__init__.py:613`) is a distinct function from `_cmd_check_artifact_stable` (`:677`) — test its advisory/drift/unreadable branch explicitly, not just the artifact sibling. Unchanged CLI-invoking tests to confirm green: `tests/test_critical_review_phantom_guard.py`, `tests/test_variant_a_writer_sites_baseline.py`. Fixture corpus README warns against casual re-baselining — ADD, don't substitute.
- **Verification**: `python3 -m pytest tests/test_critical_review_sentinel_window.py tests/test_critical_review_phantom_guard.py tests/test_variant_a_writer_sites_baseline.py -q` exits 0, with the run including at least one `_cmd_check_synth_stable` advisory-outcome test (grep the test file for a synth advisory case).
- **Status**: [ ] pending

### Task 4: Gate routing + doc-hygiene in verification-gates.md and SKILL.md
- **Files**: `skills/critical-review/references/verification-gates.md`, `skills/critical-review/SKILL.md`
- **What**: Update Steps 2c.5/2d.5 Exit-0/Exit-3 rows to describe the re-hash disambiguation (absent+stable → advisory pass; absent+drift → exclusion) and add `--artifact-path <resolved_path>` to **both** invocation blocks — the 2c.5 `check-artifact-stable` block AND the 2d.5 `check-synth-stable` block; also add it to the inline `check-synth-stable` invocation in SKILL.md (the line that currently reads `check-synth-stable --feature <name> --expected-sha <hex>`); delete the "raw stdout" mental model (replace with "the final message the Agent tool returns"); keep the total-failure literal byte-identical.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**: `verification-gates.md` Step 2c.5 route table (`:21-56`, "raw stdout" at `:27`, `check-artifact-stable` invocation block at `:29-36`, total-failure literal `:48-50`), Step 2d.5 (`:58-76`, `check-synth-stable` block at `:62-66`); SKILL.md inline `check-synth-stable` invocation at `:67` (a live 2-flag command, not just a pointer). Because `--artifact-path` is optional, a missed caller degrades to today's exclusion rather than crashing — but update all three for the fix to take effect. NOTE: `cortex-check-contract`'s missing-required-flag check is placeholder-suppressed for these `<...>`-token invocations, so no automated gate catches a missed edit — the anchored greps below ARE the gate. Mirror `plugins/cortex-core/skills/critical-review/**` regenerates via pre-commit — edit canonical only; leave the total-failure literal byte-identical so `test_critical_review_reference_pins.py` stays green.
- **Verification**: `grep -c "raw stdout" skills/critical-review/references/verification-gates.md` = 0; the `check-artifact-stable` invocation carries the flag — `grep -A7 "check-artifact-stable \\\\" skills/critical-review/references/verification-gates.md | grep -c "artifact-path"` ≥ 1; the synth block carries it — `grep -A5 "check-synth-stable \\\\" skills/critical-review/references/verification-gates.md | grep -c "artifact-path"` ≥ 1; SKILL.md's inline synth invocation carries it — `grep "check-synth-stable" skills/critical-review/SKILL.md | grep -c "artifact-path"` ≥ 1; `python3 -m pytest tests/test_critical_review_reference_pins.py -q` exits 0 (total-failure literal unchanged).
- **Status**: [ ] pending

### Task 5: Reframe the reviewer/synthesizer sentinel prose as advisory
- **Files**: `skills/critical-review/references/reviewer-prompt.md`, `skills/critical-review/references/synthesizer-prompt.md`
- **What**: Delete "preamble prose before it is fine" from `reviewer-prompt.md`; reframe the `READ_OK`/`SYNTH_READ_OK` instruction as an advisory read-attestation (no longer the load-bearing gate) consistent with the new gate semantics, without adding MUST language and without relocating emission to the final message.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `reviewer-prompt.md:17` ("emit READ_OK ... before the first `## ` heading — preamble prose before it is fine"); `synthesizer-prompt.md:16` (`SYNTH_READ_OK ... before any per-finding analysis`). Removing prose only (MUST-escalation compliant). Mirror regenerates via pre-commit — edit canonical only; keep the four load-bearing voice anchors intact.
- **Verification**: `grep -c "preamble prose before it is fine" skills/critical-review/references/reviewer-prompt.md` = 0; `grep -ci "advisory" skills/critical-review/references/reviewer-prompt.md` ≥ 1; `grep -ci "advisory" skills/critical-review/references/synthesizer-prompt.md` ≥ 1 (the synth prompt is reframed too, not just the reviewer prompt).
- **Status**: [ ] pending

### Task 6: Author ADR-0028
- **Files**: `cortex/adr/0028-gate-time-rehash-is-authoritative-drift-check.md`
- **What**: Write the ADR recording the decision to demote the read-sentinel to advisory and make the gate wrapper's re-hash authoritative on the absent branch, with the transient-drift blind spot (including mixed-cohort admission) as the accepted trade-off; cite ADR-0015 as precedent.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Follow `cortex/adr/README.md` structure (three-criteria gate, status, context/decision/consequences); precedent `cortex/adr/0015-review-could-not-run-vs-dispatch-crash-split.md`. Content is drafted in spec.md `## Proposed ADR`. Highest existing ADR is 0027.
- **Verification**: `test -f cortex/adr/0028-gate-time-rehash-is-authoritative-drift-check.md`; `grep -rl "0028" cortex/adr/` resolves; the file carries the README-required sections (`grep -cE "^## (Context|Decision|Consequences|Status)" cortex/adr/0028-*.md` ≥ 3); if the repo enforces an ADR-citation/index audit, run that targeted check (not the whole suite) and it passes.
- **Status**: [ ] pending

## Risks
- **Transient-drift blind spot (accepted).** Gate-time re-hash cannot catch change-then-restore-to-identical-SHA within one window, including mixed-cohort admission; documented in spec Edge Cases + ADR-0028, not engineered against. Revisit only if a concrete exploit emerges.
- **`--artifact-path` is optional, not required (refined from the approved spec after the plan-phase critical review).** The plan-phase review showed `required` maximizes blast radius — an atomic doc↔argparse flip, a cross-commit window where committed code demands the flag but committed orchestrator prose still omits it (unguarded, since `cortex-check-contract` is placeholder-suppressed for `<...>` invocations), and churn of two unrelated tests. Optional keeps every existing caller/test working, stays fail-closed (omission degrades to today's safe exclusion, never a false pass), and preserves fail-loud on real drift via the re-hash mismatch branch. The one residual: a caller that forgets `--artifact-path` silently keeps the old behavior for that call site — mitigated by updating all three known callers (Task 4) and by the change being fail-closed. Spec R1/Open Decisions updated to match.
- **Batch-0 commit contention (accepted, retry-absorbed).** Task 5 edits `skills/critical-review/references/*.md`, whose commit triggers the pre-commit `just build-plugin` mirror regeneration, while sibling Batch-0 tasks (1, 2, 6) commit into the same shared feature worktree — the documented dual-source-drift `.git/index.lock` contention. The overnight commit-retry loop absorbs this; no explicit serialization edge is added since the alternative (forcing a false dependency) would cost more than the occasional retry.

## Acceptance
Running the critical-review gate on a pinned artifact that is unchanged but whose reviewers omit `READ_OK` now PASSES (advisory, exit 0, `sentinel_advisory`) instead of tripping total-failure, while a genuinely drifted artifact still hard-fails (exit 3, `sentinel_absence`); `is_phantom_lifecycle_dir` handles the new event; `just test` is green; the bug-seeding "raw stdout"/"preamble prose before it is fine" language is gone and ADR-0028 records the contract change.
