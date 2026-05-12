# Plan: consolidate-commonpyread-tier-and-overnight-reportpy-read-tier

## Overview

Direct-swap consolidation (research §A): `overnight/report.py:535` migrates to `common.read_tier`, the local `_read_tier` is deleted, and the parity test's canonical-rule + key-name cases are migrated to `tests/test_common_utils.py` (which already hosts the `read_tier` test class). The audit gate (`bin/cortex-audit-tier-divergence`) and its full ecosystem retire in a second commit per research §X — its structural invariant ("two readers agree") becomes vacuously true once one canonical reader remains.

## Outline

### Phase 1: Reader consolidation (tasks: 1, 2, 3, 4)
**Goal**: `overnight/report.py` uses `common.read_tier`; `_read_tier` is gone; canonical-rule + T-A/T-B tests live in `tests/test_common_utils.py`; `tests/test_read_tier_parity.py` is deleted.
**Checkpoint**: `uv run pytest cortex_command/overnight/tests/test_report.py tests/test_common_utils.py tests/test_outcome_router.py cortex_command/overnight/tests/test_lead_unit.py tests/test_lifecycle_state.py tests/test_bin_lifecycle_state_parity.py -q` exits 0; `grep -c "_read_tier" cortex_command/overnight/report.py` = 0; commit landed.

### Phase 2: Audit-gate retirement (tasks: 5, 6, 7)
**Goal**: `bin/cortex-audit-tier-divergence` and every consumer (plugin mirror, test, fixtures, pre-commit Phase 1.9 block, justfile recipe) are deleted; CHANGELOG records the retirement.
**Checkpoint**: `just check-parity` exits 0; full test suite green; commit landed with both canonical and plugin-mirror deletions staged together.

## Tasks

### Task 1: Migrate canonical-rule + key-name tests to tests/test_common_utils.py
- **Files**:
  - `tests/test_common_utils.py` (modify — add migrated cases at end of `ReadTierTests` class or as a new parametrized test function)
  - `tests/test_read_tier_parity.py` (read for context; do not modify in this task)
  - `cortex_command/overnight/tests/test_report.py` (read T-A/T-B at lines 739–773 for migration context)
- **What**: Add a parametrized canonical-rule test reusing the existing `tests/fixtures/state/tier_parity/<slug>/events.log` fixtures (slugs: `lifecycle_start_only`, `start_then_override`, `stray_tier_after_override`). Also migrate the T-A (`test_read_tier_ignores_complexity_field_only_returns_default`) and T-B (`test_read_tier_canonical_tier_wins_over_stray_complexity`) function bodies — currently in `cortex_command/overnight/tests/test_report.py:739–773` per the spec's R6 sources clause — rebound to `common.read_tier`.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Existing test pattern in `tests/test_common_utils.py:ReadTierTests` calls `read_tier(feature, lifecycle_base=tmp_path)` — match that pattern (R6's `lifecycle_base=tmp_path / "lifecycle"` rule applies; choose either form as long as `lifecycle_base` is absolute).
  - For canonical-rule cases: `CANONICAL_CASES = [("lifecycle_start_only", "complex"), ("start_then_override", "high"), ("stray_tier_after_override", "complex")]` (copy expected values from `tests/test_read_tier_parity.py:100-107`).
  - Fixture staging pattern: stage source `tests/fixtures/state/tier_parity/<slug>/events.log` into `tmp_path / "lifecycle" / <slug> / "events.log"` (see `tests/test_read_tier_parity.py:_stage_fixture` for the existing helper — copy or inline its logic).
  - Function name fragments R6 grep-checks for: `lifecycle_start_only`, `start_then_override`, `stray_tier_after_override`, `ignores_complexity_field`, `canonical_tier_wins_over_stray_complexity`.
  - Cache isolation: `tests/test_lifecycle_state.py` and `tests/test_bin_lifecycle_state_parity.py` already use absolute `lifecycle_base` + optional `_read_tier_inner.cache_clear()` — follow that prior art (the cached inner is reachable via `read_tier.__wrapped__` at `common.py:469`).
  - Do NOT modify `tests/test_read_tier_parity.py` or `cortex_command/overnight/tests/test_report.py` yet — those are Tasks 2 and 3's scope.
- **Verification**: `uv run pytest tests/test_common_utils.py -q -k "tier"` — pass if exit 0 AND `grep -c "lifecycle_start_only\|start_then_override\|stray_tier_after_override" tests/test_common_utils.py` ≥ 3 AND `grep -c "ignores_complexity_field\|canonical_tier_wins_over_stray_complexity" tests/test_common_utils.py` ≥ 2.
- **Status**: [x] complete (201e8e7)

### Task 2: Swap report.py callsite and delete `_read_tier`
- **Files**:
  - `cortex_command/overnight/report.py` (modify — line 25 import line; line 535 callsite; delete lines 746–778)
