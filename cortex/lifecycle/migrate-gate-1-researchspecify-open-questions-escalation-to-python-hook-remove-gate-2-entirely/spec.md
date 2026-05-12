# Specification: Migrate both complexity-escalation gates to deterministic Python hook (`cortex-complexity-escalator`)

## Problem Statement

The two complexity-escalation gates (Gate 1: Research → Specify on ≥2 `## Open Questions` bullets; Gate 2: Specify → Plan on ≥3 `## Open Decisions` bullets) currently live as ~14 lines of protocol prose in `skills/lifecycle/SKILL.md`. The model executes the bullet-counting algorithm each time it reads the prose, paying tokens at every gate-evaluation point. This ticket moves both gates' evaluation to a deterministic Python utility (`bin/cortex-complexity-escalator`) invoked from a one-line SKILL.md protocol step at each transition. Both gates emit a new `gate` provenance field on `complexity_override` events, enabling future evidence-driven decisions about either gate's retention or threshold-tuning.

**Honest framing**: this migration is **prose compression with an algorithmic side-pin**, not a true determinism migration. The model still triggers the hook by executing one SKILL.md line at each transition. The migration introduces a new failure-mode topology — inline model-executed logic (which fails visibly within the model's turn output) is replaced by a subprocess (which can fail with empty stdout). The spec compensates for this categorical shift in failure surface by mandating explicit exit-code-branching prose in the replacement SKILL.md instructions (R13/R14), aligning the hook with the project's convention for every other `bin/cortex-*` invocation from a SKILL.md (precedents: `clarify.md:15`, `refine/SKILL.md:35`, `backlog/SKILL.md:82,99`, `lifecycle/references/implement.md:37,67`).

**Algorithmic scope**: the hook counts top-level bullets under the named section. It does NOT replicate refine's semantic "resolved/deferred" classification — that rule (per refine's Research Exit Gate) is intentionally semantic ("contains an inline answer"), which a deterministic regex cannot match without producing false positives and false negatives. The hook runs **after** refine's Research Exit Gate has already filtered or annotated open questions; the hook's job is to count what survives. For Open Decisions, the hook counts top-level bullets, excluding the small set of "no decisions" idioms that the corpus actually uses (`- None.`, `(none)`, the template placeholder bullet).

## Requirements

1. **Hook script exists at canonical path with telemetry shim**: `ls bin/cortex-complexity-escalator` returns the file; first 50 lines contain the `cortex-log-invocation` telemetry shim (pre-commit Phase 1.6 requirement). Acceptance: `test -x bin/cortex-complexity-escalator && head -50 bin/cortex-complexity-escalator | grep -c 'cortex-log-invocation'` ≥ 1.

2. **Hook supports `--gate` parameter selecting the evaluation mode**: Invocation `bin/cortex-complexity-escalator <feature> --gate research_open_questions` reads `lifecycle/<feature>/research.md`; invocation with `--gate specify_open_decisions` reads `lifecycle/<feature>/spec.md`. Acceptance: `bin/cortex-complexity-escalator --help` prints both gate values in its usage output. Verification: `bin/cortex-complexity-escalator nonexistent-feature --gate research_open_questions` exits non-zero with a usage-style error to stderr; `bin/cortex-complexity-escalator valid-slug --gate invalid_gate` exits non-zero with an unknown-gate error to stderr.

3. **Gate 1 algorithm (Open Questions)** counts ALL top-level bullets directly under `## Open Questions`, regardless of inline answer status or resolved/deferred annotations. A "top-level bullet" is a line that, after stripping leading whitespace, begins with one of the bullet markers `-`, `*`, or a number-period sequence (`1.`, `2.`, …). Sub-bullets nested deeper than the section's primary indent level are not counted. Fenced code blocks (triple-backtick) and blockquoted bullets (lines beginning with `> `) are excluded.

   Rationale: refine's Research Exit Gate (in `skills/refine/SKILL.md`, "Research Exit Gate" section) already resolves or defers Open Questions before the hook runs. The remaining bullets are by definition unresolved-and-non-deferred. A purely syntactic count is correct under this invariant; introducing a substring-based resolved/deferred filter inside the hook would produce both false positives (e.g., a bullet asking "Should we adopt the Resolved: convention here?" contains the substring `Resolved:`) and false negatives (e.g., a bullet `- **Resolved**: ...` with the colon outside the bold markers does not contain the substring `Resolved:`).

   Acceptance: `tests/test_complexity_escalator.py::test_open_questions_bullet_counting` has at least one pytest case for each of these bullet shapes: dash-prefixed top-level bullet; star-prefixed top-level bullet; numbered top-level bullet; nested sub-bullet (excluded); fenced code block (excluded); blockquoted bullet (excluded). All cases pass.

