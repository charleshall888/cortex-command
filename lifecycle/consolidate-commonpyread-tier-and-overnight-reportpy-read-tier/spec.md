# Specification: consolidate-commonpyread-tier-and-overnight-reportpy-read-tier

## Problem Statement

Two implementations of the canonical-tier-read rule live in the codebase post-#190: `cortex_command/common.py:read_tier` (public, lru_cache-wrapped) and `cortex_command/overnight/report.py:_read_tier` (private, uncached). Both implement the same `lifecycle_start.tier → complexity_override.to` semantic. #190 explicitly out-of-scoped this consolidation; the audit gate `bin/cortex-audit-tier-divergence` was added to make the duplication safer in the interim. With one canonical reader the gate's structural invariant ("the two readers agree") becomes vacuously true. The consolidation eliminates the duplicate, retires the now-purposeless audit gate, and migrates the test-suite's canonical-rule cases to the surviving reader's test module.

## Phases

- **Phase 1: Reader consolidation** — swap `report.py:535` callsite to `common.read_tier`, delete `_read_tier`, update `test_report.py` test imports with explicit `lifecycle_base=tmp_path / "lifecycle"` arguments to avoid lru_cache cross-test pollution, migrate canonical-rule cases (i)–(iii) AND the T-A/T-B key-name cases from `test_read_tier_parity.py`/`test_report.py` to `test_common_utils.py`, delete the parity test file.
- **Phase 2: Audit-gate retirement** — delete `bin/cortex-audit-tier-divergence`, its test file, its fixtures, its pre-commit Phase 1.9 wiring, its justfile recipe, and (via explicit `just build-plugin`) the plugin mirror; add `CHANGELOG.md` entry under `[Unreleased] → Removed`.

## Requirements

1. **`overnight/report.py:535` calls `common.read_tier`, not the local duplicate**: `grep -n "read_tier" cortex_command/overnight/report.py` shows `read_tier(name)` at the former `_read_tier(name)` callsite. Pass if `grep -c "^def _read_tier\b\|_read_tier(" cortex_command/overnight/report.py` = 0. **Phase**: Phase 1: Reader consolidation

2. **`_read_tier` is removed from `overnight/report.py`**: `grep -c "^def _read_tier" cortex_command/overnight/report.py` = 0. Pass if count = 0. **Phase**: Phase 1: Reader consolidation

3. **`read_tier` is added to the existing `from cortex_command.common import …` line at `report.py:25`**: `grep -n "from cortex_command.common import" cortex_command/overnight/report.py` shows a single import line including `read_tier` alongside the existing symbols (`_resolve_user_project_root, atomic_write, slugify`). Pass if exit 0 and the import line contains `read_tier`. **Phase**: Phase 1: Reader consolidation

