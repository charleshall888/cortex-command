# Specification: Audit skill prompts and remove verbose instructions above the floor

> **Epic gate answer**: This ticket is the DR-6 stress-test gate from `research/agent-output-efficiency/research.md`. After adversarial review in the research phase, the empirical finding is **zero high-confidence removal candidates** under the rubric "removable if it generates output above the #050 floors AND is not consumed by a downstream skill or approval gate." The deliverable for #052 is documenting that result as the DR-6 answer, not editing skill prompts. A separate backlog ticket will be filed for the Anthropic imperative-intensity rewrite axis (an orthogonal operation that also touches SKILL.md files).

## Problem Statement

Ticket #052 asks: audit 9 skill prompts against #050's output floors and remove instructions that are above the floor and not consumed downstream. The research phase produced this answer empirically: after per-skill candidate analysis AND an adversarial counter-review of every candidate, the confident-removal set is **zero**. Most initial "remove" verdicts were overturned by adversarial findings that identified load-bearing value the grep-based analysis missed: defense-in-depth disclosures, output-channel directives disguised as prose, control flow gates, sub-agent targeting for Sonnet/Haiku, Opus 4.6 warmth counter-weight, and morning-review consumers that grep cannot detect. The two weakest surviving candidates (`dev` DV1/DV2) require implementation-time line verification to decide. No candidate earned a confident "remove" verdict. This result IS the DR-6 stress-test answer for the epic: removing verbose-by-default instructions alone is not sufficient to control Opus 4.6 output — downstream tickets (#053 subagent output formats, #054+ compression) remain necessary. The deliverable is a short completion note documenting this finding with pointers to research.md's per-skill analysis, plus filing a new backlog ticket for the orthogonal imperative-intensity rewrite axis that surfaced during research but is not the ticket's original question.

## Requirements

1. **DR-6 completion note produced**. Write a short completion summary to `lifecycle/{slug}/dr6-answer.md` (or equivalent location chosen during plan phase) containing: (a) the DR-6 question as stated in `research/agent-output-efficiency/research.md`, (b) the empirical answer ("zero high-confidence removals after adversarial review"), (c) a pointer to `research.md` per-skill analysis (no duplication), (d) the implication for the epic ("proceed to #053 subagent output formats and #054+ compression; removal alone is insufficient"). Acceptance: `test -f lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md && grep -c "zero high-confidence" lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns 1.

2. **New backlog ticket filed for the imperative-intensity rewrite axis**. Create a new backlog item titled "Apply Anthropic migration rewrite table to skill prompts" (or equivalent), type `chore`, priority `low`, tags `[output-efficiency, skills]`, parent `49` (same epic as #052), with a short body describing: (a) Anthropic's `claude-opus-4-5-migration` plugin `prompt-snippets.md` rewrite table as the concrete rewrite source, (b) scope limited to 9 audited skills + references, (c) note that this is orthogonal to #050 output floor compliance and to the DR-6 stress-test, (d) verification strategy to be resolved during its own refine phase. Acceptance: `ls backlog/[0-9]*-*.md | xargs grep -l "Anthropic migration rewrite table\|imperative-intensity rewrite"` returns at least one file path.

3. **No skill file edits in #052**. The #052 deliverable is documentation and a new ticket. SKILL.md files, reference files, hooks, settings, and code remain untouched. Acceptance: `git diff --name-only main..HEAD` on the feature branch shows only paths under `lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/` and `backlog/`. No matches under `skills/`, `hooks/`, `claude/`, `tests/`, `bin/`, or other source directories.

4. **dev DV1/DV2 conditional removal candidates explicitly deferred**. The two candidates that survived adversarial review with moderate confidence (`dev` DV1 on lines 89-90, DV2 on lines 116-118) are NOT auto-included in #052 scope. They are either (a) deferred to the new imperative-intensity rewrite ticket as a bonus candidate list, or (b) left for a future per-skill cleanup. The DR-6 answer note should document this decision. Acceptance: `grep -c "DV1\|DV2\|dev/SKILL.md" lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥1.