4. **Gate 2 algorithm (Open Decisions)** counts top-level bullets under `## Open Decisions` (same marker rules and same exclusion rules as Gate 1), with three additional "no decisions" idiom exclusions:
   - The template-placeholder bullet — any bullet whose body, after stripping the marker and leading whitespace, begins with `[` (matches the specify.md template's bracketed placeholder shape).
   - The `None.` idiom — any bullet whose body, after stripping the marker, matches `^[Nn]one\b` (case-sensitive on the first character, word-boundary anchored).
   - The parenthetical `(none)` idiom — any bullet whose body matches `^\([Nn]one\b`.

   These three idioms are the corpus-attested ways authors mark "no real open decisions"; the algorithm treats them as 0 effective bullets when they appear. Acceptance: `tests/test_complexity_escalator.py::test_open_decisions_bullet_counting` has at least one pytest case for each idiom (verifying it does NOT count) plus a real-decision case (verifying it DOES count). All cases pass.

5. **Thresholds preserved**: Gate 1 fires at ≥2 effective bullets in `## Open Questions`; Gate 2 fires at ≥3 effective bullets in `## Open Decisions`. Acceptance: pytest cases assert that 1 effective bullet does not escalate, 2 effective bullets escalate Gate 1, 2 effective bullets do not escalate Gate 2, 3 effective bullets escalate Gate 2.

6. **Hook skips silently when already at Complex tier**: If `cortex_command/common.py:read_tier()` returns `complex` for the feature, the hook exits 0 with no event emission and no announcement, regardless of effective bullet count. Acceptance: pytest case `test_skip_when_already_complex` constructs a feature with a prior `complexity_override` event in events.log and ≥2 Open Questions; asserts no new event is appended and stdout is empty.

7. **Hook recognizes all three production event-payload shapes when guarding**: Standard `{"event":"complexity_override","from":"simple","to":"complex"}`, YAML-style `event: complexity_override` (no from/to), and test-fixture `{"event":"complexity_override","tier":"complex"}`. Acceptance: pytest cases construct events.log with each shape, run the hook, and assert it skips (no double-fire).

8. **Hook emits `complexity_override` event with `gate` field on escalation**: The appended event matches `{"ts":"<ISO-8601>","event":"complexity_override","feature":"<name>","from":"simple","to":"complex","gate":"<research_open_questions|specify_open_decisions>"}`. The `ts` field is auto-added by the writer; the `gate` value matches the `--gate` argument. Acceptance: `grep -c '"gate":"research_open_questions"' lifecycle/<feature>/events.log` = 1 after a Gate 1 escalation; similarly for `specify_open_decisions`. Pytest case asserts the appended JSON parses and contains all five fields plus `ts`.

9. **Read-after-write verification before announcing**: After appending the event, the hook re-reads the last line of events.log and asserts it parses as the appended event (matches `event` field, `gate` field, and `to` field). On verification failure (silent sandbox denial path), the hook exits non-zero with a stderr message naming the file, the expected event, and the failure mode (e.g., `read_after_write_mismatch` or `read_after_write_io_error`); does NOT print the success announcement on stdout. The non-zero exit + non-empty stderr + empty stdout pattern is the load-bearing signal consumed by the SKILL.md prose contract in R13/R14. Acceptance: pytest case `test_read_after_write_failure` mocks the file to be unwritable; asserts hook exits non-zero, stdout is empty, stderr names the verification failure.

10. **Path-traversal hardening on the feature-slug argument**: The hook validates that the feature argument matches the regex `^[a-zA-Z0-9._-]+$` AND that `realpath(lifecycle/<feature>)` is contained within `realpath(lifecycle/)`. On either failure, exits non-zero with a stderr message naming the rejected slug. Acceptance: `bin/cortex-complexity-escalator '../foo' --gate research_open_questions` exits non-zero with stderr; `bin/cortex-complexity-escalator 'valid-slug' --gate research_open_questions` proceeds normally.

11. **Graceful no-op on missing inputs**: Hook exits 0 silently (no event, no announcement, empty stdout, empty stderr) when any of these are true: `lifecycle/<feature>/research.md` (or `spec.md` for Gate 2) does not exist; the relevant section heading is absent in the file; the relevant section is empty (no bullets); after applying the algorithm the effective count is below threshold. Acceptance: pytest cases for each path; assert exit code 0, stdout empty, stderr empty, no events.log modification.

12. **Gate 1 announcement format on escalation**: The announcement printed to stdout is exactly `Escalating to Complex tier — research surfaced N open questions` (where N is the effective bullet count). For Gate 2: `Escalating to Complex tier — spec contains N open decisions`. Acceptance: pytest cases capture stdout and assert string equality (with regex on N).

13. **SKILL.md gate-prose collapse — Gate 1 with exit-code branching**: The current `skills/lifecycle/SKILL.md` Step 3 §5 (currently 10 lines, lines 259–268) is replaced by:

    ```
    5. **Research → Specify complexity escalation**: At the Research → Specify transition, run `cortex-complexity-escalator <feature> --gate research_open_questions`.
       - On exit 0 with non-empty stdout: announce the escalation message to the user and proceed to Specify at Complex tier.
       - On exit 0 with empty stdout: the gate did not fire (already-complex, missing section, or below threshold). Proceed to Specify at current tier.
       - On non-zero exit: surface the stderr message to the user and halt the phase transition. Resume only after the underlying failure is resolved (e.g., re-run with a corrected slug, restore sandbox write permission, address a malformed input file).
    ```

    The Gate 2 cross-reference at the end of Step 3 §5 (the sentence beginning "The same effect applies to Step 6") is removed entirely. Acceptance: `wc -l skills/lifecycle/SKILL.md` shows ≤ 369 lines (down ~5 from 374); `grep -F 'cortex-complexity-escalator <feature> --gate research_open_questions' skills/lifecycle/SKILL.md` returns ≥ 1; `grep -F 'On non-zero exit: surface the stderr' skills/lifecycle/SKILL.md` returns ≥ 1.

14. **SKILL.md gate-prose collapse — Gate 2 with exit-code branching**: The current `skills/lifecycle/SKILL.md` Step 3 §6 (currently 5 lines, lines 270–274) is replaced by:

    ```
    6. **Specify → Plan complexity escalation**: After spec approval, before the Specify → Plan transition, run `cortex-complexity-escalator <feature> --gate specify_open_decisions`. Same hook, different gate.
       - Exit-code branching is identical to Step 5 above.
    ```

    Acceptance: `wc -l skills/lifecycle/SKILL.md` shows ≤ 366 lines (down ~8 from 374 net of both gates); `grep -F 'cortex-complexity-escalator <feature> --gate specify_open_decisions' skills/lifecycle/SKILL.md` returns ≥ 1.

15. **SKILL.md-to-bin parity verification passes**: After both prose collapses reference the binary, the parity linter recognizes the reference. Acceptance: `bin/cortex-check-parity` exits 0; `bin/cortex-complexity-escalator` is NOT listed in `bin/.parity-exceptions.md`.

16. **Plugin-mirror dual-source drift detection passes**: After running `just build-plugin`, files at `plugins/cortex-core/bin/cortex-complexity-escalator` and `plugins/cortex-core/skills/lifecycle/SKILL.md` are byte-identical to their canonical sources. Acceptance: the pre-commit dual-source drift hook exits 0; `diff bin/cortex-complexity-escalator plugins/cortex-core/bin/cortex-complexity-escalator` produces no output; same for `skills/lifecycle/SKILL.md`.

17. **Test file exists with at least one passing case per acceptance criterion above**: `ls tests/test_complexity_escalator.py` succeeds; `just test tests/test_complexity_escalator.py` (or equivalent pytest invocation) exits 0. Acceptance: pytest reports ≥ 15 passing test cases.

## Non-Requirements

- **Hook does NOT downgrade complexity tier**: The hook is monotonic-upward only. If `research.md` is edited after escalation to remove open questions, the tier remains `complex`. Downgrade requires manual `complexity_override` event emission (existing feature, unchanged by this ticket).
- **Hook does NOT implement refine's semantic resolved/deferred classification**: The hook counts top-level bullets only. Refine's Research Exit Gate handles semantic classification of open questions BEFORE the hook runs. This is an intentional scope boundary — substring-based syntactic matching for "resolved" / "deferred" is unreliable against the corpus (Reviewer-1 corpus audit during refine review: ~17% miss rate across 416 top-level bullets) and would produce both false-positive and false-negative escalations.
- **Hook does NOT canonicalize existing pre-v2 event-payload shapes**: The hook tolerates all three shapes when guarding (R7) but does NOT rewrite legacy events. Schema-canonicalization is out of scope; a separate ticket can address it if needed.
- **Hook is NOT responsible for staying in sync with upstream-source prose changes**: If a future maintainer renames the `## Open Questions` / `## Open Decisions` section headings, edits the specify.md template-placeholder bullet's wording, or expands the set of "no decisions" idioms beyond `None.` / `(none)` / template-placeholder, a follow-up ticket updates the hook's algorithm. The hook is pinned to current section names and current idiom set. Pytest cases ground the current state but no automated drift detection is added in this ticket.
- **No FileChanged or PostToolUse trigger mechanisms**: The hook is invoked explicitly from a SKILL.md protocol step (Approach B per research). FileChanged adoption is rejected as first-use risk + known bugs (GH #44925, #14281); PostToolUse rejected as trigger-vs-transition semantic mismatch (research FM-4).
- **No deletion of Gate 2 prose or behavior**: Both gates preserved by Option B (scope-revision 2026-05-11). Future tickets may use the `gate` provenance data to decide on Gate 2 retention.
- **No CHANGELOG.md entry required**: Workflow Trimming's CHANGELOG requirement applies to retired surfaces with downstream consumers. Both gates are preserved; behavior is unchanged from the user's perspective. The hook is a new utility; its introduction may optionally be noted in CHANGELOG but is not required.
- **#180 D4 (Open Decisions optional) is NOT unblocked by this ticket**: Gate 2 remains a consumer of the Open Decisions section, so D4 stays BLOCKED per the audit's intended state.
- **No schema_version bump on `complexity_override` events**: Lifecycle events.log entries don't currently carry a `schema_version` field; introducing one for this single event type is out of scope. The new `gate` field is purely additive at the writer layer.
- **No sidecar state file**: The hook writes to events.log only, matching current Gate 1/Gate 2 behavior. No separate `tier-stamp.json`.
- **No auto-deployment for in-flight overnight sessions**: Sessions started before this ticket lands continue using the prose-based gates. The new hook applies to fresh sessions. No migration shim required.
- **No `--rationale` argument on the hook**: Future enhancement; out of scope. The rationale convention (`requirements/pipeline.md:130`) is preserved via the SKILL.md announcement only.
- **No drift test for upstream source files**: Adding a pytest case that reads `skills/refine/SKILL.md` and asserts specific prose remains unchanged is out of scope (overly coupling tests to author-discretion content). The "no upstream-coupling responsibility" Non-Requirement above acknowledges this trade-off explicitly.

## Edge Cases

- **research.md exists but `## Open Questions` section is absent**: Hook exits 0 silently (R11).
- **research.md has `## Open Questions` heading but no bullets**: Hook exits 0 silently.
- **research.md has bullets in three styles (`-`, `*`, `1.`)**: All counted as top-level bullets per their marker; mixed-marker sections work correctly.
- **Sub-bullets under a parent bullet**: Sub-bullets ignored; parent counts as 1.
- **Open Questions in a fenced code block**: Fenced block excluded; not counted.
- **Open Questions in a blockquote (`> - foo`)**: Blockquote excluded; not counted.
- **research.md is malformed (binary file, encoding errors)**: Hook exits non-zero with a stderr message naming the parse failure; no event emitted; no partial-state escalation. The SKILL.md prose at R13/R14 consumes this non-zero exit and halts the phase transition.
- **spec.md `## Open Decisions` contains ONLY the template-placeholder bullet** (e.g., `- [Only when implementation-level context is required...]`): Placeholder excluded by R4's idiom rule; effective count = 0; no escalation.
- **spec.md `## Open Decisions` contains a `- None.` bullet**: Excluded by R4's idiom rule; effective count = 0; no escalation. Same for `- none.`, `- (none)`, `- (None ...)`.
- **spec.md `## Open Decisions` is missing entirely**: Hook exits 0 silently.
- **events.log has TWO existing `complexity_override` events (e.g., manual escalate-and-downgrade sequence)**: Hook reads the most recent event's effective tier via `read_tier()`; if currently `complex`, skips; if currently `simple` (downgraded), evaluates and potentially re-escalates with a new event. Monotonic-upward semantic applied to the *current* tier, not the historical max.
- **Hook invocation from within an active overnight session with `--dangerously-skip-permissions`**: Read-after-write verification (R9) catches silent sandbox denial. On non-zero exit, the SKILL.md-side prose at R13/R14 surfaces the stderr and halts the phase transition; this is the contract that consumes R9's affordance. There is no implicit "orchestrator catches it" path — the SKILL.md prose IS the consumer contract.
- **Concurrent hook invocations on the same feature**: Both invocations append to events.log; the read-after-write check on each may observe the other's append. Both events are tolerated by `read_tier()` (idempotent — same effective tier). Hook does not lock or coordinate. Acceptable per the project's append-only JSONL convention (PIPE_BUF atomicity guarantee).
- **Feature slug with embedded slash (`foo/bar`)**: Rejected by R10 regex; hook exits non-zero.
- **Feature slug equal to `..`**: Rejected by the realpath-containment check (R10); hook exits non-zero.
- **A bullet under Open Questions contains the literal substring "Resolved:"** (e.g., a meta-question asking about the Resolved: convention): The hook counts it as a real top-level bullet. No substring filtering. This is intentional under R3's rationale — refine's Research Exit Gate handles semantic resolution upstream; the hook trusts the post-exit-gate state.
- **A bullet under Open Decisions begins with `[` but is NOT the template placeholder** (e.g., an author writes `[Trade-off A vs B]: ...`): Excluded by R4's idiom rule because it begins with `[`. This is a false-positive risk: an author who legitimately uses a bracketed-prefix bullet for an open decision will not have it counted. Mitigation: documented in this Edge Cases entry; spec phase has chosen the trade-off in favor of correctly handling the template-placeholder case (the more common pattern per corpus).

## Changes to Existing Behavior

- **MODIFIED**: `skills/lifecycle/SKILL.md` Step 3 §5 collapses from 10 lines of Gate 1 protocol prose to ~5 lines that invoke the hook and define exit-code branching. Effective gate behavior is preserved (same trigger condition: ≥2 top-level bullets under `## Open Questions`, hook fires; same event emission). Token cost drops at gate-evaluation time. Algorithm becomes pytest-testable rather than model-discretionary. Failure-mode topology shifts: prose was inline (failures visible mid-turn) → subprocess (failures consumed by explicit SKILL.md exit-code branching).
- **MODIFIED**: `skills/lifecycle/SKILL.md` Step 3 §6 collapses from 5 lines of Gate 2 prose to ~3 lines (hook invocation + reference to Gate 1's exit-code branching). Same preservation/improvement profile as Gate 1.
- **MODIFIED**: `complexity_override` events emitted via the new hook include a new `gate` field with values `"research_open_questions"` or `"specify_open_decisions"`. Readers (`cortex_command/common.py:read_tier()`, `skills/lifecycle/SKILL.md` "Detect complexity tier" prose) are unaffected — they read `tier`/`to` only. Future event-attribution analysis (epic 172 audit's stated need) becomes possible.
- **ADDED**: `bin/cortex-complexity-escalator` CLI utility. Available on PATH after `uv tool install` via the plugin mirror; invokable from SKILL.md protocol steps, tests, and ad-hoc debugging.
- **ADDED**: `tests/test_complexity_escalator.py` test module covering both gates' algorithms and the hook's hardening paths.
- **ADDED**: Explicit exit-code-branching contract in SKILL.md gate-prose, aligning with the project's settled convention for `bin/cortex-*` invocations from SKILL.md (precedents listed in Problem Statement).

## Technical Constraints

- **Schema source-of-truth correction (research A-4)**: Canonical writer for `lifecycle/{feature}/events.log` is `cortex_command/pipeline/state.py:288 log_event`, which performs a plain atomic append with no schema validation. The new hook uses this writer (or the same idiom: `open(path, "a") + f.write(json.dumps(entry) + "\n")`). References to `cortex_command/overnight/events.py` in the original ticket and audit are stale — that file's `EVENT_TYPES` validator governs `lifecycle/sessions/{session_id}/overnight-events-*.log`, a different log.
- **CLI shim line requirement (project.md "SKILL.md-to-bin parity enforcement"; pre-commit Phase 1.6)**: Every `bin/cortex-*` script must include the `cortex-log-invocation` telemetry shim in its first 50 lines. The new script complies.
- **SKILL.md-to-bin parity (project.md "SKILL.md-to-bin parity enforcement")**: The new script is referenced from `skills/lifecycle/SKILL.md` (both gates) — parity linter satisfied. No `bin/.parity-exceptions.md` entry needed.
- **SKILL.md size cap (project.md "SKILL.md size cap")**: 500-line cap enforced by `tests/test_skill_size_budget.py`. Current `skills/lifecycle/SKILL.md` is 374 lines; this spec reduces by ~8 lines (~366 after migration). Well within budget.
- **Sandbox registration (project.md "Per-repo sandbox registration")**: `cortex init` already registers `lifecycle/` in `sandbox.filesystem.allowWrite`. The hook's events.log writes do not require new sandbox carve-outs. Read-after-write verification (R9) plus SKILL.md exit-code branching (R13/R14) handle in-flight sessions whose sandbox state may differ.
- **Atomic JSONL append**: Plain `open(path, "a") + f.write(json.dumps(entry) + "\n")` is atomic for single writes under PIPE_BUF (4 KB). A `complexity_override` line is ~150 bytes; well within the guarantee. Matches existing `cortex_command/pipeline/state.py:303` and `cortex_command/overnight/events.py:240` precedents.
- **Plugin mirror enforcement**: `justfile` rsync recipes auto-mirror `bin/cortex-*` to `plugins/cortex-core/bin/` and SKILL.md changes via the `SKILLS=` manifest. No manifest edit required for either canonical source.
- **MUST-escalation policy (CLAUDE.md OQ3)**: The SKILL.md replacement prose uses positive-routing phrasing for the gate-fire path ("The hook handles…") and imperative-but-non-MUST phrasing for the failure path ("surface the stderr to the user and halt the phase transition"). The failure-path imperative is justified by the existing project convention for hook exit-code handling (cited in Problem Statement) and aligns with `bin/cortex-validate-commit.sh`'s deny-path precedent. No new CRITICAL/REQUIRED/MUST forms are introduced; therefore no OQ3 evidence artifact is required.
- **Refine-coupling boundary**: The hook does NOT semantically replicate `skills/refine/SKILL.md`'s Research Exit Gate logic. The hook counts bullets in the section as-found; the upstream gate is responsible for filtering or annotating bullets according to its own (semantic, model-discretionary) rules. This decoupling is intentional and is reflected in the Non-Requirements section.
- **Three-payload-shape tolerance (research A-3)**: The hook's "already escalated" guard recognizes all three production payload variants of `complexity_override` events. No canonicalization performed by this hook.

## Open Decisions

None. The structured interview and adversarial review process resolved all identified questions; remaining items are recorded as explicit Non-Requirements or Edge Cases.
