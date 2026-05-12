# Research: Suppress Dismiss-rationale leak in lifecycle clarify critic

## Epic Reference

Ticket scoped from epic research: [research/audit-interactive-phase-output-for-decision-signal/research.md](../../research/audit-interactive-phase-output-for-decision-signal/research.md). The epic audited interactive-phase output signal across `/critical-review`, clarify, and specify and decomposed fixes into separate tickets — sibling #067 handles `/critical-review` Step 4 (structural fix per epic DR-2); this ticket (#068) handles the clarify-critic Dismiss-rationale output channel. Epic research established DR-1 (decision-relevant vs. internal work distinction) and DR-4 (in-context narration suppression is less reliable than cross-boundary format specs) as the governing constraints.

## Codebase Analysis

### Primary edit site — `skills/lifecycle/references/clarify-critic.md`

The ticket body lists two files in scope. Inspection shows `clarify.md` §3a (lines 47–49) is pure delegation — it contains zero Dismiss-rationale instructions:

> "Read `~/.claude/skills/lifecycle/references/clarify-critic.md` and follow its protocol. After the critic completes, the orchestrator writes the `clarify_critic` event to `lifecycle/{feature}/events.log` with the post-critic status."

The leak is entirely inside `clarify-critic.md:73`:

> "**Dismiss** — the objection is already addressed by the source material, misreads the stated constraints, or rests on an assumption the source material explicitly rules out. **State the dismissal reason briefly.**"

The trailing sentence has no target audience, so orchestrators surface it to the user. Apply and Ask disposition definitions are not affected. Ask-to-§4 Merge Rule (lines 81–85) is the preservation anchor — must remain intact.

### Events.log schema — current state

Surveyed existing `clarify_critic` events across multiple `lifecycle/*/events.log` files: none currently carry any dismissal-rationale payload. Today's schema:

```
ts, event, feature, findings[], dispositions{apply,dismiss,ask}, applied_fixes[], status
```

`applied_fixes` is Apply-only by construction. There is no slot for Dismiss rationales. **"Route to events.log only" is therefore not a pure routing change against the current schema** — it is either (a) a schema extension that adds a `dismissals` array, or (b) a requirement-removal that drops rationale production entirely. The spec phase must pick.

### Drift-avoidance invariant

`clarify-critic.md:69` explicitly states the Apply/Dismiss/Ask framework is "reproduced here to avoid silent drift" from `/critical-review` Step 4. Sibling ticket #067 applies epic DR-2 to `/critical-review` Step 4 (eliminate Dismiss reporting entirely). After both tickets land, the shared-phrasing invariant breaks by design — the parenthetical will need a carve-out noting that Dismiss handling has intentionally diverged, or a future reader will treat the drift as a bug and re-converge.

### Canonical "log-only, not user-visible" phrasing

Precedent already exists in the same file at line 134 (Failure Handling): "Do not surface the failure as a blocking error. Note it silently in the event log." Any fix should mirror this phrasing.

### Edit-surface localization (verified)

No Dismiss-disposition references outside `clarify-critic.md` and `critical-review/SKILL.md`. Verified: `orchestrator-review.md`, `refine/SKILL.md`, `specify.md` — zero matches. No downstream consumers parse `clarify_critic` events (statusline, dashboard, metrics all scan other event types).

### Integration points the fix must preserve

- Ask-to-§4 Merge Rule (`clarify-critic.md:81–85`) — Ask items still fold into `AskUserQuestion` at §4.
- `applied_fixes` Apply-only semantics (line 106).
- Post-self-resolution count accounting (line 108) — if a new field is added, Ask→Dismiss reclassification must also be accounted for, not just Ask→Apply.
- Failure handling empty-payload pattern (line 132) — any new field must be included in the "empty on failure" list.
- YAML example block (lines 112–126) must stay synchronized with any schema change.

## Web Research

**Anthropic's canonical guidance**: Positive framing beats negative instructions. "Do not X" is unreliable and drifts further under Opus 4.7's more literal instruction-following. The current "briefly" instruction already failed for exactly this reason. Recommended counter-pattern: structural containment via structured outputs, tool calls, or file side-channels.

**Empirical reliability gap**: Structured outputs with validators achieve ~99% schema adherence; free-form prose structural tasks fail 15–20% of the time. *However*, Claude Code prompts that instruct "emit YAML matching this schema" without a validator or tool call do not have the validator-backed guarantee — schema-shaped prompting is more reliable than negative instruction but not bounded at 99%.

