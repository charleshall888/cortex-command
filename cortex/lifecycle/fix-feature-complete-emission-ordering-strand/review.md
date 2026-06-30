# Review: fix-feature-complete-emission-ordering-strand

## Stage 1: Spec Compliance

### Requirement R1: Narrow Branch 2 to genuinely-done states
- **Expected**: `classify()` triggers Branch 2 on `(W ∨ H)` and returns `already_complete` unless a retryable interactive finalization is detected (¬H ∧ merge-anchor row ∧ commit-artifacts:true ∧ committable ∧ valid-retry-target). Seven parametrized real-repo cases covering all carve-outs and the positive fall-through.
- **Actual**: `complete_route.py` lines 584–599 implement the `(W ∨ H)` trigger with the five-condition `retryable` conjunction exactly as specified. `_build_already_complete` (no-repo, `merge_anchor:"merge"`) stays green via the not-committable carve-out. All seven `_BRANCH2_CASES` use `_init_repo` real repos. Case 7 (`feature_branch_no_pr_json`) explicitly asserts `forbidden_route="first_run"`.
- **Verdict**: PASS

### Requirement R2: Commit-failed retry routes via existing routes (no new route)
- **Expected**: Route enumeration stays at 12. A commit-failed-on-main state routes `on_main`/`step9` (not `already_complete`). `test_twelve_routing_branches_covered` still asserts 12.
- **Actual**: `_ROUTE_CASES` in `test_lifecycle_complete_state_routing.py` has 12 entries; `test_twelve_routing_branches_covered` asserts `len(_ROUTE_CASES) == 12`. `test_classify_recovery_commit_failed_then_retry` drives Stage 1 (uncommitted merge-anchor row + committable delta) and asserts `on_main`/`step9` — the discriminating assertion that fails against the un-narrowed code.
- **Verdict**: PASS

### Requirement R3: Read-only, graceful, same-root, same-detection signal reads
- **Expected**: Zero `events.log` writes on every route. No `git diff HEAD`, no `collect_paths`, no `stage_artifacts` import. `_head_has_feature_complete` uses `git rev-parse --show-prefix` for git-top-relative path. Same root throughout. Nested-cortex-root H test. Stale-.git-file no-traceback test.
- **Actual**: `grep -n 'git diff HEAD|collect_paths|stage_artifacts' complete_route.py` returns nothing. `--show-prefix` present at line 270. `_finalization_committable` uses `git status --porcelain --` with scoped pathspecs (`cortex/lifecycle/{slug}/`, `cortex/backlog/index.md`, drift paths) — never events.log-only, never pathspec-less. Req 1b preserved across all routes (branch-2 parametrized test asserts `after == before`). `test_branch2_nested_cortex_root_H_uses_show_prefix` places root at `gitroot/sub/` and verifies H=True via the prefix path. `test_branch2_stale_git_file_no_traceback` confirms graceful degradation. Two grep-guard tests (`test_classify_uses_porcelain_not_git_diff_head`, `test_classify_does_not_import_collect_paths`) enforce the R3 contracts durably.
- **Verdict**: PASS

### Requirement R4: Idempotent Step-11 emission guard
- **Expected**: `complete.md` Step 11 gains a JSON-line-parse idempotent-skip guard (not a substring grep). Guard is prose-only soft routing with no new MUST/CRITICAL language. Canonical and mirror are byte-identical after `just build-plugin`.
- **Actual**: `complete.md` lines 159–160 add the idempotent-skip guard: "parse each line of the working-tree `events.log` as a JSON object and check the `event` field... Use a JSON-line parse (not a substring search)". No MUST/CRITICAL language introduced. `diff skills/lifecycle/references/complete.md plugins/cortex-core/skills/lifecycle/references/complete.md` returns empty — byte-identical.
- **Verdict**: PASS

### Requirement R5: Discriminating commit-failure-recovery round-trip test
- **Expected**: A behavioral test drives commit-failed → `on_main`/step9 → committed → `already_complete`; asserts exactly one `feature_complete` row in HEAD. The Stage-1 `on_main` assertion is the discriminator (fails against un-narrowed code).
- **Actual**: `test_classify_recovery_commit_failed_then_retry` in `test_complete_route.py` implements both stages with a real repo. Stage 1 asserts `on_main`/`step9` with a committable `cortex/backlog/index.md` delta to ensure `retryable=True`. Stage 2 commits and asserts `already_complete`. Convergence check: reads HEAD's events.log via `git show HEAD:<path>` and asserts `'"event": "feature_complete"'` count == 1. Scope note (classify is read-only, not running Step 11) is documented in the test docstring.
- **Verdict**: PASS

