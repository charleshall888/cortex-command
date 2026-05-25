# Research: Offer consolidation clusters before R15 gate in discovery decompose

Lifecycle: `cortex/lifecycle/offer-consolidation-clusters-before-r15-gate/`
Tier: complex · Criticality: high
Parent backlog: `cortex/backlog/247-offer-consolidation-clusters-before-r15-gate-in-discovery-decompose.md`

## Codebase Analysis

### Current R15 implementation

The R15 gate is implemented through `cortex_command/discovery.py`'s `emit_checkpoint_response` helper:

- **Subcommand**: `cortex-discovery emit-checkpoint-response --topic <topic> --checkpoint decompose-commit --response <response> --revision-round <int>`
- **Helper function**: `emit_checkpoint_response()` (discovery.py:537–559)
- **Validation frozensets**: `_CHECKPOINT_VALUES` (line 402), `_RESPONSE_VALUES` (lines 403–411)
- **Response options**: `approve-all`, `revise-piece`, `drop-piece`
- **Event emitted**: `approval_checkpoint_responded` with `checkpoint: decompose-commit`
- **Prose definition**: `skills/discovery/references/decompose.md` lines 100–112

Verbatim R15 loop semantics (decompose.md:104–110):

> - **`approve-all`** — proceed to write all N tickets to `cortex/backlog/`.
> - **`revise-piece <N>`** — open a free-text revision prompt scoped to ticket N's body. The agent re-walks ticket N's `## Why`, `## Role`, `## Integration`, `## Edges`, and `## Touch points` under the user's direction and re-presents the FULL batch (not just ticket N) at the gate. Loop continues until `approve-all` or all pieces are dropped.
> - **`drop-piece <N>`** — do not write ticket N to `cortex/backlog/`. Record the dropped piece in `decomposed.md` with a one-sentence rationale under a `## Dropped Items` heading. Continue the gate loop with the remaining tickets.

