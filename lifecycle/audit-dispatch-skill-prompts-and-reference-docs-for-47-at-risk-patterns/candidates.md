# Candidates: lifecycle #85 — dispatch-skill 4.7 at-risk pattern audit

Per-site audit decisions and remediation outcomes for P1–P7 across the 12 audit surfaces. Populated by Task 4's Implement-entry full-surface rescan; annotated by Pass 1 (Tasks 5–10) and Pass 3 (Task 11).

## Audit surface (12 files)

From spec R1 — Pass 1 and Pass 3 scan these exact files plus each dispatch skill's `references/*.md`:

**6 dispatch skills** (each: `SKILL.md` + all `references/*.md`):

1. `skills/critical-review/`
2. `skills/research/`
3. `skills/discovery/`
4. `skills/lifecycle/`
5. `skills/diagnose/`
6. `skills/refine/`

**6 reference / global files**:

7. `claude/reference/claude-skills.md`
8. `claude/reference/context-file-authoring.md`
9. `claude/reference/output-floors.md`
10. `claude/reference/parallel-agents.md`
11. `claude/reference/verification-mindset.md` (READ-ONLY in #85 — Pass 2 child #100 handles)
12. `claude/Agents.md`

## Pattern P1 — double-negation suppression

Signature: `omit.*entirely|do not emit|omit.*and do not`

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/critical-review/SKILL.md:22 | `3. Construct a Project Context block from these inputs. **If neither file exists** (or requirements/project.md...` | pending | | | Task 4 rescan |
| skills/critical-review/SKILL.md:138 | `Use bullets, not prose paragraphs. Each finding is a discrete bullet.` | pending | | | Task 4 rescan; lexical P1 match only — not a true double-negation |
| skills/critical-review/SKILL.md:177 | `Use bullets, not prose paragraphs. Each finding is a discrete bullet.` | pending | | | Task 4 rescan; lexical P1 match only — not a true double-negation |
| skills/lifecycle/SKILL.md:180 | `If no matching backlog item was found, omit the heading and body line entirely.` | pending | | | Task 4 rescan |
| skills/lifecycle/references/review.md:90 | `When drift is NOT detected, omit the Suggested Requirements Update section entirely.` | pending | | | Task 4 rescan |

## Pattern P2 — ambiguous conditional bypass

Signature: `Only .* satisfies|does NOT (count|satisfy)` in the same 5-line window (path-guard scope).

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/lifecycle/SKILL.md:269 | `**Determine the starting point for /refine:** follow /refine's Step 2 (Check State) normally — it checks lifecycle/{lifecycle-slug}/research.md...` | pending | | | Task 4 rescan |
| skills/diagnose/SKILL.md:231 | `teammates) does NOT count as independent confirmation — that is non-convergence.` | pending | | | Task 4 rescan |
| skills/refine/SKILL.md:49 | `NOTE: Only lifecycle/{lifecycle-slug}/research.md satisfies this check. Any file loaded from` | pending | | | Task 4 rescan; path-guard |
| skills/refine/SKILL.md:51 | `it does NOT satisfy this check regardless of path.` | pending | | | Task 4 rescan; path-guard |
| skills/refine/SKILL.md:83 | `**Path guard**: Only lifecycle/{lifecycle-slug}/research.md satisfies this check. Any file loaded from a backlog it...` | pending | | | Task 4 rescan; path-guard |

## Pattern P3 — negation-only prohibition

Signature: consecutive `^\s*[-*]? ?Do not ` lines (≥2) or `Do not [^.]+\. Do not [^.]+\.` within a sentence.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/critical-review/SKILL.md:103 | `Do not cover other angles. Do not be balanced.` | pending | | | Task 4 rescan; anchored preservation candidate (distinct-angle + no-soften) |
| skills/critical-review/SKILL.md:140 | `Do not be balanced. Do not reassure. Find the problems.` | pending | | | Task 4 rescan; anchored preservation candidate (no-soften) |
| skills/critical-review/SKILL.md:179 | `Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.` | pending | | | Task 4 rescan; anchored preservation candidate (no-soften) |
| skills/lifecycle/references/clarify-critic.md:50 | `5. Return a list of objections only — one per finding, written as prose. Do not classify or categorize them. Do not r...` | pending | | | Task 4 rescan |
| skills/lifecycle/references/clarify-critic.md:63 | `Do not be balanced. Do not summarize what the assessment got right.` | pending | | | Task 4 rescan; possible anchored preservation |
| skills/lifecycle/references/implement.md:309 | `Do not implement other tasks. Do not modify files not listed in this task.` | pending | | | Task 4 rescan; verbatim subagent-dispatch contract (P5-adjacent) |

## Pattern P4 — multi-condition gate

Definition: natural-language conditional blocks ≥10 lines without explicit control-structure syntax. Judgment-only — no regex signature.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|

*(P4 is judgment-only; Task 8 enumerates qualifying blocks during remediation. No auto-populated rows at Task 4.)*

## Pattern P5 — procedural-order dependency

Signature: `\bdo not (omit|reorder|paraphrase|alter)\b`

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/lifecycle/references/implement.md:243 | `**b. Dispatch batch**: Launch all tasks in the batch concurrently as parallel sub-tasks. Use the builder prompt templ...` | pending | | | Task 4 rescan; known verbatim-substitution contract |
| skills/lifecycle/references/plan.md:27 | `**b. Dispatch plan agents**: Launch each agent as a parallel Task tool sub-task. Use the plan agent prompt template b...` | pending | | | Task 4 rescan; known verbatim-substitution contract |
| skills/lifecycle/references/research.md:57 | `Launch all research agents concurrently as parallel Task tool sub-tasks. Use the researcher prompt template below **v...` | pending | | | Task 4 rescan; known verbatim-substitution contract |

## Pattern P6 — examples-as-exhaustive-list

Signature: `[Ss]elect .* from the following|from this menu|such as `.*:\s*$` in a section header followed by bullets.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/critical-review/SKILL.md:30 | `Select angles from the following menu, picking whichever are most likely to reveal real problems for this specific ar...` | pending | | | Task 4 rescan; anchored preservation (angle menu) per spec Technical Constraints |

## Pattern P7 — [Cc]onsider hedge

Signature: `\b[Cc]onsider\b|\btry to\b|\bif possible\b`

P7 rescan scope: all of `skills/` per Task 11 context — sites outside R1's 12-surface audit scope get `M-label: out-of-scope-of-R1` and produce no edit under #85.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/research/SKILL.md:131 | `Your job: identify alternative approaches... Consider implementation complexity, maintainability, performance...` | pending | | | Task 4 rescan; in R1 scope |
| skills/lifecycle/references/plan.md:277 | `"The backlog item said to do it this way" ... evaluate it critically and consider alternatives.` | pending | | | Task 4 rescan; in R1 scope |
| skills/diagnose/SKILL.md:74 | `from the error output and initial investigation, consider spawning a competing-hypotheses` | pending | | | Task 4 rescan; in R1 scope |
| skills/backlog/references/schema.md:64 | `Use language like "one approach might be...", "consider...", or "research could explore..."` | pending | out-of-scope-of-R1 | | Task 4 rescan; outside R1 12-surface set |
| skills/dev/SKILL.md:191 | `No active child tickets found — consider running /discovery to decompose this epic.` | pending | out-of-scope-of-R1 | | Task 4 rescan; outside R1 12-surface set |
| skills/dev/SKILL.md:195 | `Consider running /discovery to decompose this epic into child tickets.` | pending | out-of-scope-of-R1 | | Task 4 rescan; outside R1 12-surface set |
| skills/morning-review/references/walkthrough.md:142 | `Consider each configured entry's label: and command: alongside the merged features' names...` | pending | out-of-scope-of-R1 | | Task 4 rescan; outside R1 12-surface set |
| skills/pr/SKILL.md:34 | `Consider the type of change (app feature, bugfix, tooling/scripts, CI, docs) and what a reviewer would actually need to do.` | pending | out-of-scope-of-R1 | | Task 4 rescan; outside R1 12-surface set |
| skills/retro/SKILL.md:116 | `"$count retros unprocessed — consider running /evolve."` | pending | out-of-scope-of-R1 | | Task 4 rescan; outside R1 12-surface set |

## Preservation exclusions

Sites excluded from remediation per spec R10 ring-fence (7 categories + 10 anchored decisions). Rows reference the pattern section where the site also appears.

| file:line | pattern | preservation rule | notes |
|-----------|---------|-------------------|-------|

## Null-pattern log

Patterns with zero qualifying sites after classification. Format: `P<n> — N sites audited, M preservation-excluded, 0 qualifying. Reason: <summary>.`

## Incidental findings

P8-severity-gate or other out-of-scope sites surfaced during Pass 1 grep — recorded for future tickets.

## Escalations

Anchor-string reworded, section-heading renamed, or other drift surfaced during remediation — surfaced to user at Review per spec §Edge Cases.
