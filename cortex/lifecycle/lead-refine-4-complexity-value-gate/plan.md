# Plan: lead-refine-4-complexity-value-gate

## Overview

Single-phase prose change to `skills/refine/SKILL.md` §4 with paired updates to the kept-pauses inventory, a new prose-shape test, and the plugin mirror regeneration. The rewritten §4 always announces a per-feature recommendation + rationale; the `AskUserQuestion` fires conditionally (only when the recommendation diverges from full scope or the orchestrator is uncertain).

## Outline

### Phase 1: §4 rewrite + structural coupling (tasks: 1, 2, 3, 4, 5)
**Goal**: Land the §4 prose amendment, paired kept-pauses inventory entry, new prose-shape test, regenerated plugin mirror, and a final full-suite gate.
**Checkpoint**: `just test` exits 0 with the new `tests/test_refine_skill.py` passing alongside the existing kept-pauses parity test and skill-size budget test; the cortex-core plugin mirror reflects the canonical source.

## Tasks

### Task 1: Amend the §4 complexity-value gate bullet in `skills/refine/SKILL.md`
- **Files**: skills/refine/SKILL.md
- **What**: Rewrite the single-line bullet at the existing `**§4 (User Approval) — Complexity/value gate**:` anchor to (a) preserve the existing trigger conditions (3+ state surfaces / new persistent data format / ongoing per-feature upkeep), (b) introduce a per-feature recommendation step that announces the recommended option with a one-sentence rationale citing the specific spec surface(s) driving the choice, (c) instruct the orchestrator to call `AskUserQuestion` only when the recommendation is not full scope OR confidence is low — otherwise fall through to the existing approval surface, (d) specify the rendered options use the `(Recommended)` capital-R suffix on the lead option's `label`, with `Confirm current scope (Recommended)` as the default lead option, (e) carry through the existing `drop entirely / bugs-only / minimum viable` downsize labels, (f) include a short inline worked example (~3–5 lines orchestrator announcement + ~3–4 lines rendered options array) demonstrating the recommendation-first / rationale-first / `(Recommended)`-suffix shape, (g) use soft positive-routing declarative verbs (`Decide`, `Announce`, `Call`) — no new MUST/REQUIRED/CRITICAL.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Current bullet quoted in `cortex/lifecycle/lead-refine-4-complexity-value-gate/research.md` §1. The heading text `Complexity/value gate` must be preserved verbatim because `skills/refine/SKILL.md:164` cross-references it. Existing `(recommended)` (lowercase) suffix convention at `skills/lifecycle/references/implement.md:18` is parallel and is not modified — capital R is the user-facing standard for this gate per the Spec (`tools/refine §4`). Soft-form guidance: `CLAUDE.md`:72–84 MUST-escalation policy. SKILL.md size budget at `tests/test_skill_size_budget.py:59` (`CAP = 500`); current size 212 lines — comfortable margin for the inline example. The new `AskUserQuestion` mention triggers the kept-pauses parity test (covered by Task 2).
- **Verification**: `grep -c "Complexity/value gate" skills/refine/SKILL.md` returns `1` (anchor preserved); `grep -c "AskUserQuestion" skills/refine/SKILL.md` returns `≥1` (literal mention present); `grep -c "(Recommended)" skills/refine/SKILL.md` returns `≥1` (capital-R suffix specified); `grep -c "MUST decide" skills/refine/SKILL.md` returns `0` (no escalation regression). Pass if all four counts match.
- **Status**: [ ] pending

### Task 2: Add kept-pauses inventory entry in `skills/lifecycle/SKILL.md`
- **Files**: skills/lifecycle/SKILL.md
- **What**: Insert a new bullet under the `### Kept user pauses` section pointing at the rough line of the new `AskUserQuestion` mention introduced by Task 1. Format: `` - `skills/refine/SKILL.md:<line>` — <rationale> ``. The rationale notes the conditional nature — e.g., "complexity/value gate pick-menu; fires only when recommendation diverges from full scope or confidence is low."
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Existing inventory at `skills/lifecycle/SKILL.md:193–200`. Format anchor is `^- \`<path>\`:<digits> — <prose>`. The parity test at `tests/test_lifecycle_kept_pauses_parity.py:27` defines `LINE_TOLERANCE = 35`; the inventory line number must point within ±35 lines of the actual `AskUserQuestion` mention. Read the post-Task-1 `skills/refine/SKILL.md` to compute the correct anchor line. Insert in the same list block where the other refine/lifecycle pauses live.
- **Verification**: `pytest tests/test_lifecycle_kept_pauses_parity.py -q` — pass if exit 0.
- **Status**: [ ] pending

