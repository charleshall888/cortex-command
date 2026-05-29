# Specification: retire-or-re-establish-the-orphaned

## Problem Statement

After #269 removed the "Why N pieces" falsification gate from discovery prose, the code/schema subsystem that encoded it was left orphaned. Research (4 agents + adversarial) found the orphan extends beyond #270's defined scope: of the three R8b "audit-affordance" discovery events, **two are fully orphaned** — `architecture_section_written` (carries the dead `has_why_n_justification` field; this is the surface #269 deferred to #270) and `prescriptive_check_run` (its real check moved to the `cortex-check-prescriptive-prose` pre-commit hook; this event is **not** named anywhere in #270's ticket body and was **not** part of #269's deferral) — while only `approval_checkpoint_responded` is still emitted by live skill prose. Both orphans have no live emitter, a false `producers` attribution, and a dangling consumer reference to a nonexistent test file (`tests/test_discovery_events.py`) — a defect that is in fact **family-wide**: the live surviving row carries it too. The dangling references are documentation falsehoods and the orphans waste maintenance attention (every reader asks "who emits this?"). Retiring both orphans together — rather than retiring one and leaving an identical follow-up for the second — is a deliberate scope expansion beyond #270's ticket body, justified by the project's Solution-horizon "durable version" principle (the same patch applies to two nameable places, sharing the same module and the same path-routing test). This expansion is surfaced explicitly at the approval gate for the operator to ratify or veto. The chosen direction is **retire**, consistent with #269's approved conform-down posture; re-establishing the Why-N gate was rejected (no demonstrated demand, and it would reverse #268/#269/ADR-0007).

## Phases

- **Phase 1: Retire orphaned event code & registry rows** — remove the two orphaned events (and the dead Why-N field/flag) from `cortex_command/discovery.py`, delete their `bin/.events-registry.md` rows, and repoint the surviving live row's dangling consumer reference.
- **Phase 2: Reconcile tests, fixtures & changelog** — surgically reduce the shared path-routing test to the one surviving event, delete the dead-path test functions and field assertions, conform the one stale fixture, and record the retirement in `CHANGELOG.md`.

## Requirements

1. The `architecture_section_written` event, its `emit_architecture_written` function, its `emit-architecture-written` CLI subcommand, and the `has_why_n_justification` field + `--has-why-n-justification` flag are fully removed from `cortex_command/discovery.py`, including the `_coerce_bool_namespace` helper, whose sole caller is the removed `--has-why-n-justification` flag and which therefore becomes dead code. Acceptance: `grep -c 'architecture_section_written\|has_why_n_justification\|emit-architecture-written' cortex_command/discovery.py` = 0 AND `grep -c '_coerce_bool_namespace' cortex_command/discovery.py` = 0. (The second criterion is required because the helper's name contains none of the first criterion's tokens, so the token grep alone cannot detect leftover dead helper code — the exact orphan-residue failure this ticket exists to eliminate.) **Phase**: Phase 1: Retire orphaned event code & registry rows

2. The `prescriptive_check_run` event, its `emit_prescriptive_check` function, and its `emit-prescriptive-check` CLI subcommand are fully removed from `cortex_command/discovery.py`. Acceptance: `grep -c 'prescriptive_check_run\|emit-prescriptive-check' cortex_command/discovery.py` = 0. **Phase**: Phase 1: Retire orphaned event code & registry rows

3. Both orphaned event rows are removed from `bin/.events-registry.md` (hard delete — no deprecation tombstone). Acceptance: `grep -c 'architecture_section_written\|prescriptive_check_run' bin/.events-registry.md` = 0. **Phase**: Phase 1: Retire orphaned event code & registry rows

4. The surviving `approval_checkpoint_responded` row is preserved and its dangling consumer reference (the nonexistent `tests/test_discovery_events.py`) is repointed to the real consumer (`tests/test_discovery_module.py`), so no registry row references the nonexistent file. Acceptance: `grep -c 'approval_checkpoint_responded' bin/.events-registry.md` = 1 AND `grep -c 'test_discovery_events.py' bin/.events-registry.md` = 0. **Phase**: Phase 1: Retire orphaned event code & registry rows

5. The stale `### Why N pieces` heading is removed from the one fixture that still carries it; the other two fixtures are already conformed and are not touched. Acceptance: `grep -c '### Why N pieces' tests/fixtures/discovery-brief/complex-topic/research.md` = 0 AND `grep -rc '### Why N pieces' tests/fixtures/discovery-brief/` totals 0. **Phase**: Phase 2: Reconcile tests, fixtures & changelog

