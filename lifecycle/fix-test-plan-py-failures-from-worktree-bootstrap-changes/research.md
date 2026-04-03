# Research: fix-test-plan-py-failures-from-worktree-bootstrap-changes

## Codebase Analysis

### Production code (after commit `1bd7bde`)

`claude/overnight/plan.py` changed three `subprocess.run` calls:

- **Home-repo prune** (line 365): `subprocess.run(["git", "worktree", "prune", "--expire", "now"], cwd=repo_root)`
- **Home-repo worktree add** (lines 389-393): Added `cwd=repo_root` kwarg alongside existing `check=True`
- **Cross-repo prune** (line 441): `subprocess.run(["git", "worktree", "prune", "--expire", "now"], cwd=repo_path)`

### Failing tests in `claude/overnight/tests/test_plan.py`

All three failures are in `TestInitializeOvernightState`:

**1. `test_git_worktree_prune_called` (lines 90-96)**
- Old assertion: `call(["git", "worktree", "prune"])`
- Needs: `call(["git", "worktree", "prune", "--expire", "now"], cwd=Path.cwd().resolve())`
- Both the command list (added `--expire now`) and kwargs (added `cwd`) changed

**2. `test_git_worktree_add_called_with_correct_args` (lines 98-115)**
- Old assertion: `call([...], check=True)` — no `cwd` kwarg
- Needs: Add `cwd=Path.cwd().resolve()` to the `call(...)` kwargs
- Command list unchanged; only the `cwd` kwarg is new

**3. `test_cross_repo_prune_called_with_cwd` (lines 532-558)**
- Old filter: `c.args[0] == ["git", "worktree", "prune"]` (3-element list)
- Needs: `c.args[0] == ["git", "worktree", "prune", "--expire", "now"]` (5-element list)
- The `cwd == cross_repo_path` check is already present and correct

### Adjacent tests — confirmed not broken

Tests using `cmd[:3]` prefix matching are unaffected by the added `--expire now` args:

- `test_prune_called_before_add` (lines 117-135): prefix match `cmd[:3] == ["git", "worktree", "prune"]` still works
- `test_stale_worktree_directory_is_removed_before_add` (lines 154-179): prefix match on add
- `test_stale_branch_deleted_before_worktree_add` (lines 326-368): prefix match throughout
- `test_cross_repo_worktree_add_called_with_cwd` (lines 472-505): prefix match on add + separate cwd check
- `test_cross_repo_stale_branch_cleanup_with_cwd` (lines 560-586): filters on `git branch -D`, unrelated
- `test_cross_repo_prune_failure_logs_warning_and_continues` (lines 592-627): no assertion on prune command
- `test_cross_repo_base_ref_origin_head_fallback` (lines 636-680): no assertion on prune signature

### `_cross_repo_side_effects` helper (lines 435-470)

Builds positional `MagicMock(returncode=0)` objects consumed in call order. The mock sequence maps correctly to the post-`1bd7bde` call sequence. **No functional change needed.** Line 439 comment ("Home-repo git worktree prune (no cwd)") is stale — production now always passes `cwd` — but the comment is not load-bearing.

### `_run` helper and `cwd` value

The `_run` helper (used by tests 1 and 2) does not pass `project_root` to `initialize_overnight_state`. When `project_root` is None, production defaults to `Path.cwd().resolve()` as `repo_root`. The test assertions should use `Path.cwd().resolve()` as the expected `cwd` value.

## Open Questions

(none — all assertion changes are mechanical and fully determined by the production code)
