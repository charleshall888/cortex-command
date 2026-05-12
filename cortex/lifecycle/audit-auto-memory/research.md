# Research: Audit Auto-Memory for cortex-command

## Audit framing

This repo's design philosophy is **rails not memory**: skills, hooks, lifecycle phases, and the MUST-escalation policy in `CLAUDE.md` are deliberate, version-controlled, reviewable. Auto-memory is the inverse — invisible, persistent, accumulates without review. The MUST-escalation policy in `CLAUDE.md:52` already requires evidence artifacts for new MUSTs; auto-memory bypasses that gate entirely.

In a recent session, two memories (`parallel-sessions-inline-default` and `commit-to-recommendation-after-research`) caused deviations from explicit lifecycle protocol instructions. That prompted this audit.

The audit discriminates between **two distinct rail types**:

1. **Repo-authoring rails** — guidance for someone editing cortex-command itself. Lives in this repo's `CLAUDE.md`. Does NOT ship to other repos.
2. **Plugin workflow rails** — guidance for someone *using* the shipped plugins (`cortex-core`, `cortex-overnight`, `cortex-dev-extras`) in any repo. Lives inside `skills/*/SKILL.md` and `skills/*/references/`. Mirrored into `plugins/*/` by the pre-commit hook and ships via `/plugin install`.

A memory that doesn't have a clean fit in either type is a strong signal the rule was over-extracted from a specific incident.

## Per-memory triage (final)

| # | File | Verdict | Rail type | Home | One-line rationale |
|---|------|---------|-----------|------|--------------------|
| 1 | `feedback_audit_user_facing_affordances.md` | **PROMOTE** | repo-authoring | this-repo `CLAUDE.md` | Cited example (Clarify-phase audit) is cortex-command-specific; activates only when editing cortex-command itself |
| 2 | `feedback_commit_to_recommendation_after_research.md` | **DISCARD** | — | — | Conflicts with deliberate menu-polls in refine §4 value-gate, clarify §4 question-threshold, critical-review Step 4 Ask. Partly redundant with the harness's "exploratory questions → recommendation" rule. Already partially codified at `skills/research/SKILL.md:159` (Agent 4 output format requires "Recommended approach: [rationale]"). |
| 3 | `feedback_design_principle_what_why_not_how.md` | **PROMOTE** | repo-authoring | this-repo `CLAUDE.md` | Conceptual partner to MUST-escalation policy at `CLAUDE.md:52`; universal principle, load-bearing for cortex-command authoring |
| 4 | `feedback_empirically_verify_synthesis_claims.md` | **PROMOTE** | plugin-workflow | `skills/critical-review/SKILL.md` Step 4 (line ~104 anchor-check) | Operationalizes the existing "new evidence, not prior reasoning" anchor-check into a measurement step |
| 5 | `feedback_parallel_sessions_inline_default.md` | **DISCARD** | — | — | Originating incident was real but isolated; the broad "stateful for remainder of conversation" interpretation is what caused the protocol deviation. The concrete shared-state hazards are case-by-case awareness, not a rail-worthy rule. |

**Tally: 3 PROMOTE, 2 DISCARD, 0 KEEP.**

### Memory 1 — `feedback_audit_user_facing_affordances.md`

**Claim:** When auditing skill/phase structure for token-efficiency consolidation, don't classify a phase boundary as "ceremonial" based on artifact-production analysis alone — a phase can produce no artifact and still be load-bearing because of a user-facing affordance.

**Verified against current repo:**
- `skills/lifecycle/references/clarify.md` (the cited canonical example) exists with `AskUserQuestion` in its §4 Question Threshold.
- `skills/lifecycle/SKILL.md` has an explicit "Kept user pauses" inventory section with a parity test at `tests/test_lifecycle_kept_pauses_parity.py`.
- Principle remains live and aligned with the parity-test design.

**Why holds?** Yes — the failure mode (auditor classifies a user-blocking gate as "ceremony") is structural and recurs whenever someone trims the harness.

**Generalization:** Applies whenever cortex-command's own phases get audited. Other-repo users who install the plugin don't typically edit its internals; this is not plugin-workflow material.