6. The dead-path test functions for both orphaned events are removed from `tests/test_discovery_module.py`, the `has_why_n_justification` kwargs/assertions are stripped, and the `--help`/CLI test no longer asserts the removed subcommands. The shared path-routing test (`test_emit_subcommands_honor_resolve_events_log_path`) exists to prove *cross-emitter* path-resolution parity across three emitters; with only `approval_checkpoint_responded` surviving, that parity property is no longer expressible by a single emitter. Therefore the surviving emitter's path-resolution assertion is folded into a dedicated single-emitter test (or the existing `emit_checkpoint_response` test) and the now-degenerate multi-emitter test is removed — cross-emitter parity coverage is **intentionally retired** (a single emitter cannot diverge from itself), not silently dropped while claiming preservation. Acceptance: `just test` exits 0 AND `grep -c 'architecture_section_written\|prescriptive_check_run' tests/test_discovery_module.py` = 0 (no test asserts on a retired event). **Phase**: Phase 2: Reconcile tests, fixtures & changelog

7. The events-registry gates pass after the row removals and consumer-reference repoint. Acceptance: `just check-events-registry` exits 0 AND `just check-events-registry-audit` exits 0. **Phase**: Phase 1: Retire orphaned event code & registry rows

8. The retirement is recorded under the existing `## [Unreleased]` section of `CHANGELOG.md` (not inside a shipped release block such as `## [v2.0.0]`), noting Tolerant-Reader compatibility of any already-archived event rows. Acceptance: `grep -c 'architecture_section_written' CHANGELOG.md` ≥ 1 AND the new entry's line number is greater than the `## [Unreleased]` heading's line number and less than the next `## [` heading's line number (placement is under Unreleased, verifiable with `grep -n`). **Phase**: Phase 2: Reconcile tests, fixtures & changelog

### Priority (MoSCoW)

All eight requirements are **Must** for this cleanup, in two tiers:

- **Blocking-Must (1, 2, 3, 6, 7)** — without all of these the end-state is inconsistent or `just test` / the registry gates fail.
- **Consistency-Must (4, 5, 8)** — the family-wide dangling-ref repoint (4), the fixture conform #269 deferred here (5), and the convention-required CHANGELOG entry (8). These ship in the same change, not deferred: leaving a known-false consumer reference on the live row while editing that exact registry file, or skipping the #269-deferred fixture, would re-create the residue this ticket exists to remove. (Req 4 was reclassified Should→Must after critical review — invoking the durable-version principle to expand scope to a second orphan while filing the family-wide honesty fix as droppable was inconsistent.)
- **Won't (this ticket)**: re-establish the Why-N gate; touch or retire the live `approval_checkpoint_responded` event itself; add a deprecation tombstone; migrate/rewrite historical event logs; add a read-side compatibility shim; alter the prescriptive-prose pre-commit enforcement. (Enumerated in Non-Requirements.)

## Non-Requirements

- Does NOT touch, retire, or alter the live `approval_checkpoint_responded` event, its emitter, or its subcommand — only its stale consumer-reference cell is corrected.
- Does NOT re-establish the Why-N falsification gate in the research template or `SKILL.md` (option (c) rejected — no demonstrated demand; reverses the accepted conform-down posture).
- Does NOT add a `deprecated-pending-removal` tombstone or 30-day grandfather window. That precedent protects in-flight prose sessions still emitting a just-removed event; neither orphan was ever emitted by live prose, so there are no in-flight emitters to protect — hard delete is correct.
- Does NOT migrate, rewrite, or delete historical `events.log` files that contain these event rows; they remain on disk and parseable.
- Does NOT add a historical-compatibility read-side shim. That pattern (project.md) governs deleted *pipeline modules* with archived-log readers; no Python reader parses these discovery events, so the pattern does not apply.
- Does NOT modify the prescriptive-prose enforcement itself — the `cortex-check-prescriptive-prose` pre-commit hook is the live mechanism and stays untouched; only the vestigial `prescriptive_check_run` event is removed.
- Does NOT remove or alter the `DRIFTED_VOCAB_TOKENS` drift-guard in `tests/test_discovery_gate_presentation.py` (which negatively asserts the retired `Why N pieces` token stays absent from `skills/discovery/SKILL.md`). It is deliberately retained as a regression guard against the vocabulary drifting back; `SKILL.md` already lacks the token, so `just test` stays green. This surface was reviewed and intentionally left in place — it is not a missed touch point.

