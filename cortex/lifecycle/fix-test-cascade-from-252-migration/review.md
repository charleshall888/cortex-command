# Review: fix-test-cascade-from-252-migration

**Cycle**: 1
**Reviewer**: Claude Code (harness-review skill)
**Date**: 2026-05-25

---

## Stage 1: Spec Compliance

### R1 — SourceFileLoader rewrites for four affected files

**Rating: PASS**

AST acceptance checks run against all four files:

- `tests/test_resolve_backlog_item.py`: imports `cortex_command.backlog.resolve_item as _resolver_module`; zero `SourceFileLoader` calls — PASS/PASS
- `tests/test_load_parent_epic.py`: imports `cortex_command.backlog.load_parent_epic as load_parent_epic_module`; zero `SourceFileLoader` calls — PASS/PASS
- `tests/test_superseded_frontmatter_tolerance.py`: imports both `_load_parent_epic_module` and `_resolve_item_module`; zero `SourceFileLoader` calls — PASS/PASS
- `tests/test_variant_a_writer_sites_baseline.py`: imports `cortex_command.lifecycle.complexity_escalator as _escalator_module`; zero `SourceFileLoader` calls; canonical `@pytest.fixture(scope="module") def escalator_module(): return _escalator_module` shape retained — PASS/PASS

Module-private symbol preservation verified for each:
- `test_resolve_backlog_item.py`: `resolver` fixture returns the module alias; tests access `resolver.slugify`, `resolver._item_title`, `resolver._parse_frontmatter`, `resolver._resolve_*` via the alias.
- `test_load_parent_epic.py`: `load_parent_epic_module` alias; `_load_script_module()` shim at ~L419 returns the module directly, preserving the `_load_script_module().normalize_parent` access shape in `test_drift_normalize_parent`.
- `test_superseded_frontmatter_tolerance.py`: both module aliases expose `_parse_frontmatter`; used at L125 and L204 respectively.
- `test_variant_a_writer_sites_baseline.py`: fixture exposes the escalator module; unit tests access it through the `escalator_module` fixture.

### R2 — Subprocess fixes for eight affected files

**Rating: PASS**

`pytest tests/test_resolve_backlog_item.py tests/test_load_parent_epic.py tests/test_check_prescriptive_prose.py tests/test_commit_preflight.py tests/test_superseded_frontmatter_tolerance.py tests/test_variant_a_writer_sites_baseline.py tests/test_clarify_critic_alignment_integration.py tests/test_cortex_morning_review_gc_demo_worktrees.py` exits 0 with 104 tests passed, no FAILED or ERROR lines.

Per-callsite verification:

**2a. Default `-m` invocation** — confirmed in all seven files:
- `test_resolve_backlog_item.py`: `[sys.executable, "-m", "cortex_command.backlog.resolve_item", *args]`
- `test_load_parent_epic.py` (`_run` and `_run_no_env`): `[sys.executable, "-m", "cortex_command.backlog.load_parent_epic", slug]`
- `test_superseded_frontmatter_tolerance.py`: `load_parent_epic` and `resolve_item` callsites both use `-m` form
- `test_check_prescriptive_prose.py`: two callsites use `[sys.executable, "-m", "cortex_command.lint.prescriptive_prose", ...]`
- `test_clarify_critic_alignment_integration.py`: `[sys.executable, "-m", "cortex_command.backlog.load_parent_epic", slug]`
- `test_variant_a_writer_sites_baseline.py`: three callsites use `[sys.executable, "-m", "cortex_command.lifecycle.complexity_escalator", ...]`
- `test_cortex_morning_review_gc_demo_worktrees.py`: `_run_gc` uses `[sys.executable, "-m", "cortex_command.overnight.gc_demo_worktrees", active_session_id]`

**2b. Helper-split for `test_commit_preflight.py`** — confirmed:
- `_invoke_module` at L93: uses `[sys.executable, "-m", "cortex_command.commit.preflight"]`; consumed by `test_normal_repo_emits_valid_json`, `test_bare_repo_exits_3`, `test_empty_repo_emits_empty_repo_note`, `test_binary_diff_no_crash`
- `_invoke_wrapper` at L113: uses `[str(SCRIPT_PATH)]`; consumed only by `test_shim_records_invocation` (L302)
- Both helpers carry docstrings explaining their purpose and the wrapper-shim dependency

**2c. SCRIPT_PATH re-point for `test_git_env_hardening`** — confirmed:
- `_PYTHON_SCRIPT_PATH = REPO_ROOT / "cortex_command" / "commit" / "preflight.py"` defined at L340 with inline comment explaining the #252 reason
- `test_git_env_hardening` at L419 reads `_PYTHON_SCRIPT_PATH` (L436-437); the `SCRIPT_PATH` constant at L43 still points at the bash wrapper (used only by `_invoke_wrapper`)

**Implementer-flagged deviation 1 (Task 7)**: The `body_placeholder` string was corrected from `` `bin/cortex-load-parent-epic` `` to `` `cortex-load-parent-epic` `` in `_build_dispatch_prompt`. This matches the canonical template string at `skills/refine/references/clarify-critic.md:65`. The fix was legitimately masked by the earlier wrapper-crash failure. The correction brings the test's string comparison into agreement with the canonical doc it reads — no spec violation; this is an incidental defect that the subprocess fix unmasked.

