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
| skills/critical-review/SKILL.md:22 | `**If neither file exists** ... **omit the Project Context section entirely** — do not inject an empty placeholder...` | not-a-failure-mode | | | Conditional-else-branch output directive; steps 1-2 establish positive routing, step 3 is the explicit absence-branch |
| skills/critical-review/SKILL.md:138 | `Skip sections where the agent returned no findings — do not emit empty section headers.` | not-a-failure-mode | | | Positive verb "Skip" precedes the negation; "do not emit" reinforces rather than creating gappy-synthesis risk |
| skills/critical-review/SKILL.md:177 | `Skip sections where the agent returned no findings — do not emit empty section headers.` | not-a-failure-mode | | | Same analysis as :138 (duplicate structure in a parallel subsection) |
| skills/lifecycle/SKILL.md:180 | `If no matching backlog item was found, omit the heading and body line entirely.` | not-a-failure-mode | | | Clear conditional-else-branch with explicit trigger |
| skills/lifecycle/references/review.md:90 | `When drift is NOT detected, omit the Suggested Requirements Update section entirely.` | not-a-failure-mode | | | Conditional-else-branch with positive "When X NOT detected" framing |

## Pattern P2 — ambiguous conditional bypass

Signature: `Only .* satisfies|does NOT (count|satisfy)` in the same 5-line window (path-guard scope).

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/lifecycle/SKILL.md:269 | `**Determine the starting point for /refine:** follow /refine's Step 2 normally... does NOT satisfy this check` | qualifying | M2 | ee8b599 | M2 rewrite — prose path-guard with embedded negation → explicit if/then rules list; see Escalations for commit-subject deviation |
| skills/diagnose/SKILL.md:231 | `teammates) does NOT count as independent confirmation — that is non-convergence.` | not-a-failure-mode | | | Clarifier on a positive "Converged" definition that comes first; not a path-guard-under-ambiguity hazard |
| skills/refine/SKILL.md:49-51 | `NOTE: Only lifecycle/{lifecycle-slug}/research.md satisfies this check ... it does NOT satisfy this check regardless of path.` | qualifying | M2 | ee8b599 | M2 rewrite — pseudocode prose annotation replaced with explicit exact-path conditional + comment block; co-located fix covers lines 49 and 51 |
| skills/refine/SKILL.md:83 | `**Path guard**: Only lifecycle/{lifecycle-slug}/research.md satisfies this check. ... does NOT satisfy` | qualifying | M2 | ee8b599 | M2 rewrite — prose path-guard converted to numbered rules list |

## Pattern P3 — negation-only prohibition

Signature: consecutive `^\s*[-*]? ?Do not ` lines (≥2) or `Do not [^.]+\. Do not [^.]+\.` within a sentence.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/critical-review/SKILL.md:103 | `Do not cover other angles. Do not be balanced.` | preservation-excluded | | | Anchored R10 — distinct-angle rule + no-soften cluster (per-angle reviewer prompt) |
| skills/critical-review/SKILL.md:140 | `Do not be balanced. Do not reassure. Find the problems.` | preservation-excluded | | | Anchored R10 — no-soften cluster (synthesis fallback section) |
| skills/critical-review/SKILL.md:179 | `Do not be balanced. Do not reassure. Find the through-lines and make the strongest case.` | preservation-excluded | | | Anchored R10 — no-soften cluster (synthesis main section); paired with "Do not soften or editorialize" at :195 |
| skills/lifecycle/references/clarify-critic.md:50 | `5. Return a list of objections only — one per finding, written as prose. Do not classify or categorize them...` | qualifying | M1 | e245cf7 | M1 rewrite to positive exclusion framing ("Output scope is raw findings: exclude...") |
| skills/lifecycle/references/clarify-critic.md:63 | `Do not be balanced. Do not summarize what the assessment got right.` | qualifying | M1 | e245cf7 | M1 rewrite to positive framing ("Write a one-sided critique — focus on what the assessment got wrong...") |
| skills/lifecycle/references/implement.md:309 | `Do not implement other tasks. Do not modify files not listed in this task.` | preservation-excluded | | | Verbatim subagent-dispatch template — preservation category 3 (control-flow gate); Task 9 covers the P5 dimension |

## Pattern P4 — multi-condition gate

Definition: natural-language conditional blocks ≥10 lines without explicit control-structure syntax. Judgment-only — no regex signature.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|

*(P4 is judgment-only; Task 8 enumerates qualifying blocks during remediation. No auto-populated rows at Task 4.)*

Task 8 scan outcome: heuristic scan (≥10 consecutive non-empty, non-structured lines with ≥3 conditional markers, excluding code fences) returned 3 candidate blocks — all false positives on manual review:
- `skills/research/SKILL.md:1-19` — YAML frontmatter (not prose)
- `skills/lifecycle/SKILL.md:57-73` — numbered 1–5 step list with explicit code fences (explicit control structure)
- `claude/reference/claude-skills.md:15-26` — markdown table (structured format)

The repo's authoring convention (numbered steps, bullet lists, code fences, tables) consistently applies explicit control structure to all multi-conditional content. P4 null on this surface.

## Pattern P5 — procedural-order dependency

