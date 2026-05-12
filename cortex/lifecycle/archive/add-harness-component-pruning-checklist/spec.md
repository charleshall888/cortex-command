# Specification: add-harness-component-pruning-checklist

## Problem Statement

Cortex-command has no practice for identifying when overnight runner components have become unnecessary scaffolding. As Claude's capabilities improve, components added to compensate for model limitations — fresh process isolation per retry, post-failure brain agent triage, file-based plan hand-offs — may no longer earn their place. The morning report surfaces failures but nothing surfaces unnecessary complexity. This feature adds a standalone `/harness-review` skill that evaluates all overnight runner components against a structured 4-question rubric, prints human-review candidates to the terminal, and leaves the pruning decision to the user.

## Requirements

1. **Curated component inventory in SKILL.md**: The skill prompt contains a curated list of all overnight runner components with their file paths, a one-line original rationale for each, and an initial classification (initially-load-bearing or pruning-candidate). This classification is a starting position for evaluation, not a terminal verdict.
   - Acceptance criteria: SKILL.md lists all overnight runner components (`runner.sh`, `batch_runner.py`, `brain.py`, `claude/pipeline/retry.py`, `throttle.py`, `deferral.py`, `state.py`, `report.py`, `batch_plan.py`, `plan.py`, `backlog.py`, `events.py`, `status.py`, `integration_recovery.py`, `interrupt.py`, `smoke_test.py`, orchestrator prompt) with one-line rationale and initial classification. No component is marked as exempt from rubric evaluation.

2. **Runtime inventory completeness check**: Before evaluating components, the skill scans `claude/overnight/` and `claude/pipeline/` for `.py` and `.sh` files not present in the SKILL.md inventory. Unlisted files are reported separately and flagged for potential addition to the inventory on the next SKILL.md update.
   - Acceptance criteria: Skill protocol instructs Claude to list files in `claude/overnight/` and `claude/pipeline/` and compare against the SKILL.md inventory. Output includes a coverage statement: "Evaluated N components from inventory; found M additional unlisted files: [list]." If M = 0, states "No unlisted files detected." Also verifies each listed component's module-level docstring against SKILL.md rationale and notes mismatches (changed rationale, undocumented component, file missing from disk).

3. **4-question rubric evaluation for all components**: For each component in the inventory, the skill evaluates four questions: (1) What model limitation did this compensate for? (2) Is that limitation still real at Claude's current baseline? (3) What would fail or degrade if removed? (4) Verdict: `load-bearing`, `experiment-candidate`, or `likely-deprecated`. No component is exempted from rubric evaluation based on initial classification.
   - Acceptance criteria: Every component receives a verdict entry with answers to all four questions. The output begins with a one-line disclaimer: "Note: this assessment reflects model judgment only — no empirical session data was consulted. Treat verdicts as structured hypotheses, not conclusions." Components initially classified as load-bearing may still receive `experiment-candidate` or `likely-deprecated` verdicts if the rubric warrants it.

4. **Human-review candidates surfaced**: The output concludes with a summary section listing components with verdict `experiment-candidate` or `likely-deprecated`, ordered by estimated risk of removal (lowest blast radius first).
   - Acceptance criteria: Output contains a dedicated summary section titled "Candidates for Review" that is empty ("none — all components evaluated as load-bearing") if no candidates exist, or lists each candidate with its verdict and one-line reason.

5. **Pruning rubric embedded inline**: The 4-question rubric is part of the skill prompt body itself — not in a separate reference file or deferred to runtime judgment.
   - Acceptance criteria: SKILL.md protocol section contains the four rubric questions as a numbered list applied to every component.

6. **Terminal-only output**: Skill prints its evaluation to the terminal. No file is written to disk.
   - Acceptance criteria: SKILL.md protocol contains no instructions to write files; running the skill produces no new files in the repo.

7. **Skill deployed via existing symlink architecture**: New SKILL.md placed at `skills/harness-review/SKILL.md` is globally symlinked via the existing `skills/* → ~/.claude/skills/*` mechanism. No additional deploy steps required.
   - Acceptance criteria: File exists at `skills/harness-review/SKILL.md` with required `name` and `description` frontmatter. `just check-symlinks` passes.

## Non-Requirements

- Does NOT auto-create backlog items for flagged components — output is advisory only; a human makes the pruning call.
- Does NOT modify any overnight runner files during evaluation.
- Does NOT run on a schedule or trigger automatically — user-invoked only.
- Does NOT evaluate skills, hooks, lifecycle, or other cortex-command components — scope is overnight runner only.
- Does NOT require a morning report to exist (no dependency on prior session data).
- Does NOT produce a structured machine-readable file (JSON, CSV) — terminal output only.

## Edge Cases

- **Run from non-cortex-command repo**: Claude attempts to read `claude/overnight/` and finds no files. Skill outputs a one-line notice — "No overnight runner found at expected path" — and exits without error.
- **Component listed in SKILL.md not found on disk** (renamed or removed): Skill notes the discrepancy — "Component listed in inventory not found at `{path}`" — and skips rubric evaluation for that component, flagging it as a maintenance item.
- **Files found in `claude/overnight/` or `claude/pipeline/` not in SKILL.md inventory**: Skill reports them in the coverage statement — "M additional unlisted files found: [list]. These were not evaluated. Update the SKILL.md inventory to include them." Does not silently skip — the coverage statement always reflects actual scan results.
- **Module docstring absent**: Fall back to reading inline comments in the first 30 lines of the file. If no rationale is discoverable, note "rationale undocumented" and flag the component for documentation.
- **All components verdict load-bearing**: Output "Candidates for Review: none — all components evaluated as load-bearing." No candidates section is omitted or hidden.
- **User runs harness-review while overnight session is active**: Skill reads docstrings and scans directories (read-only); no conflict with active session.

## Technical Constraints

- SKILL.md must include `name: harness-review` and `description:` frontmatter — required by the skill schema (confirmed in lifecycle.config.md review criteria).
- Do NOT set `disable-model-invocation: true` — this skill invokes Claude for evaluation.
- Skill reads files at `claude/overnight/` and `claude/pipeline/retry.py` relative to project root; assumes invoked from repo root (standard Claude Code behavior).
- No argument-hint or inputs frontmatter required — skill takes no arguments.
- Component inventory in SKILL.md must be updated manually when overnight runner components are added or removed. The runtime scan (R2) surfaces unlisted files but does not auto-update the inventory.
