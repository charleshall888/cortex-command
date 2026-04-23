# Axis B Candidate Enumeration Scan (B1 + B2)

Discovery pass for #053 (add-subagent-output-formats-compress-synthesis) Task 7.
No skill file edits are made by this task. Task 8 reads this file to drive
pattern-bucketed edits.

## Scan Commands

- **B1**: `grep -n "CRITICAL:\|[Yy]ou [Mm]ust\|ALWAYS \|NEVER \|REQUIRED to\|think about\|think through" <file>`
- **B2**: `grep -n "IMPORTANT:\|make sure to\|be sure to\|remember to" <file>`

## In-Scope Files Scanned (14 files)

1. `skills/critical-review/SKILL.md`
2. `skills/diagnose/SKILL.md`
3. `skills/discovery/SKILL.md`
4. `skills/lifecycle/SKILL.md`
5. `skills/overnight/SKILL.md`
6. `skills/research/SKILL.md`
7. `skills/backlog/SKILL.md`
8. `skills/pr-review/SKILL.md`
9. `skills/lifecycle/references/implement.md`
10. `skills/lifecycle/references/clarify-critic.md`
11. `skills/lifecycle/references/orchestrator-review.md`
12. `skills/lifecycle/references/plan.md`
13. `skills/lifecycle/references/review.md`
14. `skills/discovery/references/orchestrator-review.md`

Note: `skills/dev/SKILL.md` is NOT in this scan — DV1/DV2 already handled in Task 9.

## Exclusion Categories

A match in ANY of these categories is excluded from the candidate list:

1. Inside code fence (``` ``` or indented code block)
2. Output-channel directive: controls downstream JSON schema, event format, or review verdict
3. Control-flow gate: gates entry into a named phase or step
4. Preservation list item (all 14 P1 anchors)
5. Mixed-case / bold / title-case variant (ALL-CAPS only is in scope)
6. Single-word ALL-CAPS procedural marker (BEFORE, THEN, STOP, ANY)

## B1 Pattern Matches (Core Table)

Baseline total: 4 matches across 4 files. Each match classified below.

### Match B1-1 — `skills/diagnose/SKILL.md:16`

