# Review: collapse-byte-identical-refine-references-files-orchestrator-reviewmd-specifymd-lifecycle-canonical

## Stage 1: Spec Compliance

### Requirement R1: Delete `skills/refine/references/orchestrator-review.md`
- **Expected**: `test ! -f skills/refine/references/orchestrator-review.md` exits 0.
- **Actual**: File absent from working tree; test exits 0.
- **Verdict**: PASS
- **Notes**: Deletion is staged in commit `ace0bd9`.

### Requirement R2: Delete `skills/refine/references/specify.md`
- **Expected**: `test ! -f skills/refine/references/specify.md` exits 0.
- **Actual**: File absent from working tree; test exits 0.
- **Verdict**: PASS
- **Notes**: Deletion is staged in commit `ace0bd9`.

### Requirement R3: Redirect refine SKILL.md Step 5 to lifecycle canonical
- **Expected**: `grep -c "Read \`\${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md\`" skills/refine/SKILL.md` returns 1; `grep -c "Read \`references/specify.md\`" skills/refine/SKILL.md` returns 0.
- **Actual**: Counts are 1 and 0 respectively (verified with `grep -F` and single-quoted literal patterns to avoid shell expansion of `${CLAUDE_SKILL_DIR}`). The new line at SKILL.md:156 reads ``Read `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` and follow it (its full protocol) with these adaptations:``.
- **Verdict**: PASS
- **Notes**: The implementer applied a small wording deviation from the literal spec substitution (`(§1–§4)` → `(its full protocol)`) by writing `follow it (its full protocol)` rather than the awkward `follow its full protocol (its full protocol)` that a literal substitution would have produced. The spec's intent is preserved (scope clause widened to cover `## Hard Gate`) and the spec's exact grep pattern still matches once. Secondary path count of `${CLAUDE_SKILL_DIR}/../lifecycle/references/specify.md` across SKILL.md is 2 (one for Step 5 invocation at L156, one inside the R5 Hard Gate row at L163), matching the spec's secondary expectation.

### Requirement R4: Tighten §5 adaptation row (mitigation M2.1)
- **Expected**: `grep -F "Do NOT emit the \`phase_transition\` JSON template" skills/refine/SKILL.md` returns one match.
- **Actual**: Returns one match at L162: ``**§5 (Transition)**: Skip — /cortex-core:refine does not log phase transitions. Do NOT emit the `phase_transition` JSON template embedded in this section, and do NOT run `/cortex-core:commit` from within /cortex-core:refine; the caller (/cortex-core:lifecycle) owns phase-transition logging and commit-artifacts.``
- **Verdict**: PASS
- **Notes**: Wording matches spec verbatim.