## Edge Cases

- **Archived event logs contain the retired event types** (e.g. `cortex/research/interactive-overnight-mode/events.log`, `cortex/lifecycle/reframe-.../events.log`): expected behavior — they remain on disk and parseable. No reader errors, because no Python reader parses these event names (verified) and all event readers tolerate unknown event types. One archived row even carries a `status` value no longer in the current validator set, confirming these are non-reproducible historical artifacts, not live output.
- **Shared path-routing test co-asserts all three sibling events**: removing two of three must reduce the expected event set to exactly `{"approval_checkpoint_responded"}` and the count assertion to 1. Expected behavior — an incorrect count (e.g. leaving it at 2) would assert an impossible state; the gate is `just test` green plus the surviving assertion naming only the live event.
- **Top-level test imports of the removed functions**: the test module imports the emit functions at module scope, so a partial deletion (code removed, imports/tests not) fails the entire file at collection. Expected behavior — the code deletions and test edits reach a consistent working state together before `just test` is evaluated.
- **A future need for an architecture-write audit affordance**: out of scope. If one later arises, it is re-added against the then-current template vocabulary (the current schema still encodes the retired Why-N concept, so it would not be reused verbatim); retaining the dead event now buys no usable head start.

## Changes to Existing Behavior

- REMOVED: the `architecture_section_written` and `prescriptive_check_run` events, their `emit-architecture-written` / `emit-prescriptive-check` CLI subcommands, and the `--has-why-n-justification` flag (`cortex_command/discovery.py`). These were never invoked by any live skill; the CLI surface shrinks by two subcommands.
- REMOVED: the two corresponding rows in `bin/.events-registry.md`.
- MODIFIED: the surviving `approval_checkpoint_responded` registry row's `consumers` cell — repointed from the nonexistent `tests/test_discovery_events.py` to the real `tests/test_discovery_module.py`.
- REMOVED: the stale `### Why N pieces` section from `tests/fixtures/discovery-brief/complex-topic/research.md`.

## Technical Constraints

- **Hard delete, not tombstone** — see Non-Requirements rationale.
- **Events-registry gate behavior**: the two orphan rows carry `scan_coverage=gate-enforced`, but the staged-mode gate scans only skill-prompt/`prompts` sources for unregistered emissions — it does not scan Python and does not stat producer/consumer files. Hard-deleting the rows is safe specifically because **no skill prose emits these event names** (verified), not because of their `audit-affordance` category; the live `approval_checkpoint_responded` emission in `decompose.md`/`SKILL.md` correctly keeps its row required. Both `just check-events-registry` and `just check-events-registry-audit` exit 0 today and must after the deletion (Req 7).
- **Backlog grep-target gate**: do NOT author a `grep -c "architecture_section_written"` (or `prescriptive_check_run`) Done-When in the #270 *backlog* ticket body — after retirement the token resolves in neither `bin/.events-registry.md` nor `cortex_command/`, and `tests/test_backlog_grep_targets_resolve.py` would fail. (Acceptance criteria living in this spec are safe; that test scans only `cortex/backlog/*.md`.)
- **No dual-source mirror**: `cortex_command/discovery.py`, `tests/`, the fixtures, and `bin/.events-registry.md` are single-source — they have no `plugins/` mirror, so no parity-driven double edits. (Only option (c), rejected, would have touched mirrored `skills/` files.)
- **Validation coupling**: the code deletions and the test reconciliation must land in a consistent working state together before `just test` is meaningful (module-scope import coupling).

## Open Decisions

None deferred to implementation. The resolution direction (retire), the option among a/b/c (retire-event), and the dangling-ref fix scope (family-wide) are resolved. The one operator-facing choice — expand scope to the second orphan (`prescriptive_check_run`) vs. keep #270 narrow and file a sibling follow-up — is **not** an implementation-level decision; it is presented for the operator to ratify or veto at the §4 approval gate (see Problem Statement). The spec is drafted for the expand-to-both option; a veto narrows it to `architecture_section_written` only and reverts Req 2 plus the `prescriptive_check_run` portions of Reqs 3/6 to a sibling ticket.

## Proposed ADR

None considered.

<!-- The retirement follows the already-accepted #268/#269/ADR-0007 conform-down posture; it is easily reversed (git), unsurprising given the lineage, and its trade-off was resolved by research — so it does not meet the three-criteria ADR gate. Re-establishing the Why-N gate (option c) WOULD have been ADR-shaped, but it was rejected. -->
