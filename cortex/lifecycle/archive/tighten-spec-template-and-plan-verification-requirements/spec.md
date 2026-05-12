# Specification: tighten-spec-template-and-plan-verification-requirements

> Epic reference: `research/harness-design-long-running-apps/research.md` — this ticket closes the template-side gap identified in DR-3 of that epic. The evaluator agent option (DR-1) is deferred pending rubric definition.

## Problem Statement

Overnight feature workers self-evaluate against two artifacts — the spec's acceptance criteria and the plan's verification steps — without human oversight. When those criteria are prose ("the feature works correctly", "confirm the section was added"), the worker cannot perform an objective self-check and instead self-attests. This has caused real failures: CHANGES_REQUESTED after all 9 tasks reported success because a spec compliance detail was not captured as a testable check. The fix is to tighten the pass bars for two existing orchestrator-review checklist items (S1 and P4) so that only binary-checkable criteria pass, and to update the spec and plan template descriptions to guide authors toward the correct format at write time. The template already has the right structure (Requirements with acceptance criteria slots, Non-Requirements for scope boundaries); the gap is pass-bar quality, not structural absence. Tightening the criteria here reduces overnight deferrals and closes the most common path for self-evaluation bias without adding runtime cost or new agents.

All five requirements are **must-have**. Template guidance (R4, R5) is must-have — not merely nice-to-have — because without it, authors write prose acceptance criteria that then fail orchestrator review after the artifact is written. The checklist enforcement (R1–R3) and the authoring-time template guidance (R4–R5) are the two reinforcing layers; removing either layer leaves a gap. This classification is explicit, not a default.

## Requirements

1. **(M) S1 Criteria tightened in orchestrator-review.md**: The S1 Criteria column is updated to require binary-checkable acceptance criteria — defined as: (a) runnable as a command with an observable output AND explicit pass/fail criterion (exit code, test result, grep count ≥ N), (b) an observable state verifiable by file or directory inspection naming the specific file path, the specific string/pattern to find, and the expected true/false result — without running the full feature, or (c) annotated "Interactive/session-dependent: [one-sentence rationale]" when neither (a) nor (b) is possible. "Objectively evaluable" alone is no longer sufficient.
   - Acceptance criteria: `skills/lifecycle/references/orchestrator-review.md` S1 Criteria column contains the phrase "binary-checkable" and the three-part condition. `grep -c 'binary-checkable' skills/lifecycle/references/orchestrator-review.md` returns ≥ 1.

2. **(M) S1 exception path consistent with P4**: Both S1 and P4 use the identical annotation format "Interactive/session-dependent: [one-sentence rationale]" for criteria that cannot be expressed as a command or observable state check. The rationale must explain why — not merely assert that a command is not possible.
   - Acceptance criteria: The phrase "Interactive/session-dependent:" appears in both the S1 and P4 Criteria descriptions in orchestrator-review.md. `grep -c 'Interactive/session-dependent' skills/lifecycle/references/orchestrator-review.md` returns ≥ 2.

3. **(M) P4 Criteria tightened in orchestrator-review.md**: The P4 Criteria column is updated to require that each task's Verification field either (a) names a specific runnable command with expected output and explicit pass/fail criterion, (b) describes a specific observable state (file exists at named path, line count = N, grep match count = N) checkable without running the full feature, or (c) is annotated "Interactive/session-dependent: [one-sentence rationale]". Verification fields consisting only of prose descriptions do not pass.
   - Acceptance criteria: `skills/lifecycle/references/orchestrator-review.md` P4 Criteria column contains the three-part condition and the annotation format. A verification field reading "confirm the feature works correctly" would be a P4 flag under the new criteria.

4. **(M) specify.md Requirements template description updated**: The Requirements section template in `skills/lifecycle/references/specify.md` §3 includes a parenthetical showing that acceptance criteria must be binary-checkable, with at least one concrete example (e.g., "`just test` exits 0 — pass if exit code = 0", "`grep -c 'pattern' file` = N", or "Interactive/session-dependent: [rationale]").
   - Acceptance criteria: `grep -c 'binary-checkable' skills/lifecycle/references/specify.md` returns ≥ 1.