### Requirement R5: Add `## Hard Gate` adaptation row (mitigation M2.2)
- **Expected**: `grep -F "Hard Gate" skills/refine/SKILL.md | grep -F "Applies"` returns at least one match.
- **Actual**: Returns one match at L163. The bullet acknowledges the §4 (User Approval) interaction surfaced in critical review, beyond the spec's literal "carries through unchanged" wording — a hardening, not a deviation downward.
- **Verdict**: PASS
- **Notes**: Bullet uses ``**`## Hard Gate`**:`` form rather than the existing `**§N (Name)**:` shape — this is the established way to address `##`-headings in adaptation lists per plan Task 1, and the deviation is documented in the plan as intentional (preserves the heading's literal `##` for traceability).

### Requirement R6: Mirror trees pruned via build-plugin
- **Expected**: `test ! -f plugins/cortex-core/skills/refine/references/orchestrator-review.md` and `test ! -f plugins/cortex-core/skills/refine/references/specify.md` exit 0.
- **Actual**: Both files absent; both tests exit 0.
- **Verdict**: PASS
- **Notes**: Mirror prune via rsync `-a --delete` worked correctly. Mirror SKILL.md is byte-identical to canonical (verified with `diff -q`).

### Requirement R7: Dual-source parity test passes
- **Expected**: `python -m pytest tests/test_dual_source_reference_parity.py` exits 0.
- **Actual**: 35 tests passed in 0.03s, exit 0 (run via `.venv/bin/pytest`).
- **Verdict**: PASS
- **Notes**: Parametrized count dropped by 2 vs pre-change baseline (refine's two deleted canonical files automatically dropped from the glob).

### Requirement R8a: Static cross-skill resolution check
- **Expected**: `test -r skills/lifecycle/references/specify.md && test -r skills/lifecycle/references/orchestrator-review.md` exits 0.
- **Actual**: Both files exist and are readable; test exits 0.
- **Verdict**: PASS
- **Notes**: Plan-level synthetic substitution check (Task 4 hardening over R8a) also passes — the regex `${CLAUDE_SKILL_DIR}/<rest>` extracts `../lifecycle/references/specify.md` and the substituted path `skills/refine/../lifecycle/references/specify.md` resolves to a readable file. This was confirmed via the python one-liner from Task 4 returning exit 0 with no bad paths.

### Requirement R8b: Post-merge manual smoke
- **Expected**: Implementer attests in PR description (or follow-up comment) that the next post-merge `/cortex-core:refine` session produces a complete spec.md without resolution errors.
- **Actual**: Spec explicitly defers this to post-merge operator attestation. Pre-merge verification is impossible per spec rationale (synthetic fixtures cannot satisfy the orchestrator-review skip rule under refine standalone).
- **Verdict**: PARTIAL (deferred per spec)
- **Notes**: This is a deferred runtime check, not a pre-merge gate. Plan-level Task 4 added a synthetic substitution check that closes the path-resolution coverage gap for claim (a) pre-merge; R8b's residual role is post-merge confirmation of the transitive orchestrator-review hop (claim (b)). Verification Strategy gate 8 strengthens R8b's evidence requirements (must include either the literal `## Hard Gate` in the produced spec OR an `orchestrator_review` event with `phase: "specify"` in events.log). Cannot be PASS at this point per spec acceptance criterion.

### Requirement R9: Pre-commit drift hook does not block
- **Expected**: `git commit` succeeds without "dual-source drift detected" stderr; `git diff --quiet plugins/cortex-core/skills/refine/` exits 0.
- **Actual**: Commit `ace0bd9` exists in HEAD with all 13 expected paths; `git diff --quiet plugins/cortex-core/skills/refine/` exits 0 (no drift remaining).
- **Verdict**: PASS
- **Notes**: Pre-commit hook Phase 4 did not block the commit; mirror tree is in sync with canonical.

### Requirement R10: Source-dir-scoped grep gate
- **Expected**: `git grep -F "skills/refine/references/orchestrator-review.md" -- 'skills/*/SKILL.md' 'skills/*/references/*.md' 'hooks/' 'claude/' 'plugins/' 'bin/' 'tests/' 'docs/' '*.justfile'` returns no matches; same form for `skills/refine/references/specify.md`.
- **Actual**: Both grep commands returned no matches.
- **Verdict**: PASS
- **Notes**: Live source dirs are clean. `backlog/`, `research/`, `lifecycle/`, `CHANGELOG.md` intentionally out of pathspec per spec.

### Requirement R11: No remaining references in mirror trees
- **Expected**: `git grep -F "<path>" -- 'plugins/'` returns no matches for both deleted paths.
- **Actual**: Both grep commands returned no matches in `plugins/`.
- **Verdict**: PASS
- **Notes**: rsync `--delete` correctly pruned the mirror tree.

## Requirements Drift
**State**: none
**Findings**:
- The new `${CLAUDE_SKILL_DIR}/..` cross-skill walk pattern is consistent with the project's "Maintainability through simplicity" attribute — it consolidates two near-byte-identical canonical files into one, eliminating ~346 lines of static-corpus cost and removing a documented drift surface (parent epic 172 audit found 1-line drift). This is iterative trimming, not new architectural complexity. The pattern itself is documented in the SKILL.md adaptation list and in `requirements/project.md` "Architectural Constraints" implicitly via the existing dual-source enforcement model.
- R8b's post-merge operator-attested verification appears to defer a "Handoff readiness" gate, but this is a deliberate spec decision with documented rationale (synthetic fixtures cannot reliably exercise the orchestrator-review skip rule under refine standalone because `lifecycle_start` is not emitted; tier evaluation is undefined). The plan-level Task 4 synthetic substitution check closes the path-resolution gap pre-merge for claim (a), and R8b is now strengthened to require objective grep/log evidence beyond the bare "no error" signal. Net handoff posture is not weakened relative to the project's quality attribute — the deferral is bounded and evidence-bearing.
**Update needed**: None

## Stage 2: Code Quality

- **Naming conventions**: The new R5 Hard Gate row uses ``**`## Hard Gate`**:`` form rather than the existing `**§N (Name)**:` pattern. This deviation is intentional and documented in plan Task 1 ("R5's row addresses a `##`-level heading rather than a §-numbered section; the divergent backtick-wrapped form is intentional"). It preserves the heading's literal `##` so a future reader can match the row to its source. Stylistically consistent with how adaptation lists address `##`-level headings — acceptable.
- **Error handling**: N/A — this is a docs/SKILL.md change, not behavior. No new control flow or error paths introduced.
- **Test coverage**: Plan Task 4's synthetic substitution check (a plan-level hardening over R8a, not in the spec) was actually run and passes — verified the python one-liner against the post-commit working tree returns exit 0 with the path set `{'../lifecycle/references/specify.md'}` and an empty bad-paths list. R7 dual-source parity test passes (35/35). R8b is the only verification deferred, and that deferral is explicit in the spec.
- **Pattern consistency**: The `${CLAUDE_SKILL_DIR}/..` cross-skill walk pattern is well-formed: substitution applies at refine's invocation time per the corrected critical-review semantics in spec.md "Technical Constraints"; the trailing `..` walks up to the plugin's `skills/` parent before descending into lifecycle's references; resolves correctly under both repo-development and end-user plugin-cache layouts. The pattern is unambiguously documented in SKILL.md Step 5 and in spec.md edge cases. Adjacent intra-skill `references/X.md` reads (lines 38, 65, 86 of SKILL.md) intentionally remain bare-relative — the asymmetry is documented as a deliberate trade-off, not an oversight.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