Signature: `\bdo not (omit|reorder|paraphrase|alter)\b`

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/lifecycle/references/implement.md:243 | `**b. Dispatch batch**: Launch all tasks in the batch ... Use the builder prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions.` | verbatim-contract-preservation | SKIP | | Spec R11 default; one of 3 known verbatim subagent-dispatch contracts |
| skills/lifecycle/references/plan.md:27 | `**b. Dispatch plan agents**: ... Use the plan agent prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions.` | verbatim-contract-preservation | SKIP | | Spec R11 default; one of 3 known verbatim subagent-dispatch contracts |
| skills/lifecycle/references/research.md:57 | `Launch all research agents ... Use the researcher prompt template below **verbatim** for each agent — substitute the variables but do not omit, reorder, or paraphrase any instructions.` | verbatim-contract-preservation | SKIP | | Spec R11 default; one of 3 known verbatim subagent-dispatch contracts |

## Pattern P6 — examples-as-exhaustive-list

Signature: `[Ss]elect .* from the following|from this menu|such as `.*:\s*$` in a section header followed by bullets.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/critical-review/SKILL.md:30 | `Select angles from the following menu, picking whichever are most likely to reveal real problems for this specific ar...` | qualifying | M1 | 0ea0a41 | M1 rewrite — reframed as "representative angle examples — not an exhaustive set" with explicit invite to invent; menu authority and distinct-angle anchor preserved |

## Pattern P7 — [Cc]onsider hedge

Signature: `\b[Cc]onsider\b|\btry to\b|\bif possible\b`

P7 rescan scope: all of `skills/` per Task 11 context — sites outside R1's 12-surface audit scope get `M-label: out-of-scope-of-R1` and produce no edit under #85.

| file:line | site excerpt | classification | M-label | commit SHA | notes |
|-----------|-------------|----------------|---------|------------|-------|
| skills/research/SKILL.md:131 | `Your job: identify alternative approaches... Consider implementation complexity, maintainability, performance...` | (a) conditional-requirement | M1 | bb447c2 | M1 rewrite — "Consider X,Y,Z,W" → "weigh tradeoffs on four dimensions: X, Y, Z, W" |
| skills/lifecycle/references/plan.md:277 | `"The backlog item said to do it this way" ... evaluate it critically and consider alternatives.` | (a) conditional-requirement | M1 | bb447c2 | M1 rewrite — "consider alternatives" → "weigh alternatives" |
| skills/diagnose/SKILL.md:74 | `from the error output and initial investigation, consider spawning a competing-hypotheses` | (b) genuinely optional | | | Step 6 is explicitly titled "Optional: Competing-Hypotheses Team" with an explicit skip path at :77 — no remediation |
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
| skills/critical-review/SKILL.md:103 | P3 | anchored: distinct-angle rule + no-soften | `grep -F "Do not cover other angles" skills/critical-review/SKILL.md` = 1 |
| skills/critical-review/SKILL.md:140 | P3 | anchored: no-soften cluster | Paired with `Do not soften or editorialize` anchor at :195 |
| skills/critical-review/SKILL.md:179 | P3 | anchored: no-soften cluster | `grep -F "Do not soften or editorialize" skills/critical-review/SKILL.md` = 1 |
| skills/lifecycle/references/implement.md:309 | P3 | category 3: control-flow gate in verbatim subagent-dispatch template | Also classified under P5 (Task 9) as verbatim-contract-preservation |

## Null-pattern log

Patterns with zero qualifying sites after classification. Format: `P<n> — N sites audited, M preservation-excluded, 0 qualifying. Reason: <summary>.`

- P1 — 5 sites audited, 0 preservation-excluded, 0 qualifying. Reason: all 5 regex matches are conditional-else-branch output directives with explicit positive-conditional framing ("if X, omit Y"); under 4.7 literalism the conditional establishes routing context before the negation fires, so no gappy-synthesis risk. Two sites (critical-review:138/:177) combine positive verb "Skip" with reinforcing "do not emit" — semantically equivalent clauses rather than a true double-negation.

- P4 — 0 sites qualified after heuristic scan (3 candidates, all false positives on manual review — all had explicit control structure: YAML, numbered steps, markdown table). Reason: repo authoring convention consistently uses numbered steps, bullets, code fences, and tables for multi-conditional content. No natural-language conditional blocks ≥10 lines without explicit structure found on the 12 surfaces.

- P5 — 3 sites audited, 3 verbatim-contract SKIP, 0 qualifying. Reason: all 3 sites are the known verbatim subagent-dispatch contracts at `lifecycle/references/{implement,plan,research}.md` that spec R11 / Non-Req #2 enumerate explicitly as SKIP. Ordering is load-bearing for verbatim substitution — the literal negation is correct under 4.7. Pass 1 surfaced no additional non-verbatim P5 sites.

## Incidental findings

P8-severity-gate or other out-of-scope sites surfaced during Pass 1 grep — recorded for future tickets.

## Escalations

Anchor-string reworded, section-heading renamed, or other drift surfaced during remediation — surfaced to user at Review per spec §Edge Cases.

- **P2 commit-subject deviation from spec R5 format (2026-04-21T21:41Z)**: Commit `ee8b599` contains the P2 remediation diff (`skills/lifecycle/SKILL.md` and `skills/refine/SKILL.md` per-site rewrites) but its subject is `Cascade 088 wontfix closure to epic 82 dependent tickets` — it was created by a concurrent daytime session that swept up #85's unstaged skill-file WIP into its own backlog-cascade commit. Spec R5 requires the commit subject to match `^[0-9a-f]+ Remediate P[1-7]`; this commit does not. R5 acceptance (`git log --oneline main ... | grep -E '^[0-9a-f]+ Remediate P[1-7] '`) will return 0 matches for P2 despite the remediation diff being correctly applied. Review phase should note this as a known R5 cosmetic deviation — not a correctness failure, since the post-commit P2 signature no longer matches at the remediated positions.
