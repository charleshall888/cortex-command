# Research: audit-skill-gate-pause-inventory

## Headline Finding

**The lifecycle skill has 9 user-blocking pauses; 4 are unambiguously load-bearing and 5 are candidates for removal or soft-routing.** The 4 kept pauses protect decisions the harness cannot make autonomously: complexity/criticality classification at Clarify, critical-review outcome arbitration at Research, spec approval before plan, and plan approval before implementation. The 5 candidate pauses are ceremonial in the sense that no observable affordance would be lost if they fired as auto-advance — specifically, the pre-phase announcements at Research start, Specify start, Implement start, Review start, and Complete start are structural only (they emit `phase_transition` events but do not gate a decision). **Investigation finding**: the 5 ceremonial pauses are kept today because the `tests/test_lifecycle_kept_pauses_parity.py` parity test asserts against a hardcoded inventory in `skills/lifecycle/SKILL.md:67-91` — removing any pause without updating both the SKILL.md inventory and the parity test causes a test failure. The policy decision (which pauses to remove) cannot be resolved through codebase investigation alone; it requires the operator to decide whether auto-advance on phase announcements is safe given their team's review practices. This research artifact presents the inventory and the coupling, not the removal decision.

## Research Questions

1. **How many user-blocking pauses does the lifecycle skill currently have?** → **Answered.** Nine. The inventory lives at `[skills/lifecycle/SKILL.md:67-91]` under "Kept user pauses." The parity test at `[tests/test_lifecycle_kept_pauses_parity.py:45-67]` validates this count against the implementation.

2. **Which pauses have a user-facing affordance the harness cannot substitute for?** → **Answered.** Four: (a) Clarify complexity/criticality classification — Claude presents the classification and the user confirms or overrides before any downstream routing decision; (b) Research→Decompose gate — user reviews the research output and chooses approve / revise / drop / promote-sub-topic; (c) Spec approval before Plan — user reads and approves spec.md before plan is written; (d) Plan approval before Implement — user reads and approves plan.md before implementation starts.

3. **Which pauses are structural announcements with no blocking decision?** → **Answered with caveat.** Five: pre-phase announcement pauses at Research start, Specify start, Implement start, Review start, and Complete start. Each emits a `phase_transition` event `[skills/lifecycle/SKILL.md:254-256]` and waits for user acknowledgment. No decision is required from the user — the pause is an affordance for noticing that the phase changed, not for making a choice. Caveat: the operator may use these pauses to review context before Claude continues; removing them changes the UX, not the contract.

4. **What enforces the current pause inventory?** → **Answered.** The parity test at `[tests/test_lifecycle_kept_pauses_parity.py:45-67]` reads the "Kept user pauses" section from `skills/lifecycle/SKILL.md` and asserts each pause in the hardcoded expected-set is present. Adding or removing a pause without updating both files causes the test to fail. The test was added at `[commit:adfa8b10]` as part of the sentinel-gate resilience work.

5. **Is there a cross-skill framework for gate-pause policy, or is this lifecycle-specific?** → **Answered.** Lifecycle-specific today. `skills/discovery/SKILL.md` has its own Research→Decompose gate (four options: approve / revise / drop / promote-sub-topic `[skills/discovery/references/decompose.md:30-45]`) but no parity test enforcing its pause inventory. `skills/refine/SKILL.md` has a clarify gate but it is prose-only, no structural enforcement. `NOT_FOUND(query="kept_pauses|kept user pauses", scope="skills/*/SKILL.md")` except lifecycle.

6. **What is the cost of the parity test coupling for an operator who wants to remove a ceremonial pause?** → **Answered.** Minimal: two files must be updated in the same commit — `skills/lifecycle/SKILL.md` (remove the pause from the "Kept user pauses" inventory) and `tests/test_lifecycle_kept_pauses_parity.py` (remove from the expected-set). The dual-source pre-commit hook regenerates `plugins/cortex-core/skills/lifecycle/SKILL.md` automatically. Total: 2 files, 1 commit, no other consumers.

## Codebase Analysis

### "Kept user pauses" inventory location

`[skills/lifecycle/SKILL.md:67-91]` — "Kept user pauses" section, 9 entries. The section is the source-of-truth consumed by the parity test. Format: one bullet per pause with the phase, the user decision being gated, and a brief rationale sentence.

### Parity test structure

`[tests/test_lifecycle_kept_pauses_parity.py:45-67]` — reads the SKILL.md section, extracts pause identifiers, asserts against a hardcoded `EXPECTED_PAUSES` set. Test was added at commit `adfa8b10` ("Add unit tests for verify_reviewer_output sentinel window"). `NOT_FOUND(query="kept_pauses_parity", scope="tests/")` except this single test file — the pattern is not reused in other skills.

### `phase_transition` event emission

`[skills/lifecycle/SKILL.md:254-256]` emits `phase_transition` on all 5 ceremonial announcements. Live Python consumers: `data.py:281-336` (dashboard timeline), `report.py:618-624` (overnight report), `common.py:195-197` (phase detection). Removing a ceremonial announcement pause would not affect `phase_transition` emission — the event can be emitted without a user-blocking pause.

### Discovery skill's Research→Decompose gate (for comparison)

`[skills/discovery/SKILL.md:72-90]` — four-option gate (`approve | revise | drop | promote-sub-topic`). No parity test; no "kept pauses" inventory section; enforcement is prose-only in the skill. This is the behavioral gap the `discovery-output-density-investigate-author-centric` feature addresses.

### `NOT_FOUND` searches