**Prior art for the pattern**: Reflexion (internal memory buffer for verbal reinforcement cues vs. user response), CRITIC (tool-interactive routing), and Claude Code subagents (return-only-the-summary isolation) all architecturally separate internal-bookkeeping output from user-facing output via different *destinations*, not by instructing "don't narrate."

**Anti-pattern confirmation**: Research on CoT monitorability shows LLMs *can* hide reasoning when instructed to, but the suppression is fragile under training dynamics and model upgrades. Structural/channel separation is the only robust fix.

**Load-bearing recommendation**: Do not rely on "do not surface" as the primary lever. Restructure the orchestrator's output contract so that Dismiss items are emitted via a different channel (file write / structured field) than user-facing output.

## Requirements & Constraints

**Directly applicable — `requirements/pipeline.md:127`**:

> "When the orchestrator resolves an escalation or makes a non-obvious feature selection decision (e.g., skipping a feature, reordering rounds), the relevant events.log entry should include a `rationale` field explaining the reasoning."

This is a project-level convention endorsing `events.log` as the canonical sink for orchestrator decision rationales. A Dismiss disposition is by definition a non-obvious decision (the orchestrator overrode a surfaced objection). The convention argues for preserving Dismiss rationales in the event record, not dropping them.

**Append-only JSONL** (`requirements/pipeline.md:126`): `events.log` is append-only JSONL — constrains write pattern.

**Schema stability matters**: Multiple downstream consumers of events.log exist (statusline, dashboard, metrics per `requirements/observability.md` and `requirements/pipeline.md`), though none parse `clarify_critic` events today. Additive schema changes are safe; required-field changes would be risky.

**No direct coverage**: No requirements file specifies interactive-phase output hygiene for Clarify/Research/Spec phases. Alignment with the general simplicity principle (`requirements/project.md:19`) is transitive, not direct.

**Scope**: Modifying shared lifecycle reference files is in scope. No conflicts with out-of-scope boundaries.

## Tradeoffs & Alternatives