- **Pattern matched**: `ALWAYS ` (ALL-CAPS multi-word imperative)
- **Line**: `ALWAYS find root cause before attempting fixes. No fixes without completing Phase 1.`
- **Context**: Under `## Rule` heading, top of the Systematic Debugging section.
- **Exclusion category**: **4 — Preservation list item (P1 Anchor #7)**
- **Decision**: **EXCLUDED**
- **Rationale**: This is P1 Anchor #7 from the baseline scan (`ALWAYS find root cause before attempting fixes`). Explicitly untouchable by the preservation list regardless of pattern.

### Match B1-2 — `skills/overnight/SKILL.md:248`

- **Pattern matched**: `You must ` (multi-word imperative)
- **Line**: `Scan $CORTEX_COMMAND_ROOT/lifecycle/sessions/*/overnight-state.json (sorted by modification time, most recent first) and load the first file whose phase is not complete using load_state(state_path=<path>) from cortex_command.overnight.state. You must pass the explicit state_path argument — the default path points to a different location. This mirrors the runner's own auto-discovery logic and works correctly whether state was written by a sandboxed or non-sandboxed session.`
- **Context**: Prose paragraph in `### Step 1: Load Existing State` under `## Resume Flow`. Not inside a code fence or indented block — free prose.
- **Exclusion category**: none apply
  - Not inside a code fence (Cat 1): prose paragraph at top-level `### Step 1`, no backticks around it.
  - Not an output-channel directive (Cat 2): instructs argument passing at call-site, does not control downstream JSON/event/verdict schema.
  - Not a control-flow gate (Cat 3): the sentence around the `you must` instructs a single argument-passing detail, not entry into a named phase.
  - Not a preservation anchor (Cat 4): not on the 14-item P1 list.
  - Not mixed-case variant (Cat 5): the pattern-matched phrase is `You must` — within scope as a multi-word imperative (the pattern regex explicitly includes `[Yy]ou [Mm]ust`).
  - Not a single-word marker (Cat 6): multi-word phrase.
- **Decision**: **QUALIFYING CANDIDATE**
- **Suggested soften** (for Task 8 reference only, not applied here): rephrase as a declarative call-site note (e.g., "Pass the explicit `state_path` argument — the default path points to a different location.").

### Match B1-3 — `skills/lifecycle/references/clarify-critic.md:43`

- **Pattern matched**: `you must ` (multi-word imperative, lowercase via pattern `[Yy]ou [Mm]ust`)
- **Line**: `2. Derive 3–4 challenge angles from the confidence assessment. The three dimensions you must cover are:`
- **Context**: Inside the verbatim prompt template passed to the clarify-critic subagent. The `## Instructions` block under `---` at line 28–50. Free prose (numbered list item), not inside a code fence.
- **Exclusion category**: none apply
  - Not inside a code fence (Cat 1): numbered list inside prompt body, no backticks around this line. (The code fence in the file is later, at line 54 with the Finding/Concern format — separate location.)
  - Not an output-channel directive (Cat 2): governs the content dimensions the critic should cover in its challenge; does not control a JSON schema, event format, or verdict. The actual output format (Finding/Concern) is defined separately in a code fence below.
  - Not a control-flow gate (Cat 3): does not gate entry into a named phase — it's a within-step directive about analytic coverage.
  - Not a preservation anchor (Cat 4): not on the 14-item P1 list.
  - Not mixed-case variant (Cat 5): the phrase `you must` is in scope per the pattern regex.
  - Not a single-word marker (Cat 6): multi-word phrase.
- **Decision**: **QUALIFYING CANDIDATE**
- **Suggested soften** (for Task 8 reference only, not applied here): rephrase as declarative coverage statement (e.g., "Derive 3–4 challenge angles from the confidence assessment. Cover these three dimensions:").

### Match B1-4 — `skills/lifecycle/references/review.md:64`

- **Pattern matched**: `CRITICAL:` (ALL-CAPS prefix)
- **Line**: `CRITICAL: The Verdict section MUST contain a JSON object with exactly these fields:`
- **Context**: Under `### Write Review` section, introducing the Verdict JSON schema specification.
- **Exclusion category**: **2 — Output-channel directive**
- **Decision**: **EXCLUDED**
- **Rationale**: Directly controls the downstream review verdict JSON schema (field names `verdict`, `cycle`, `issues`) and is explicitly flagged by the spec as an out-of-scope CRITICAL/MUST instance in `skills/lifecycle/references/review.md`. Softening this would relax schema enforcement that downstream review parsing depends on.

## B2 Pattern Matches (Analogue)

Baseline total: 0 matches across all 14 in-scope files.

**Per-file scan results**:

| File | B2 matches |
|------|-----------|
| `skills/critical-review/SKILL.md` | 0 |
| `skills/diagnose/SKILL.md` | 0 |
| `skills/discovery/SKILL.md` | 0 |
| `skills/lifecycle/SKILL.md` | 0 |
| `skills/overnight/SKILL.md` | 0 |
| `skills/research/SKILL.md` | 0 |
| `skills/backlog/SKILL.md` | 0 |
| `skills/pr-review/SKILL.md` | 0 |
| `skills/lifecycle/references/implement.md` | 0 |
| `skills/lifecycle/references/clarify-critic.md` | 0 |
| `skills/lifecycle/references/orchestrator-review.md` | 0 |
| `skills/lifecycle/references/plan.md` | 0 |
| `skills/lifecycle/references/review.md` | 0 |
| `skills/discovery/references/orchestrator-review.md` | 0 |

No B2 candidates, qualifying or excluded. Confirmation pass expected empty
per baseline and per spec — result consistent with expectation.

## Summary

### Total matches found

| Axis | Total matches | Qualifying candidates | Excluded |
|------|--------------:|----------------------:|---------:|
| B1   | 4             | 2                     | 2        |
| B2   | 0             | 0                     | 0        |

### Qualifying candidates (inputs for Task 8)

| # | File | Line | Pattern | Suggested soften direction |
|---|------|-----:|---------|---------------------------|
| 1 | `skills/overnight/SKILL.md` | 248 | `You must` | Declarative call-site note |
| 2 | `skills/lifecycle/references/clarify-critic.md` | 43 | `you must` | Declarative coverage statement |

### Excluded matches (documented for audit trail)

| # | File | Line | Pattern | Exclusion category |
|---|------|-----:|---------|-------------------|
| 1 | `skills/diagnose/SKILL.md` | 16 | `ALWAYS` | 4 — P1 Anchor #7 |
| 2 | `skills/lifecycle/references/review.md` | 64 | `CRITICAL:` | 2 — Output-channel directive (explicitly called out in spec) |

### Consistency with baseline and spec

- B1 match count (4) matches the baseline file exactly.
- B2 match count (0) matches the baseline file exactly.
- Qualifying-candidate count (2) falls within the spec's stated "2–4 actual
  instances outside exclusion categories" — confirming the corpus is already
  largely softened, as expected.
- Both excluded matches are excluded for reasons called out explicitly in
  the task spec (P1 preservation list and the review.md CRITICAL/MUST carve-out).
