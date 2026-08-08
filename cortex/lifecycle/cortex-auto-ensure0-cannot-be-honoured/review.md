# Review: cortex-auto-ensure0-cannot-be-honoured (cycle 1)

Tier `moderate`, criticality `high` → **Stage 1 only**. Stage 2 (code quality) is complex-tier-only and does not run; the incidental quality checks that did run are recorded under Stage 1 Notes rather than as a Stage 2 rating.

**Reviewer independence — stated limitation.** This session's standing directive forbids dispatching sub-agents, so the review ran in the implementing context rather than in a fresh read-only reviewer. Every requirement below is therefore rated on **executed evidence** (a command and its observed output), not on reading the diff. Where the evidence was produced during Implement rather than re-run here, that is said so explicitly.

**Test baseline consumed**: `just test` → 8/8 suites passed, exit 0, run against `f88852bf`. The only later commit (`7dae58bf`) touches lifecycle markdown, so the baseline is current. Not re-executed by this review.

**Requirements loaded**: `cortex-load-requirements` → `COVERAGE:loaded`; `cortex/requirements/project.md`, `glossary.md`, `lifecycle.md`. Note the ticket declares three areas (`lifecycle`, `install`, `tests`) but `cortex/requirements/install.md` and `tests.md` do not exist — a structural absence research already recorded, not a load failure.

**Changed files** (`f50b0b51..HEAD`): `cortex_command/lifecycle/init_ensure.py`, `cortex_command/init/handler.py`, `cortex_command/lifecycle/tests/test_init_ensure.py`, `cortex_command/init/tests/test_handler_ensure.py`, `cortex/requirements/project.md`. No `plugins/` path appears — confirming the spec's Technical Constraint that neither module is a dual-source mirror.

## Stage 1 — Spec compliance

| # | Requirement | Rating | Evidence |
|---|---|---|---|
| 1 | Helper's probe removed | **PASS** | `grep -c _check_not_attached_worktree cortex_command/lifecycle/init_ensure.py` → `0`. Re-run at review time. |
| 2 | CLI-surface probe removed | **PASS** | `grep -c _check_not_attached_worktree cortex_command/init/handler.py` → `0`. Re-run at review time. |
| 3 | `--ensure` succeeds from an attached worktree, marker is the sole new path | **PASS** | Run in a real worktree of this repo at `f88852bf`: printed `exit=0`, and the `git status --porcelain --ignored` before/after diff's only added line was `> !! cortex/.cortex-init`. First attempt showed extra added lines (`.venv/`, `__pycache__/`, `_version.py`) — those were `uv`'s venv creation in a fresh worktree, not `ensure` writes; re-run with the venv pre-warmed isolated the criterion exactly as specified. |
| 4 | Uninitialized repo still refuses, including from a worktree | **PASS** | Scratch `git init` repo with no `cortex/`, invoked from an attached worktree of it: exit `2`, stderr `` `cortex init --ensure`: this repo is not yet initialized for cortex (no `cortex/`)… `` — contains `not yet initialized`. Case (iii) is demonstrably doing the guard's job. |
| 5 | `CORTEX_AUTO_ENSURE=0` silences the helper in a worktree | **PASS** | From the worktree: exit `0`, `git status --porcelain` printed nothing, and `cortex/.cortex-init` was **not** written. `cortex/requirements/project.md`'s opt-out parenthetical is now true as written. |
| 6 | Both test modules pass with pytest launched from inside a worktree | **PASS** | From the worktree: `29 passed`, exit `0`. Measured baselines it replaces: `test_handler_ensure.py` 19 failed / 3 passed, `test_init_ensure.py` 1 failed / 7 passed (20 failed / 10 passed combined). Count reconciles: 22 + 1 new = 23, and 8 − 2 deleted = 6. |
| 7 | Regression test pins CWD-independence | **PASS** | `test_ensure_is_cwd_independent_from_attached_worktree` exists and passes. **Mutation-verified**: reinstating an ambient-CWD probe at the top of `_run_ensure` made exactly this test fail (`ScaffoldError: mutation-check: invoked inside a git worktree`); removing it again made it pass, and `git diff --quiet cortex_command/init/handler.py` confirmed the file returned byte-identical. The pin is not self-sealing. |
| 8 | Tests pinning the deleted behavior are removed, not left asserting it | **PASS** | `grep -c test_r11a_worktree_attached_refusal` → `0`; `test_r11b_regular_checkout_baseline` → `0`. `grep -rn "invoked inside a git worktree" cortex_command/` → `0` hits, so no test anywhere still asserts the refusal. |
| 9 | Docstrings stop claiming a worktree refusal | **PASS** | `grep -ci worktree cortex_command/lifecycle/init_ensure.py` → `0`. |
| 10 | Supersede recorded where a contributor will look | **PASS** | `grep -c "attached worktree" cortex/requirements/project.md` → `1`; `grep -c '#273' cortex/requirements/project.md` → `1`. Both printed `0` on unmodified HEAD (checked during Plan), so the criterion could fail and did not. |

**No FAIL. No PARTIAL.**

### Notes (incidental quality observations, not a Stage 2 rating)

- **Scope beyond the plan's task text, correctly taken.** Task 2 also removed two residual claims the plan did not enumerate: `_run_ensure`'s docstring listed "worktree-attached refusal" among its `Raises`, and a second ordered-gate comment block (`handler.py:325`) still named it as step (b). Both would have left the file describing behavior it no longer has — exactly the class of defect that passes a reading review and fails an executing one. Dispatch letters were renumbered `(a)–(d)` consistently in both blocks; the five-case labels (i)–(v) were left alone as spec-referenced.
- **No dead imports.** `subprocess` and `Path` were removed from `init_ensure.py` (the probe was their only consumer) and retained in `handler.py` (still used by `_resolve_repo_root`). An AST-based unused-import scan over all four touched files reports nothing but `from __future__ import annotations`.
- **Release-type marker corrected pre-push.** The deletion commit was initially authored with `[release-type: minor]`; this is a bug fix, so the marker was removed by amend and the change takes the default patch bump. No push had occurred.
- **Deferred work the spec asked to be filed separately is still unfiled.** `enter.py:321-322` writes `index.md` and syncs the backlog before `:330` decides the state, so any surviving `ensure_code != 0` (case (iii), R19) still leaves a half-applied phase. The spec placed this in Non-Requirements with "File separately"; it survives this change untouched, as intended. Raising it at Complete rather than silently dropping it. Symptom 3 needs no new ticket — `cortex/requirements/lifecycle.md`'s own Open Questions already owns it.

## Requirements Drift

- **State**: `none`
- **Findings**: None. The one requirements clause this change touches — `cortex/requirements/project.md`'s `CORTEX_AUTO_ENSURE=0 opt-out` bullet — was updated as Requirement 10, so the requirements already capture the new behavior rather than lagging it. `lifecycle.md` and `glossary.md` contain zero mentions of `init-ensure`, `AUTO_ENSURE`, or the worktree refusal (`grep` → no matches), so neither carries a claim this change falsifies. The exit-2 cause list changed, and project.md now records it.
- **Update needed**: None

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
