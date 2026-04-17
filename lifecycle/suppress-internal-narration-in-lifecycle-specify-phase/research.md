# Research: Suppress internal narration in lifecycle specify phase

## Epic Reference

This ticket is one of four decomposed from the audit at [research/audit-interactive-phase-output-for-decision-signal/research.md](../../research/audit-interactive-phase-output-for-decision-signal/research.md). The audit surveys four interactive-phase narration problems across /critical-review, clarify, specify, and plan; this ticket owns only the specify-phase items (§2a, §2b, §3a) plus the paired Step 5 disposition in `orchestrator-review.md`. The epic's **DR-4 (Mechanism distinction for in-context narration)** is the load-bearing principle: remove the output *requirement* rather than add "be compact" instructions, because in-context suppression competes with the model's narration tendency whereas structural removal does not.

## Codebase Analysis

### Files that will change
- `skills/lifecycle/references/specify.md` — §2a Research Confidence Check, §2b Pre-Write Checks, §3a Orchestrator Review delegation line.
- `skills/lifecycle/references/orchestrator-review.md` — Step 5 Fix Agent dispatch (mechanism + disposition of returned report), Step 4 pass/fail handling where it interacts with the fix-agent return.

Explicitly out of scope (do not modify): `orchestrator-review.md §4`'s one-line on-pass assessment; `clarify.md`, `plan.md`, `/critical-review` (sibling tickets in epic 66).

### Current state (quoted passages)

**specify.md §2a clean pass** (line 55):
> "If all three signals pass: proceed to §3. No event is logged."

The pass path is silent by omission; no positive directive forbids the orchestrator from announcing "confidence check passed." Current behavior is emergent.

**specify.md §2a failure, cycle 1** (line 61):
> "Announce the flagged signals to the user, explaining why Research must be re-run."

No length or format constraint. The event log is written separately.

**specify.md §2b Pre-Write Checks** (lines 78–97): four concrete verification steps — code-fact verification, research cross-check, open-decision resolution, silent-omission guard. No "do not narrate" directive.

**specify.md §3a** (line 143) delegates entirely to `orchestrator-review.md`:
> "Before presenting the artifact to the user, read and follow orchestrator-review.md for the specify phase."

**orchestrator-review.md Step 5 Fix Agent prompt** (line 98):
> "Report: what you changed and why. Format: changed [file path] — [one-sentence rationale]."

No instruction governs what the orchestrator does with the returned report.

**orchestrator-review.md Step 4 on pass**:
> "Show the user a one-line assessment summarizing what was checked and the result."

Explicitly out of scope.

### Precedent patterns in sibling reference files
- **`clarify-critic.md` Failure Handling** (line 134): "Do not surface the failure as a blocking error. Note it silently in the event log." — closest precedent for silent absorption.
- **`complete.md`**: uses the phrasing "skip this silently" and "silently acceptable" for missing-artifact handling.
- **`implement.md`** (line 248): "flag it as an issue rather than silently deviating" — establishes that silent *deviation* is the anti-pattern; silent *successful passage* is fine.

### Integration points and dependencies
- **`confidence_check` event** is written on §2a failure (lines 62–65, 72–75). Cycle counting at line 57 uses `count of existing confidence_check events` — changing what is logged on pass affects cycle detection (see Open Questions).
- **`orchestrator_dispatch_fix` event** is logged when Step 5 dispatches a fix. The orchestrator is the sole downstream consumer of the fix-agent's return report. No external module parses it.
- **`orchestrator_review` event** is written per review cycle and feeds the cycle-cap logic at orchestrator-review.md lines 161–168. Any silent re-run must still emit this event.
- **No downstream consumer for §2b checks**: no artifact written, no event logged. Suppressing their narration has no machine-consumed impact.
- **No tests** assert the current narration behavior.

### Conventions for instruction-edit phrasing
Three existing patterns:
1. Explicit pass-silence: "No event is logged" (specify.md §2a).
2. Functional silence: "skip this silently" (complete.md).
3. Non-blocking silence: "Note it silently in the event log" (clarify-critic.md).

## Web Research