### Task 3: Create `tests/test_refine_skill.py` with §4 prose-shape assertions
- **Files**: tests/test_refine_skill.py
- **What**: Create a new pytest module with four test functions asserting the rewritten §4 prose: (a) `\(Recommended\)` appears within 35 lines after the `Complexity/value gate` anchor; (b) `I recommend` (or the looser `recommend `) appears inside the §4 bullet block; (c) one of `rationale` or `because` appears between the `Complexity/value gate` anchor and the first `(Recommended)` literal — proving rationale-first ordering; (d) negative: the substring `MUST decide` does NOT appear in the §4 bullet block (regression guard against MUST-escalation drift).
- **Depends on**: [1]
- **Complexity**: simple
- **Context**: Follow the conventions in `tests/test_lifecycle_kept_pauses_parity.py` — `from pathlib import Path`; `REPO_ROOT = Path(__file__).parent.parent`; section-slice with `re.search(r"### …", content, re.MULTILINE | re.DOTALL)` or analogous bullet-bounded slice. Helper `_slice_section_4(text: str) -> str` returning the §4 bullet content (anchor on `Complexity/value gate` literal, slice until the next `**§5`/`**Hard Gate**`/blank-line-then-bullet boundary). Each `def test_*` is one assertion. Tests run via `pytest tests/test_refine_skill.py`.
- **Verification**: `pytest tests/test_refine_skill.py -q` — pass if exit 0; `grep -c "^def test_" tests/test_refine_skill.py` returns `≥4`. Both checks must pass.
- **Status**: [ ] pending

### Task 4: Regenerate cortex-core plugin mirror via `just build-plugin`
- **Files**: plugins/cortex-core/skills/refine/SKILL.md, plugins/cortex-core/skills/lifecycle/SKILL.md
- **What**: Run `just build-plugin` to regenerate the cortex-core plugin mirror from the canonical sources amended in Tasks 1 and 2. The recipe rsyncs `skills/<name>/` → `plugins/cortex-core/skills/<name>/`. Stage the regenerated mirrors so the commit captures both canonical and mirror updates in lockstep.
- **Depends on**: [1, 2]
- **Complexity**: simple
- **Context**: Recipe at `justfile:519–551` (`build-plugin`) iterates `BUILD_OUTPUT_PLUGINS` (cortex-core, cortex-overnight); cortex-core's `SKILLS` list at `justfile:527` includes both `refine` and `lifecycle`. The pre-commit hook at `.githooks/pre-commit:71–92` also runs `just build-plugin` and has a drift loop at lines 261–286 — running explicitly first surfaces any unexpected drift before commit time.
- **Verification**: `diff <(sed -n '/Complexity\/value gate/,/Hard Gate/p' skills/refine/SKILL.md) <(sed -n '/Complexity\/value gate/,/Hard Gate/p' plugins/cortex-core/skills/refine/SKILL.md)` — pass if exit 0 (canonical and mirror §4 sections identical).
- **Status**: [ ] pending

### Task 5: Run the full test suite and commit
- **Files**: (no source modifications; commit step only)
- **What**: Run `just test` to verify all assertions hold across the integrated change (new `test_refine_skill.py`, existing `test_lifecycle_kept_pauses_parity.py`, `test_skill_size_budget.py`, and any other tests touching refine). Once green, invoke `/cortex-core:commit` to commit the changes from Tasks 1–4 as a single logical change.
- **Depends on**: [1, 2, 3, 4]
- **Complexity**: simple
- **Context**: `just test` invokes the pytest suite at the project root; pytest collects `tests/test_*.py` automatically, so the new file from Task 3 is picked up. Commit message should follow imperative-mood, capitalized, ≤72-char subject convention (e.g., `Lead refine §4 complexity-value gate with recommended option`). The pre-commit hook (`.githooks/pre-commit`) will also run `just build-plugin` and the drift loop — if Task 4 was complete, this is a no-op; if a regression slipped through, the hook will surface it before the commit lands.
- **Verification**: `just test` — pass if exit 0; `git log --oneline -1` returns a single commit whose subject begins with `Lead refine` (or similar in-scope wording) — pass if the most recent commit covers the §4 change.
- **Status**: [ ] pending

## Risks

- **Prose-only conditional-fire enforcement**: The conditional `AskUserQuestion` semantic ("fire only when recommendation ≠ full scope OR confidence is low") is enforced via prose instruction to the orchestrator, not via control flow in a skill-helper module. Per CLAUDE.md "Skill / phase authoring guidelines", prose-only enforcement is acceptable where the cost of occasional deviation is low — here, deviation just means the user sees an extra pick-menu, which is recoverable. If the deviation rate proves higher than expected post-merge, a follow-up could collapse the conditional into a `cortex_command/refine.py` subcommand. Surfacing as a risk for visibility, not as a blocker.
- **Capital-R `(Recommended)` divergence from lowercase `(recommended)` at `implement.md:18`**: User-facing memory wording standardizes on capital R for the refine gate; `implement.md`'s lowercase convention is unchanged. Future "make consistent" PRs may surface the divergence. The Spec records the rationale (matches user-facing memory wording, more visually distinct) so the resolution is auditable.
- **Inventory line drift if §4 bullet later moves**: The kept-pauses parity test has a ±35-line tolerance. Larger future restructurings of `skills/refine/SKILL.md` could push the actual `AskUserQuestion` mention outside the tolerance window without tripping any other test. The parity test is the canonical safety net — any change to refine §4 must run `just test` locally; the pre-commit hook also runs the suite.
