# Plan: open-critical-review-agent-count

## Overview

Narrow `/cortex-core:critical-review`'s reviewer width from "default 2, escalate to
3–4" to a flat 1–2 with no escalation tier, and reconcile the three consumers that
restate or contradict the old rule. Pure prose change across three independent
files; the synthesizer, `references/`, and the residue schema are untouched, so no
size-pin move and no step renumbering. Key decision: the escalation clause is
*deleted* rather than tightened — it is the mechanism that made the documented
default unreachable in 82 of 82 measured runs.

## Outline

### Phase 1: Narrow reviewer width (tasks: 1, 2, 3, 4)
**Goal**: Reviewer width reads 1–2 everywhere it is stated, with criticality
weighting preserved as a single clause and no path to 3+.
**Checkpoint**: No "3–4" or "3-4" survives in `skills/critical-review/SKILL.md` or
`docs/skills-reference.md:110`; `project.md:38` states 1–2 and carries no model
routing; SKILL.md is smaller than at HEAD.

## Tasks

### Task 1: Rewrite the width rule and reconcile Step 4 in SKILL.md
- **Files**: `skills/critical-review/SKILL.md`
- **What**: Replace Step 2's width sentence with a flat 1–2 range, delete the
  escalation clause entirely, and add the criticality-weighting and
  over-subscription clauses. Reconcile Step 4's total-failure fallback (currently
  "derive 3–4 angles") to the same range, and make its partial-coverage branch read
  coherently at width 1. Adjust the frontmatter and the one-line intro so
  parallelism is no longer asserted unconditionally.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Line 3 `description` and line 4 `when_to_use` are the L1 surface
  (byte sum currently 652, budget 795 in `tests/test_l1_surface_ratchet.py:57`);
  all four `must_contain` phrases from `tests/fixtures/skill_trigger_phrases.yaml`
  ("critical review", "pressure test", "adversarial review", "challenge from
  multiple angles") must survive verbatim. Line 10 is the intro ("dispatched in
  parallel … then a synthesis pass"). Line 18 is the width rule. Line 20 carries the
  angle-distinctness rule that R3's over-subscription clause must sit alongside —
  it is the source of the upward pressure, so the new clause belongs adjacent to it,
  not in a separate step. Line 34 holds both the partial-coverage branch and the
  fallback. **The file uses an en-dash in "3–4"**, unlike `docs/skills-reference.md`.
  Step 5 (Synthesize), Step 6 (residue), and Step 7 (Present and apply) are OUT OF
  SCOPE and must keep their numbers — `skills/refine/references/clarify-critic.md:61`
  cites "Step 7" by number under an explicit keep-in-sync contract. Spec R1, R2, R3,
  R4, R5, R6, R9.
- **Verification**: `sed -n '/## Step 2:/,/## Step 3:/p' skills/critical-review/SKILL.md | grep -c "3–4\|3-4"`
  = 0; `grep -c "3–4" skills/critical-review/SKILL.md` = 0;
  `sed -n '/## Step 2:/,/## Step 3:/p' skills/critical-review/SKILL.md | grep -Ec "highest-severity|highest severity"` ≥ 1;
  `sed -n '/## Step 2:/,/## Step 3:/p' skills/critical-review/SKILL.md | grep -Ec "not widen|don't widen|does not widen"` ≥ 1;
  `grep -c "^## Step 7: Present and apply" skills/critical-review/SKILL.md` = 1;
  `uv run pytest tests/test_skill_routing_disambiguation.py tests/test_l1_surface_ratchet.py` passes
- **Status**: [x] done (5430bb66 2026-08-04T22:03:54-04:00)

### Task 2: Update the skills-reference width description
- **Files**: `docs/skills-reference.md`
- **What**: Line 110 currently reads "default 2, escalating to 3-4 on high/critical
  criticality or novel claims". Restate it as the 1–2 range with the criticality
  weighting. Leave its "A synthesis agent merges the parallel findings" sentence
  intact — the synthesizer is retained.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: This file uses a **plain hyphen** in "3-4", not the en-dash SKILL.md
  uses — grep for both forms. Only the critical-review entry changes; the research
  entry at line 54 describes a different skill's 1–6 fan-out and is out of scope.
  Spec R7.
- **Verification**: `grep -n "3-4\|3–4" docs/skills-reference.md` returns no line in
  the critical-review entry; `grep -c "A synthesis agent merges" docs/skills-reference.md` = 1
- **Status**: [x] done (65812df9 2026-08-04T22:00:50-04:00)

### Task 3: Amend the ratified width constraint in project.md
- **Files**: `cortex/requirements/project.md`
- **What**: On line 38's "Critical-review gates at spec only" bullet, replace the
  width half with the 1–2 range plus criticality weighting, and delete the
  "routed to Sonnet with an Opus synthesizer" clause. Preserve the "gates at spec
  only" first half, the plan-phase-carries-no-gate statement, and the trailing
  "Supersedes #383".
- **Depends on**: none
- **Complexity**: trivial
- **Context**: The model-routing clause is dead prose — `cortex/adr/0032-cortex-selects-no-model.md`
  (status: accepted) deleted the `synthesizer → opus` constant, and
  `cortex/adr/README.md:51-55` forbids other docs restating a superseded decision
  body. Line 39 ("Dispatched agents are bounded") names the synthesizer as a
  load-bearing example and is OUT OF SCOPE — the synthesizer survives, so that
  example stays accurate. Spec R8.
- **Verification**: the "Critical-review gates at spec only" line satisfies all of
  `grep -c "Critical-review gates at spec only.*1–2" cortex/requirements/project.md` = 1,
  `grep -c "Opus synthesizer" cortex/requirements/project.md` = 0, and
  `grep -c "Supersedes #383" cortex/requirements/project.md` = 1
- **Status**: [x] done (0b853af5 2026-08-04T22:01:06-04:00)

### Task 4: Verify acceptance end to end and commit
- **Files**: `skills/critical-review/SKILL.md`, `docs/skills-reference.md`,
  `cortex/requirements/project.md`, `cortex/lifecycle/open-critical-review-agent-count/plan.md`
- **What**: Confirm the byte-reduction requirement, run the mirror and ratchet
  tests, then commit via `/cortex-core:commit`. The pre-commit hook regenerates the
  `plugins/cortex-core/` mirror from staged blobs and folds it into the commit, so
  mirror paths appear that this plan does not name — expected, not drift.
- **Depends on**: [1, 2, 3]
- **Complexity**: simple
- **Context**: R9 requires `wc -c skills/critical-review/SKILL.md` lower than at
  HEAD — capture the HEAD size with `git show HEAD:skills/critical-review/SKILL.md | wc -c`
  and compare, since the working copy is already modified by Task 1. `references/`
  is untouched, so `size-pin.txt` stays 4702 and the
  `just ratchet-refs` → `just build-plugin` → `just ratchet-refs` sequence is NOT
  run. Never stage `plugins/cortex-core/` by hand. Spec R9, R10.
- **Verification**: `uv run pytest tests/test_dual_source_reference_parity.py tests/test_reference_size_ratchet.py tests/test_skill_size_budget.py`
  passes; `test $(wc -c < skills/critical-review/SKILL.md) -lt $(git show HEAD:skills/critical-review/SKILL.md | wc -c)` exits 0;
  `git show --stat HEAD` after commit lists the three source files plus regenerated mirror paths
- **Status**: [ ] pending

## Risks

- **The prose may not bind.** Width prose has a 0-for-82 compliance record on this
  exact skill and its most recent revision was ignored by both subsequent runs. The
  spec accepts this on an explicit user decision and states the falsifier
  (`reviewers.dispatched` in future residue files). Task 1 is where the theory
  either works or doesn't — the escalation clause must be *deleted*, not softened
  into a narrower escalation, or the change reproduces the failure it targets.
- **Width 1 weakens the skill's differentiator.** At width 1 there are no
  through-lines or tensions to find, and the only remaining boundary against
  `/devils-advocate` is dispatch vs. no-dispatch. Accepted; the user chose the
  aggressive floor knowingly.
- **R5 is judgment-verified, not command-verified.** Whether Step 4's reworded
  partial-coverage sentence is true at width 1 is a semantic reachability call. If
  the reviewer disagrees with Task 1's wording, that is a legitimate review flag
  rather than a test failure.
