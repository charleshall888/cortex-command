# Review: favor-long-term-solutions

## Stage 1: Spec Compliance

### Requirement 1: Canonical principle in `project.md`
- **Expected**: A bold-prefixed `**Solution horizon**` paragraph in `cortex/requirements/project.md` Philosophy of Work, placed immediately after the `**Complexity**` paragraph, expressing the known-redo test and the phased-lifecycle carve-out, in soft positive-routing language only. Acceptance: `grep -c '^\*\*Solution horizon\*\*:'` returns `1`; `grep -c 'known-redo\|already planned\|unplanned-redo\|phased lifecycle\|deliberately-scoped phase'` returns ≥`2`; MUST/NEVER/REQUIRED/CRITICAL scan against the new block returns `0`.
- **Actual**:
  - `**Solution horizon**` paragraph present at line 21 of `cortex/requirements/project.md`, immediately after `**Complexity**` at line 19 (blank line 20).
  - `grep -c '^\*\*Solution horizon\*\*:' cortex/requirements/project.md` → `1`.
  - Known-redo phrase scan: the paragraph contains three of the five anchor phrases (`already planned`, `deliberately-scoped phase`, `unplanned-redo`) but `grep -c` counts matching lines, and the entire paragraph is a single line, so the literal command returns `1`. The conceptual intent (≥2 anchor phrases present) is satisfied; the literal acceptance bound is structurally unreachable given the paragraph's single-line form.
  - MUST/NEVER/REQUIRED/CRITICAL scan on line 21 → `0`.
  - Phased-lifecycle carve-out present: "A deliberately-scoped phase of a multi-phase lifecycle is not a stop-gap; stop-gap means unplanned-redo."
  - Soft positive-routing language used throughout: "ask: do I currently know…", "If yes, propose…", "If no, **Complexity** above still applies".
- **Verdict**: PASS
- **Notes**: The literal `grep -c` acceptance for the phrase scan is internally inconsistent with the single-line paragraph format the spec also implies (a "paragraph"). Treating the requirement at the intent level (≥2 anchor phrases must appear) — clearly satisfied. Flagged as an authoring oversight in the spec acceptance, not an implementation defect.

### Requirement 2: Operational pointer in `CLAUDE.md`
- **Expected**: A new `## Solution horizon` section in `CLAUDE.md`, placed immediately before `## Design principle: prescribe What and Why, not How`, containing a one-sentence operational trigger plus a cross-reference to `cortex/requirements/project.md` Philosophy of Work. Soft positive-routing only. Acceptance: section header count `1`; appears textually before `## Design principle…`; `grep -c 'cortex/requirements/project.md' CLAUDE.md` returns prior baseline + 1; MUST scan returns `0`.
- **Actual**:
  - `## Solution horizon` section present at line 60 of `CLAUDE.md`; `## Design principle…` at line 64. Ordering correct.
  - `grep -c '^## Solution horizon$' CLAUDE.md` → `1`.
  - Baseline `grep -c 'cortex/requirements/project.md'` on `HEAD:CLAUDE.md` → `0`; post-change → `1`. Baseline + 1 ✓.
  - MUST/NEVER/REQUIRED/CRITICAL scan on lines 60–63 → `0`.
  - One-sentence operational trigger present: "Before suggesting a fix, ask whether you already know it will need to be redone…".
  - Cross-reference present: "The canonical statement of this principle, and its reconciliation with the simplicity defaults, lives in `cortex/requirements/project.md` under Philosophy of Work."
- **Verdict**: PASS
- **Notes**: All acceptance criteria literally satisfied.

### Requirement 3: Explicit reconciliation with `**Complexity**` ("simpler is correct")
- **Expected**: The new `**Solution horizon**` paragraph must contain text explicitly stating the principle does NOT override the `**Complexity**` philosophy in the no-known-redo case — i.e., when redo is not already known, the simpler fix remains correct. Acceptance: `simpler|simple` appears ≥1 time in the new paragraph block; the surrounding sentence expresses a *when-condition* relationship, not an override.
- **Actual**:
  - `simpler|simple` count in line 21 → `1` (matches in "the simpler fix is correct").
  - Reconciliation sentence: "If no, **Complexity** above still applies — the simpler fix is correct, and speculating about future redo is itself over-engineering."
  - The sentence frames Solution horizon as a *when-condition* (the durable-version branch fires only when redo is currently known), and explicitly defers to `**Complexity**` otherwise. Not framed as an override.
- **Verdict**: PASS
- **Notes**: The "speculating about future redo is itself over-engineering" clause provides additional defense against the edge case spec'd (paragraph misread as endorsing speculative future-proofing). Strong reconciliation.

## Requirements Drift
**State**: none
**Findings**:
- None. The CLAUDE.md `## Solution horizon` section is faithfully a pointer to the canonical statement in `project.md`'s Philosophy of Work. The operational-trigger sentence in CLAUDE.md ("Before suggesting a fix, ask whether you already know it will need to be redone…") is a paraphrase of the canonical paragraph's known-redo test and does not introduce new constraints. The phased-lifecycle carve-out and the simplicity-default fallback are both present in the canonical paragraph and faithfully gestured at in the CLAUDE.md operational form.
**Update needed**: None

## Stage 2: Code Quality

- **Prose clarity**: The canonical paragraph in `project.md` is dense but each clause earns its place — known-redo test (three concrete triggers: planned follow-up, multiple known applications, nameable sidestepped constraint), the if-yes/if-no branches, the reconciliation with `**Complexity**`, the phased-lifecycle carve-out, and the closing "current knowledge, not prediction" anchor. No filler. The CLAUDE.md section trims appropriately: one-sentence trigger + pointer.
- **Internal consistency**: The CLAUDE.md operational form uses second-person ("ask whether you already know") while the canonical paragraph in `project.md` uses first-person ("ask: do I currently know"). Both are coherent for their respective surfaces (CLAUDE.md addresses the agent; project.md reads as the agent's internal heuristic). Not a defect, but worth noting as a deliberate voice shift between surfaces.
- **Soft positive-routing compliance**: Both blocks contain zero MUST/NEVER/REQUIRED/CRITICAL terms. Phrasing is consistently soft-positive: "ask", "propose", "still applies", "is correct". Compliant with the CLAUDE.md MUST-escalation policy and the spec's Technical Constraint that no evidence artifact exists for escalation.
- **Pattern consistency**:
  - `project.md` paragraph follows the existing Philosophy of Work bold-prefixed paragraph style (`**Complexity**`, `**Quality bar**`, `**Workflow trimming**`, etc.). Placement immediately after `**Complexity**` is logical because Solution horizon constrains Complexity rather than standing independently.
  - `CLAUDE.md` section follows the existing `## Principle name` top-level pattern (`## Design principle: prescribe What and Why, not How`, `## MUST-escalation policy (post-Opus 4.7)`, `## Skill / phase authoring guidelines`). Header capitalization (`## Solution horizon`) is consistent with neighbors that use sentence case for the leading word + lowercase thereafter.
- **Faithful reconciliation with `**Complexity**`**: The `**Solution horizon**` paragraph explicitly references `**Complexity**` by name and defers to it in the no-known-redo case. The `**Complexity**` paragraph itself is unmodified (per the spec's Non-Requirements), preserving the existing simplicity default as the base rule with Solution horizon as the *when-redo-is-known* override branch.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
