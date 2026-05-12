# Review: suppress-dismiss-rationale-leak-in-lifecycle-clarify-critic

## Stage 1: Spec Compliance

### Requirement 1: Extend schema with `dismissals` field
- **Expected**: A `dismissals:` line between `applied_fixes` and `status` in the schema block under "Required fields:", plus the field documented in the prose paragraph immediately after the schema.
- **Actual**: Line 112 of `skills/lifecycle/references/clarify-critic.md` contains `dismissals: <array of {finding_index, rationale} objects — one per Dismiss disposition>` between `applied_fixes` and `status: "ok"`. Prose on lines 118–120 documents the `{finding_index, rationale}` element shape, the zero-based `finding_index` linkage to `findings`, the empty-array convention when zero Dismiss dispositions, and the `len(dismissals) == dispositions.dismiss` invariant.
- **Verdict**: PASS
- **Notes**: Plan-authoritative grep `grep -A 15 "^Required fields:$" ... | grep -c "^dismissals:"` = 1. Prose grep `grep -A 30 "^Required fields:$" ... | grep -c "dismissals"` = 4 (≥3 required). The spec's literal `awk '/^Required fields:/,/^\`\`\`$/'` returned 0 — this is the awk-range defect the plan calls out under "Verification precedence"; the plan's grep is authoritative.

### Requirement 2: Rewrite dispositioning output contract
- **Expected**: Remove the "State the dismissal reason briefly." sentence from the Dismiss definition; add a "Dispositioning Output Contract" subsection with four clauses (sole output is YAML, verbatim write to events.log, user-facing scope limited to §4 Ask merge + silent Apply, Dismiss rationales only in `dismissals[].rationale`).
- **Actual**: `grep -c "State the dismissal reason briefly"` = 0 (removed). New `### Dispositioning Output Contract` subsection present at lines 81–88 inside `## Disposition Framework`. Four bullets cover: "sole output" (line 85), "verbatim" write to `lifecycle/{feature}/events.log` (line 86), user-facing scope restriction to §4 Ask-merge + silent Apply (line 87), `dismissals[].rationale` as the only home for Dismiss rationales (line 88).
- **Verdict**: PASS
- **Notes**: Plan-corrected awk range `/^## Disposition Framework/,/^## Ask-to-Q&A Merge Rule/` returns 1 subsection heading. Spec's `/^## [^D]/` boundary returned 0 — awk-range inclusive/exclusive defect noted in plan. All four `grep -cF`/`grep -cE` bullet checks return ≥1. Bullet 4's final sentence ("there is no prose surface in which a Dismiss rationale could appear") directly encodes the structural-enforcement design principle from spec §"Design Principle".

### Requirement 3: Preserve Ask-to-§4 merge path verbatim
- **Expected**: The Ask disposition paragraph and the Ask-to-Q&A Merge Rule section remain textually identical to their pre-change form.
- **Actual**: Line 75 retains "the fix is not for the orchestrator to decide unilaterally." (count = 1). Line 92 retains "Ask items from the critic are **not** presented as a blocking escalation separate from §4. They are folded into the §4 question list …" verbatim (count = 1).
- **Verdict**: PASS
- **Notes**: Both literal `grep -F` checks match exactly.

### Requirement 4: Narrow `applied_fixes` semantics; add Ask→Dismiss parallel
- **Expected**: Remove the unqualified "fixes from both initial Apply dispositions and self-resolution reclassifications" phrasing; explicitly scope Ask→Apply to `applied_fixes`; document Ask→Dismiss routing to `dismissals[].rationale`; contrast `dismissals` with `applied_fixes`.
- **Actual**: Line 122 reads: "…the resulting fix description is appended to `applied_fixes` (the `applied_fixes` array thus carries initial Apply dispositions and Ask→Apply self-resolution reclassifications). If self-resolution reclassifies an Ask item as Dismiss, `ask` decreases and `dismiss` increases; the resolved rationale lands in `dismissals[].rationale` (not in `applied_fixes`) because `dismissals` is the Dismiss-disposition counterpart to `applied_fixes`." Line 118 also states `dismissals` is the Dismiss-disposition counterpart.
- **Verdict**: PASS
- **Notes**: Old unqualified phrase `grep -cF ...` = 0. Ask→Apply scoping regex = 1. `dismissals[].rationale` present (count = 2). Field-contrast regex `dismissals.{0,60}applied_fixes|applied_fixes.{0,60}dismissals` = 3 matches. All four R4 sub-acceptance checks pass.

### Requirement 5: Extend YAML example with Dismiss scenarios
- **Expected**: YAML example demonstrates both an initial Dismiss and an Ask→Dismiss reclassification; `dispositions.dismiss` equals `len(dismissals)` = 2; distinguishing comments mark the two cases.
- **Actual**: Lines 141–145 show `dismissals:` with two entries. Entry 1 (`finding_index: 1`) has inline comment "# initial Dismiss disposition — source material explicitly distinguishes…". Entry 2 (`finding_index: 3`) has inline comment "# Ask→Dismiss self-resolution reclassification — resolved against a documented project convention". Line 137 shows `dismiss: 2`, consistent with `len(dismissals) = 2`.
- **Verdict**: PASS
- **Notes**: `finding_index` count = 2, `dismiss: 2` matches, both "initial" and "reclassif" substrings present inside the YAML block.

