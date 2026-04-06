# Research: Address verification_passed dead code in exit reports

## Codebase Analysis

### Files involved

- **`claude/pipeline/prompts/implement.md`** — single source of truth for exit report schema. `verification_passed` appears at line 83 (schema table), line 95 (complete example), line 106 (question example). `committed` appears at lines 82, 94, 105 with the same dead-code pattern.
- **`claude/overnight/batch_runner.py`** — `_read_exit_report()` (line 419) returns `tuple[str | None, str | None, str | None]` (action, reason, question). Called in exactly one production location: `execute_feature()` at line 969. Uses `data.get()` for known keys and ignores all other fields.
- **`claude/overnight/events.py`** — event type registry (~35 constants in `EVENT_TYPES` tuple). Existing worker events: `WORKER_NO_EXIT_REPORT`, `WORKER_MALFORMED_EXIT_REPORT`.
- **`claude/overnight/tests/test_exit_report.py`** — 9 test cases for `_read_exit_report`, 5 scenarios for the validation loop. All assert against 3-tuple returns.
- **`claude/overnight/conflict.py`** — has a separate `_read_exit_report()` closure (line 304) with return type `Optional[dict]`. Completely unrelated; the repair agent prompt uses a different exit report schema that never included `verification_passed`.

### Dead fields

Both `verification_passed` and `committed` are dead code with the same pathology: written by builder agents in exit reports, never read by any Python code in the entire codebase. No Python file, shell script, dashboard, or morning report consumer reads these fields.

### Existing patterns

- Event constants use `SCREAMING_SNAKE_CASE` with `lower_snake_case` string values
- `_read_exit_report()` is tolerant of extra fields (uses `data.get()`)
- The validation loop in `execute_feature()` follows: read report → handle `question` → handle malformed → fall through to completion

## Web Research

### Self-reported verification is a known anti-pattern

- **opslane/verify**: External verification layer for Claude Code that replaces self-reported verification with independent Opus judge + parallel Sonnet browser agents checking acceptance criteria. Principle: "You can't trust what an agent produces unless you told it what 'done' looks like before it started."
- **Blake Crosley's Stop Hook pattern**: Documents "Phantom Verification" anti-pattern (agents claiming tests pass without running them). Solution: PreToolUse hook that runs tests independently. False completion dropped from 35% to 4%.
- **Martin Fowler's Harness Engineering**: Categorizes verification into feedforward (preventive) and feedback (corrective) controls. Emphasizes computational sensors (type checkers, linters, tests) over LLM-based inferential sensors. Self-reported verification is "more non-deterministic."
- **Augment Code's Pre-Merge Verification Guide**: "AI-generated tests often share the same blind spots as the code generator." Recommends advisory mode before enforcement. When enabled, verification must block merges, not merely notify.

### Dead fields are "boat anchor" anti-patterns

The `verification_passed` field fits the Boat Anchor anti-pattern: code kept in a system despite having no use. YAGNI applies — remove unused code rather than keeping it speculatively. Key risk: boat anchors "obscure the true functionality of the codebase, leading to confusion and errors."

### Industry consensus

Every reference implementation moves toward external verification, not trusting agent self-reports. The distinction between confidence (self-reported) and verification (externally proven) is fundamental. `verification_passed: true` from an agent is a confidence signal, not verification evidence.

## Requirements & Constraints

### No requirement specifies verification_passed

No requirements file defines which fields an exit report must contain. Only `action` is referenced in requirements — for deferral triggering (`requirements/pipeline.md` line 70) and conflict escalation (line 47). There is no requirement that agents self-report verification status.

### Pipeline verification is external

Verification is handled by the smoke test gate (`claude/overnight/smoke_test.py`) and the SHA comparison circuit breaker (`before_sha == after_sha`). These are pipeline-level controls, not agent self-reports.

### Architectural constraints favor removal

- "Complexity must earn its place by solving a real problem that exists now" (`requirements/project.md` line 19)
- "Maintainability through simplicity — complexity is managed by iteratively trimming" (`requirements/project.md` line 30)
- "Tests pass and the feature works as specced. ROI matters" (`requirements/project.md` line 21)

### Repair attempt cap is fixed

The repair attempt limit (max 2 for test failures, single Sonnet→Opus for merge conflicts) is a fixed architectural constraint (`requirements/pipeline.md` line 101). Any new pause/block behavior would need to respect these caps.

## Tradeoffs & Alternatives

### Alternative A: Read + advisory log

Add `verification_passed` to `_read_exit_report()` return type. Log `WORKER_VERIFICATION_FAILED` event when `action == "complete"` but `verification_passed == False`. Still mark task done.

- **Pros**: Forensic signal in event logs; non-blocking; ~15 lines of Python
- **Cons**: Changes return type (9+ test updates); consumes inherently unreliable signal; adds code complexity for a field of known-low trust; advisory warnings add noise without actionable remediation during overnight sessions

### Alternative B: Read + pause on mismatch

Same as A, but pause the feature on mismatch.

- **Pros**: Catches "confused but honest" agent scenario
- **Cons**: High false-positive risk; dishonest agents bypass by writing `true`; could halt overnight sessions on false positives (most damaging failure mode for unattended automation); more complex pause/escalation path

### Alternative C: Remove the field (recommended)

Delete `verification_passed` and `committed` from the exit report schema in `implement.md`. No Python changes.

- **Pros**: Eliminates dead code and false safety impression; zero-risk (no Python changes, no test changes); smallest diff (~6 lines removed); honest architecture; clean slate for ticket 025's external verification
- **Cons**: Loses the field as a future signal (but ticket 025 proposes a better mechanism)

### Alternative D: Remove + document for ticket 025

Same as C, plus document in the commit/backlog that the replacement should be externally verified.

- **Pros**: All of C's benefits plus clear architectural intent
- **Cons**: Minimal overhead (just a note)

## Adversarial Review

### Failure modes

- **In-flight overnight sessions**: An overnight run dispatched before the prompt change could write the old schema including `verification_passed`. This is harmless — `_read_exit_report()` ignores unknown fields via `data.get()` — but if strict validation is ever added, hallucinated or cached fields could break parsing.
- **Agent hallucination**: After removal, agents may still write `verification_passed` from training data or cached context. This is also harmless due to `data.get()` tolerance, but exit report parsing should remain tolerant of extra fields.

### Deferred runtime trust gap

Ticket 025 deferred the `verification_passed` question to this ticket (036). This ticket recommends removal. The chain means the runtime trust gap identified in 025's adversarial review — that `action` is unconditionally trusted — is intentionally closed without a runtime mitigation. The real mitigation path is ticket 021 (evaluator rubric) or external verification gates, not self-reported booleans. This should be stated as an explicit architectural decision.

### Assumptions that hold

- `_read_exit_report()` is tolerant of extra fields (confirmed: uses `data.get()`)
- `committed` has no semantic relationship to the `before_sha == after_sha` circuit breaker (confirmed: the circuit breaker checks git SHAs, not exit report fields)
- No downstream consumer reads exit report JSON files for these fields (confirmed: no Python, shell, or dashboard code references them)

### Recommended mitigations

1. Document the architectural decision in the commit message: verification is external, not self-reported
2. Keep `_read_exit_report()` tolerant of extra fields (it already is)
3. Acknowledge the deferred trust gap in the backlog item resolution

## Open Questions

- Should `committed` be removed in the same change as `verification_passed`? (The codebase analysis confirms it is identically dead code, and the adversarial review found no semantic relationship to any existing pipeline mechanism.)