**Verdict: PROMOTE → this-repo `CLAUDE.md`.** Should be visible to every contributor auditing a phase boundary. Invisibility actively undermines its purpose.

### Memory 2 — `feedback_commit_to_recommendation_after_research.md`

**Claim:** When research/clarify surfaces tradeoffs across multiple approaches, propose the recommended approach with explicit reasoning rather than escalating to an `AskUserQuestion` menu.

**Verified against candidate plugin homes:**
- `skills/research/SKILL.md:159` — Agent 4 (Tradeoffs & Alternatives) output format already requires "Recommended approach: [rationale]". The principle is *already structurally enforced* at the agent layer.
- `skills/refine/SKILL.md` Step 5 §4 — the complexity/value gate **deliberately presents 2–3 alternatives** ("drop entirely", "bugs-only", "minimum viable") and asks the user to choose. This is a value-gate menu by design; memory #2's rule would tell the agent to commit to one, contradicting it.
- `skills/lifecycle/references/clarify.md` §4 — Question Threshold uses `AskUserQuestion` for low-confidence dimensions. Deliberate question gate.
- `skills/critical-review/SKILL.md` Step 4 — already says "**Ask** when the fix involves user preference, scope decision, or genuine uncertainty." The carve-out memory #2 wants is already there.

**Why fails?** The rule either conflicts with deliberate gate design or is already implemented in the target skills. It's also partially redundant with the harness's "For exploratory questions, respond with a recommendation" rule.

**Generalization:** The originating frustration was specific to one session. The rule does not cleanly generalize without a carve-out so dense it would muddy more than help.

**Verdict: DISCARD.** No clean plugin home; rule conflicts with deliberate design in multiple places; principle is already structurally enforced where it matters.

### Memory 3 — `feedback_design_principle_what_why_not_how.md`

**Claim:** Prescribe What (decisions, gates, output shapes) and Why (failure modes, intent), resist prescribing How (step-by-step method). Capable models (Opus 4.7+) figure out method themselves.

**Verified against current repo:**
- Aligned with `CLAUDE.md:52` post-Opus-4.7 MUST-escalation policy ("Default to soft positive-routing phrasing").
- Reflected in recent commits like `b151025c` (extract OQ6 tone policy, drop meta-rule) and `d7ed3d87` (extract lifecycle SKILL.md body to references/).
- Reflected in the broader epic #82 harness adaptation theme.

**Why holds?** Yes — actively driving live design decisions.

**Generalization:** Universal principle for harness authoring; load-bearing for cortex-command's design philosophy.

**Verdict: PROMOTE → this-repo `CLAUDE.md`.** Conceptual partner to the MUST-escalation policy — co-locate to prevent drift.

### Memory 4 — `feedback_empirically_verify_synthesis_claims.md`

**Claim:** Before applying/dismissing adversarial-synthesis verdicts, run the empirical checks the reviewers' claims rest on. Specific numbers can be specific-and-wrong.

**Verified against current repo:**
- `skills/critical-review/SKILL.md:104` contains the verbatim anchor-check: "Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning."
- Memory #4's contribution: making "new evidence" actionable — explicitly measure (`time`, `wc -c`, grep), don't just re-read the artifact text.

**Why holds?** Yes — the #190 incident is preserved in git; the over-trust failure mode is real.

**Generalization:** Applies to every critical-review Step 4 session.

**Verdict: PROMOTE → `skills/critical-review/SKILL.md` Step 4 strengthening.** Ships in cortex-core plugin to every repo where critical-review is used.

### Memory 5 — `feedback_parallel_sessions_inline_default.md`

**Claim:** When the user flags parallel sessions, prefer inline work over subagent dispatch, skip regenerators that touch shared state, and persist that mode for the remainder of the conversation.

**Verified against current repo:**
- `skills/lifecycle/references/concurrent-sessions.md` exists and covers `.session` files and listing incomplete features — but does not cover the inline-default behavior.
- The dual-source pre-commit hook (`just setup-githooks`) already enforces canonical→mirror sync at commit time, which catches some clobber scenarios.

