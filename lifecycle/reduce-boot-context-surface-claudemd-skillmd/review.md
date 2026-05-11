# Review: reduce-boot-context-surface-claudemd-skillmd

## Stage 1: Spec Compliance

### Requirement R1: Baseline measurement
- **Expected**: `baseline.md` exists with CLAUDE.md line count, per-skill desc+wtu char counts (13 skills), sum, body line counts, `/doctor` notes; `grep -c '^|' baseline.md >= 13`.
- **Actual**: `baseline.md` exists; `grep -c '^|' = 22` (>=13). Records CLAUDE.md pre-change 67 lines / 7867 bytes; total desc+wtu 7228; body line counts for all 13 skills; `/doctor` tooling gap noted ("interactive and cannot be invoked non-interactively"). Acknowledges historical reconstruction methodology (baseline retrieved via `git show <commit>^:...`).
- **Verdict**: PASS
- **Notes**: Reconstruction-after-the-fact for body counts is a minor caveat but the spec did not require pre-change capture timing — only that the file exists and records the metrics.

### Requirement R2: Test-fixture expansion prerequisite
- **Expected**: Fixture covers 13 skills; each has >=3 phrases; landed in a separate commit before R5; `pytest tests/test_skill_descriptions.py` exits 0.
- **Actual**: Fixture has top-level `skills:` mapping with all 13 skills. Min `must_contain` length = 3. Phrase types comply (slash commands, multi-word imperatives, path tokens under `must_contain_paths`). `pytest tests/test_skill_descriptions.py` passes.
- **Verdict**: PASS
- **Notes**: Fixture structure changed (added `skills:` parent key) but spec did not constrain that detail; tests handle the structure. Spec called out follow-up backlog #197 for independent corpus, which exists.

### Requirement R3: CLAUDE.md policy extraction
- **Expected**: CLAUDE.md <=60 lines; `docs/policies.md` exists; OQ6 pointer line present; 100-line-rule absent; OQ3 retained.
- **Actual**: `wc -l CLAUDE.md = 60`; `docs/policies.md` exists with OQ6 content; `grep -c "Tone/voice policy: see docs/policies.md" = 1`; `grep -c "CLAUDE.md is capped at 100 lines" = 0`; `grep -c "## MUST-escalation policy" = 1`. OQ3 (lines 51-59) retained.
- **Verdict**: PASS

### Requirement R4: CLAUDE.md L42 frontmatter convention update
- **Expected**: L42 mentions `when_to_use:`; `grep -c "when_to_use" CLAUDE.md >= 1`.
- **Actual**: Line 42 reads "New skills go in `skills/` with `name` and `description` frontmatter; `when_to_use:` is optional and concatenated to `description:` for routing." `grep -c "when_to_use" = 1`.
- **Verdict**: PASS

### Requirement R5: Description and `when_to_use:` compression (non-uniform caps)
- **Expected**: Routing-pressure cluster (critical-review, lifecycle, discovery, refine, dev, research) ≤1000 chars; others ≤400 chars (requirements stricter per R6); `pytest tests/test_skill_descriptions.py` exits 0.
- **Actual**: `just measure-l1-surface` reports: critical-review 785, lifecycle 890, discovery 966, refine 630, dev 285, research 378 (all ≤1000); backlog 319, commit 208, diagnose 294, morning-review 320, overnight 314, pr 237, requirements 151 (all ≤400). Tests pass.
- **Verdict**: PASS
- **Notes**: `post-trim-measurement.md` describes the caps using a different framing ("R6 caps", "300-char cap for heavyweight exempt") that doesn't match the spec's R5 categorization, but all values still satisfy the spec's binding R5/R6 caps.

### Requirement R6: requirements SKILL.md description trim
- **Expected**: `description:` ≤200 chars.
- **Actual**: 149 chars: "Use /cortex-core:requirements to gather requirements or define project scope. disable-model-invocation:true — invoked only by explicit slash command."
- **Verdict**: PASS

### Requirement R7: SKILL.md body trimming (Level 2 reduction)
- **Expected**: diagnose, overnight, critical-review, lifecycle SKILL.md bodies ≤250 lines; references/ dirs exist; `pytest tests/test_skill_size_budget.py` passes; no new size-budget-exception markers.
- **Actual**: diagnose 112, overnight 133, critical-review 113, lifecycle 172 — all ≤250. All four `references/` directories exist with extracted files. `pytest tests/test_skill_size_budget.py` passes (5 passed). Cross-references via `${CLAUDE_SKILL_DIR}/references/<name>.md` resolve to existing files.
- **Verdict**: PASS