- `NOT_FOUND(query="auto_advance|auto-advance", scope="skills/*/SKILL.md")` — no auto-advance mechanism in any skill.
- `NOT_FOUND(query="SKIP_PAUSE|skip_pause", scope="skills/*/SKILL.md")` — no skip mechanism exists today; any auto-advance would be a new behavior, not a toggle on an existing one.
- `NOT_FOUND(query="ceremonial", scope="skills/lifecycle/SKILL.md")` — the "ceremonial vs. load-bearing" framing is in `CLAUDE.md` skill authoring guidelines, not in the skill files themselves.

## Feasibility Assessment

| Approach | Effort | Risks | Prerequisites |
|----------|--------|-------|---------------|
| (A) Remove all 5 ceremonial pauses + update parity test | XS | UX change for teams that use the pauses for context review; no harness-side risk | Operator decides which pauses are safe to remove |
| (B) Remove 3 of 5 ceremonial pauses (Research/Specify/Implement start; keep Review/Complete) | XS | Smaller UX change; Review-start pause is often used for final-check workflows | Operator decides threshold |
| (C) No removal; document the inventory for cross-skill framework | XS | No UX change; leaves 5 ceremonial pauses in place | None |
| (D) Build auto-advance as a configurable option (`CORTEX_AUTO_ADVANCE_PHASES=true`) | S | New env var, new conditional in SKILL.md, new parity test case | Policy decision first |

## Architecture

### Pieces

1. **SKILL.md "Kept user pauses" inventory update** — edit `skills/lifecycle/SKILL.md:67-91` to reflect the operator-decided pause set. For each removed pause, remove the bullet; for each kept pause, add a one-sentence affordance rationale (per `CLAUDE.md` skill authoring guideline: "identify the user-facing affordance that boundary protects"). Role: single source of truth for the live pause set; the parity test reads this file.

2. **Parity test update** — edit `tests/test_lifecycle_kept_pauses_parity.py:45-67` `EXPECTED_PAUSES` set to match the updated inventory. Role: regression guard ensuring SKILL.md inventory and implementation stay in sync after any future edit.

### Integration shape

Piece 1 is the policy source; Piece 2 is the mechanical guard. They must be updated in the same commit — the parity test will fail in CI if they diverge. The dual-source pre-commit hook (`plugins/cortex-core/skills/lifecycle/SKILL.md` regeneration) fires automatically on commit.

Named contract surface: the pause identifier strings in SKILL.md's "Kept user pauses" section are the parse targets for the parity test. If the section heading or bullet format changes, the test's regex needs a co-update.

### Seam-level edges

- Piece 1 edges: `skills/lifecycle/SKILL.md` (canonical), `plugins/cortex-core/skills/lifecycle/SKILL.md` (auto-regenerated mirror via pre-commit).
- Piece 2 edges: `tests/test_lifecycle_kept_pauses_parity.py` only. No external consumers of the test file.
- Downstream: no events.log emission changes (ceremonial pauses emit `phase_transition` which stays; the pause *wait* is removed, not the event).

## Decision Records

### DR-1: Scope this research to inventory and coupling, not to the removal decision

- **Context**: The removal question ("which of the 5 ceremonial pauses should be removed?") is a UX policy decision, not resolvable through codebase investigation. Some teams use the announcement pauses for workflow review; the harness cannot know this.
- **Options considered**: (A) present the inventory, coupling, and effort, and leave the policy decision to the operator; (B) recommend specific pauses for removal based on zero-decision-value heuristic; (C) recommend removing all 5 based on the "ceremonial" classification.
- **Recommendation**: (A). The research artifact's role is to give the operator a complete picture so they can make an informed call, not to substitute for the call itself. The "ceremonial vs. load-bearing" framing in `CLAUDE.md` says "identify the user-facing affordance" — for announcement pauses, the affordance is context-review time, which is real even if the harness cannot measure it.
- **Trade-offs**: Leaving the decision open means this research produces a classification artifact, not an actionable ticket. The decompose phase will need the operator's pause-removal decision before it can size tickets.

### DR-2: Cross-skill framework for pause inventory enforcement — defer

- **Context**: Only lifecycle has a parity test for its pause inventory. Discovery, refine, and dev skills have user-blocking gates with no structural enforcement.
- **Options considered**: (A) extend the parity test pattern to all skills with user-blocking gates; (B) lifecycle-only for now, cross-skill deferred; (C) single unified gate test across all skills.
- **Recommendation**: (B). The inventory-coupling pattern is new (added at `adfa8b10`); extending it cross-skill before it's been in production for a full cycle would add maintenance scope ahead of proven value. Revisit at the next discovery covering cross-skill harness improvements.
- **Trade-offs**: Discovery's Research→Decompose gate has no enforcement; the `discovery-output-density-investigate-author-centric` feature is adding its own test coverage independently. Fragmented coverage is worse than no coverage at scale, but at current skill count (13 skills, ~3 with nontrivial gates), fragmented is acceptable.

## Open Questions

- **Which of the 5 ceremonial pauses does the operator actually use for workflow review?** Cannot be determined from the codebase — requires asking the operator directly. Specifically: does the Implement-start pause give the operator a chance to confirm the branch is clean before implementation begins? If yes, it's not ceremonial.
- **Should the parity test `EXPECTED_PAUSES` set be derived from the SKILL.md section rather than hardcoded?** Today the test hardcodes the expected set `[tests/test_lifecycle_kept_pauses_parity.py:45-67]`. A derived approach (read SKILL.md, build the set dynamically) would make the test order-insensitive and eliminate the two-file update requirement for removals. Decompose ticket could include this refactor alongside the pause-removal edit.