### Anthropic guidance directly relevant
- **Positive instructions beat negation**: the docs explicitly prefer positive framing ("communicate concisely") over "do not narrate" instructions; negation competes with the model's default.
- **Eliminating preambles**: the idiomatic modern mechanism is a direct system-prompt directive to respond without preamble, or — preferably — a structured-output / tool-calling contract that removes the preamble surface.
- **Two-stage coverage-then-filter**: Anthropic's own pattern for "report every issue, defer importance filtering to a separate step" directly mirrors the §2a failure-path "bulleted signal list, no prose expansion" idea.
- **Subagent returns**: parents *summarize and relay* by default; forcing absorption without relay requires explicit instruction AND/OR a structured envelope. Subagents are explicitly recommended for "isolating operations that produce large amounts of output... verbose output stays in the subagent's context while only the relevant summary returns."
- **Evaluator-optimizer pattern** (Anthropic cookbook, AWS guidance): the canonical shape for review-and-fix loops is a structured verdict (PASS/FAIL + issues), not prose — a programmatic gate terminates the loop.
- **Opus 4.7 posture**: "may skip verbal summaries after tool calls, jumping directly to the next action" — the model is already quieter by default; removing narration *triggers* (e.g., instructions like "summarize after") is more effective than adding suppressors.

### Third-party corroboration
- Google ADK: `disallow_transfer_to_parent=True` forces structured returns only — deterministic envelope.
- Microsoft Foundry / OpenAI Agents SDK: JSON-schema envelopes for sub-agent returns are the baseline pattern.

### Takeaway per surface
- **Surface 1 (clean-pass) → structural:** silence-on-pass is gate behavior; do not make it an instruction.
- **Surface 2 (failure-path) → schema/template:** the Anthropic coverage-then-filter split is almost verbatim what the ticket requires.
- **Surface 3 (§2b) → remove the trigger:** don't add a "don't narrate" instruction; remove whatever instruction re-enables narration on pass.
- **Surface 4 (§3a) → structured envelope:** canonical evaluator-optimizer shape. Subagent boundary is the high-reliability lever.

## Requirements & Constraints

### From requirements/project.md
- **Handoff readiness**: "A feature isn't ready for overnight until the spec has no open questions, success criteria are verifiable by an agent with zero prior context, and all lifecycle artifacts are fully self-contained. The spec is the entire communication channel." → the spec must carry the load, not the runtime narration.
- **Context efficiency**: deterministic preprocessing hooks, not model judgment, filter verbose output. The ticket is adjacent to this attribute but not an instance of it — this is an LLM-instruction edit, not a deterministic filter. Aligned with the *goal* (signal over noise) not the *mechanism*.

### From requirements/multi-agent.md
- **Context hygiene**: "verbose output stays in the subagent's context while only the relevant summary returns" — reinforces the §3a structured-envelope case.
- No constraint directly governs specify-phase narration.

### From DR-4 (epic research)
> "For each in-context noise location, remove or restructure the requirement rather than adding 'be compact' instructions. Example: instead of 'do this check but don't narrate it,' restructure the phase to 'do this check; if it passes, continue without output; if it fails, [state the specific minimum output].'"

This is the governing principle for all four surfaces.

### Scope anchors (preserve — do not touch)
- `orchestrator-review.md §4`'s one-line pass assessment.
- Anti-warmth instructions in critical-review reviewer prompt.
- `AskUserQuestion` output-channel directive in clarify §4.
- Loop-back control-flow gate in specify §2a (behavior preserved; narration suppressed).

## Tradeoffs & Alternatives

### §2a clean-pass
- **A. Instruction edit**: add explicit "do not announce" directive. Pros: one-line change. Cons: in-context suppression; competes with model tendency (DR-4).
- **B. Structural restructure** *(recommended)*: remove the announcement surface entirely. Current line 55 is already close — a cleaner phrasing that makes the silence positive (e.g., "If all three signals pass: continue to §3. Do not emit any acknowledgment; only §3 output is user-visible.") removes the ambiguous emergent behavior.
- **Audit-trail hazard (adversarial F1)**: today clean-pass writes no `confidence_check` event, and cycle counting relies on "number of existing confidence_check events". If a future edit naïvely adds a pass event, cycle counting breaks. Spec must either (a) leave the no-pass-event invariant explicit in a comment, or (b) add a pass event with `action: pass` and update cycle counting to filter on `action: loop_back|declined`.