4. **`cortex_command/overnight/tests/test_report.py` imports `read_tier` from `cortex_command.common`, not `_read_tier` from `cortex_command.overnight.report`, and migrated callsites pass `lifecycle_base=tmp_path / "lifecycle"` explicitly**: pass if all three hold —
    - `grep -E '^[^#]*_read_tier' cortex_command/overnight/tests/test_report.py` returns no executable references (comments containing `_read_tier` are tolerated; the grep gate is anchored to non-comment lines because R4's scope is binding/import changes, not prose rewrites);
    - `grep -c "from cortex_command.common import read_tier\|from cortex_command.common import .*\bread_tier\b" cortex_command/overnight/tests/test_report.py` ≥ 1;
    - every migrated callsite in the file passes `lifecycle_base=tmp_path / "lifecycle"` (or an equivalent absolute path) rather than relying on the default `Path("lifecycle")`; verify with `grep -c "read_tier(.*lifecycle_base\s*=" cortex_command/overnight/tests/test_report.py` matching the count of post-migration `read_tier(` callsites in the file. Test bodies that previously imported `_read_tier` (alone or alongside other `overnight.report` helpers) rebind to `from cortex_command.common import read_tier` and keep any co-imported `overnight.report` helpers intact. **Phase**: Phase 1: Reader consolidation

5. **`cortex_command/overnight/tests/test_report.py` passes**: `uv run pytest cortex_command/overnight/tests/test_report.py -q` exits 0. **Phase**: Phase 1: Reader consolidation

6. **Canonical-rule cases (i)–(iii) AND the T-A/T-B key-name cases are preserved in `tests/test_common_utils.py`**: pass if all of —
    - `grep -c "lifecycle_start_only\|start_then_override\|stray_tier_after_override" tests/test_common_utils.py` ≥ 3 (one occurrence per CANONICAL_CASES slug);
    - `grep -c "ignores_complexity_field\|canonical_tier_wins_over_stray_complexity" tests/test_common_utils.py` ≥ 2 (T-A and T-B function-name fragments preserved);
    - the migrated cases call `common.read_tier(slug, lifecycle_base=…)` with an absolute `lifecycle_base` (either `tmp_path / "lifecycle"` for tmp-staged fixtures or a `REPO_ROOT`-anchored absolute path for repo fixtures) and use the existing `tests/fixtures/state/tier_parity/<slug>/events.log` fixtures (preserved in tree) for CANONICAL_CASES. **Phase**: Phase 1: Reader consolidation

7. **`tests/test_read_tier_parity.py` is deleted**: `test -f tests/test_read_tier_parity.py && echo EXISTS || echo ABSENT` prints `ABSENT`. Pass if output = `ABSENT`. **Phase**: Phase 1: Reader consolidation

8. **`tests/fixtures/state/tier_parity/` is preserved** (the migrated cases continue to use these fixtures): `test -d tests/fixtures/state/tier_parity && ls tests/fixtures/state/tier_parity/` lists `lifecycle_start_only`, `start_then_override`, `stray_tier_after_override`. Pass if all three directories exist. **Phase**: Phase 1: Reader consolidation

9. **`bin/cortex-audit-tier-divergence` is deleted**: `test -f bin/cortex-audit-tier-divergence && echo EXISTS || echo ABSENT` prints `ABSENT`. Pass if output = `ABSENT`. **Phase**: Phase 2: Audit-gate retirement

10. **`plugins/cortex-core/bin/cortex-audit-tier-divergence` is deleted and staged in the same commit as R9**: `test -f plugins/cortex-core/bin/cortex-audit-tier-divergence && echo EXISTS || echo ABSENT` prints `ABSENT`. The pre-commit hook does NOT auto-rebuild the plugin mirror on deletion-only commits (Phase 2's `--diff-filter=ACMR` trigger excludes Deletions); the implementer MUST run `just build-plugin` after `git rm bin/cortex-audit-tier-divergence` and before `/cortex-core:commit`, so the rsync `--delete` sync removes the mirror and `git status` shows the mirror deletion staged alongside the canonical deletion. Pass if output = `ABSENT`. **Phase**: Phase 2: Audit-gate retirement

11. **`tests/test_audit_tier_divergence.py` is deleted**: `test -f tests/test_audit_tier_divergence.py && echo EXISTS || echo ABSENT` prints `ABSENT`. Pass if output = `ABSENT`. **Phase**: Phase 2: Audit-gate retirement

12. **`tests/fixtures/audit_tier/` is deleted**: `test -d tests/fixtures/audit_tier && echo EXISTS || echo ABSENT` prints `ABSENT`. Pass if output = `ABSENT`. **Phase**: Phase 2: Audit-gate retirement

13. **Pre-commit Phase 1.9 block is removed from `.githooks/pre-commit`**: `grep -c "Phase 1.9\|tier_audit_triggered\|audit-tier-divergence" .githooks/pre-commit` = 0. Pass if count = 0. **Phase**: Phase 2: Audit-gate retirement

14. **Justfile recipe `audit-tier-divergence` is removed**: `grep -c "^audit-tier-divergence:" justfile` = 0 AND `grep -c "bin/cortex-audit-tier-divergence" justfile` = 0. Pass if both counts = 0. **Phase**: Phase 2: Audit-gate retirement

15. **`CHANGELOG.md` `[Unreleased] → Removed` section documents the retirement**: `grep -A 2 "cortex-audit-tier-divergence" CHANGELOG.md` returns at least one matching block under the `## [Unreleased]` / `### Removed` heading. The entry must (a) name the retired files (`bin/cortex-audit-tier-divergence`, `tests/test_audit_tier_divergence.py`, `tests/fixtures/audit_tier/`, pre-commit Phase 1.9 block in `.githooks/pre-commit`, justfile recipe, plugin mirror), (b) state the replacement entry point ("the canonical-rule cases preserved in `tests/test_common_utils.py` pin the `read_tier` semantic; structural divergence is no longer possible because one canonical reader remains"), and (c) note that no user-side cleanup is required (the gate is contributor-tooling only). Pass if grep returns a non-empty match in the expected section. **Phase**: Phase 2: Audit-gate retirement

16. **Full test suite green**: `uv run pytest tests/ cortex_command/overnight/tests/ -q` exits 0. **Phase**: Phase 2: Audit-gate retirement

17. **`just check-parity` exits 0**: removed `bin/` script + plugin mirror leave no dangling parity references. Pass if exit code = 0. **Phase**: Phase 2: Audit-gate retirement

18. **`outcome_router.py:830` review-gating path remains correct**: `uv run pytest tests/test_outcome_router.py cortex_command/overnight/tests/test_lead_unit.py -q` exits 0. The binding name `cortex_command.overnight.outcome_router.read_tier` is unchanged by this work, so existing monkeypatches in these tests continue to apply. Pass if exit code = 0. **Phase**: Phase 1: Reader consolidation

19. **`tests/test_lifecycle_state.py` and `tests/test_bin_lifecycle_state_parity.py` pass**: these test modules import `_read_tier_inner` from `cortex_command.common` (lines 17 and 33 respectively) and `cache_clear()` between cases — neither needs to change for this consolidation. The cache-isolation pattern they already use (absolute `lifecycle_base=tmp_path` AND `_read_tier_inner.cache_clear()`) is the prior art that R4 and R6 adopt for their migrations. `uv run pytest tests/test_lifecycle_state.py tests/test_bin_lifecycle_state_parity.py -q` exits 0. **Phase**: Phase 1: Reader consolidation

## Non-Requirements

- **No widening of `common.read_tier`'s signature.** The function continues to take `(feature, lifecycle_base=Path("lifecycle"))` and return a tier string. No richer tuple-return, no provenance field, no second cache parameter.
- **No change to `outcome_router.py:830`.** That callsite already uses `common.read_tier`; no migration is needed there.
- **No new audit tooling.** The retired `cortex-audit-tier-divergence` is not replaced by a corpus-shape audit or any other gate; the canonical-rule tests in `test_common_utils.py` are the sole semantic pin.
- **No change to `read_events()` lowercasing behavior** in `cortex_command/overnight/events.py`. The lowercase normalization remains in place for its other consumers (`report._render_feature_block` calls `read_events()` directly at `report.py:178` and elsewhere).
- **No backfill of lowercase event-name handling in `common.read_tier`.** The canonical reader stays case-sensitive on the `"event"` field; if archived-log readability becomes a requirement later, that change is filed separately.
- **No tag-pinned recovery affordance.** The retired gate is contributor-tooling only with zero external consumers; the standard git history is the only recovery path.
- **No documentation rewrite.** `docs/internals/pipeline.md` and `docs/overnight-operations.md` contain no references to `_read_tier`, `cortex-audit-tier-divergence`, or `tier-divergence`; no doc edits are required.
- **No preservation of case (iv) of `tests/test_read_tier_parity.py`.** Case (iv) was the cross-reader corpus sweep — both `common.read_tier` and `_read_tier` against every in-tree `lifecycle/*/events.log`. With one reader remaining, agreement with itself is vacuous. The case is dropped, not migrated.

## Edge Cases

- **An events.log line with `"event": "LIFECYCLE_START"` (uppercase) was previously classified by `report._read_tier` (via `read_events()` lowercasing) and is now classified by the case-sensitive `common.read_tier` as if the event field were absent**: returns `"simple"` instead of the recorded tier. No in-tree corpus uses uppercase events today. **Expected behavior**: accept the canonical reader's stricter rule. If a future archive read needs lowercase tolerance, file a separate ticket.
- **A test that uses `monkeypatch.setattr("cortex_command.overnight.report._read_tier", …)` silently no-ops after the import-swap**: no occurrences observed in the current test suite, but the implementation must grep for this pattern (`rg "report\._read_tier\b"`) before declaring Phase 1 done. Acceptance: `grep -rn "report\._read_tier" tests/ cortex_command/` returns zero results after Phase 1.
- **A future contributor reintroduces a divergent reader**: not preventable by tooling after the audit gate is retired. Mitigation: the canonical-rule cases (i)–(iii) and the T-A/T-B key-name cases in `tests/test_common_utils.py` and the `common.read_tier` docstring serve as the convention pin. Code review is the only structural guard.
- **lru_cache cross-test pollution in migrated `test_report.py` cases**: post-migration, `test_report.py` becomes a new cached-reader consumer. The cache key for `_read_tier_inner` is `(events_path_str, exists, mtime_ns, size)`. If migrated callsites use the default `lifecycle_base=Path("lifecycle")`, the path component is the relative string `"lifecycle/<feature>/events.log"` and does not vary across tests sharing a feature slug — only `(exists, mtime_ns, size)` discriminates, and on filesystems with coarse mtime resolution two same-length one-line events.log writes can collide. **Mitigation (mandatory, encoded in R4)**: every migrated callsite passes `lifecycle_base=tmp_path / "lifecycle"` (or an absolute equivalent) so the path component varies per test, producing a unique cache key per (feature × tmp_path) combination. This matches the prior-art pattern in `tests/test_lifecycle_state.py` and `tests/test_bin_lifecycle_state_parity.py`.
- **Phase 1's commit re-triggers the still-wired pre-commit Phase 1.9 audit**: harmless. `bin/cortex-audit-tier-divergence` inlines its canonical-rule logic and does not import `report._read_tier` or `common.read_tier`. The audit operates on `lifecycle/*/events.log` corpus contents, which Phase 1 does not modify; the audit returns the same result it returns on any other commit touching `report.py`. No phase reordering needed.
- **Dual-source mirror deletion is contributor-driven, not hook-driven**: `.githooks/pre-commit` Phase 2's `--diff-filter=ACMR` excludes Deletions, so staging only `git rm bin/cortex-audit-tier-divergence` does NOT trigger `just build-plugin`. The Phase 2 implementer MUST run `just build-plugin` after `git rm` and before `/cortex-core:commit` so rsync `--delete` removes the mirror and the deletion is staged alongside the canonical deletion. Pre-commit Phase 4 verifies index/working-tree symmetry — if both deletions are staged, Phase 4 passes; if only one is staged, Phase 4 detects drift and blocks. R10 encodes this contributor workflow.

## Changes to Existing Behavior

- **MODIFIED**: `cortex_command/overnight/report.py:535` calls `common.read_tier(name)` instead of the local `_read_tier(name)`. Behavior is identical on the current in-tree corpus; semantic difference on uppercase event-names is the explicit edge case above.
- **REMOVED**: `cortex_command/overnight/report.py:_read_tier` function (lines 746-778).
- **REMOVED**: `bin/cortex-audit-tier-divergence` and its mirror at `plugins/cortex-core/bin/cortex-audit-tier-divergence`.
- **REMOVED**: `tests/test_audit_tier_divergence.py` and `tests/fixtures/audit_tier/` directory.
- **REMOVED**: `tests/test_read_tier_parity.py` (after migrating cases (i)–(iii) and T-A/T-B to `tests/test_common_utils.py`).
- **REMOVED**: Pre-commit Phase 1.9 block at `.githooks/pre-commit:200-225`.
- **REMOVED**: Justfile recipe `audit-tier-divergence` at `justfile:363-365` (including the comment at line 363).
- **ADDED**: `tests/test_common_utils.py` gains a parametrized canonical-rule test reusing fixtures under `tests/fixtures/state/tier_parity/`, plus T-A/T-B key-name tests covering the `tier` vs `complexity` distinction.
- **ADDED**: `CHANGELOG.md` entry under `[Unreleased] → Removed` documenting the audit-gate retirement, naming retired files, the replacement (the migrated canonical-rule + key-name tests), and the absence of user-side cleanup.

## Technical Constraints

- **Dual-source enforcement** (`requirements/project.md:29`): edits to `bin/cortex-*` MUST be paired with the plugin-mirror sync. Pre-commit Phase 4 verifies index/working-tree symmetry of plugin mirrors but its rebuild step (Phase 3 → `just build-plugin`) only runs when Phase 2's `--diff-filter=ACMR` trigger fires; deletions do not fire Phase 2's trigger. For deletion-only commits affecting `bin/cortex-*`, the implementer MUST run `just build-plugin` after `git rm` and before `/cortex-core:commit` so the mirror deletion is staged before pre-commit's symmetry check runs.
- **Workflow trimming preference** (`requirements/project.md:23`): hard-deletion preferred over deprecation. CHANGELOG entry required for retired surfaces.
- **Lifecycle artifact location**: `tests/fixtures/state/tier_parity/<slug>/events.log` files are preserved as fixtures for the migrated canonical-rule cases. They live under `tests/fixtures/state/` not `tests/fixtures/audit_tier/` (the latter is the audit-gate-specific fixture tree being deleted).
- **Test discovery boundary**: `cortex_command/overnight/tests/test_report.py` lives under the package tree; `tests/test_common_utils.py` lives in the top-level test tree. Both run under `just test`.
- **outcome_router monkeypatch seam**: tests at `tests/test_outcome_router.py:85,306,352` and `cortex_command/overnight/tests/test_lead_unit.py:1666,1696,1731,1766,1805` patch `cortex_command.overnight.outcome_router.read_tier`. The consolidation does NOT affect these — the binding name in `outcome_router` is unchanged.
- **lru_cache contract** (`cortex_command/common.py:_read_tier_inner`): the cache key is `(events_path_str, exists, mtime_ns, size)` where `events_path_str = str(lifecycle_base / feature / "events.log")`. To avoid cross-test pollution, callers in tests MUST supply an absolute `lifecycle_base` (e.g., `tmp_path / "lifecycle"`) so the path-string varies per test. The pattern is established in `tests/test_lifecycle_state.py` and `tests/test_bin_lifecycle_state_parity.py`; R4 and R6 require migrated tests follow it. Optional belt-and-braces: an autouse `_read_tier_inner.cache_clear()` fixture (the cached inner is reachable via `read_tier.__wrapped__` at `common.py:469`).
- **MUST-escalation policy**: the MUST language in this spec (R4's mandatory `lifecycle_base` arg, R10's contributor `just build-plugin` step, Technical Constraints dual-source paragraph) is grandfathered prior to per-clause audit. The R4/R10 MUSTs are encoding contributor-workflow steps the pre-commit hook does not enforce automatically; effort=high dispatch evidence is not applicable because the failure mode is "implementer skips a manual step," not "Claude routes incorrectly." If a future audit finds these MUSTs unjustified, they soften per CLAUDE.md §"MUST-escalation policy."
- **Commit discipline**: phases land as separate commits. Phase 1 commit body subject ≤72 chars in imperative mood. Phase 2 commit body must also reference the CHANGELOG entry. Use `/cortex-core:commit` for both.

## Open Decisions

- None. All Open Questions raised in `research.md` were resolved during the spec interview; all critical-review objections were applied to the spec text.