### Requirement R6: Record the committed-iff-complete invariant in ADR-0004
- **Expected**: A concise amendment subsection in `cortex/adr/0004-*.md` stating the committed-iff-complete refinement and its carve-outs; no duplicate normative statement in `complete.md`/`project.md`; no false attribution to ADR-0004's prior text.
- **Actual**: Amendment subsection "Committed-iff-complete invariant for re-invocation routing" is present. It correctly states ADR-0004's prior position (merge-is-terminal; events.log canonical; no prior claim about uncommitted working-tree rows). The five-condition retryable check and rejected alternatives (two-commit, emit-then-rollback) are correctly described. Five of six carve-out bullets are accurate. However, the **"Missing anchor → `review` phase"** bullet contains two factual errors: (1) it says "no `feature_complete` row is present at all" — the carve-out is actually about a `feature_complete` row with an **absent** `merge_anchor` field (which defaults to `"review"` via `ev.get("merge_anchor", "review")`); (2) it says "the router returns `review` to continue forward, not `already_complete`" — this contradicts the section header ("shapes that still route `already_complete`"), misstates the implementation (this shape routes `already_complete`), and references a non-existent route name. The code and tests correctly implement this case (test case `uncommitted_no_anchor` asserts `already_complete`); the error is documentation-only. No duplicate normative statement in `complete.md` or `project.md`.
- **Notes**: Documentation-only defect in a should-have requirement. The five-condition invariant and four other carve-outs are correctly recorded. The no-false-attribution criterion is satisfied.
- **Verdict**: PARTIAL

### Requirement R7: Golden-route-table and `nothing_staged` note coherence (incl. precedence test)
- **Expected**: `test_feature_complete_precedes_pr_state` updated to use `_init_repo` + committed row (H=True → retryable=False via `not _h`). `nothing_staged` note correct under narrowed Branch 2. Twelve-route count unchanged.
- **Actual**: `test_feature_complete_precedes_pr_state` (lines 621–671 in `test_lifecycle_complete_state_routing.py`) uses `_init_repo`, commits the `feature_complete` row so H=True, and asserts `already_complete`/`step12`. Docstring explicitly states "the committed-row construction, not the no-repo accident... is what proves the short-circuit fires." The `nothing_staged` note at `complete.md:178` is broadened to: "common on the worktree path post-merge, and on the on_main commit-retry path when the finalization set was already committed in a prior attempt." Twelve-route count asserts 12. Mirror byte-identical.
- **Verdict**: PASS

---

## Stage 2: Code Quality

- **Naming conventions**: All three new helpers (`_head_has_feature_complete`, `_drift_files_from_review`, `_finalization_committable`) follow the module's `_verb_noun` / `_verb_adjective` private-helper naming pattern. Variables `complete_seen`, `has_merge_anchor_row`, `_h`, `retryable` are clear and consistent. `current_branch` hoisted to a single declaration before Branch 2 (line 559), reused cleanly in both the retryable guard and Branch 3.

- **Error handling**: Every new git call degrades toward the safe direction: `_head_has_feature_complete` returns False on `None` (git failure/no-commits/git-absent); `_finalization_committable` returns False on `None` (git failure → already_complete = today's behavior); `_drift_files_from_review` returns `[]` on file absence or read error (reduces pathspec list only, never breaks the probe). Python short-circuit evaluation means `_finalization_committable` is not called when `not _h` is False or `has_merge_anchor_row` is False, avoiding unnecessary git calls on the fast-path. `read_commit_artifacts` defaults to True on absence, which is correct (true → retryable can still be true, but `_finalization_committable` guards the unsafe direction).

- **Test coverage**: All seven carve-out matrix cases use `_init_repo` real repos (not `_make_root`), making them discriminating on committed-vs-uncommitted state rather than the no-repo accident. The nested-cortex-root test (`test_branch2_nested_cortex_root_H_uses_show_prefix`) is the critical structural discriminator for the git-top-relative H path — without `--show-prefix`, the test would route `on_main` instead of `already_complete`. The stale-.git-file test confirms graceful degradation of all three new signals simultaneously. The existing `_GOLDEN` table and `_ROUTE_CASES` tables are untouched. The valid-retry-target guard is explicitly tested (case 7 asserts `forbidden_route="first_run"` with a gh stub returning 0 orphan matches).

- **Pattern consistency**: `_head_has_feature_complete` uses the same line-wise `json.loads` skip-on-`JSONDecodeError` loop as the working-tree scan above it — satisfying the spec's "torn final row is treated identically by both" invariant. The `--show-prefix` / git-top-relative path convention matches `bare_python_import.py` and siblings. `_git_out` helper reused throughout. No `stage_artifacts` import; `_drift_files_from_review` is a minimal inline read+regex matching the spec's weight constraint. The `<!-- finalization-commit-step -->` region in `complete.md` is not touched by the Step-11 guard edit (guard sits before line 161 where the marker opens), so `test_complete_md_finalization_commit.py`'s positive/negative token guards remain satisfied.

---

## Requirements Drift
**State**: none
**Findings**:
- None
**Update needed**: None

---

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": ["ADR-0004 'Missing anchor → review phase' carve-out bullet has two factual errors: (1) it says 'no feature_complete row is present at all' but the carve-out is for a feature_complete row with absent merge_anchor field (which defaults to \"review\" via ev.get(\"merge_anchor\", \"review\")); (2) it says 'the router returns review to continue forward, not already_complete', which contradicts the section header 'shapes that still route already_complete' and misstates the implementation — this shape routes already_complete. Documentation-only defect in a should-have requirement; code and tests correctly implement the missing-anchor case."], "requirements_drift": "none"}
```
