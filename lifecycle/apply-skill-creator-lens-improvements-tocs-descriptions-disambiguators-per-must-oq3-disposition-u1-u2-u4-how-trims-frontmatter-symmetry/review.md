# Review: apply-skill-creator-lens-improvements-tocs-descriptions-disambiguators-per-must-oq3-disposition-u1-u2-u4-how-trims-frontmatter-symmetry

## Stage 1: Spec Compliance

### Requirement R1: TOCs on four >300-line files
- **Expected**: `## Contents` H2 section in the first 25 lines of each of the 4 files (lifecycle/SKILL.md, lifecycle/references/plan.md, lifecycle/references/implement.md, critical-review/SKILL.md), positioned before the first protocol-equivalent H2; numbered list of explicit `[text](#anchor)` links; H2 entries only.
- **Actual**: All 4 files have `## Contents` within the first 25 lines (verify.sh's `head -25 ... grep -q '^## Contents$'` passed all 4). lifecycle/SKILL.md ships 12 numbered entries; critical-review/SKILL.md ships 4. Each TOC is positioned immediately after frontmatter and before the first protocol H2.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R2: when_to_use frontmatter on all 4 SKILL.md files
- **Expected**: `when_to_use` field on lifecycle, refine, critical-review, discovery SKILL.md files; sibling-disambiguator clauses present per file (`Different from /cortex-core:refine|lifecycle|research|/devils-advocate`); description ≤1024 chars per file.
- **Actual**: All 4 files have `when_to_use` (verify.sh confirms count=4). All 4 disambiguators present:
  - lifecycle: "Different from /cortex-core:refine — refine stops at spec.md..."
  - refine: "Different from /cortex-core:lifecycle — refine produces spec only..."
  - discovery: "Different from /cortex-core:research..." plus a second "Different from /cortex-core:lifecycle..." (correctly dual since discovery has two siblings)
  - critical-review: "Different from /devils-advocate — devils-advocate runs inline..."
  - Description char counts: lifecycle 866, refine 377, critical-review 764, discovery 662 — all under 1024.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R3: OQ3 per-MUST disposition (uniform soften)
- **Expected**: 4 MUSTs in review.md (lines 64, 72, 78, 80) and 3 MUSTs in clarify-critic.md (lines 26, 155, 159) softened to declarative-behavioral phrasing; verdict-JSON format contract preserved; closed-allowlist warning-template, dismissals invariant, and cross-field invariant prose retained sans imperative.
- **Actual**: review.md lines 64-90 show declarative-behavioral phrasing — "The Verdict section is a JSON object with exactly these fields:" / "Alternative field names like 'overall'... are not used." / "Alternative values like 'PASS'... are not used." / "Your review.md includes a ## Requirements Drift section using exactly this format:". The strict format-contract emphasis (exact field names, exact values, requirements_drift matching rule) is preserved; the imperative mood is dropped. Acceptance check `awk 'NR>=60 && NR<=90' ... grep -cE 'MUST|CRITICAL|REQUIRED'` returns 0. clarify-critic.md lines 26, 155, 159 all softened — line 26: "uses one of the two verbatim templates listed above and does not echo raw filesystem error text"; line 155: "is present on every post-feature event. It is `true` when..."; line 159: "Cross-field invariant: any post-feature event whose findings[] contains at least one item with `origin: 'alignment'` has `parent_epic_loaded: true`. Violation indicates a write-side bug." Acceptance check `awk 'NR>=20 && NR<=170' ... grep -cE 'MUST|REQUIRED'` returns 0. Schema annotation at line 138 lowercased to `# required` to keep the regex sweep clean. Verdict-JSON format contract intact (all "verdict"/"APPROVED"/"CHANGES_REQUESTED"/"REJECTED" enum values still exact-match-mandated by declarative phrasing).
- **Verdict**: PASS
- **Notes**: Declarative-behavioral semantics preserved across all 7 sites. The lowercased `# required` on line 138 is a sensible defensive edit to avoid false positives in the verify regex; semantics unchanged (the field is still required by the Required-fields header on line 132).

### Requirement R4 U1: critical-review Apply/Dismiss/Ask trim
- **Expected**: Replace ~30-line Apply/Dismiss/Ask body at lines 336-365 with ~5-line directive containing "Default ambiguous to Ask" and anchor-checks; verbose worked-example block removed (`Compliant: R10 strengthened` absent).
- **Actual**: critical-review/SKILL.md lines 357-360 contain the 4-line directive ("Apply when... / Dismiss when... / Ask when... / Default ambiguous to Ask. Anchor-checks: dismissals must be pointable to artifact text, not memory; resolutions must rest on new evidence, not prior reasoning."). Lines 362-369 retain the "After classifying all objections" sequence. `grep -c "Default ambiguous"` returns 1; `grep -c "Compliant: R10 strengthened"` returns 0.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R4 U2: Constraints "Thought/Reality" tables
- **Expected**: u2-decisions.md exists, lists KEEP/DROP for every row in the 12 corpus tables, retained rows cite a specific identifier, dropped rows confirm "no specific identifier" (or include reality_text= for traceability), no wholesale-removal unless all rows lacked an identifier.
- **Actual**: u2-decisions.md exists with completion sentinel `<!-- u2-decisions:complete -->`. Summary table reports 33 KEEP / 23 DROP across 11 files (decompose.md correctly noted as bullet-list, not table — vacuous). Spot-checks confirmed:
  - `lifecycle/references/review.md` post-edit shows 4 rows (rows containing PARTIAL, verdict/APPROVED/CHANGES_REQUESTED/REJECTED, detected, requirements docs) — matches the 4 KEEPs in u2-decisions.md. Two dropped rows (Code-quality-issues-minor and reviewer-does-not-modify) are absent — drift check inside verify.sh confirms drop semantics.
  - `refine/references/clarify-critic.md` post-edit shows 6 rows — matches 6 KEEP / 1 DROP. The dropped row (rubber-stamping rationale) is absent.
  - `lifecycle/references/specify.md` table wholesale-removed (all 4 rows DROP, no specific identifiers); `## Hard Gate` heading and intro paragraph preserved per spec edge case.
  - `discovery/references/clarify.md` shows 3 rows — matches the 3 KEEPs.
  - verify.sh's drift check (recompute DROP reality_text from u2-decisions and assert each file does not contain the drop text) returns clean for all 12 corpus files.
- **Verdict**: PASS
- **Notes**: Named-consumer rule applied conservatively per spec: e.g., review.md row referencing PARTIAL retained because PARTIAL is a schema enum value — appropriate KEEP. No false KEEPs on rows lacking named identifiers; no false DROPs on rows with named identifiers.

### Requirement R4 U4: Slugify HOW-prose trim
- **Expected**: lifecycle/SKILL.md slugify block replaced with one-line reference to `cortex_command.common`; old verbose example ("underscores become hyphens, not stripped") removed.
- **Actual**: lifecycle/SKILL.md line 51: "Use the canonical `slugify()` from `cortex_command.common`." `grep -c "cortex_command.common"` returns 3 (skill body + Step 2 detect-phase command + outputs section), `grep -c "underscores become hyphens, not stripped"` returns 0.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R5: Backlog/182 amendment for metrics.py:221 parser hardening
- **Expected**: backlog/182 body amended with "Parser hardening at metrics.py:221" sub-bullet; tags updated to include `metrics-parser`; status preserved.
- **Actual**: backlog/182 line 10 tags include `metrics-parser`. Line 93 contains "### 3a. Parser hardening at `metrics.py:221` (per #178 R5 amendment)". Line 95 explains the alias-lookup/normalized-field-name parsing scope and FM-7 protection rationale. `grep -c "metrics.py" backlog/182-*.md` returns ≥1.
- **Verdict**: PASS
- **Notes**: None.

### Requirement R6: Frontmatter symmetry on critical-review
- **Expected**: 4 fields added (`argument-hint`, `inputs`, `outputs`, `preconditions`); `precondition_checks` NOT added; argument-hint quoted to dodge Issue #22161 TUI bracket-syntax hang.
- **Actual**: critical-review/SKILL.md frontmatter contains all 4 fields with quoted `argument-hint: "[<artifact-path>]"`. No `precondition_checks` field. inputs cites artifact-path (optional, auto-detect fallback); outputs cites synthesis prose + optional residue write at `lifecycle/{feature}/critical-review-residue.json`; preconditions: run from project root + artifact path resolves. Acceptance check: `awk` count = 4, `precondition_checks` count = 0.
- **Verdict**: PASS
- **Notes**: The `outputs` value uses `critical-review-residue.json` rather than the spec's example `critical-review-{phase}.md`. The spec example was inaccurate — the actual atomic-write path in critical-review/SKILL.md line 335 is `lifecycle/{feature}/critical-review-residue.json`. The implementer correctly used the truthful path. This is a positive deviation that prevents the frontmatter from documenting a non-existent path.

### Requirement R7: New backlog item for clarify-critic schema validator + warning-template runtime validator
- **Expected**: New backlog item exists; references clarify-critic.md lines 26, 155, 159 as the prose MUSTs the validator replaces; parent links to 178 (or epic 172).
- **Actual**: `backlog/186-clarify-critic-schema-validator-and-warning-template-runtime-validator.md` exists. Line 8 sets `parent: 178`. Body cites lines 26, 155, 159 explicitly (line 20: "MUST/REQUIRED imperatives at lines 26, 155, and 159"). Scope covers (a) dismissals invariant `len(dismissals) == dispositions.dismiss`, (b) cross-field invariant `origin: alignment → parent_epic_loaded: true`, (c) warning-template allowlist runtime check. Indexed in both backlog/index.md and backlog/index.json.
- **Verdict**: PASS
- **Notes**: None.

## Requirements Drift

**State**: none
**Findings**:
- None. The implementation is purely mechanical edits to skill prose, frontmatter, backlog metadata, and lifecycle artifacts. No new behavior introduced; no architectural pattern changed. Workflow-trimming philosophy (project.md:23) is reinforced via the U1/U2/U4 trims. Dual-source canonical/mirror invariant is preserved (all 6 spot-checked diff -q pairs return clean). SKILL.md-to-bin parity surface is not affected (no `bin/cortex-*` references touched). MUST-escalation policy (CLAUDE.md OQ3) is the policy this implementation IS executing — uniform soften per the closed evidence list — so no drift introduced; rather, prior MUST-bearing prose is brought into compliance.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with project patterns. Frontmatter field names (`when_to_use`, `argument-hint`, `inputs`, `outputs`, `preconditions`) match existing canonical fields in lifecycle/SKILL.md and refine/SKILL.md. The new backlog/186 follows the kebab-case slug + numeric-prefix convention. The R5 tag `metrics-parser` aligns with existing tag-naming style in 182.
- **Error handling**: verify.sh uses `set -euo pipefail` with explicit `fail()` and `ok()` helpers; assertion failures exit non-zero with diagnostic messages; the Python embedded snippets use `sys.exit(1)` with `print('FAIL: ...')` patterns. Drift-check loop iterates the 12-file corpus and fails closed on first match. ran clean (`ALL PASS`) at this review.
- **Test coverage**: Plan.md prescribed per-task verification + cross-corpus verify.sh; events.log shows 12 task_complete events (tasks 1-12) plus phase_transitions for all spec→plan→implement→review boundaries. The single verify.sh script consolidates all spec acceptance criteria (R1-R7 + 178 self-amendments + U2 cross-corpus drift) into one assertion script that exits 0 with `ALL PASS` — confirmed in this review.
- **Pattern consistency**: TOC format consistent across all 4 files (numbered list, lowercase-hyphenated anchors, H2 entries only, positioned right after frontmatter). when_to_use format consistent across the 4 SKILL.md files (single-string `Use when X. Different from /cortex-core:Y — Z.` template; discovery uses two `Different from` clauses correctly because it has two siblings). OQ3 soften pattern consistent between review.md and clarify-critic.md — both shift from imperative "MUST/CRITICAL/REQUIRED" prose to declarative-behavioral phrasing while preserving exact-name/exact-value/cross-field-invariant prose semantics.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