### Requirement 6: Extend Failure Handling with `dismissals: []`
- **Expected**: Failure-path event payload includes `dismissals` alongside the existing empty `findings` and `applied_fixes` arrays.
- **Actual**: Line 153: "Write a `clarify_critic` event with `status: \"failed\"` and empty `findings`, `applied_fixes`, `dismissals`, and zero counts in `dispositions`."
- **Verdict**: PASS
- **Notes**: Failure-handling regex returns 1 match. Shape consistency between success and failure paths is preserved.

### Requirement 7: Add Constraints-table row for Dismiss-rationale routing
- **Expected**: One new row in the `| Thought | Reality |` table; Reality cell names both `dismissals` and `events.log`, with `dismissals` appearing before `events.log`.
- **Actual**: Line 167: `| "Surface Dismiss rationales to the user so they can see the critic's work" | Dismiss rationales go to the \`dismissals\` array in \`events.log\` only; the user-facing response surface is reserved for §4 Ask merge and silent Apply confidence revisions. |`
- **Verdict**: PASS
- **Notes**: Plan-corrected regex `^\|.*[Dd]ismiss.*\|.*dismissals.*events\.log` returns 1 match. `dismissals` precedes `events.log` in the Reality cell. Row cross-references the same scope constraint articulated in the Dispositioning Output Contract — deliberate redundancy between Disposition Framework and Constraints table for discoverability.

### Requirement 8: Downstream consumer audit (no broken consumers)
- **Expected**: No file outside this ticket's lifecycle directory, the epic research directory, other features' lifecycle artifacts, and the two `clarify*.md` references themselves consumes the `clarify_critic` schema in a way broken by the additive `dismissals` field.
- **Actual**: The spec's `grep -rn "clarify_critic" …` audit (with the plan's corrected exclusion filters including `requirements/` and `lifecycle/`, and the `:` line-anchor fix) returns 0 unexcluded matches.
- **Verdict**: PASS
- **Notes**: Additive schema extension; forward-only per Non-Requirements.

### Requirement 9: No structural change to `clarify.md`
- **Expected**: `skills/lifecycle/references/clarify.md` §3a is untouched across the 6 implementation commits.
- **Actual**: `git log HEAD~6..HEAD -- skills/lifecycle/references/clarify.md` returns no commits; `git diff HEAD~6 HEAD -- skills/lifecycle/references/clarify.md` produces no output.
- **Verdict**: PASS
- **Notes**: Delegation-only posture preserved as required by spec §"Changes to Existing Behavior" UNCHANGED list.

## Requirements Drift

**State**: none
**Findings**:
- None. The change is a structural-output-contract tightening of a single lifecycle skill reference file. It reinforces the project.md principles "Complexity: Must earn its place by solving a real problem that exists now. When in doubt, the simpler solution is correct." (the fix replaces a free-form prose channel with a structured YAML artifact) and "Handoff readiness" / spec clarity (removing user-facing noise that obscures decision signal). No new behaviors, capabilities, or scope boundaries are introduced. `events.log` append-only JSONL and orchestrator write-ownership — both codified in `requirements/pipeline.md` per Technical Constraints — remain unchanged.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: Consistent with existing patterns. `dismissals` (plural) mirrors `findings` and `applied_fixes`. Element shape `{finding_index, rationale}` follows the spec's stated rationale (finding_index over finding-prose avoids duplication with `findings[i]`). Schema-descriptor line style (`<array of ... — one per ...>`) matches the sibling `findings` and `applied_fixes` descriptors exactly.
- **Error handling**: Failure-path shape consistency is preserved — line 153 adds `dismissals` to the same empty-arrays enumeration as `findings` and `applied_fixes`. Both success (`dismissals: []` on zero Dismiss dispositions, per line 120) and failure paths emit the field, so downstream parsers never encounter a "key missing" vs "key-present-but-empty" bifurcation. Invariant `len(dismissals) == dispositions.dismiss` is textual-only (documented as non-requirement in spec — no programmatic validator in scope). Edge cases (Ask→Dismiss reclassification, zero dispositions, critic failure) are covered in both spec "Edge Cases" and the file's own prose + example.
- **Test coverage**: The plan's Verification Strategy consists of: (a) per-task grep acceptance checks (all self-sealing — each returns a specific integer count gate), (b) spec-level end-to-end re-run of acceptance greps (exercised here and all pass with plan-corrected variants), (c) manual `/lifecycle` run against a small backlog item to inspect real `events.log` output (exercisable but not performed as part of this review), (d) regression sweep over the next several lifecycle features. The self-sealing grep acceptance is the strongest testable layer; items (c)–(d) are behavioral checks deferred to real use, appropriate given the change is doc-only. The plan explicitly corrects several spec greps with regex-range defects (awk inclusive/exclusive boundary behavior, pipe escaping in alternation, order sensitivity) and marks the plan's grep authoritative — this review follows that precedence and all plan-corrected greps pass.
- **Pattern consistency**: Follows existing clarify-critic.md patterns faithfully. (1) Schema block indentation and descriptor style match pre-existing fields. (2) YAML example formatting (top-level `- ts:`, 2-space indent, quoted prose values, same field order as schema) matches the original example's structure. (3) Failure Handling enumeration pattern is extended in-place rather than restructured. (4) Constraints table row uses the existing "Thought (quoted misconception) | Reality (plain-prose correction)" format. (5) Dispositioning Output Contract lands as a `###` subsection under `## Disposition Framework` — parallel in depth to the neighbouring Ask-to-Q&A Merge Rule — preserving the section hierarchy. Positive-framing prose (structural contract) over negative instruction is consistent with the stated Design Principle.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
