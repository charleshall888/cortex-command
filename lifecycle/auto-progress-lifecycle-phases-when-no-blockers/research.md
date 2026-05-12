# Research: Auto-progress lifecycle phases when no blockers

Audit `skills/lifecycle/` and `skills/refine/` to inventory every user-blocking pause at phase boundaries and classify ceremonial (remove) vs. substantive (keep). Targets the user-observed behavior where Review→Complete (and other transitions) sometimes pause for confirmation when no decision needs to be made.

## Codebase Analysis

### Pause inventory (file:line, classification, rationale)

| # | File:Line | Type | Current text (excerpt) | Disposition |
|---|-----------|------|------------------------|-------------|
| 1 | `skills/lifecycle/SKILL.md:60` | substantive | "Present the candidates via `AskUserQuestion` and halt for user selection" (ambiguous backlog resolver match) | Keep |
| 2 | `skills/lifecycle/SKILL.md:106` | conditional/ceremonial | "If resuming from a previous session, report the detected phase and offer to continue or restart from an earlier phase" | Reframe — see Adversarial #7 |
| 3 | `skills/lifecycle/references/backlog-writeback.md:11–15` | substantive | "If parsed `status` is `complete`: present prompt … Close lifecycle / Continue from current phase" | Keep |
| 4 | `skills/lifecycle/references/clarify.md:55–61` | conditional | "If any dimension is still low confidence or critic raised Ask items: present via AskUserQuestion (≤5 questions). Otherwise: skip questions and proceed" | Keep — already conditional |
| 5 | `skills/lifecycle/references/clarify.md:115` | substantive | "If `cortex-update-item` fails, surface the error and ask the user to resolve" | Keep |
| 6 | `skills/lifecycle/references/specify.md:36–60` | conditional | Structured interview only fires when answers aren't evident from research | Keep |
| 7 | `skills/lifecycle/references/specify.md:65–70` | conditional | Cycle ≥ 2 confidence-check loop-back prompt | Keep |
| 8 | `skills/lifecycle/references/specify.md:161` | ceremonial-framing | "**The user must approve before proceeding to Plan. If the user requests changes, revise the spec and re-present.**" | **Reframe** — see M1 |
| 9 | `skills/lifecycle/references/plan.md:96–109` | substantive | Low-confidence synthesizer fallback presents competing variants for user-pick | Keep |
| 10 | `skills/lifecycle/references/plan.md:275–282` | ceremonial-framing | "**The user must approve before implementation begins. If the user requests changes, revise and re-present.**" | **Reframe** — see M1 |
| 11 | `skills/lifecycle/references/implement.md:16–43` | substantive | §1 Branch selection: 3-way AskUserQuestion (current branch / autonomous worktree / feature branch) | Keep |
| 12 | `skills/lifecycle/references/implement.md:114` | substantive | At 30 iterations (~1 hr), pause and offer to suspend polling | Keep |
| 13 | `skills/lifecycle/references/implement.md:195–201` | substantive | Task failure → retry/skip/abort prompt | Keep |
| 14 | `skills/lifecycle/references/implement.md:265` | (correct already) | "Proceed automatically — do not ask the user for confirmation before entering the next phase" | No change |
| 15 | `skills/lifecycle/references/review.md:192–203` | conditional (correct already) | APPROVED → auto-Complete; CHANGES_REQUESTED cycle 1 → auto-Implement; otherwise escalate | No change (but see Adversarial #4 — cycle counter bug) |
| 16 | `skills/lifecycle/references/review.md:147` | substantive | Missing `## Requirements Drift` section → re-dispatch, then escalate after one retry | Keep |
| 17 | `skills/lifecycle/references/complete.md:12–13` | substantive | If tests fail, halt git workflow until resolved | Keep |
| 18 | `skills/lifecycle/references/complete.md:72` | (correct already) | "Do not ask the user to choose — branch-and-state-driven" | No change |
| 19 | `skills/refine/SKILL.md:21` | substantive | Empty `$ARGUMENTS` → prompt for input | Keep |
| 20 | `skills/refine/SKILL.md:38–41` | substantive | Exit 2 ambiguous match → user picks candidate | Keep |
| 21 | `skills/refine/SKILL.md:62` | ceremonial | "If both artifacts exist and the user chooses to re-run, re-running will overwrite the existing spec" | **Reframe** — skip silently when both exist; only re-run on explicit request |
| 22 | `skills/refine/SKILL.md:148–150` | substantive | Unresolved `## Open Questions` in research.md → resolve or defer each before Spec | Keep |
| 23 | `skills/refine/SKILL.md:160–161` | substantive | Spec phase §4 Complexity/value gate — present alternatives before approval | Keep |

### Phase Transition contract analysis

`skills/lifecycle/SKILL.md:161–172` (Phase Transition section) says:

> "After completing a phase artifact, announce the transition and proceed to the next phase automatically."

**Ambiguity** (per Adversarial #3): "completing a phase artifact" is ambiguous — it could mean "the artifact exists on disk" OR "the artifact has been approved." Per-phase prose currently treats `spec.md`/`plan.md` existence as separate from approval, which is consistent with the second reading. The spec must disambiguate this explicitly.

### Verdict routing in review.md

Already correctly auto-routes (review.md:192–203):
- APPROVED → Complete (auto)
- CHANGES_REQUESTED cycle 1 → Implement (auto)
- CHANGES_REQUESTED cycle 2+ or REJECTED → escalate to user

**Adversarial #4 finding**: the cycle counter (`cortex_command/common.py:188–196`) uses `re.findall(r'"verdict"\s*:\s*"([A-Z_]+)"', review_content)` against `review.md`. If the reviewer overwrites `review.md` each cycle (per `review.md:64` "Write your review to lifecycle/{feature}/review.md"), the cycle count stays at 1 forever and cycle-2 escalation never fires — silent infinite-rework loop. **This pre-existing bug must be fixed before auto-advance on CHANGES_REQUESTED is safe.**

### Critical-review interaction

`specify.md:149–151` and `plan.md:269–273` auto-invoke critical-review for tier=complex features. After synthesis returns, the prose says "Present the synthesis to the user before spec/plan approval."

**Disposition**: Apply/Dismiss is a real user decision per the existing alignment-considerations propagation contract (`refine/SKILL.md:120`). Keep. Critical-review synthesis presentation is NOT ceremonial.

### Refine vs Lifecycle scope split

- **Clarify**: canonical in `lifecycle/references/clarify.md`; refine delegates (no duplication)
- **Research**: delegated to `/cortex-core:research` skill from both refine and lifecycle paths
- **Specify**: canonical in `lifecycle/references/specify.md`; refine delegates with documented adaptations (refine/SKILL.md:155–173). The Complexity/value gate (refine §4 adaptation) is refine-only.

No contradictory pauses across the two skills.

## Web Research

- **Anthropic's framework is monitor-and-intervene, not gate-every-step.** "On the most complex tasks, Claude Code stops to ask for clarification more than twice as often as humans interrupt it." Source: [Measuring agent autonomy](https://www.anthropic.com/research/measuring-agent-autonomy). Auto-mode adds gates for irreversible actions (e.g., cancelling subscriptions). Source: [Auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode).
- **Industry convergence (LangGraph, Temporal, CrewAI, AutoGen): auto-advance on clean verdict; pause only for irreversible/high-blast-radius/REJECTED.** LangGraph's `interrupt()` is purpose-built for *selective* pauses; unconditional pauses are explicitly an anti-pattern. Source: [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).
- **Approval fatigue is documented:** after 20–30 similar prompts, users rubber-stamp. Source: [UX Magazine — Consent Fatigue](https://uxmag.com/articles/consent-fatigue-are-we-designing-people-into-compliance). High-impact/irreversible actions → strong confirmation; routine/reversible → light or post-hoc check. Source: [Reversible vs irreversible decisions](https://www.howtothink.ai/learn/reversible-versus-irreversible-decisions).
- **Best-practice rule**: "Any irreversible or difficult-to-reverse action should require human approval by default." Source: [Noma Security — destructive capabilities](https://noma.security/blog/the-risk-of-destructive-capabilities-in-agentic-ai/).

**Application caveat (Adversarial #2)**: the Anthropic "twice as often" data is about *clarification mid-task*, not *deliberate approval gates at irreversible-action seams*. Don't misapply it to spec/plan approval.

## Requirements & Constraints

- **`requirements/project.md:13` Handoff readiness**: *"The spec is the entire communication channel."* Spec approval is the formal contract between daytime collaboration and overnight execution.
- **`requirements/project.md:11` Day/night split**: Daytime is close iterative collaboration. Pauses are appropriate when daytime alignment is genuinely needed.
- **`docs/interactive-phases.md:49–78`** explicitly states Specify and Plan require user approval; Implement/Review/Complete are automated.
- **`requirements/pipeline.md:19–42`**: forward-only phase transitions; deferral halts ambiguous decisions.
- **`requirements/pipeline.md:132–134`**: state file reads are not protected by locks (forward-only transitions make this safe); the design depends on monotonic phase progression.
- **`CLAUDE.md` MUST-escalation policy**: soft positive-routing is default; MUST language requires evidence per epic #82.
- **`docs/policies.md`** (tone): no tone directives shipped; rewrites must use standard Claude Code voice.

## Tradeoffs & Alternatives

**Alternative A — Prose-only rewrite.** Edit SKILL.md and references markdown to remove ceremonial preambles. ~50–100 lines changed. Low complexity. Risk: load-bearing routing logic (review verdict, cycle counter) is prose-only — known failure mode per `requirements/project.md:33` (Skill-helper modules).

**Alternative B — Full helper subcommand (`cortex_command/lifecycle.py`).** Extract phase-transition routing into Python. ~600–800 LOC. High complexity. Maintainability win for testability. Overkill for transitions that are genuinely simple state progressions.

**Alternative C — Hybrid (recommended by Agent 4).** Prose rewrite + a Python helper subcommand only for review-verdict routing (the one load-bearing branching transition). ~350 LOC. Matches the existing `critical_review.py` / `discovery.py` precedent.

**Adversarial-adjusted recommendation**: **Alternative C with two corrections**:
1. The helper returns *advice*; the skill emits the `phase_transition` event after it commits to entering the next phase. Helper writes no events. (Adversarial #5)
2. Fix the cycle counter (`common.py:188–196`) before any auto-advance on CHANGES_REQUESTED ships. Either change `review.md` to append-only, or compute cycle from `review_verdict` events in `events.log` (preferred — events.log is already append-only). (Adversarial #4)

## Adversarial Review

1. **Spec/Plan approval are NOT ceremonial — they are the highest-blast-radius transitions in the lifecycle.** Removing the gates violates the daytime/overnight handoff contract (`requirements/project.md:13`). Reframe instead: convert "ceremonial question + approval gate" into "approval surface IS the question." Present the artifact summary + Risks directly as the AskUserQuestion options, with Approve / Request Changes / Cancel as the response set. One pause, no preamble. (M1)
2. **Plan→Implement has the highest blast radius**: launches commits, sub-agents in worktrees, and on the autonomous-worktree path a 4-hour detached subprocess. Removing plan approval makes the Risks section inert.
3. **SKILL.md:163 "after completing a phase artifact" is ambiguous.** Per-phase prose's gate-keeping IS the disambiguation (artifact must be approved to be "complete"). Spec must state this rule explicitly. (M9)
4. **Cycle counter is structurally broken** (`common.py:188–196`): regex-counts verdict JSON in `review.md`, but `review.md` is overwritten each cycle per `review.md:64`. Count stays at 1 forever → cycle-2 escalation never fires → infinite rework loop possible. **Pre-existing bug; auto-advance on CHANGES_REQUESTED is unsafe until fixed.** (M2)
5. **Helper event-logging direction must be reversed** in Alternative C: helper returns advice; skill emits event after committing to next phase. (M6)
6. **Critical-review synthesis presentation is NOT ceremonial** — Apply/Dismiss is a real decision surface. (M5)
7. **Resume "offer to continue or restart" (`SKILL.md:106`) is load-bearing for staleness detection.** `docs/interactive-phases.md:131–135` explicitly notes the readiness gate doesn't assess content freshness. Enrich (surface staleness signals — artifact age, commits since) rather than remove. (M4)
8. **Test coverage gap is severe.** No existing test asserts that lifecycle auto-advances rather than pausing. Minimum surface: grep `events.log` for expected `phase_transition` sequence on happy path with no intervening human-input events. (M7)
9. **Backward compatibility**: there is no `spec_approved`/`plan_approved` marker on disk — only artifact existence. The detector assumes existence = approval. In-flight lifecycles paused at "spec approval gate" could silently auto-advance under new prose. Add explicit approval events to `events.log` (or sentinel files) and update `common.py:253` accordingly. (M3)
10. **§2a cycle-2 confidence-check loop** in specify.md is a legitimate pause and must be explicitly enumerated as a kept-pause to prevent over-eager removal. (M8)
11. **Within-phase prompts (e.g., implement.md §1 branch selection) must NOT be conflated with phase-transition auto-advance.** The spec must carve out: transition auto-advance ≠ deletion of within-phase prompts. (#11 in adversarial)

## Open Questions

These must be resolved before Spec phase.

1. **Q1: Spec→Plan and Plan→Implement disposition** (this is the decision-point):
   - **Option A (user's initial answer)**: full auto-advance, no approval gate at all.
   - **Option B (adversarial recommendation M1)**: keep the approval pause, but reframe — the artifact summary IS the AskUserQuestion options (Approve / Request Changes / Cancel). No separate "are you ready to approve?" preamble. One question, not two.
   - **Option C**: full auto-advance for Plan→Implement only; keep Spec→Plan approval gate (since spec is the daytime/overnight handoff contract).
   - **Recommendation**: Option B for both. Eliminates the ceremonial friction the user complained about without losing the daytime alignment surface that Handoff readiness requires.

2. **Q2: Cycle counter bug (Adversarial #4) — fix in this lifecycle or split into a separate ticket?**
   - In-scope: needed before CHANGES_REQUESTED auto-advance is safe.
   - Out-of-scope option: file separately and treat this lifecycle as "prose-only, defer auto-routing fixes until counter is fixed."
   - **Recommendation**: fix in this lifecycle. It's a 1-line change (count events.log entries instead of regexing review.md) and the auto-advance contract depends on it.

3. **Q3: Approval-event marker on disk (Adversarial #9)** — add `spec_approved` / `plan_approved` events to events.log + update phase detector?
   - In-scope: closes the backward-compatibility hole for in-flight lifecycles.
   - Out-of-scope option: defer; treat existing in-flight lifecycles as a known migration issue.
   - **Recommendation**: in-scope. The phase detector already reads events.log via `common.py`; adding two event types is mechanical.

4. **Q4: Hybrid Alternative C (Python helper for review verdict) — in this lifecycle or follow-up?**
   - **Recommendation**: prose-only this lifecycle (Alternative A simplified). The cycle-counter fix (Q2) and approval-event additions (Q3) are the actual load-bearing helpers; the rest of the routing is already correctly prose-described. A standalone `route-review-verdict` subcommand is premature optimization once the cycle-counter is fixed in `common.py`.

## Considerations Addressed

None — `research-considerations` was not passed in this invocation.