| Alt | Description | Complexity | Reliability (per DR-4) | Coordination w/ #067 |
|-----|-------------|------------|------------------------|----------------------|
| **A** | Behavioral reword — keep "state reason" text, add explicit "events.log only, not user-visible" audience constraint | 2 files, ~3–6 lines | **Low/Medium** — same mechanism class that already failed with "briefly" | Parallel reword possible, but doesn't structurally enforce |
| **B** | Schema extension — add `dismissals: [{finding, rationale}]` array to `clarify_critic` event; reword Dismiss definition to point at schema destination | 1 file, ~10–15 lines + example | **Highest** — schema-bound output requirement; removes "narrate briefly" ambiguity entirely | Diverges from #067 (which eliminates dismiss output entirely) — drift-avoidance parenthetical at line 69 must be updated |
| **C** | Silent-by-default + user-facing "expand" command | 3+ files (new command surface) | High for default; override machinery is speculative | Worst — /critical-review would need a parallel command |
| **D** | Eliminate rationale entirely (mirror sibling #067's DR-2 fix) | 1 file, ~2 lines removed | **Highest** — removes requirement surface | Best — textually symmetric with #067 |
| **E** | Two-disposition rewrite (collapse Dismiss into silent "no-action") | 30–50 lines across 2 files | High | Requires simultaneous /critical-review rewrite |

### Two candidate recommendations (disagreement — see Open Questions)

- **Tradeoffs-agent recommendation**: **Alt D** (eliminate entirely). Rationale: DR-4 says the strongest lever is removing the output requirement; Alt D removes it; textually mirrors sibling #067.
- **Adversarial-agent rebuttal + recommendation**: **Alt B** (schema extension). Rationale:
  1. Ticket body says "events.log **only**" — a destination marker, not an instruction for absence.
  2. Epic research §54: "The fix is: Dismiss rationale **is written to events.log only**, not to the user-visible conversation." This is explicit routing, not elimination.
  3. `requirements/pipeline.md:127` endorses `rationale` fields on events.log for non-obvious decisions. Eliminating Dismiss rationale capture is a convention violation.
  4. Epic DR-2's justification for eliminating Dismiss in `/critical-review` depends on prior synthesis exposure (Step 3 showed all objections). Clarify-critic has **no prior synthesis exposure** — the critic's raw prose never reaches the user before disposition. Alt D loses the only audit trace.
  5. DR-4 argues for **structural containment** — Alt B *is* the structural containment (schema-bound field); Alt D removes it from the option space entirely.

## Adversarial Review

**Rejects Alt D on scope and audit-trail grounds**:

- Alt D redefines "only" as "nowhere" — a silent scope creep beyond the ticket's literal text.
- Alt D breaks `requirements/pipeline.md:127` rationale convention.
- Alt D is asymmetric with its justification: epic DR-2 relies on prior synthesis exposure that clarify-critic does not have.
- If Alt D lands, zero audit trail remains for which critic objections were dismissed and why — the critic's raw prose was never user-visible to begin with.

**Favors Alt B with specific guardrails**:

- Add `dismissals: [{finding, rationale}]` as a schema field (required-when-nonzero; empty on failure per existing pattern).
- Assert `len(dismissals) == dispositions.dismiss` in the spec (prevents lazy orchestrator from emitting count-only).
- Replace `clarify-critic.md:73` text: strike "State the dismissal reason briefly." and replace with a schema-destination directive ("Record the dismissal reason in the event's `dismissals` array; do not narrate.").
- Update `clarify-critic.md:69` drift-avoidance parenthetical to note that Dismiss handling intentionally diverges from `/critical-review` Step 4 (preventing a future "consistency fix" regression).
- Extend failure-handling list at line 132 to include `dismissals: []` on failure.
- Extend self-resolution count accounting at line 108 to cover Ask→Dismiss reclassification (not just Ask→Apply).

**Edge cases and assumptions to watch**:

- No validator exists for `clarify_critic` events today. Without one, Alt B degrades toward Alt A reliability in the worst case (an orchestrator can emit `dismissals: []` with `dispositions.dismiss: 3`). Mitigation: spec the invariant textually; a full JSONL validator is out-of-scope (potential follow-up ticket).
- Self-resolution Ask→Dismiss reclassification: the rationale captured would be the self-resolution reasoning, not the original critic objection. Spec must clarify which prose lands in `dismissals[].rationale`.
- Schema extension is safe because no consumer parses `clarify_critic` today. If strict parsers emerge later (dashboard work), schema versioning becomes a concern — note as a future risk, not a blocker.
- Preservation surface under-enumerated in ticket: ticket names only Ask→§4; spec must also preserve `applied_fixes` Apply-only semantics, failure-handling empty-payload pattern, and self-resolution count accounting.

**Agent 4 defect noted**: Tradeoffs agent symmetrized epic DR-2 from `/critical-review` to clarify-critic without checking whether DR-2's "prior exposure in Step 3" premise holds in clarify-critic. It does not. This is the largest defect in the multi-agent synthesis.

## Open Questions

1. **Alt D (eliminate) vs. Alt B (schema extension) — which satisfies the ticket?** The tradeoffs agent recommends Alt D; the adversarial agent rebuts with a strong case for Alt B grounded in (a) ticket-text fidelity ("only" = destination), (b) epic research §54 ("is written to events.log only"), (c) `requirements/pipeline.md:127` rationale convention, and (d) clarify-critic lacks the prior-synthesis-exposure premise that justified DR-2 in `/critical-review`. Adversarial reasoning is stronger, but the final call is a spec-phase decision that may involve the user's judgment on audit-trail value.

   **Deferred: will be resolved in Spec by surfacing the disagreement to the user and selecting based on the audit-trail preservation question.**

2. **Should the `clarify-critic.md:69` drift-avoidance parenthetical be updated in this ticket, or deferred to sibling #067?** The invariant breaks regardless of which fix lands. Updating it in both tickets risks merge coordination; updating it in one (whichever lands first) is cleaner. This is a scope boundary question.

   **Deferred: will be resolved in Spec — likely in-scope for this ticket since #067's timing is not guaranteed, but the user may prefer to keep the fix scopes minimal and fix the parenthetical in whichever ticket lands second.**

3. **Should `clarify.md` §3a gain a one-line reinforcement** (e.g., "Critic dispositions are internal bookkeeping — only Ask items surface to the user via §4") or remain pure delegation? The ticket says both files are in scope; Agent 1 found §3a currently has nothing to edit. A reinforcement is defensive but may be unnecessary belt-and-suspenders.

   **Deferred: will be resolved in Spec — the call depends on whether the user wants defense-in-depth here or trusts the single edit site to hold.**