5. **(M) plan.md Verification field template updated in both plan templates with prohibition**: Both the standard plan template (§3) and the competing-plan agent prompt template (§1b) in `skills/lifecycle/references/plan.md` are updated with: (a) placeholder text showing the three acceptable formats (command+output+pass-fail, observable state, Interactive/session-dependent annotation), and (b) a "Prohibited:" entry — co-located with the existing "Prohibited:" list in §1b and an equivalent structural note in §3 — stating that Verification fields consisting only of prose descriptions that require human judgment are not acceptable. Adding a prohibition is necessary for §1b in particular because sub-agents follow structural prohibitions, not placeholder prose.
   - Acceptance criteria: `grep -c 'Interactive/session-dependent' skills/lifecycle/references/plan.md` returns ≥ 2 (once per template block). `grep -c 'Prohibited' skills/lifecycle/references/plan.md` returns ≥ the current count + 1 (the existing §1b Prohibited list is extended, not duplicated).

## Non-Requirements

- Does not retroactively update existing spec.md or plan.md artifacts in any lifecycle/ directory
- Does not add new checklist items (S6, S7, etc.) to orchestrator-review.md — only the Criteria column of S1 and P4 changes
- Does not add an evaluator agent to the overnight runner pipeline (deferred per epic research DR-1)
- Does not add a runtime agent-based spec quality gate in /refine (deferred per epic research DR-3)
- Does not modify `claude/pipeline/prompts/implement.md` (self-attestation checkpoint gap is a follow-on concern — separate ticket)
- Does not change the orchestrator-review skip rule for low+simple features (separate backlog item)
- Does not modify parser.py, batch_runner.py, state.py, runner.sh, or any overnight runner code
- Does not require changes to existing lifecycle.config.md overrides or the /lifecycle SKILL.md
- Does not introduce a structured sub-field format change (e.g., `Verify: [command] | Pass if: [criterion]`) — this scope decision was evaluated in research tradeoff analysis and rejected in favor of enforcement-based improvement at lower integration cost

## Edge Cases

- **Non-deterministic verification (hook fire, live session, UI)**: A hook test that requires a live Claude Code session cannot be expressed as a bare shell command. The "Interactive/session-dependent: [rationale]" annotation handles this. The rationale must explain why a command is not possible — e.g., "Interactive/session-dependent: fires only during a live Claude Code session, not from a bare shell command." An annotation without rationale ("Interactive/session-dependent: yes") does not pass.

- **Format (b) pass/fail boundary**: An observable state check passes under format (b) only if it names: (1) the specific file path, (2) the specific string or pattern to match (e.g., the header `## Verification Strategy`), and (3) the expected result (present/absent, count = N). A criterion like "confirm the section was added" fails because it names no file, no pattern, and no expected result — even though it could be rephrased as an observable state check. The distinguishing question: can an agent run `grep 'specific pattern' specific/path` and get an unambiguous true/false answer?

- **Multiple acceptance criteria per requirement**: If a requirement lists multiple acceptance criteria, all must be binary-checkable (or use the annotation). One prose criterion among binary-checkable ones is sufficient to flag S1 for that requirement.

- **Low+simple bypass**: The orchestrator-review skip rule (low criticality AND simple tier → skip entirely) means updated S1 and P4 never fire for that feature class. This is a documented gap not addressed by this ticket.

- **Incremental migration**: Artifacts written before this change are not retroactively invalid. When an artifact is re-reviewed (e.g., after CHANGES_REQUESTED), it is evaluated against the criteria active at review time — the new S1/P4 bars apply.

## Technical Constraints

- Changes confined to three files (scope decision — structural format changes and parser changes are explicitly excluded per Non-Requirements): `skills/lifecycle/references/orchestrator-review.md`, `skills/lifecycle/references/specify.md`, `skills/lifecycle/references/plan.md`
- Both plan template blocks in plan.md must be updated — the competing-plan agent prompt template in §1b and the standard plan template in §3 are separate markdown code blocks in the same file
- The §1b "Prohibited:" list in plan.md already prohibits code patterns; the Verification prohibition must be added to this existing list (not as a standalone note that sub-agents may ignore)
- The S1/P4 annotation format ("Interactive/session-dependent: [rationale]") must appear verbatim in specify.md's template description and plan.md's template description, not just in orchestrator-review.md — authors need to see it at write time, not only at review time
- The wording change must be backward-compatible: criteria that were already binary-checkable (exit codes, `just test`, file existence checks) still pass under the new wording
- The `grep` commands in the acceptance criteria are for overnight self-verification — the implementation agent should run each one after writing the changes