R15 is itself a loop — revise-piece and drop-piece both re-present the full batch in the same gate session. This is a load-bearing fact for the placement decision (see Adversarial #3).

### Existing §3 "Consolidation Review" (decompose.md:46–52)

Already-present prose-only reactive surface:

> If during ticket authoring the agent finds that two pieces share identical Touch points and identical Role paragraphs, that is a signal the research-phase merger missed a case — surface this to the user with the option to return to research rather than silently consolidating at decompose time. If no consolidation candidates surface, proceed to §4.

This is a narrow reactive case (identical Touch points + identical Role) routing back to research, distinct from the new feature's proposed proactive set-level consolidation.

### Files that would change under the ticket as written

- `skills/discovery/references/decompose.md` — new pre-R15 protocol section
- `skills/discovery/SKILL.md` — registration of the new gate, possibly in the kept-pauses-style enumeration
- `cortex_command/discovery.py` — new helper subcommand if the surface is a separate checkpoint, OR new entries in `_RESPONSE_VALUES` if folded into R15
- `bin/.events-registry.md` — new event row OR new `checkpoint` value for existing `approval_checkpoint_responded`
- New test coverage under `tests/test_discovery_*`

### Helper-module pattern

Discovery follows the project's "Skill-helper modules" architectural constraint (project.md:35): atomic CLI subcommands fusing validation + mutation + telemetry. The pattern for adding a new gate is well-trodden — existing subcommands like `emit_architecture_written()`, `emit_checkpoint_response()`, `emit_prescriptive_check()` all share shape. Event paths resolve through `resolve_events_log_path()` (line 153–197) honoring R13 re-run suffixes and `LIFECYCLE_SESSION_ID`.

### Discovery has no kept-pauses parity test

`tests/test_lifecycle_kept_pauses_parity.py` scans only `skills/lifecycle/` and `skills/refine/`. Discovery has zero parity enforcement for its `AskUserQuestion` call sites. Adding a new pause to discovery decompose ships into a no-test zone.

### Decomposed.md corpus evidence

- `cortex/research/swap-daytime-autonomous-for-worktree-interactive/decomposed.md` shows consolidations were user-driven at R15 in round-1 — the existing flow already supports consolidation, just reactively.
- The R15 corpus across the entire project: exactly four `approval_checkpoint_responded` events with `checkpoint: decompose-commit`. Three completed in round 0 (one-shot approve); only `swap-daytime-autonomous-for-worktree-interactive` looped (round 1). See Adversarial #1 for full enumeration.

## Web Research

Industry prior art surveyed across AI agents, code review, ticket trackers, refactoring tools.

**Prevailing pattern: unified rich-surface review with conditional consolidation options, not a separate pre-gate pause.**

- "Approval Fatigue" guidance (aipatternbook.com): "Reviewing a coherent diff of twenty changes is more effective than reviewing twenty individual prompts." Target ~10 actions per session via a Steering Loop.
- Smashing Magazine (Feb 2026), "Designing For Agentic AI": multi-step ops should present as one consolidated surface with unified Proceed/Edit/Handle-Myself controls, not a pause per step.
- **Direct prior art**: Jira "Duplicate AI" and "Merge Assistant" — AI scans on create/update, surfaces duplicates with similarity signals, offers single-click merge. **Inline at create/update, conditional on signal, never a separate gate.**
- AI backlog-grooming tools (Eesel, Aziro, Fini Labs) all describe the same conditional inline pattern.
- GitHub itself does NOT add a "your linked issues look like duplicates" pre-merge prompt — a deliberate choice to avoid surprising the merger.

**Principled exception** — when to split out instead of fold in: arxiv 2510.05307 ("When Should Users Check?") found 81% of participants preferred intermediate confirmation IF checkpoints land on high-error-probability early steps. Split out only when the splittable decision has materially different error characteristics from the rest of the surface.

**Threshold guidance**: Just-in-time refactoring research (Pantiuchina et al., ICPC '18; AntiCopyPaster 2.0; EM-Assist) treats this as binary classification with learned confidence thresholds, tuned for low false-positive rate. No clean numerical default; conservative threshold from a labeled corpus.

**Detection mechanics**: standard recipe is embed → cluster → threshold over title+body+touch-points, with cosine-similarity floor.

**Web research's recommendation: fold into existing R15 surface with a conditional option that disappears when no candidates exist.** Industry prior-art convergence is strong; the arxiv split-out exception requires evidence the consolidation decision has materially different error characteristics, which the ticket does not assert.

Primary sources:
- [Approval Fatigue — aipatternbook.com](https://aipatternbook.com/approval-fatigue)
- [Smashing — Designing Agentic AI](https://www.smashingmagazine.com/2026/02/designing-agentic-ai-practical-ux-patterns/)
- [When Should Users Check? — arxiv 2510.05307](https://arxiv.org/html/2510.05307)
- [Merge Assistant — Atlassian Marketplace](https://marketplace.atlassian.com/apps/3453335153/merge-assistant)
- [Duplicate AI for Jira](https://www.secretbakery.io/products/atlassian-jira/duplicate-ai-find-duplicate-issues-merge-issues-jira-cloud/)
- [NN/G — Progressive Disclosure](https://www.nngroup.com/articles/progressive-disclosure/)
- [Towards Just-In-Time Refactoring Recommenders — ICPC'18](https://www.cs.wm.edu/~denys/pubs/ICPC'18-BPA.pdf)

## Requirements & Constraints

### Discovery is documented inline (no area doc)

`cortex/requirements/project.md:55`:

> Discovery and backlog are documented inline (no area docs): `skills/discovery/SKILL.md`, `cortex/backlog/index.md`. Ticket body authoring is enforced via `skills/backlog-author/` (the shared sub-skill) and validated at pre-commit by `bin/cortex-check-prescriptive-prose` (LEX-1 scanner...).

All discovery constraints live inline in skill files. No `cortex/requirements/discovery.md` exists.

### Kept user pauses inventory

`cortex/requirements/project.md:27`:

> Kept user pauses come in two kinds: (a) `AskUserQuestion`-site pauses where a phase blocks for an interactive answer; (b) phase-exit pauses where a phase exits cleanly and waits for the user to re-invoke after performing an out-of-band action. The `skills/lifecycle/SKILL.md` kept-pauses inventory and `tests/test_lifecycle_kept_pauses_parity.py` enforce both kinds.

**The inventory and parity test are scoped to lifecycle and refine.** Discovery has no equivalent. A new discovery pause cannot be silently caught by drift unless parity coverage is added.

### User-affordance authoring principle

`CLAUDE.md` "Skill / phase authoring guidelines":

> Before classifying a phase boundary or gate as ceremonial, identify the user-facing affordance that boundary protects. A pause that looks redundant from the agent's perspective may be the only point where a human can redirect, reject, or reshape the work before the lifecycle advances.

The dual reads as: don't add a pause unless you can name the affordance it protects, and don't remove one unless you can confirm it doesn't protect one.

### Events-registry constraint

`bin/.events-registry.md` declares every emitted event with consumer + scan_coverage + producer + schema. The existing `approval_checkpoint_responded` row at line 116 already covers both R4 and R15 via the `checkpoint` field — reusing it with a new checkpoint value (e.g., `consolidation-offer`) avoids a new event row.

### LEX-1 scanner on merged bodies

`bin/cortex-check-prescriptive-prose` enforces the 5-section body template with `## Why`, `## Role`, `## Integration`, `## Edges` as forbidden sections for path:line / section-index / multi-line-fenced patterns, and `## Touch points` as the permitted section. Merging two ticket bodies requires:

- `## Role`, `## Integration`: prose merge (not concatenation) — author must rewrite
- `## Edges`, `## Touch points`: bullet union (safe)
- `## Why`: prose merge

### Backlog `grep -c` resolution

Any acceptance criterion using `grep -c "<token>"` against events.log must use a token registered in `.events-registry.md` (enforced by `tests/test_backlog_grep_targets_resolve.py`).

## Tradeoffs & Alternatives

### Alternative A: Separate pre-R15 pause

Insert a dedicated `AskUserQuestion` between ticket-body authoring and the R15 surface. Detector scans the authored set; if candidates surface, present with merge-vs-keep tradeoff; if none, skip silently.

**Pros**: Clean separation of concerns — consolidation is a different decision shape than per-ticket review. Dedicated framing makes the merge tradeoff explicit rather than buried in a menu. R15 grammar stays narrow.

**Cons**: Adds a kept-pause and (per Requirements above) discovery has no parity test to catch drift. Two surfaces means up to two round trips. Detection logic must be tuned to keep false-positive rate near zero or the silent-skip promise fails. Sets precedent for future pre-pauses each lobbying for their own gate.

### Alternative B: Folded into R15 surface (new option)

R15 grows a new option alongside `approve-all` / `revise-piece` / `drop-piece` — e.g., `merge-pieces <N,M,...>` or `consolidate`. Detector runs after authoring; candidate clusters surface as a derived suggestion within the R15 surface; user can take the merge action in the same round trip.

**Pros**: Single round trip on the happy path. Consolidates the post-decompose decision space into one surface. No new kept-pauses entry. Reuses existing dispatch shape, existing event schema.

**Cons**: R15's grammar grows. Post-merge state may itself contain new merge candidates — R15 must re-run detection on each loop. Hides the merge tradeoff inside an option list, which may demote it from "explicit question" to "one of several actions" — the same framing failure mode the ticket diagnoses.

### Alternative C: Do nothing

Leave the flow as-is. R15 already lets users respond to over-decomposition via `drop-piece` and `revise-piece`. The observed 10→6 case is real but rare (1 of 4 R15 invocations in the corpus has looped).

**Pros**: Zero implementation cost. Preserves narrow R15 grammar. The user's R15 affordance is already general enough.

**Cons**: Concedes the framing-inversion argument (the agent has the information about ticket shapes, so the agent should raise the question). Decomposed.md audit trail is messier (dropped pieces with separate rationales) than a clean pre-step merge would produce.

### Alternative D: Augment R15 with one new response value, no detection (surfaced by Adversarial)

Add `consolidate-pieces <N,M,...>` to `_RESPONSE_VALUES`. Semantically identical to `revise-piece` but explicit about merger as a first-class action — user names the candidates, the gate opens a free-text revision to merge the named bodies, re-presents the full (now smaller) batch. **No detector. No event. No parity-test debt. No false-positive risk.**

**Pros**: Removes the diagnosed friction (user can SAY "consolidate 3,4,5" instead of revise-then-drop-then-drop) with minimal change — one new value in `_RESPONSE_VALUES`, one new bullet in `decompose.md:104`. Inherits the existing R15 loop. Removes the detection-oracle problem entirely.

**Cons**: User still has to NOTICE the consolidation opportunity. Doesn't satisfy the ticket's "skill should be proactive" framing.

### Alternative E: Upstream R3 tightening (surfaced by Adversarial)

The root cause of over-decomposition is the research → decompose handoff. `skills/discovery/references/research.md:116-117` currently has soft prose ("if the piece count grows large, consider merging..."). Replace with a hard falsification gate at piece_count > 5 (matching the existing "Why N pieces" trigger at SKILL.md:85), forcing the architecture-write loop to justify N or merge.

**Pros**: Fixes the upstream cause rather than papering over the downstream symptom. No new gate, no new event, no detection oracle, no kept-pause debt. The piece-set entering decompose is already minimal.

**Cons**: Changes a different skill (research, not decompose). Doesn't directly answer the ticket as written — it solves the underlying problem rather than implementing the requested feature.

### Recommended approach

**Reject A and B as currently framed. Adopt D, with optional E as a follow-up consideration.**

The decisive evidence is from Adversarial #1 and #3: only one R15 invocation in the corpus has ever looped, and the "two round trips" framing conflates "messages within one loop" with "separate gate invocations." The ticket as written is designed around a single observed instance and a category error about R15's existing loop behavior. The web prior-art evidence favors B (fold-in), but Adversarial #10–#11 surfaced Option D which inherits B's surface economy without B's grammar-growth and re-detection-loop concerns.

D is the smallest change that addresses the ticket's underlying friction (the user can name the consolidation directly instead of doing revise-then-drop-then-drop). It does not require a detection oracle, does not require parity coverage, does not require new events, does not require a kept-pause inventory entry, and does not commit the project to a fragile threshold ("6+ tickets").

If the Spec phase chooses to ship the ticket as originally framed, the guard-rails in Adversarial's recommendations are mandatory (resolve §3 duplication, pin the threshold to data, define the silent-skip contract, add discovery parity coverage in the same PR).

## Adversarial Review

### Failure modes and edge cases

**1. The "two round trips" premise is n=1.** Counted every `approval_checkpoint_responded` event with `checkpoint: decompose-commit` in the corpus. Exactly **four** R15 invocations exist: three completed in round 0 (one-shot `approve-all`), one (`swap-daytime-autonomous-for-worktree-interactive`) looped to round 1. The ticket cites that exact case as motivation. **The feature is being designed around a single observed instance.**

**2. The "6+ tickets" threshold has no provenance and lands at the wrong number.** Counting tickets across all `decomposed.md` files in the corpus: distribution is 12, 11, 10, 10, 7, 6, 6, 5, 5, 5, 5, 4, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 1, 1 — only 7 of ~30 discoveries (~23%) ended at ≥6. The upstream "Why N pieces" gate in `SKILL.md:85` fires at piece_count > 5 — a "6+" trigger in the new gate is essentially the same threshold from a different direction, suggesting **the over-decomposition is more cheaply addressed by tightening R3** (see Alternative E).

**3. The R15 re-presentation cost is overstated.** R15 is itself a loop (`decompose.md:107`: `revise-piece <N>` re-walks ticket N and re-presents the FULL batch; `drop-piece <N>` continues the gate loop). A user asking "merge 3,4,5 into one" via revise-then-drop-then-drop costs three responses but in ONE gate session, not "two round trips." **The ticket conflates messages within a loop with separate gate invocations — a category error.**

**4. Detection oracle problem.** Spec defers the hardest part (detection signal) to plan. The silent-skip promise is load-bearing in the desired behavior. With false-positive rate p, every (1/p)-th high-piece-count discovery gets a pointless gate. The web agent's JIT-refactoring citations correctly identify confidence-thresholded surfacing as the standard recipe, but the spec hasn't committed to a confidence floor.

**5. False-positive cost is asymmetric and high.** A false-positive pre-pause forces the user to read N candidate-cluster descriptions, evaluate each one, and answer "no" before reaching the actual R15 review. NN/G's preference for fold-in over staged-disclosure exists precisely because pre-pause patterns amortize poorly when the precondition's false-positive rate is non-trivial.

### Security concerns and anti-patterns

**6. The existing §3 "Consolidation Review" is duplicate scope.** `decompose.md:46–52` already has a reactive consolidation surface. The new feature proposes another consolidation surface with a fuzzier trigger. Two adjacent surfaces with overlapping intent and different triggers is the source-of-truth fragmentation that Discovery's "no per-shape branching" constraint (decompose.md line 17) warns against. **Shipping both is anti-pattern.**

**7. R3 falsification is soft prose, not a hard gate.** `research.md:116` reads "consider merging pieces..." — a hint, not a gate. The over-decomposition the ticket diagnoses is more cheaply fixed by tightening R3 than by adding a new gate downstream (Alternative E).

**8. Parity-test gap invites silent drift.** Discovery has no kept-pauses parity coverage. Adding a new conditional pause to a no-parity zone is a known-fragile pattern this project's CLAUDE.md explicitly warns against ("Prefer structural separation over prose-only enforcement for sequential gates"). If the feature ships, **parity coverage for discovery must ship with it**, not as a follow-up.

### Assumptions that may not hold

**9. "Skip silently when none do" requires a binary detector.** Real-world detection is graded. The ticket and Spec must commit to a behavior on low-confidence candidates — surface ("I found one but I'm unsure" — defeats silent-skip) or suppress ("only fire when confidence ≥ T" — needs T calibration data the project doesn't have).

**10. The fold-vs-separate framing both miss the cheapest option (Alternative D).** Neither web nor tradeoffs proposed augmenting R15 with one new response value because both anchored on "we need a detection-driven proactive surface." That anchor is itself the bug.

**11. "Consolidation needs distinct framing" doesn't survive R15 inspection.** Agent 4 argues consolidation is a set-level decision R15 can't carry. But R15 already presents the full set (`decompose.md:107`: "re-presents the FULL batch") — it IS the set-level decision surface. The framing claim assumes R15 is a per-ticket linear walk, which it is not.

### Recommended mitigations

- **Strongest recommendation**: adopt **Alternative D** (one new R15 response value, no detector) OR **Alternative E** (tighten R3 upstream).
- If shipping as written (A or B): **resolve the §3 duplication first** (subsume or remove §3 — do not ship two consolidation surfaces).
- If shipping as written: **pin the threshold to data**. The "6+" needs provenance or honest documentation as arbitrary.
- If shipping as written: **define the silent-skip contract** (confidence floor) before deferring detection to plan.
- If shipping as written: **discovery kept-pauses parity test ships in the same PR**, not as a follow-up.
- **Treat the n=1 anecdote as a non-quorum**. The project's MUST-escalation policy is the appropriate evidentiary analogue: one transcript does not justify a new mechanism.

## Open Questions

1. **Direction**: Resolved — Spec on **Alternative D** (add `consolidate-pieces <N,M,...>` to R15's `_RESPONSE_VALUES`). The user explicitly directed the orchestrator to make the call after seeing the alternatives. Reasoning: D directly addresses the diagnosed friction (one response instead of three for the consolidation case) at minimum cost (no detector, no event, no parity debt, no kept-pause entry, no threshold). The n=1 corpus does not support investing in a detector (A or B); E remains valid as a complementary follow-up at the upstream R3 surface.

2. **§3 duplication question**: Resolved — Not applicable. §3 ("Consolidation Review") covers reverse-detection of research-phase merger misses (identical Touch points + Role). Alternative D adds a user-driven consolidation primitive at R15. These are different cases and do not overlap; §3 stays as-is.

3. **Threshold provenance**: Resolved — Not applicable. D has no threshold; the user names the candidates explicitly.

4. **Silent-skip contract**: Resolved — Not applicable. D has no detector; there is nothing to skip silently.

5. **Discovery parity coverage**: Deferred — D does not add a new `AskUserQuestion` site (it adds a new response value to an existing site). Discovery's parity-coverage gap remains a real follow-up issue but is orthogonal to this ticket; surface as a separate backlog item if not already tracked.

6. **Web vs Tradeoffs contradiction**: Resolved — Adversarial corpus inspection redirected past both. Both A and B were over-engineered relative to the evidence base. D inherits the spirit of fold-in (no new pause) without the detection-oracle commitment.