**Why fails as a rail?** The originating incident (#198) was a one-time interruption during opus-reviewer dispatch. The memory's broad "stateful for remainder of conversation" interpretation is what caused the protocol deviation noted in the audit prompt. The concrete shared-state hazards (regenerators clobbering files) are real but are better handled by case-by-case awareness than by a rail that creates a stateful session-spanning override. Codifying the rule would re-create the failure mode the audit is trying to prevent.

**Generalization:** The concrete hazards generalize, but encoding them as a behavioral rule for `concurrent-sessions.md` would either (a) repeat the over-broad failure mode, or (b) be so narrowly scoped that it adds noise without protection.

**Verdict: DISCARD.** Concurrent-session hazards remain case-by-case awareness; if the failure mode recurs, a more carefully scoped rail can be authored from that specific incident's evidence per the MUST-escalation policy.

## Candidate-home evaluation for the 3 PROMOTE verdicts

| Memory | Home | Fit check |
|--------|------|-----------|
| 1 (audit-affordances) | this-repo `CLAUDE.md` — new "Skill / phase authoring guidelines" subsection (or extension to Conventions) | The principle is meta-guidance for harness authoring; sits naturally next to the MUST-escalation policy. The kept-pauses inventory in `skills/lifecycle/SKILL.md` is the concrete artifact this principle protects — cross-reference it. |
| 3 (what-why-not-how) | this-repo `CLAUDE.md` — adjacent to or inside the MUST-escalation policy section | These two policies are conceptually paired ("trust capable models, don't over-prescribe"). Co-location avoids drift. |
| 4 (measure-don't-reread) | `skills/critical-review/SKILL.md` Step 4 anchor-check (line ~104) | The Step 4 anchor-check is the precise hook. One-sentence operationalization keeps the existing rule and adds the "measure, not re-read" clause. Ships in cortex-core plugin. |

## Strategic question 1: Disable auto-memory entirely for this repo?

**Out of scope — user owns this.** The user has stated they will handle turning off auto-memory themselves (mechanism: their choice — `CLAUDE.md` instruction, harness setting, manual file-deletion, etc.). The audit's recommendation that the channel should be closed stands; the implementation does not need to live in this spec.

This also moots strategic question 2 (MUST-escalation policy coherence): if the disable lives outside this spec, there is no in-spec rule to cross-reference.

The 5 existing memory files (2 DISCARD + 3 PROMOTE) are similarly user-owned cleanup: the DISCARD verdicts justify deletion; the PROMOTE files become redundant once the rails land. Deletion is a follow-up action the user manages.

## Strategic question 3: Decomposition — single lifecycle vs. discovery+epic

**Single lifecycle.** With scope reduced to 3 PROMOTE rails — two `CLAUDE.md` edits (R1, R2) and one `skills/critical-review/SKILL.md` edit (R3) — the work is small enough to plan and review as one unit. No epic+children overhead is justified.

## Constraints honored

- The 5 memory files were read in full as source of truth.
- No memory files deleted by the audit (user-owned cleanup, deferred).
- No edits to `skills/`, `hooks/`, `claude/hooks/`, or `bin/cortex-*` yet — those edits will land via the spec/plan/implement phases of this lifecycle.
- `feedback_parallel_sessions_inline_default` was NOT applied during this audit; concurrent sessions were not flagged.
- No new MUST/CRITICAL/REQUIRED language proposed in any promotion.

## Notable accuracy notes from verification

- Memory #4's "resolutions must rest on new evidence, not prior reasoning" is **already verbatim** at `skills/critical-review/SKILL.md:104`. R3 strengthens it; it does not duplicate.
- Memory #2's principle is **already partially codified** at `skills/research/SKILL.md:159` (Agent 4 "Recommended approach: [rationale]" output format) and is **deliberately contradicted** by `skills/refine/SKILL.md` Step 5 §4 (complexity/value gate as intentional menu).
- Memory #5's stateful claim is the part that caused the protocol deviation noted in the audit prompt; codifying any version of it risks re-creating that failure mode.

## Open questions for spec phase

None. All design choices for the 3 surviving promotions are resolved.
