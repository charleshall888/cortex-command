# Review: reconcile-lifecycleconfigmd-asset-vs-the-cortex

## Stage 1: Spec Compliance

### Requirement 1: Asset carries the `backlog:` block
- **Expected**: The 11-line `backlog:` block (comment header + `backend: cortex-backlog` default + commented `github-issues`/`jira`/`none` alternatives + `instructions:` example) added verbatim to `skills/lifecycle/assets/lifecycle.config.md`. `grep -c '^backlog:'` = 1, `grep -c 'backend: cortex-backlog'` = 1, `grep -c 'instructions:'` = 1.
- **Actual**: `grep -c '^backlog:'` = 1, `grep -c 'backend: cortex-backlog'` = 1, `grep -c 'instructions:'` = 1. The block (asset lines 18–28) is byte-identical to the init template's block; it was inserted immediately after `synthesizer_overnight_enabled: false` (line 17) and before the closing `---`, exactly as the plan's Task 1 Context specified.
- **Verdict**: PASS
- **Notes**: The asset's body sentence "Copy this file to your project root…" (line 33) is preserved as the intended asset-only body difference, outside the gated frontmatter region.

### Requirement 2: Plugin mirror regenerated in the same commit
- **Expected**: `diff skills/lifecycle/assets/lifecycle.config.md plugins/cortex-core/skills/lifecycle/assets/lifecycle.config.md` exits 0; pre-commit dual-source drift hook passes.
- **Actual**: `diff` exits 0 (mirror byte-identical to canonical). `tests/test_dual_source_reference_parity.py` is green (the asset↔mirror gate), confirming the mirror was regenerated.
- **Verdict**: PASS
- **Notes**: The binding cross-file byte-identity check (asset frontmatter region == init-template frontmatter region) also exits 0: `python3 ... split(b'---',2)[1]` comparison returns 0. This is the non-tautological reconcile-target check, not just the rsync-copy mirror diff.

### Requirement 3: Frontmatter parity gate (asset↔init-template) — true byte compare
- **Expected**: `tests/test_lifecycle_config_parity.py` reads raw bytes, slices the region between the `---` delimiters, byte-compares the two regions; does NOT route through `_extract_frontmatter_text`; fails if the `backlog:` block is dropped from the asset.
- **Actual**: `_frontmatter_region(raw)` does `raw.split(b"---", 2)[1]` on raw bytes — no `splitlines()`/`"\n".join()` normalization, so it stays CRLF/trailing-newline sensitive. `test_frontmatter_byte_parity` asserts `_frontmatter_region(ASSET.read_bytes()) == _frontmatter_region(TEMPLATE.read_bytes())` via the pure `_assert_regions_equal` helper. `test_divergence_sentinel` mutates one region in memory and asserts the byte-compare raises — proving the gate fails on divergence (hence on a dropped `backlog:` block). `.venv/bin/pytest tests/test_lifecycle_config_parity.py -q` exits 0.
- **Verdict**: PASS
- **Notes**: Comparison is genuinely byte-level and bypasses the line-ending-normalizing production parser, per the spec's most load-bearing constraint.