**Implementer-flagged deviation 2 (Task 8)**: Six `@pytest.mark.skipif(sys.platform == "win32", ...)` decorators were removed from `test_cortex_morning_review_gc_demo_worktrees.py`. The skip reason was `"bash-only script; not supported on Windows"`. After `-m` conversion the test no longer invokes the bash wrapper, so the Windows exclusion is no longer correct. The removal is justified and within the scope of the Task 8 conversion.

### R3 — `id(tmp_path)` cache-key fix at all 7 parity sites

**Rating: PASS**

`grep -rnE "cache_key = \(id\(tmp_path\)" tests/` returns no matches (exit code 1).

All seven files verified:
- `test_cortex_auto_bump_version_parity.py:221`: `dict[tuple[str, str], ...]`, L230: `cache_key = (str(tmp_path), case)`
- `test_cortex_backlog_ready_parity.py:176`: `dict[tuple[str, str], ...]`, L190: `cache_key = (str(tmp_path), case)`
- `test_cortex_complexity_escalator_parity.py:154`: `dict[tuple[str, str], ...]`, L168: `cache_key = (str(tmp_path), case)`
- `test_cortex_lifecycle_counters_parity.py:154`: `dict[tuple[str, str], ...]`, L168: `cache_key = (str(tmp_path), case)`
- `test_cortex_lifecycle_state_parity.py:146`: `dict[tuple[str, str], ...]`, L156: `cache_key = (str(tmp_path), case)`
- `test_cortex_load_parent_epic_parity.py:166`: `dict[tuple[str, str], ...]`, L171: `cache_key = (str(tmp_path), case)`
- `test_cortex_log_invocation_parity.py:336`: `dict[tuple[str, str], ...]`, L370: `cache_key = (str(tmp_path), case)`

### R4 — Closeout signal

**Rating: PASS**

Full suite run (`1488 passed, 27 skipped, 1 xfailed`) with exactly one failure: `tests/test_log_invocation_perf.py::test_log_invocation_fast_path_budget` — the documented pre-existing excluded failure.

Direct pytest invocation check: `.venv/bin/pytest tests/ --tb=no -q --no-header 2>&1 | grep -E "^(ERROR|FAILED) " | grep -v "tests/test_log_invocation_perf\.py" | wc -l` = 0.

### R5 — No production-side changes outside test infrastructure

**Rating: PASS**

`git diff --name-only main...HEAD -- cortex_command/ bin/ skills/ hooks/ claude/ pyproject.toml justfile | grep -vE '^cortex_command/dashboard/tests/' | wc -l` = 0.

`git diff --name-only main...HEAD -- plugins/ | grep -vE '^plugins/[^/]+/(skills|hooks|bin)/' | wc -l` = 0.

---

## Stage 2: Code Quality

All requirements PASS; proceeding to Stage 2.

### Naming conventions

Consistent with project patterns:
- `_invoke_module` / `_invoke_wrapper` naming follows the `_run` / `_run_no_env` helper naming convention used throughout the test suite
- `_PYTHON_SCRIPT_PATH` follows the ALL_CAPS module-level constant convention; the underscore prefix is appropriate for a test-file-scoped constant not intended for export
- Module aliases (`_resolver_module`, `_escalator_module`, `load_parent_epic_module`) match the Task 15 canonical model and the names already present in the test files

### Error handling

Appropriate for the context:
- `_invoke_module`/`_invoke_wrapper` use `check=False` (correct — callers assert on returncode)
- `_run_gc` docstring explains the stripped-env hermeticity intent
- The Task 7 body_placeholder string fix means `_build_dispatch_prompt`'s `.replace()` call now matches the canonical template; previously it would silently fail to substitute (the pre-fix string was never present in the template)

### Test coverage

All 11 plan tasks completed and checked off. Per the plan's Task 11 verification: `just test` exits 0 OR failure surface exactly equals `test_log_invocation_perf`. Confirmed — the plan-level closeout acceptance is met.

### Pattern consistency

The implementation follows the canonical Task 11/12/15 model established during #252:
- Direct module import + fixture returning the module alias (Tasks 1–4 match Task 15's `test_complexity_escalator.py:34,40–43`)
- `-m` subprocess invocation throughout (Tasks 5–8)
- `str(tmp_path)` cache key with `dict[tuple[str, str], ...]` annotation (Tasks 9–10 match `test_cortex_commit_preflight_parity.py:317`)

The `_load_script_module()` shim in `test_load_parent_epic.py:419` that wraps `return load_parent_epic_module` is a functional one-liner preserving the pre-existing call shape in `test_drift_normalize_parent`. This avoids touching the test's assertion logic for a pattern that is already correct. It is slightly redundant — a direct reference would be cleaner — but not a defect.

One minor style observation: `tests/test_cortex_morning_review_gc_demo_worktrees.py:143` has an extra blank line between the `_run_gc` function body and `test_clean_matching_worktree_is_removed` (two blank lines followed by a blank line from removed `@pytest.mark.skipif`). This is cosmetic and does not affect behavior.

---

## Requirements Drift

**State**: none

**Findings**:
- None

**Update needed**: None

---

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
