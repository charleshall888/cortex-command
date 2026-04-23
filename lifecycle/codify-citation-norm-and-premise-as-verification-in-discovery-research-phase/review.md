# Review: codify-citation-norm-and-premise-as-verification-in-discovery-research-phase

## Stage 1: Spec Compliance

Nine requirements evaluated. Note on acceptance commands: three of the spec's awk range patterns (`/^## Constraints/,/^##[^#]|\Z/` and `/^## Codebase Analysis/,/^##[^#]/`) return 0 on macOS (BSD) awk because the end pattern `^##[^#]` matches the start heading itself, collapsing the range to a single line. This is a spec defect noted in the instructions — I fell back to bare grep and visual inspection of the file.

### Requirement 1 — Citation-or-marker rule added to `## Constraints`: PASS
- Spec awk acceptance: 0 (BSD awk defect).
- Fallback `grep -c "Citations" skills/discovery/references/research.md`: 1.
- Visual inspection: `skills/discovery/references/research.md:145` contains `- **Citations**: codebase-pointing claims must carry an inline \`[file:line]\` citation traceable to codebase-agent findings, OR an explicit inline \`[premise-unverified: not-searched]\` marker when the author did not investigate the claim.` — verbatim spec wording, inside `## Constraints`.

### Requirement 2 — Empty-corpus reporting rule: PASS
- Spec awk acceptance: 0 (BSD awk defect).
- Fallback `grep -c "Empty-corpus reporting"`: 1.
- Visual inspection: `research.md:146` contains the Empty-corpus bullet with verbatim spec wording, inside `## Constraints`.

### Requirement 3 — Prerequisites-retargeting instruction in §5: PASS
- `grep -cF "implementation-sequencing only"`: 1.
- Visual inspection: `research.md:75` contains the retargeting paragraph, placed after the §5 Feasibility bullet list (ending at line 73) and before §6 (starting at line 77). Verbatim spec wording. Column structure at `research.md:111` (`| Approach | Effort | Risks | Prerequisites |`) is preserved.

### Requirement 4 — Three example bullets demonstrating classification judgment in §6: PASS
- Spec awk acceptance: 0 (BSD awk defect).
- Visual inspection of `research.md:93-96` under `## Codebase Analysis` inside the §6 template:
  - Line 94: grounded `[file:line]` citations (`src/foo.py:42`, `src/bar.py:18`, `src/baz.py:88`).
  - Line 95: `NOT_FOUND(query="async ContextVar usage", scope="src/**/*.py")` empty-corpus finding.
  - Line 96: #092-pattern — vendor-endorsed inference correctly flagged `[premise-unverified: not-searched]` rather than fabricated citation.
- The third example is the load-bearing judgment case (external-endorsement-without-codebase-evidence) that distinguishes classification from syntax. Matches plan's suggested wording and spec Req 4(c).

### Requirement 5 — Signal-format contract section: PASS
- `grep -c "\[file:line\]"`: 2 (≥ 1).
- `grep -c "premise-unverified: not-searched"`: 4 (≥ 1).
- `grep -c "NOT_FOUND(query"`: 4 (≥ 1).
- `grep -n "^### Signal formats"`: hit at line 148.
- Visual inspection of `research.md:148-154` confirms H3 `### Signal formats` subsection with preamble naming the markers as stable contract for `/discovery decompose`, followed by three bullets defining `[file:line]`, `[premise-unverified: not-searched]`, and `NOT_FOUND(query=<string>, scope=<path-or-glob>)`.

### Requirement 6 — Prospective applicability, no retroactive language: PASS
- `grep -cE "retroactive|retroactively|backfill|audit pass"`: 0.

### Requirement 7 — `orchestrator-review.md` unchanged: PASS
- `git diff 8840b25..HEAD -- skills/discovery/references/orchestrator-review.md`: empty.

### Requirement 8 — `decompose.md` unchanged: PASS
- `git diff 8840b25..HEAD -- skills/discovery/references/decompose.md`: empty.

### Requirement 9 — `skills/research/SKILL.md` and `skills/research/` unchanged: PASS
- `git diff 8840b25..HEAD -- skills/research/`: empty.

All nine requirements PASS. Proceeding to Stage 2.

## Stage 2: Code Quality

### Naming conventions
Marker tokens are used consistently across the four edit sites:
- Constraints bullets (lines 145-146): `[file:line]`, `[premise-unverified: not-searched]`, `NOT_FOUND(query=<search-string>, scope=<path-or-glob>)`.
- Signal formats subsection (lines 152-154): same three tokens with parameter placeholders matching the Constraints usage.
- §5 retargeting paragraph (line 75): references `NOT_FOUND(query, scope)` (signature-only form, no parameters — natural in running prose).
- §6 examples (lines 94-96): concrete instantiations of all three tokens with realistic parameter values.
No drift between definitional and example-site forms.

### Error handling
N/A — prose protocol edit, not code.

### Test coverage
All nine spec acceptance criteria are covered by the four task-level verifications. Plan tasks 1 and 4 explicitly noted the BSD awk defect and documented the bare-grep fallback. Visual read-back was performed per plan's final instruction.

### Pattern consistency
New bullets at lines 145-146 follow the existing `- **Label**: prose.` convention used by the three pre-existing Constraints bullets (Read-only / All findings in the artifact / Scope). The `### Signal formats` H3 sits as a natural child of the `## Constraints` H2, giving #139 a discoverable anchor. The §6 examples live inside the markdown code fence (preserved open at line 81, close at line 126) as a sub-bullet group under the four original placeholder bullets, preserving template narrative flow for first-time authors while adding the marker demonstration.

## Requirements Drift
**State**: none
**Findings**:
- None. The marker vocabulary is a skill-internal contract between `skills/discovery/references/research.md` (producer) and `skills/discovery/references/decompose.md` / ticket #139 (consumer). It is adjacent to project.md's "Daytime work quality: Research before asking. Don't fill unknowns with assumptions" principle but operates at the skill-implementation layer, not the project-governance layer. Project.md names quality principles in the abstract; specific enforcement mechanisms for those principles live inside the skills that implement them. No project-level Quality Attribute is needed.
**Update needed**: None

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
