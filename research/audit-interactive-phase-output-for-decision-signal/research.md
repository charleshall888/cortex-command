# Research: audit-interactive-phase-output-for-decision-signal

## Research Questions

1. What does `/critical-review` currently output to the user, and where is the noise?
   → **Synthesis (Step 3) is already structured from #053. The noise is in Step 4 — the Apply/Dismiss/Ask disposition walkthrough has no output format constraint and can expand arbitrarily. The existing "compact summary" instruction already fails in practice.**

2. What does the lifecycle clarify phase output beyond the 5-field package, and where does noise come in?
   → **The Dismiss-rationale output channel in the clarify-critic disposition framework ("State the dismissal reason briefly") has no specified target audience — orchestrators surface it to the user even though it is internal bookkeeping. Ask items from the critic correctly surface via §4 questions; Dismiss rationale should not reach the user at all.**

3. What does the specify phase produce that isn't decision-relevant for the user?
   → **Four internal phases have no suppress/format constraint: §2b pre-write checks (orchestrator narrates its own verification), §2a clean-pass announcement (no "say nothing" instruction), §2a failure-path announcement (no length constraint on signal description prose), and §3a orchestrator-review fix-agent reports (no disposition instruction after the fix agent returns).**

4. Which of #052's 14 preservation anchors touch these phases?
   → **Key preserved items: anti-warmth counter-weights in critical-review ("Do not be balanced. Do not reassure."); output-channel directive (`AskUserQuestion` in clarify §4 and specify §4); control flow gate in specify §2a (loop-back logic). These must not be removed or softened.**

5. Is there an interactive vs. overnight distinction that constrains what can be reduced?
   → **Yes. Clarify and specify always run interactively (user is present). Critical review in specify §3b is interactive by design. The overnight runner does not run clarify/specify phases — it enters at implement. So reductions here are safe for overnight; they won't affect file-based artifacts.**

---

## Codebase Analysis

### Critical Review — `critical-review/SKILL.md`

