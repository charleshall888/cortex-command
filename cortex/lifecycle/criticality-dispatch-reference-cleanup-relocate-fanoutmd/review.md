# Review: criticality-dispatch-reference-cleanup-relocate-fanoutmd

Reviewed against `spec.md` (17 requirements, 4 phases). All acceptance commands below were
executed, not eyeballed. Targeted test suites (`test_resolve_model`, `test_research_fanout_matrix`,
`test_lifecycle_references_resolve`, `test_dual_source_reference_parity`) run green: **92 passed**.
`just build-plugin` produces no `plugins/` diff; `cortex-check-parity`, `cortex-check-skill-path
--audit`, `cortex-check-bare-python-import --audit`, `cortex-check-contract --audit` all exit 0.

## Stage 1: Spec Compliance

### Requirement 1: Pure lifecycle-matrix module, no dispatch.py import/modification
- **Expected**: New stdlib-only `(role, criticality) → model` module; no `import ...dispatch`; `dispatch.py` not in the diff.
- **Actual**: `cortex_command/lifecycle/resolve_model_cli.py` is stdlib-only (argparse/sys/typing). `grep -nE "import .*dispatch|from .*dispatch"` returns nothing. Across all #334 commits, `cortex_command/pipeline/dispatch.py` does not appear in the changed-files set.
- **Verdict**: PASS
- **Notes**: The structural-unmergeability rationale (orchestrator-fix `sonnet|sonnet|sonnet|opus` row) is captured in the module docstring + a comment.

### Requirement 2: Verb contract (`--criticality` optional, role-conditional)
- **Expected**: `--role` required; `--criticality` optional; synthesizer = opus with/without criticality; tier-keyed role with criticality omitted exits nonzero.
- **Actual**: Live: `--role synthesizer` → `opus` (exit 0); `--role synthesizer --criticality low` → `opus` (exit 0); `--role review` (no criticality) → exit 2. argparse registers `--role required=True`, `--criticality required=False, default=None`.
- **Verdict**: PASS

### Requirement 3: Full role-threshold lattice pinned to today's values
- **Expected**: Every value-bearing cell reproduced exactly (review/builder high+critical=opus, orchestrator-fix critical=opus / high=sonnet, competing-plan critical=sonnet, synthesizer=opus).
- **Actual**: `test_table_coverage` parametrizes all 13 cells; `_LIFECYCLE_MATRIX` matches the spec rows verbatim. Discriminator (`orchestrator-fix@high=sonnet` vs `review@high=opus`) and the three critical=opus cells asserted live and in tests.
- **Verdict**: PASS

### Requirement 4: Fail loud on unknown input; never default
- **Expected**: unknown role / unknown criticality / tier-keyed-missing-criticality / undefined cell → exit 2, stderr names valid values, nothing on stdout.
- **Actual**: Live — `--role bogus --criticality high` exit 2; `--role competing-plan --criticality low` (undefined cell) exit 2; `--role review` (missing) exit 2. `test_unknown_role_exits_2_and_lists_valid_roles` asserts stderr names all five roles and `out == ""`. No safe default anywhere.
- **Verdict**: PASS