### §2a failure-path
- **A. Tighten prose instruction** (e.g., "one-line per signal, no prose expansion"): lower reliability — "one line" rots into paragraphs on complex-tier specs.
- **B. Embedded template + word cap** *(recommended)*: provide exact output shape with a ≤15-word cap per signal line and a concrete example. Schema-style enforcement is more reliable than prose guidance (web research).
- **Template-rot hazard (adversarial F2)**: do not inline the specific signal names (C1/C2/C3) in the template — signals may be renamed or a C4 added. Bind by reference: "emit one bulleted line per flagged signal from the list above, ≤15 words per line."
- **Slot-fill hazard (adversarial F7)**: include an explicit example of target terseness in the instruction.

### §2b pre-write checks
- **A. Add "do not narrate" directive**: in-context suppression; weakest mechanism.
- **B. Restructure to conditional phrasing** *(recommended)*: rewrite §2b so each check's output requirement is conditional — "if verification fails, surface the specific failing claim; otherwise continue to §3 with no output." Removes the decision point "should I say something on pass?"
- **Audit-visibility hazard (adversarial F3)**: §2b is currently invisible on pass too (no event, no artifact). User approves the spec in §4 trusting §2b happened. Options for spec to consider:
  - Pure silence (accepts the current audit gap).
  - Minimum-viable breadcrumb: a single structured line on pass, e.g., "pre-write checks: N claims verified, research re-read." (One-line acceptable per project convention for §4 pass assessments.)
  - Add a `pre_write_check` event to `events.log` on pass (silent to user, audit to log).
  Spec should pick one; the tradeoff is user-transparency vs. narration surface.

### §3a fix-agent disposition
- **A. Prose instruction only** (add "absorb silently, re-run checklist, surface only pass/fail" to orchestrator-review.md): lowest-effort change. Cons: DR-4 explicitly warns this class of in-context suppression instruction has lower reliability.
- **B1. Behavioral instruction in orchestrator-review.md §4** (absorb, silent re-run, surface only pass/fail): slightly more invasive than A; still an instruction edit.
- **B2. Structured envelope for fix-agent return** *(adversarial-recommended)*: change the fix-agent prompt's "Report:" line to a strict schema (e.g., `verdict`, `files_changed`, `rationale ≤15 words`). Orchestrator parses the envelope, logs it, and never surfaces it. This is the canonical evaluator-optimizer shape from the web research and aligns with Anthropic's subagent-envelope guidance. The fix-agent returns at a subagent boundary — exactly where format specs are *most* reliable per DR-4.
- **B3. Sub-agent re-review**: checklist re-run becomes a dedicated subagent call returning pass/fail only. Cleanest boundary; highest latency and cost; likely over-engineered for a specify-phase fix loop.
- **Recommended for spec**: **B2** is the strongest mechanism per web research (structured envelope at a subagent boundary is high-reliability) and DR-4 (removes the requirement to produce prose rather than instructing the orchestrator not to relay it). A is minimum-viable. Spec phase picks between A, B1, and B2.

## Open Questions

These questions are for the Spec phase (§5 structured interview) to resolve with the user:

1. **§2a clean-pass audit-trail**: should clean-pass write a `confidence_check` event with `action: pass` (preserves audit; requires cycle-count filter update), or preserve the current no-event invariant (current behavior; but leaves silence unaudited)? Deferred: will be resolved in Spec by asking the user.

2. **§2a failure-path word cap**: confirm a hard per-line cap (≤15 words is proposed) and require an inline example of acceptable terseness, rather than relying on "one-line." Deferred: will be resolved in Spec.

3. **§2b audit breadcrumb on pass**: three options — pure silence, one-line structured summary on pass, or a new `pre_write_check` event in `events.log`. Deferred: will be resolved in Spec by asking the user.

4. **§3a mechanism choice**: A (plain instruction), B1 (behavioral instruction in orchestrator-review.md §4), or B2 (structured envelope at fix-agent return boundary). Research recommends B2 on reliability grounds (DR-4 + web evidence); the user indicated at Clarify that this choice is deferred to Spec. Deferred: will be resolved in Spec by asking the user.

5. **§3a orchestrator re-read guard (adversarial F5)**: before silently re-running the checklist, should the orchestrator be required to re-read the fresh artifact and verify basic validity (file exists, non-empty, parseable markdown), to prevent silent pass on a malformed rewrite? Deferred: will be resolved in Spec.

6. **§3a `orchestrator_review` event on silent re-run (adversarial F6)**: confirm that silent re-run still writes a per-cycle `orchestrator_review` event so cycle-cap logic at orchestrator-review.md lines 161–168 remains intact. Deferred: will be resolved in Spec (likely trivial "yes" but worth confirming scope).