- **What**: Replace the sole production `_read_tier(name)` call at `report.py:535` with `read_tier(name)`. Append `read_tier` to the existing import line at `report.py:25`. Delete the `_read_tier` function body (`report.py:746–778`). Note: `test_report.py` will be transiently broken between this task and Task 3 — do not run the test suite between them. The Task 3 verification covers both.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Current import at `report.py:25`: `from cortex_command.common import _resolve_user_project_root, atomic_write, slugify` — extend to include `read_tier`.
  - `_read_tier` function body spans `report.py:746–778`; delete the entire function including its docstring and the trailing blank line before `_read_acceptance` at line 781.
  - The binding name `cortex_command.overnight.outcome_router.read_tier` is unchanged by this work; do NOT touch `outcome_router.py:830` or its monkeypatch seams.
  - `read_events()` import at the top of `report.py` may become unused after `_read_tier` is deleted — check `grep -n "read_events" cortex_command/overnight/report.py` and remove the import only if it is genuinely unused (the function is also called at `report.py:178` and elsewhere, so likely retained).
- **Verification**:
  - `grep -c "^def _read_tier\b\|_read_tier(" cortex_command/overnight/report.py` = 0 — pass if count = 0 (R1, R2).
  - `grep "from cortex_command.common import" cortex_command/overnight/report.py` shows a single import line containing `read_tier` alongside `_resolve_user_project_root`, `atomic_write`, `slugify` — pass if exit 0 (R3).
- **Status**: [x] complete (18ce622)

### Task 3: Migrate test_report.py callers to common.read_tier with lifecycle_base arg
- **Files**:
  - `cortex_command/overnight/tests/test_report.py` (modify — replace executable `_read_tier` references with `read_tier(feature, lifecycle_base=tmp_path / "lifecycle")`; delete T-A and T-B test functions at lines 739–773 since they migrated in Task 1; comments containing `_read_tier` at lines 339/344 may be edited for accuracy but R4 tolerates them as-is)
- **What**: Rebind every executable `_read_tier` import/call in `test_report.py` to `read_tier` from `cortex_command.common`, threading `lifecycle_base=tmp_path / "lifecycle"` through every callsite. Delete the T-A/T-B test bodies (lines 739–773) since they now live in `tests/test_common_utils.py` per Task 1.
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - Executable `_read_tier` reference sites in `test_report.py` (from the grep audit): lines 498, 508, 515, 525, 532, 539, 591, 602, 635, 651, 663, 677, 688, 699, 720. T-A/T-B (lines 739–773) are deleted, not rebound.
  - Each rebinding pattern looks like: `from cortex_command.overnight.report import _read_tier` → `from cortex_command.common import read_tier`; co-imported `overnight.report` helpers (e.g. `_read_acceptance`, `_read_last_phase_checkpoint`) stay on their existing import lines.
  - Each call pattern looks like: `_read_tier(feature)` → `read_tier(feature, lifecycle_base=tmp_path / "lifecycle")`. Every test in this file already uses `monkeypatch.chdir(tmp_path)`, so the relative path `tmp_path / "lifecycle"` resolves identically to what `_read_tier`'s hardcoded `Path("lifecycle/{feature}/events.log")` was reading.
  - Edge-case sanity check from the spec: run `grep -rn "report\._read_tier" tests/ cortex_command/` and confirm zero results before declaring this task done — guards against silent monkeypatch no-ops.
- **Verification**:
  - `grep -E '^[^#]*_read_tier' cortex_command/overnight/tests/test_report.py` returns no executable matches (comment lines tolerated per R4) — pass if exit code = 1 OR all results are comment lines.
  - `grep -c "from cortex_command.common import .*\bread_tier\b\|from cortex_command.common import read_tier" cortex_command/overnight/tests/test_report.py` ≥ 1 — pass if count ≥ 1 (R4).
  - `grep -rn "report\._read_tier" tests/ cortex_command/` returns no results — pass if exit code = 1.
  - `uv run pytest cortex_command/overnight/tests/test_report.py -q` exits 0 — pass if exit code = 0 (R5).
- **Status**: [x] complete (7c3b86f)

### Task 4: Delete tests/test_read_tier_parity.py and commit Phase 1
- **Files**:
  - `tests/test_read_tier_parity.py` (delete via `git rm`)