### Requirement 5: Independent golden-anchor test (frozen literal after Phase 1 parse)
- **Expected**: Phase-1 parsed the live `model-selection.md`; Phase-3 froze parsed values into the test as a literal; test survives deletion; no remaining `model-selection.md` reference in the test.
- **Actual**: `_expected_golden_matrix()` is a frozen literal transcribed from spec Req 3 (docstring explicitly states it is NOT copied from the module's `_LIFECYCLE_MATRIX`, avoiding circular module==module). `grep -c "model-selection.md" tests/test_resolve_model.py` = 0. Test passes. The freeze-to-literal in Task 6 preserved the guarantee; the module was renamed/the asset removed without breaking the anchor.
- **Verdict**: PASS
- **Notes**: The golden test additionally encodes undefined cells as `None` and asserts the module exits 2 for them — a genuinely discriminating check, not a tautology.

### Requirement 6: Verb wired (parity) within Phase 1
- **Expected**: `[project.scripts]` entry; executable dual-channel binstub; Phase-1 test contains the literal console name; no W003 orphan; no parity-exceptions/events-registry row.
- **Actual**: `pyproject.toml:73` `cortex-resolve-model = "cortex_command.lifecycle.resolve_model_cli:main"`. `bin/cortex-resolve-model` is executable, four-branch dual-channel wrapper. `test_cortex_resolve_model_binstub_smoke` subprocess-invokes the binstub (literal console name present). `cortex-check-parity` exits 0. `grep -c "cortex-resolve-model"` in `bin/.parity-exceptions.md` and `bin/.events-registry.md` = 0.
- **Verdict**: PASS

### Requirement 7: Value-bearing dispatch sites resolve via the verb; exact prior directive gone
- **Expected**: All 6 sites (review.md, orchestrator-review.md, implement.md, plan.md×2, critical-review/SKILL.md) run the verb; exact prior directive strings absent.
- **Actual**: 6 `cortex-resolve-model --role` invocations across the 5 files (plan.md has 2: competing-plan tier-keyed §1b + synthesizer §1b.d). Exact-string greps for the prior review.md and orchestrator-review.md directives = 0. Tier-keyed sites pass `--criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)"`; the two synthesizer sites run `--role synthesizer` with NO criticality read.
- **Verdict**: PASS

### Requirement 8: Hard-fail handler, not a guess
- **Expected**: Each migrated site halts/escalates on nonzero verb exit (and corrupt/absent state for tier-keyed); synthesizer sites have no criticality read.
- **Actual**: Every site contains an explicit "On nonzero exit ... halt and escalate rather than guessing or substituting a model" instruction. `grep -Fc "cortex-lifecycle-state" skills/critical-review/SKILL.md` = 0 — confirming no criticality read was added for the synthesizer dispatch (the standalone-critical-review regression fix is intact).
- **Verdict**: PASS

### Requirement 9: Migrated prose is lint-clean
- **Expected**: L201 / SP001-SP002 / E101-E103 pass on migrated prose.
- **Actual**: `cortex-check-bare-python-import --audit`, `cortex-check-skill-path --audit`, `cortex-check-contract --audit` all exit 0. No resolve-model contract violations. `--criticality` absence at synthesizer sites is contract-clean (optional flag).
- **Verdict**: PASS

### Requirement 10: `model-selection.md` deleted only after golden values frozen
- **Expected**: Canonical + mirror deleted; golden test still passes with no `model-selection.md` reference.
- **Actual**: `test ! -f skills/lifecycle/assets/model-selection.md` and `... plugins/cortex-core/...` both true. Golden test passes; `grep -c "model-selection.md"` in the test = 0.
- **Verdict**: PASS

### Requirement 11: Durable rationale relocated to sdk.md; stale numbers deleted; bullets verified
- **Expected**: Four durable bullets + the two profile facts present; all version-pinned tokens absent; dated evidence pointer preserved; no new ADR.
- **Actual**: `docs/internals/sdk.md:149-152` carries all four bullets (parallel→sonnet, exploration→haiku, complex+low/med→sonnet "over-engineering", "Reviews follow criticality"). Line 154 carries both profile facts ("128K max output token", "Explore agent uses Haiku"). `grep -ciE "SWE-bench|GPQA|/MTok|per MTok|Sonnet 4\.6|< ?2%"` = 0. Line 156 preserves the dated-evidence pointer to `cortex/research/opus-4-7-harness-adaptation/`. No new ADR.
- **Verdict**: PASS

### Requirement 12: sdk.md points at executable sources; no restated table
- **Expected**: References `cortex-resolve-model` and `resolve_model()`/`_MODEL_MATRIX` as authoritative.
- **Actual**: `sdk.md:144` names `cortex-resolve-model` as the lifecycle-matrix authority ("do not restate its table here; the golden-anchor test ... is the parity anchor"); `sdk.md:145` names `resolve_model()`/`_MODEL_MATRIX` for the pipeline matrix. Greps ≥1 each.
- **Verdict**: PASS

### Requirement 13: criticality-matrix.md — model column removed, behavior matrix kept, narration deleted
- **Expected**: "Model selection" column removed, table well-formed, line-24 narration deleted, verb pointer without the capital-M phrase.
- **Actual**: `grep -c "Model selection"` = 0; `grep -c "023, 024, 025"` = 0. Behavior matrix (header/separator/4 data rows, lines 17-22) is well-formed — uniform 5 pipes per row. Line 24 replaced with a lowercase "Per-role model resolution ... owned by the `cortex-resolve-model` verb" pointer.
- **Verdict**: PASS

### Requirement 14: fanout.md relocated to research/references/
- **Expected**: `test -f skills/research/references/fanout.md` AND `test ! -f skills/lifecycle/references/fanout.md`.
- **Actual**: Both true — file moved.
- **Verdict**: PASS

### Requirement 15: All fanout citers repointed across every path form; no dangling reference
- **Expected (conjunction of 5)**: (1) `test_research_fanout_matrix.py` passes; (2) `test_lifecycle_references_resolve.py` passes; (3) `cortex-check-skill-path --audit` exit 0; (4) `grep -rl "fanout.md" skills/lifecycle` returns nothing; (5) no `lifecycle/references/fanout.md` substring anywhere in scope.
- **Actual**: All 5 conditions PASS. Conditions 1, 2 — `test_research_fanout_matrix.py` and `test_lifecycle_references_resolve.py` both green (10 passed). Condition 3 — `cortex-check-skill-path --audit` exits 0. Condition 5 — `grep -rl "lifecycle/references/fanout.md" skills docs tests` returns nothing. **Condition 4 now PASSES** (cycle-1 failure resolved by fix commit `8f16faf5`): `grep -rl "fanout.md" skills/lifecycle` returns nothing. `criticality-matrix.md:26` was reworded from the bare-noun "see fanout.md" to "the tier × criticality fan-out matrix owned by the `/cortex-core:research` skill (the count-source-of-truth and dispatch protocol)" — dropping the `fanout.md` token entirely and repointing readers at the owning skill. No lifecycle file names `fanout.md` in any form.
- **Verdict**: PASS
- **Notes (cycle 2)**: Re-verified independently. The reword is prose beneath the Behavior Matrix table (not a table cell), so the matrix at lines 17–22 remains well-formed (uniform 5 pipes/row, model column still removed at line 24, 023/024/025 narration still gone). The new `/cortex-core:research` pointer is lint-clean — it landed through the pre-commit contract checker, and `cortex-check-skill-path --audit` exits 0. No regression to Req 13.

### Requirement 16: Mirrors regenerated and committed with canonical
- **Expected**: `just build-plugin` yields no `plugins/` diff; `test_dual_source_reference_parity.py` passes.
- **Actual**: `just build-plugin` produces no `git diff` under `plugins/`; dual-source parity test passes.
- **Verdict**: PASS

### Requirement 17: Whole suite green
- **Expected**: `just test` exits 0 after Phase 4.
- **Actual**: All four targeted suites pass (92 passed). Per the implementer note (full `just test` stated green); targeted re-run confirms the in-scope tests. No failures observed.
- **Verdict**: PASS
- **Notes**: Only the targeted suites were re-run here; the full `just test` pass is trusted per the review instructions.

## Stage 2: Code Quality
- **Naming conventions**: Consistent with the resolver-verb family — module `resolve_model_cli.py` mirrors `state_cli.py`; `main(argv)` entry point; `_LIFECYCLE_MATRIX` / `_CRITICALITY_INDEPENDENT` / `_ROLE_CHOICES` private constants; binstub `cortex-resolve-model` matches the console-name convention.
- **Error handling**: Fail-loud exit 2 with stderr naming valid values at every rejection path (unknown role via argparse choices, missing criticality, undefined cell). No silent default; the "a default would mask a typo" rationale is documented inline. The defensive `row is None` branch is unreachable-by-choices but harmless.
- **Test coverage**: Golden anchor is genuinely independent — `_expected_golden_matrix()` is transcribed from the spec, not copied from `_LIFECYCLE_MATRIX` (docstring states this explicitly; a same-module copy would degrade to circular module==module). Undefined cells encoded as `None` and asserted to exit 2 (negative control). The four-row presence assertion prevents a zero-match pass. Subprocess binstub smoke provides the parity-wiring signal. No casefold/case-insensitive ambiguity — argparse `choices` enforce exact lowercase tokens, and assertions compare exact `model + "\n"`; a case guard is unnecessary given the closed choice set.
- **Pattern consistency**: Binstub follows the dual-channel template (force-source → wheel-probe → working-tree pyproject fallback → exit-2 remediation), matching the established family. fanout repoints honor ADR-0009: research SKILL.md uses own-dir `${CLAUDE_SKILL_DIR}/references/fanout.md`, discovery uses body-resolved `${CLAUDE_SKILL_DIR}/../research/references/fanout.md` propagated into reference files, docs use a relative markdown link. The `NON_FEATURE_SUBDIRS` side-fix (adding `"assets"` alongside `"references"`) is sound — it extends the existing non-feature-subdir exclusion so prose abbreviating `lifecycle/assets/<file>` is not misread as a broken feature-directory citation; symmetric with the pre-existing `references` entry and consistent with its documented rationale.

## Requirements Drift
**State**: none
**Findings**:
- None. `cortex/requirements/project.md` makes no reference to `model-selection.md`, `fanout.md`, `cortex-resolve-model`, `criticality-matrix`, or `sdk.md`; the single-sourcing aligns with the project's stated "deterministic behavior belongs in the CLI" principle, and the change correctly introduces no MUST escalation and no new ADR (reversible refactor).
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 2, "issues": [], "requirements_drift": "none"}
```