### Requirement 4: Positive content assertion + sentinel-mutation self-test
- **Expected**: Test asserts the asset region is non-empty and carries the load-bearing option lines via a SHARED `_assert_options_present` helper used by BOTH the positive-content test and the convergent-loss sentinel; the convergent-loss sentinel asserts byte-parity still PASSES on the convergent mutation while the positive check fails. `grep -c 'def test_'` ≥ 2.
- **Actual**: `grep -c 'def test_'` = 4 (meets the plan's strengthened ≥ 4). `_assert_options_present` checks line-integrity substrings — `backend: cortex-backlog`, `# backend: github-issues`, `# backend: jira`, `# backend: none`, `# instructions:`, plus the documenting-comment lines `# Freeform prose hint` and `harden in #318` (closes the generic-`none`-substring and convergent-comment-loss holes). It is called by `test_asset_frontmatter_carries_options` (test 2) and `test_convergent_loss_sentinel` (test 4) — `grep -c '_assert_options_present'` = 3 (one def + two calls), so the sentinel exercises the production check rather than re-inlining. `test_convergent_loss_sentinel` deletes `# backend: github-issues` from both in-memory regions, then asserts (i) `_assert_options_present` raises AND (ii) `_assert_regions_equal` still PASSES on the two mutated regions — proving the residual case a pure two-file diff misses.
- **Verdict**: PASS
- **Notes**: The shared-helper discipline means a real convergent deletion of `# backend: github-issues` from both files would fail the production `test_asset_frontmatter_carries_options`, not merely the sentinel.

### Requirement 5: ADR records the reconcile-and-gate decision
- **Expected**: `cortex/adr/0017-*.md` exists; cited by the test; no ADR numbering gap; `just test` ADR citation audit passes.
- **Actual**: `cortex/adr/0017-reconcile-and-gate-lifecycle-config-sources.md` exists. `grep -rl '0017' tests/test_lifecycle_config_parity.py` is non-empty (cited in the module docstring as ADR-0017). The ADR corpus is contiguous 0001–0017 (no gap). `pytest -k adr` → 13 passed. The ADR has `status: proposed` frontmatter, `# title`, `## Context`, `## Decision`, `## Trade-off / rejected alternatives` — matching the README's frontmatter convention and ADR-0016's shape, and clears the three-criteria gate (hard to reverse: one-way ratchet once plugin-only users copy the completed asset; surprising: dual-maintained sources in two distribution channels; real trade-off: generate-from-source / parsed-dict / thin-pointer / bare-reconcile each rejected with stated reasons).
- **Verdict**: PASS

### Requirement 6: setup.md schema block corrected
- **Expected**: `grep -c 'Six keys'` = 0; `grep -c 'backlog'` ≥ 1; `grep -c 'synthesizer_overnight_enabled'` ≥ 1; plan adds `grep -c 'backlog.backend'` ≥ 1 and asset-path ≥ 1.
- **Actual**: `Six keys` = 0; `backlog` = 6; `backlog.backend` = 1; `synthesizer_overnight_enabled` = 1; asset path = 1. The block (line 118–120) removes the false count framing, names the asset as the single place to read the scaffolded schema (ADR-0017 cited), and corrects the consumed set: `test-command`, `commit-artifacts`, `demo-commands`, `backlog.backend`, `synthesizer_overnight_enabled` are code-consumed; `type`/`skip-specify`/`skip-review`/`default-tier`/`default-criticality` are advisory/optional-override. This is the accurate active/advisory characterization the spec required.
- **Verdict**: PASS

### Requirement 7: overnight.md repointed; stale inline example removed
- **Expected**: EITHER the stale example removed (no `skip-specify:`/`skip-review:` signature inside yaml fences) OR every retained lifecycle.config.md YAML example contains a `backlog` line; AND `backlog` present.
- **Actual**: Removed arm holds — `awk '/^```yaml/,/^```$/' | grep -cE 'skip-specify:|skip-review:'` = 0 (the stale fenced frontmatter example is gone). The section now points at the asset as the canonical annotated scaffolded field list (including the `backlog:` block), kept byte-identical by the CI gate (ADR-0017 cited). Whole-file `backlog` ≥ 1. The surrounding `test-command` guidance and the "Other fields" prose are preserved; the retained prose list is guidance, not a divergent full copy-target re-enumeration.
- **Verdict**: PASS

### Requirement 8: overnight-operations.md field list + consumed-but-unscaffolded exception
- **Expected**: scaffolded-field list includes `backlog` and `synthesizer_overnight_enabled`; pointer repointed at the asset honoring the one-place-to-check rule; `branch-mode` documented as a consumed-but-unscaffolded exception in the consumer section, NOT folded into the scaffolded enumeration line.
- **Actual**: Section-scoped (`lifecycle.config.md consumers` … `### Auth`) grep: `synthesizer_overnight_enabled` = 1, `backlog` = 1, `branch-mode` = 1. The "Scaffolded fields include …" line now lists `synthesizer_overnight_enabled` and the `backlog:` backend block. A dedicated "**Consumed-but-unscaffolded exception**" paragraph documents `branch-mode` (read by `read_branch_mode`, in neither scaffolded template, scaffolding deferred as a follow-up bound by the ADR-0017 gate). The "Fields include" enumeration line carries NO `branch-mode` (`grep 'Fields include' | grep -c 'branch-mode'` = 0) — the exact exception-vs-scaffolded distinction R8 turns on. The `:717` "do not enumerate fields in more than one doc" rule is restated and the asset is named the single referent.
- **Verdict**: PASS

### Requirement 9: Single named authority for the scaffolded schema
- **Expected**: All three docs name the skills asset as the one scaffolded-schema referent; no divergent full re-enumeration; the asset named as a config-file referent; `branch-mode` handled only as a documented exception.
- **Actual**: `grep -l 'skills/lifecycle/assets/lifecycle.config.md' docs/setup.md docs/overnight.md docs/overnight-operations.md` lists all three. Operator-judgment confirmation: each doc points at the gate-kept asset as the scaffolded-schema authority rather than maintaining a competing full schema listing — setup.md ("the single place to read the scaffolded schema rather than re-listing it here"), overnight.md ("the one place to copy from rather than an inline example that can drift"), overnight-operations.md ("the one place to check … do not enumerate the scaffolded fields in more than one doc"). The remaining per-doc prose (setup.md's consumed/advisory split; overnight.md's "Other fields" guidance) is overlapping guidance, not a divergent full re-enumeration. `branch-mode` appears only as the consumer-section exception, not in any scaffolded enumeration. The asset is consistently named as a config-file referent, not a generic "doc location."
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Clear and intention-revealing. `_frontmatter_region`, `_assert_regions_equal`, `_assert_options_present`, and the four `test_*` functions mirror the established `tests/test_dual_source_reference_parity.py` vocabulary (`assert_byte_parity`, sentinel naming). `REPO_ROOT`/`ASSET`/`TEMPLATE` module constants match the sibling test's `REPO_ROOT` convention. The ADR slug and title follow the `cortex/adr/` corpus pattern.
- **Error handling**: Helpers raise `AssertionError` with named diagnostics (byte counts and a reconcile-direction hint; the missing-option-line list; a delimiter-count message when fewer than two `---` markers are found). `_frontmatter_region` fail-loud on a malformed file rather than silently slicing garbage. The sentinels mutate in memory only (no disk writes), matching the crash-safe pattern of the dual-source test.
- **Test coverage**: All plan Verification steps executed and pass — R1 grep trio, R2 mirror diff + cross-file byte-identity, R3/R4 pytest (4 tests, `_assert_options_present` call-count = 3), R5 ADR existence + citation + numbering + citation audit (13 passed), R6–R9 region-scoped/non-pre-satisfied-token greps. `.venv/bin/pytest tests/test_lifecycle_config_parity.py tests/test_dual_source_reference_parity.py -q` → 63 passed. The gate is genuinely discriminating: the divergence sentinel proves byte-parity fails on mismatch, and the convergent-loss sentinel proves the positive-content assertion catches the residual case while byte-parity stays green.
- **Pattern consistency**: The parity test deliberately and correctly diverges from the production `_extract_frontmatter_text` (whose line-ending normalization would mask CRLF/trailing-newline drift) while reusing the dual-source test's pure-helper + in-memory-sentinel structure. The ADR matches `cortex/adr/0016`'s section shape and the README's frontmatter convention and three-criteria gate. Reconcile direction is up (asset ← template); the init template content is untouched, avoiding the `.cortex-init` drift-report side effect the spec's Non-Requirements call out.

## Requirements Drift
**State**: none
**Findings**:
- None. #335 is hygiene plus a durable CI gate grounded in #317's existing FR (configurable backlog backend). The new surfaces honor project.md's Philosophy of Work (the gate is a structural test, not prose enforcement; complexity earns its place via the named recurrence risk under #318), the Solution horizon (a one-way-ratchet reconcile + reversible gate mechanism, recorded in an ADR), and the ADR three-criteria gate (cleared and documented). No new uncaptured behavior relative to `cortex/requirements/project.md`.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