**Step 3 (Present)**: "Output the review result directly. Do not soften or editorialize." — one sentence. The synthesis itself is well-structured (4 named sections from #053). No noise here.

**Step 4 (Apply Feedback)**: This is where noise lives. The instruction says:

> "Present a compact summary: what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about 'Ask' items in a single consolidated message."

The phrase "compact summary" exists but fails in practice — agents walk through every objection with its disposition and reasoning, include dismissed items with explanatory prose, re-state the objection before giving the disposition.

The underlying problem is structural: Apply items changed the artifact (done, no user action needed); Dismiss items are resolved (internal bookkeeping); only Ask items require user attention. The current design surfaces all three classes, which is why formatting Step 4 more tightly hasn't worked. The fix must eliminate the requirement to report Dismiss items entirely, and restrict Apply reporting to a bullet list of changes — not the objections they addressed.

**Preservation constraint (CR1/CR2 from #052)**: The anti-warmth instructions ("Do not be balanced. Do not reassure. Find the problems.") are in the *reviewer and synthesis prompts* — not in Step 4. Step 4 is the orchestrator's post-synthesis action. Changing Step 4 output format doesn't touch CR1/CR2.

---

### Lifecycle Clarify — `clarify.md` + `clarify-critic.md`

**§3a (Critic Review)**: The instruction is "Read clarify-critic.md and follow its protocol." The clarify-critic disposition framework instructs:

> "Dismiss — ...State the dismissal reason briefly."

No target audience is specified. "Briefly" does not mean "to yourself" — orchestrators surface Dismiss rationales to the user as inline commentary. This is the actual noise source.

Raw critic findings (the prose objections) never reach the user directly — only the orchestrator consumes them. The Dismiss-rationale output channel is the leak.

Ask items from the critic are correctly handled: they fold into the §4 question list and surface via `AskUserQuestion`. That path must not be suppressed.

Apply items (revisions to the confidence assessment) are correct to apply silently — the confidence revision is internal and the user sees the downstream effect (revised question set or no questions).

The fix is: Dismiss rationale is written to events.log only, not to the user-visible conversation.

**§4 (Question Threshold)**: Uses `AskUserQuestion` — a preservation anchor. This must stay. But the preamble to the questions can be compressed.

**§5 (5-output package)**: Already well-scoped. The five fields are all decision-relevant. This is signal, not noise.

**§7 (Write-backs)**: The `update-item` command is plumbing. Agents sometimes narrate it; they shouldn't.

**Structural alternative (noted for decompose)**: The clarify-critic could return machine-readable output (YAML matching the events.log schema) consumed silently by the orchestrator, eliminating the leak channel structurally rather than behaviorally. This is more robust but more complex than a behavioral instruction. Decompose should note this as an option for spec but the simpler behavioral fix should be tried first.

---

### Lifecycle Specify — `specify.md`

**§2a (Research confidence check)**: Two noise locations:
1. Clean-pass path: no "say nothing" instruction — agents announce "confidence check passed"
2. Failure-path announcement: "Announce the flagged signals to the user, explaining why Research must be re-run" — no format constraint, agents produce unconstrained prose for each of C1/C2/C3. The user needs to know research is re-running; they don't need a full prose explanation of each signal.

**§2b (Pre-write checks)**: Verification of code facts before drafting the spec. The orchestrator does this work inline in its own reasoning. No "don't narrate" constraint. This is qualitatively different from suppressing a subagent's return — the orchestrator is narrating its own steps. A behavioral instruction ("do not narrate verification steps") is the correct lever, but it competes with the model's in-context narration tendency.

**§3a (Orchestrator review)**: Two noise locations:
1. The orchestrator-review.md §4 mandated "one-line assessment" on pass — this is fine (one line is acceptable noise); NOT a target for suppression.
2. The fix-agent report: when a fix is dispatched (Step 5), the fix-agent prompt ends with "Report: what you changed and why. Format: changed [file path] — [one-sentence rationale]." `orchestrator-review.md` has no instruction governing what the orchestrator does with that report. Agents relay it verbatim to the user. This is a missed noise location — the orchestrator should absorb the fix-agent report and re-run the checklist silently, only surfacing the pass/fail result.

**§3b (Critical review at spec)**: Invokes critical-review, presents synthesis. Same Step 4 problem applies. If Step 4 is fixed globally, it carries over to spec §3b. Monitor §3b behavior after the global fix.

**§4 (User approval — approval surface)**: Already has the 4-field output-floor format. This is signal.

---

## Domain & Prior Art

The output floors reference (`claude/reference/output-floors.md`) defines minimum content for phase transitions and approval surfaces — a lower bound. It explicitly says "the floor is a lower bound, not a ceiling" but provides no ceiling guidance. This is the gap #050 did not close.

The #052 preservation anchors cover control-flow gates, output-channel directives, and anti-warmth counter-weights. None of those are at stake here — the target is in-phase narration.

**Mechanism distinction (important):** Anthropic's multi-agent guidance ("Each subagent needs an objective, an output format, guidance on tools, and clear task boundaries") applies to subagent *returns* — structured output crossing an agent boundary into parent context. That principle does not directly apply to in-context orchestrator narration, which is the agent narrating its own reasoning steps. These are different mechanisms:

- **Subagent output format specs** (cross-boundary returns): High reliability. The format spec constrains what the subagent emits. This is how #053's fixes worked.
- **In-context suppress instructions** (orchestrator narrating its own work): Lower reliability. The instruction competes with the model's trained tendency to narrate in-context work. The existing "compact summary" instruction in Step 4 demonstrates this failure mode.

The fix for in-context narration must address the *requirement surface* (remove the Dismiss-reporting requirement, remove the clean-pass announcement requirement) rather than just adding "be more compact" instructions. Removing what the instruction requires the orchestrator to output is more reliable than asking it to be briefer.

---

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| A. Eliminate Dismiss-rationale output from clarify §3a (events.log only); add explicit instruction not to narrate §3a critic pass/fail | S | Medium — behavioral instruction for in-context work; competes with narration tendency | None |
| B. Restructure critical-review Step 4: remove Dismiss requirement, restrict Apply to bullet list of changes, suppress the "dismissed N objections" style reporting | S | Medium — the existing "compact summary" instruction already fails; removal of the Dismiss requirement is the key structural change | None |
| C. Add format constraint to specify §2a clean-pass path ("say nothing") and failure-path announcement (one-line per signal, no prose expansion) | S | Low — clean-pass suppression is easy; failure-path needs careful wording to keep the actionable message | None |
| D. Address specify §2b pre-write narration and §3a fix-agent report absorption | S | Medium — §2b is in-context narration (same mechanism risk as A); §3a fix-agent report absorption requires adding a disposition instruction to orchestrator-review.md | orchestrator-review.md must be in scope |
| E. Combine A+B+C+D in one ticket | M | Medium — 4 files, two different mechanism types | orchestrator-review.md in scope |

**Note on orchestrator-review.md scope**: Approach D requires modifying `orchestrator-review.md` (to add a disposition instruction for fix-agent reports). This file was not in the original scope; it must be added.

**Note on /refine Step 6**: Out of commissioned scope (user specified /critical-review, clarify, spec). Has the same "summarize everything" pattern. Worth a follow-up ticket.

---

## Decision Records

### DR-1: Scope — what counts as "decision-relevant" output

- **Context**: The user's complaint is noise that makes it harder to read and make a decision. The question is what information serves that goal vs. what is internal work product.
- **Options considered**: (a) Treat everything during a phase as potentially useful; (b) Distinguish internal work (verification, critic pass, disposition reasoning, fix-agent reports) from user decision points (questions, synthesis output, approval surface, one-line phase outcome).
- **Recommendation**: Option (b). The user's decision points are: answering questions (clarify §4), reviewing the spec (specify approval), and responding to the critical review synthesis (critical-review Step 3). Everything else is internal work. The one-line orchestrator-review pass assessment on clean pass is acceptable (it signals something was checked); prose narration of what was checked is not.
- **Trade-offs**: Agents lose the ability to "show their work" by default. If a user wants to see critic internals or orchestrator review output, they can ask. Default must be silence on internal phases.

### DR-2: Critical review Step 4 — what to report

- **Context**: Step 4 currently requires "what was changed (one line per fix), what was dismissed and why, and — only if any remain — ask about 'Ask' items." The Dismiss requirement is the surface area for expansion.
- **Options considered**: (a) Keep dismissed items with rationale, improve format; (b) Eliminate Dismiss reporting entirely — report only Apply changes (one line each) and Ask items.
- **Recommendation**: Option (b). Dismiss items were raised and resolved internally; they are irrelevant to the user's decision. Apply items should appear as a compact list of what changed (not as "I took the objection about X and decided to Y"). Ask items are the only ones requiring user input. This is a structural change to what the compact summary contains, not just a format tightening.
- **Trade-offs**: User loses visibility into what was challenged and rejected. Acceptable — the synthesis (Step 3) already showed all objections; Step 4 is resolution, not presentation.

### DR-3: Specify §3b — critical review in nested context

- **Context**: Critical review runs again inside specify §3b. A format change to Step 4 should carry over automatically. However, nested invocation context is larger (more conversational pressure), which may affect compliance.
- **Recommendation**: Fix critical-review Step 4 globally; monitor §3b after the fix rather than adding separate handling. Separate handling would require duplicating Step 4 logic in the lifecycle skill, which is worse than accepting some risk of context-pressure divergence.
- **Trade-offs**: If the fix doesn't hold in §3b context, a follow-up is needed. Accept this risk.

### DR-4: Mechanism distinction for in-context narration

- **Context**: Suppress instructions for in-context orchestrator work (§2b, §2a, §3a fix-agent report) are less reliable than format specs for subagent returns. The primary lever is removing the *requirement* to produce the output, not asking the agent to be briefer.
- **Recommendation**: For each in-context noise location, remove or restructure the requirement rather than adding "be compact" instructions. Example: instead of "do this check but don't narrate it," restructure the phase to "do this check; if it passes, continue without output; if it fails, [state the specific minimum output]."
- **Trade-offs**: Requires careful rewording of each location to preserve the behavioral intent while eliminating the narration surface.

---

## Open Questions

None.