5. **Research.md is the authoritative rationale archive**. The #052 deliverable does not duplicate research.md's per-skill analysis, adversarial findings, or rationale entries. The completion note references research.md by path and line/section — it is the canonical artifact for any future audit cycle, if one ever occurs. Acceptance: `grep -c "research.md" lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/dr6-answer.md` returns ≥1.

## Non-Requirements

- Does NOT edit any `skills/*/SKILL.md` files
- Does NOT edit any `skills/*/references/*.md` files
- Does NOT apply Anthropic's imperative-intensity rewrite table (filed as a separate new ticket per R2)
- Does NOT apply surgical sentence removals (including the dev DV1/DV2 conditional candidates — deferred per R4)
- Does NOT mandate atomic per-skill commits (the previous spec's R6 is withdrawn; this ticket is documentation-only)
- Does NOT produce a `## Did Not Remove` appendix (research.md already contains the rationale at higher fidelity; the previous spec's R4 is withdrawn as duplication)
- Does NOT run verification dry-runs on any skills (the previous spec's R5 is withdrawn; nothing is being edited in skills/)
- Does NOT touch `claude/reference/output-floors.md` or other reference docs
- Does NOT file any sub-tickets beyond the one in R2
- Does NOT change the ticket's criticality or tier (still complex/high — the decision to ship a negative result IS a complex judgment affecting shared workflow infrastructure's intervention roadmap)

## Edge Cases

- **Plan phase discovers a genuinely high-confidence removal candidate missed by adversarial review**: document it in the DR-6 answer note with rationale, surface to user for decision; do NOT auto-include in #052 scope. The baseline expectation is that research's adversarial pass was sufficient.
- **User changes their mind and wants the rewrite axis bundled into #052 after all**: stop execution, re-open spec phase with the new decision, re-run the critical-review loop. The current spec assumes the "ship honest negative" direction is final.
- **New backlog ticket for rewrite axis conflicts with an existing backlog item**: search backlog for overlapping titles before creating; if a duplicate exists, annotate it with the #052 discovery instead of creating a second ticket.
- **DR-6 question in research.md turns out to reference content that has since changed**: verify the research/agent-output-efficiency/research.md file during plan phase; if DR-6 framing has shifted, re-anchor the completion note against the current framing.
- **dev DV1/DV2 candidates get picked up by the rewrite axis ticket**: acceptable — they naturally belong in a rewrite-focused ticket since the rewrite axis can handle conditional verification on exact line content without the scoping awkwardness of including them in #052.

## Changes to Existing Behavior

- **ADDED**: A DR-6 completion note in `lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/` documenting the stress-test result for the epic chain. This artifact becomes the citeable answer to "is removal alone sufficient to control Opus 4.6 output in skill prompts?"
- **ADDED**: A new backlog ticket for the imperative-intensity rewrite axis, scoped as a separate chore ticket with its own refine/plan/implement cycle.
- **No changes** to any skill prompt, reference file, hook, setting, or code. The intervention roadmap for the epic is updated via the DR-6 answer artifact; no runtime behavior of any skill changes.

## Technical Constraints

- Scope: documentation and backlog-item creation only. No edits to `skills/`, `hooks/`, `claude/`, `tests/`, `bin/`, or any other source directory.
- The DR-6 completion note references but does not duplicate `research/agent-output-efficiency/research.md` or `lifecycle/audit-skill-prompts-and-remove-verbose-instructions-above-the-floor/research.md`. Both files are authoritative sources; the note is a pointer.
- The new backlog ticket created under R2 must follow project backlog conventions: YAML frontmatter with `id`, `title`, `status: draft`, `priority`, `type`, `parent`, `blocked-by`, `tags`, `created`, `updated`. Use `backlog add` or the `create-item` utility per project convention rather than hand-authoring the file.
- The new ticket is NOT a blocker for #052's completion — it is a follow-up filed atomically within the same feature branch.
- Criticality stays `high` even at the reduced scope because the DR-6 answer shapes intervention decisions for the broader epic chain (#053, #054+). A wrong DR-6 answer would misdirect those downstream tickets.

## Open Decisions

None. All decisions resolved during spec interview and critical review.