- **What**: `git rm tests/test_read_tier_parity.py`. Then run the Phase 1 acceptance sweep, stage the lifecycle artifacts (`lifecycle/consolidate-commonpyread-tier-and-overnight-reportpy-read-tier/`), and commit via `/cortex-core:commit`. The commit must NOT skip hooks; pre-commit Phase 1.9 is still wired at this point and will re-fire (harmless — it inlines its canonical-rule logic and operates on the unchanged corpus per the spec's Edge Cases section).
- **Depends on**: [3]
- **Complexity**: simple
- **Context**:
  - Fixtures at `tests/fixtures/state/tier_parity/` are PRESERVED (Task 1 reuses them); only the test file is removed.
  - Commit subject (imperative, ≤72 chars): `Consolidate report._read_tier into common.read_tier` (or similar).
  - The `/cortex-core:commit` skill handles message validation and the commit invocation — do not run `git commit` directly.
  - Phase 1.9 pre-commit will fire because `report.py` is in the staged diff; it should pass on the current corpus (no events.log content changed).
- **Verification**:
  - `test -f tests/test_read_tier_parity.py && echo EXISTS || echo ABSENT` prints `ABSENT` — pass if output = `ABSENT` (R7).
  - `test -d tests/fixtures/state/tier_parity && ls tests/fixtures/state/tier_parity/` lists `lifecycle_start_only`, `start_then_override`, `stray_tier_after_override` — pass if all three present (R8).
  - `uv run pytest tests/test_outcome_router.py cortex_command/overnight/tests/test_lead_unit.py tests/test_lifecycle_state.py tests/test_bin_lifecycle_state_parity.py -q` exits 0 — pass if exit code = 0 (R18, R19).
  - `git log -1 --pretty=%s` shows the Phase 1 commit subject — pass if a new commit landed since the start of this task.
- **Status**: [ ] pending

### Task 5: Delete audit-gate canonical sources and wiring
- **Files**:
  - `bin/cortex-audit-tier-divergence` (delete via `git rm`)
  - `tests/test_audit_tier_divergence.py` (delete via `git rm`)
  - `tests/fixtures/audit_tier/` (delete via `git rm -r`)
  - `.githooks/pre-commit` (modify — remove the `# Phase 1.9` block at lines 200–225, including the section comment and the trailing blank line before the next `# ---` divider)
  - `justfile` (modify — remove the `audit-tier-divergence:` recipe at lines 363–365, including any preceding comment header)
  - `plugins/cortex-core/bin/cortex-audit-tier-divergence` (deleted via `just build-plugin` rsync `--delete` in this task — do NOT `git rm` it directly; the rsync sync handles the mirror deletion and pre-commit Phase 4 verifies symmetry)
- **What**: Hard-delete the audit-gate canonical script, its test, its fixture tree, the pre-commit Phase 1.9 block, and the justfile recipe. Then run `just build-plugin` to propagate the source deletion to the plugin mirror via rsync `--delete`. After `just build-plugin`, `git status` should show the mirror deletion staged alongside the canonical deletion (R10).
- **Depends on**: [4]
- **Complexity**: complex
- **Context**:
  - Spec's Edge Cases: deletion-only commits do NOT trigger pre-commit Phase 2's `--diff-filter=ACMR` auto-rebuild of the plugin mirror — running `just build-plugin` manually is REQUIRED before commit, otherwise pre-commit Phase 4's symmetry check blocks the commit (R10).
  - Pre-commit Phase 1.9 location (read via grep audit): `.githooks/pre-commit:200–225`. Surrounding context: ends right before the `Phase 2 — Short-circuit decision` divider at line 227.
  - Justfile recipe location: `justfile:363–365` — two lines (`audit-tier-divergence:` header + `bin/cortex-audit-tier-divergence` invocation), plus any preceding comment.
  - The plugin-mirror rsync command lives in `justfile:507–539` (`build-plugin` recipe); its `--delete` flag handles deletions automatically — no manual `git rm` of the mirror needed.
- **Verification**:
  - `test -f bin/cortex-audit-tier-divergence && echo EXISTS || echo ABSENT` prints `ABSENT` — pass if output = `ABSENT` (R9).
  - `test -f plugins/cortex-core/bin/cortex-audit-tier-divergence && echo EXISTS || echo ABSENT` prints `ABSENT` — pass if output = `ABSENT` (R10).
  - `test -f tests/test_audit_tier_divergence.py && echo EXISTS || echo ABSENT` prints `ABSENT` — pass (R11).
  - `test -d tests/fixtures/audit_tier && echo EXISTS || echo ABSENT` prints `ABSENT` — pass (R12).
  - `grep -c "Phase 1.9\|tier_audit_triggered\|audit-tier-divergence" .githooks/pre-commit` = 0 — pass if count = 0 (R13).
  - `grep -c "^audit-tier-divergence:" justfile` = 0 AND `grep -c "bin/cortex-audit-tier-divergence" justfile` = 0 — pass if both = 0 (R14).
  - `git status --short` shows both `D bin/cortex-audit-tier-divergence` AND `D plugins/cortex-core/bin/cortex-audit-tier-divergence` in the staged set — pass if both deletions are staged.
- **Status**: [ ] pending

### Task 6: Add CHANGELOG entry under [Unreleased] → Removed
- **Files**:
  - `CHANGELOG.md` (modify — insert a new bullet under the existing `## [Unreleased]` → `### Removed` section)
- **What**: Document the audit-gate retirement under `[Unreleased]` → `### Removed`. The entry must (per R15): (a) name every retired surface — `bin/cortex-audit-tier-divergence`, `plugins/cortex-core/bin/cortex-audit-tier-divergence`, `tests/test_audit_tier_divergence.py`, `tests/fixtures/audit_tier/`, the pre-commit Phase 1.9 block in `.githooks/pre-commit`, and the `audit-tier-divergence` justfile recipe; (b) state the replacement entry point ("the canonical-rule cases preserved in `tests/test_common_utils.py` pin the `read_tier` semantic; structural divergence is no longer possible because one canonical reader remains"); (c) note that no user-side cleanup is required (the gate is contributor-tooling only).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - `## [Unreleased]` and `### Removed` headings already exist in `CHANGELOG.md` near the top of the file — append the new bullet to the existing `### Removed` list.
  - Phrasing convention: match the existing terse bullets in that section (single paragraph with bolded headline noun, prose body, optional sub-bullets for user-side cleanup / replacement workflow).
  - No `### Removed` user-facing migration steps apply — explicitly say so to match the "no user-side cleanup required" pattern.
- **Verification**:
  - `grep -B 2 -A 5 "cortex-audit-tier-divergence" CHANGELOG.md` returns a block under the `## [Unreleased]` / `### Removed` heading containing each of the six retired-surface names AND the replacement-entry-point phrase AND a no-user-cleanup statement — pass if all three conditions hold visually on inspection (R15).
- **Status**: [ ] pending

### Task 7: Run Phase 2 acceptance and commit Phase 2
- **Files**:
  - (lifecycle artifacts only — no source files touched)
- **What**: Run the full Phase 2 acceptance sweep, stage the CHANGELOG edit + the Task 5 deletions + the lifecycle artifacts, and commit via `/cortex-core:commit`. With the Phase 1.9 block already removed (Task 5), no tier-divergence audit will fire on this commit. The commit body must reference the CHANGELOG entry per the spec's Commit discipline constraint.
- **Depends on**: [6]
- **Complexity**: simple
- **Context**:
  - Commit subject (imperative, ≤72 chars): `Retire cortex-audit-tier-divergence post-consolidation` (or similar).
  - Commit body must mention the CHANGELOG entry (e.g. "CHANGELOG: [Unreleased] → Removed entry added").
  - `/cortex-core:commit` handles message validation; do not bypass.
- **Verification**:
  - `uv run pytest tests/ cortex_command/overnight/tests/ -q` exits 0 — pass if exit code = 0 (R16).
  - `just check-parity` exits 0 — pass if exit code = 0 (R17).
  - `git log -1 --pretty=%s` shows the Phase 2 commit subject AND `git log -1 --pretty=%b` contains a CHANGELOG reference — pass if both hold.
- **Status**: [ ] pending

## Risks

- **Lowercase-event-name semantic change.** `report._read_tier` (via `read_events()`) lowercased event names; `common.read_tier` is case-sensitive. The in-tree corpus has no uppercase events today, so the consolidation is silent in practice — but a hand-edited archive containing `"event": "LIFECYCLE_START"` would post-consolidation classify as `"simple"` (default) instead of the recorded tier. Spec's Edge Cases section accepts this; if archive readability becomes a future requirement, it files separately. Operator can preempt by raising the question now.
- **`test_report.py` lru_cache cross-test pollution.** Mandatory mitigation in R4: every migrated callsite passes `lifecycle_base=tmp_path / "lifecycle"` (or an absolute equivalent). This task list encodes that in Task 2's verification. If the implementer skips the `lifecycle_base` arg on any migrated callsite, tests can pass individually and fail in suite — Task 2's `uv run pytest cortex_command/overnight/tests/test_report.py -q` verification catches the suite-level failure.
- **Plugin-mirror deletion-on-commit symmetry.** Task 5 requires running `just build-plugin` manually after `git rm bin/cortex-audit-tier-divergence` and before commit, because pre-commit Phase 2's `--diff-filter=ACMR` does NOT trigger on deletions. If the implementer forgets, pre-commit Phase 4 blocks with a symmetry error — recoverable by running `just build-plugin` and re-staging.
- **Phase 1 commit re-triggers Phase 1.9 audit.** Harmless per spec Edge Cases — the audit inlines its canonical-rule logic and operates on the unchanged corpus. No phase reordering needed.
- **Audit gate's future reintroduction.** Once retired, a contributor could reintroduce a divergent reader; only code review + the migrated canonical-rule + T-A/T-B tests in `tests/test_common_utils.py` defend against this. Spec's Non-Requirements section accepts this trade per workflow-trimming preference (`requirements/project.md:23`).