### Requirement R8: L1 reduction success criterion
- **Expected**: `post-trim-measurement.md` records post-trim measurements alongside baseline; per-file caps from R3/R5/R6/R7 hold.
- **Actual**: `post-trim-measurement.md` records CLAUDE.md 67→60 lines (-7), aggregate L1 7228→5777 bytes (-20.1%), per-skill bytes/caps, body line counts for the 4 trimmed skills (1632→530, -67.5%), `/doctor` gap, plugin-mirror parity result.
- **Verdict**: PASS
- **Notes**: The "Pass?" column applies non-spec caps (300/200) to routing-pressure cluster skills, mislabeling `research` as MISS. The actual spec caps (R5: ≤1000 for routing-pressure cluster) are all satisfied; this is a doc-classification inaccuracy in the measurement file, not a violation of R8's binding acceptance criterion (which is just "file exists with measurements").

### Requirement R9: Skill-routing non-regression
- **Expected**: `pytest tests/test_skill_descriptions.py` passes; new `tests/test_skill_routing_disambiguation.py` exists and passes; lifecycle path tokens (`skills/`, `hooks/`, `claude/hooks/`, `bin/cortex-`, `cortex_command/common.py`) asserted via `must_contain_paths` key.
- **Actual**: Test exists, has explicit `must_contain_paths` handling and asserts presence in lifecycle SKILL.md. 23 tests in the disambiguation suite pass. Fixture has `must_contain_paths:` block under lifecycle listing all five required path tokens.
- **Verdict**: PASS

### Requirement R10: Plugin-mirror regeneration
- **Expected**: `diff -r --brief skills plugins/cortex-core/skills` shows only morning-review, overnight exclusions; `pytest tests/test_plugin_mirror_parity.py` passes.
- **Actual**: `diff` output: "Only in skills: morning-review" / "Only in skills: overnight" — exactly the two expected exclusions. `pytest tests/test_plugin_mirror_parity.py` passes (3 tests). Documented in post-trim-measurement.md with both task-literal-awk and intent-correct-awk variants.
- **Verdict**: PASS

### Requirement R11: Byte-count utility
- **Expected**: `just measure-l1-surface` exits 0; stdout contains ≥14 lines matching `^[a-z-]+\s+\d+$`; script at `bin/cortex-measure-l1-surface`; `bin/cortex-check-parity` exits 0.
- **Actual**: `just measure-l1-surface` outputs 14 lines matching the pattern (13 skill rows + total). `bin/cortex-measure-l1-surface` exists, executable, referenced in `justfile` line 352-353. `bin/cortex-check-parity` exits 0.
- **Verdict**: PASS

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

## Stage 2: Code Quality
- **Naming conventions**: New script `bin/cortex-measure-l1-surface` follows the `cortex-*` prefix convention. Reference files use kebab-case (`a-to-b-downgrade-rubric.md`, `phase-1-investigation.md`) consistent with existing references/ pattern. Justfile recipe `measure-l1-surface` matches script name suffix. No naming drift.
- **Error handling**: The measure-l1-surface script is small and prints byte counts deterministically; failures propagate via non-zero exit. Test fixtures handle missing `must_contain_paths` keys gracefully (asserts presence before indexing). Plugin-mirror parity test does not regress.
- **Test coverage**: All requirement-specified verifications were run: `test_skill_descriptions.py` (2 passed), `test_skill_routing_disambiguation.py` (23 passed), `test_skill_size_budget.py` (5 passed), `test_measure_l1_surface.py` (4 passed), `test_plugin_mirror_parity.py` (3 passed). 37 total passed in 0.47s. Cross-references in trimmed SKILL.md bodies resolve to existing extracted reference files.
- **Pattern consistency**: References-extraction pattern follows the established `skills/lifecycle/references/` precedent with `${CLAUDE_SKILL_DIR}/references/<topic>.md` substitution. New script wired via justfile recipe to satisfy SKILL.md-to-bin parity. Dual-source mirror preserves the `disable-model-invocation:true` filter as designed. CLAUDE.md update follows the project's "rules-only deployment" convention (tone policy extracted to docs/policies.md rather than removed).

Minor observations (non-blocking):
- `post-trim-measurement.md` "Caps from spec R6" mis-cites the spec — caps are split across R3/R5/R6 with the routing-pressure cluster cap (≤1000) from R5, not R6. The mislabeling falsely flags `research` as MISS when it is well within its R5 cap. This is a doc-internal inconsistency in the measurement artifact, not a violation of R8 (which only requires the file exist with measurements).
- `baseline.md` is a historical reconstruction post-some-tasks-landing rather than a pre-change snapshot, but it does capture/justify the baseline numbers via `git show` against the right commits.

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
