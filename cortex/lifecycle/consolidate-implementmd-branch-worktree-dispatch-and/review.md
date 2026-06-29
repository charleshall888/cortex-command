# Review: consolidate-implementmd-branch-worktree-dispatch-and

## Stage 1: Spec Compliance

### Requirement 1: Inside-repo helper canonicalizes both sides
- **Expected**: A pure helper in `worktree.py` runs the containment check on the resolved worktree path AND the resolved repo root, via `Path.resolve()` + `relative_to`/`commonpath` (never `startswith`/`commonprefix`); a symlinked-root unit test proves the legitimate same-repo case is not flagged.
- **Actual**: `_is_worktree_inside_repo` (worktree.py:170-193) resolves BOTH operands (`worktree_path.resolve()` :187, `repo.resolve()` :188) and decides containment via `relative_to` over the resolved paths (:190), explicitly rejecting `startswith`/`commonprefix` in the docstring. `test_containment_symlinked_repo_root_not_flagged` (real on-disk symlink, `_repo_root` returns the unresolved symlink while branch (c) `.resolve()`s the worktree) and `test_branch_c_path_is_resolved` both pass.
- **Verdict**: PASS
- **Notes**: The both-operands-resolve closes the documented `_repo_root()`-unresolved vs `resolve_worktree_root`-resolved asymmetry.

### Requirement 2: Containment check folded into `create_worktree`, gating EVERY return path
- **Expected**: Check runs after `worktree_path`/`repo` are computed and resolved and BEFORE the idempotent `exists()` branch and the `git worktree add` branch; conditioned on same-repo; raises a containment-specific error (not the generic `worktree_creation_failed`).
- **Actual**: The guard sits at worktree.py:236-240, after `repo` (:225) and `worktree_path` (:227) are computed, and strictly before the idempotent `if worktree_path.exists():` at :243 and `git worktree add` at :299. It is gated on `not cross_repo` and raises `ValueError("worktree_escapes_repo: ...")`, distinct from the `worktree_creation_failed` at :313. Because it precedes creation, a failure leaves nothing on disk.
- **Verdict**: PASS
- **Notes**: Placement-before-idempotent-return is the load-bearing requirement and is met.

### Requirement 3: Discriminating exit-contract tests with negative controls and the idempotent path
- **Expected**: Parametrized coverage of (a) fresh same-repo success, (b) fresh-override escape asserting the containment-specific message, (c) pre-registered out-of-repo worktree (idempotent path), (d) resolver-unavailable failure, (e) cross-repo exempt success.
- **Actual**: All five present and passing — `test_containment_fresh_same_repo_ok` (a), `test_containment_fresh_override_escape` (b, asserts `"worktree_escapes_repo" in str(...)`), `test_containment_idempotent_registered_escape` (c, registers the out-of-repo worktree via `git worktree add` so `exists()` is True then asserts the containment message), `test_containment_repo_unresolvable` (d), `test_containment_cross_repo_exempt` (e). Bonus (f) symlink and (g) overnight same-repo escape further harden it.
- **Verdict**: PASS
- **Notes**: Case (c) is genuinely discriminating — it really registers the worktree so the idempotent early-return would fire absent the guard, and the message assertion distinguishes the containment raise from a generic create failure.

### Requirement 4: Step-v emit stays correctly gated (emit-gating guard)
- **Expected**: The `interactive_worktree_entered` emit fires only on success and is skipped on containment failure; structurally it sits on the success branch after the precondition/`EnterWorktree` success.
- **Actual**: implement.md step-iii halts on create failure ("Surface the stderr output to the user and exit §1a — do not proceed to handoff.", L119); a containment escape is exactly such a failure (exit 1). Operation 5 "Emit event" (L141-147) runs only "once the session CWD is rooted in the worktree (via `EnterWorktree` on the `selected` path, or the cd-shim on the `suppressed` path)". Requirement 3's exit-1-on-escape tests prove create halts before any rooting.
- **Verdict**: PASS

### Requirement 5: Heredoc removed — gated on the containment check existing
- **Expected**: The `python3 - <<'EOF'` block deleted from canonical and mirror; lands only with Requirement 2's check present.
- **Actual**: `grep -c "python3 - <<"` = 0 in both `skills/lifecycle/references/implement.md` and the mirror. Phase 1 (containment check, commit 804012d1) precedes the Phase 2 deletion, so no commit window lacks the check.
- **Verdict**: PASS

### Requirement 6: Branch/worktree narration routes on verb outputs
- **Expected**: `wc -l` ≤ 285, with all Requirement-7 locks intact.
- **Actual**: `wc -l skills/lifecycle/references/implement.md` = 277 (≤ 285). Narration consolidated onto `cortex-lifecycle-dispatch-choice`, `cortex-lifecycle-branch-mode`/`cortex-lifecycle-picker-decision` `{fire,reason}` outputs and the verbs; all locks below stay green.
- **Verdict**: PASS

### Requirement 7: All structural locks stay green, with discriminating acceptance for the unguarded ones
- **Expected**: The six named lock tests pass; `create_worktree` literal within ±60 of `EnterWorktree(`; §1 `command -v` and §1a step-iii both name `cortex-worktree-create`; `grep -c "bash -s --"` = 2; `grep -c "_interactive_overnight_check.sh"` ≥ 2.
- **Actual**: All six named tests plus the new contract test pass (58 passed). `create_worktree` at L117/L121 vs `EnterWorktree(` at L136 (within 19/15 lines). §1 gate `command -v cortex-worktree-create` (L51) and §1a step-iii `cortex-worktree-create --feature interactive-{slug}` (L114) agree. `bash -s --` count = 2; `_interactive_overnight_check.sh` count = 2.
- **Verdict**: PASS
- **Notes**: The new `bash -s -- == 2` count lock (`test_sidecar_invocation_form_bash_s_count`) is present in the contract test and passing.

### Requirement 8: Agent-owned menu-mutation MECHANICS preserved
- **Expected**: Both the option-demotion mechanic (strip `(recommended)` / demote on dirty tree) and the runtime-probe hide instruction (remove the worktree option from the array on exit 1) remain — not merely the fail-open diagnostic.
- **Actual**: Demotion mechanic present at L46 ("strip the `(recommended)` suffix from that option's label if present" + the warning-prefix prepend). Runtime-probe hide present at L57 ("remove `Implement on feature branch with worktree` from the options array").
- **Verdict**: PASS

### Requirement 9: Step-v dash/slash bug fixed by dash RE-RESOLVE
- **Expected**: cd-shim (op 2), `EnterWorktree` path (op 4), fallback (op 5) re-resolve with the dash `interactive-{slug}` form; `grep -c "cortex-worktree-resolve interactive/{slug}"` = 0; a unit test proves the dash form resolves flat while slash nests.
- **Actual**: Slash-form resolve count = 0; dash-form resolve count = 3 (L129 cd-shim, L139 EnterWorktree resolved-path, L149 fallback). `test_interactive_dash_vs_slash_resolve` asserts dash → `.claude/worktrees/interactive-myslug` and slash → `.claude/worktrees/interactive/myslug` (passing). Legitimate branch-name docs (`interactive/{slug}` at L25/L117) are not resolve calls and stay.
- **Verdict**: PASS

### Requirement 10: Stale heading guardrail not applied; real locks documented
- **Expected**: None of the five overnight-pinned headings introduced; `grep -c "Check Criticality"` = 0; the real implement.md headings intact.
- **Actual**: `grep -c "Check Criticality"` = 0. Real headings present and intact: `### 1. Pre-Flight Check`, `### 1a. Interactive Worktree Creation (Alternate Path)`, `### 2. Task Dispatch`, `### 3. Rework (Review Re-Entry)`, `### 4. Transition`.
- **Verdict**: PASS

### Requirement 11: L130 safe rewrite (triple-collision)
- **Expected**: After the L124-132 trim, the literal `create_worktree` token survives in §1a and `test_lifecycle_enterworktree_callsites.py` passes; the branch-name doc stays `interactive/{slug}`.
- **Actual**: `create_worktree` token = 2 in §1a (L117, L121); `test_lifecycle_enterworktree_callsites.py` passes. L117 retains the branch-name prose "resolves the branch as `interactive/{slug}`" while the resolve-call args were de-slashed.
- **Verdict**: PASS

### Requirement 12: Mirror regenerated and committed together; kept-pauses line updated explicitly
- **Expected**: `diff -q` canonical vs mirror = no difference; `just test` green; kept-pauses implement.md anchor repointed to the relocated pause; docstrings updated if §1a sub-steps renumbered.
- **Actual**: `diff -q` reports no difference for both implement.md and kept-pauses.md mirrors. kept-pauses anchor repointed `50 → 37`; `test_lifecycle_kept_pauses_parity.py` passes (37 lands within the §1 picker region, well inside the ±35 tolerance). Sub-steps did not renumber (still iii / step v), so the `worktree_precondition.py` "§1a step v" and `worktree_create_cli.py` "§1a step iii" docstring references remain accurate.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: `_is_worktree_inside_repo` follows the established `_`-prefixed private-helper convention in worktree.py (`_repo_root`, `_main_worktree_root`, `_branch_exists`, `_resolve_branch_name`, `_find_git_repo`). The `worktree_escapes_repo` error token mirrors the existing `worktree_creation_failed` token shape. Consistent.
- **Error handling**: Appropriate and well-discriminated — the containment failure raises a distinct `ValueError("worktree_escapes_repo: ...")` separate from the generic `worktree_creation_failed`, so the CLI wrapper's exit-1 path is preserved while remaining message-distinguishable (the basis of test 3b/3c assertions). Because the check precedes creation, a failure leaves no dangling worktree — strictly better than the deleted post-create heredoc. The resolver-unavailable path (3d) surfaces the underlying `CalledProcessError` as a loud non-zero exit, which is consistent.
- **Test coverage**: All plan verification steps executed; 58 tests pass across the seven named suites plus the new containment block. The containment tests are genuinely discriminating: case (c) registers a real out-of-repo worktree via `git worktree add` so `exists()` is True and the porcelain idempotent return would fire absent the guard; (f) uses a real symlink to prove both-operands-resolve; (e) is a true negative control (cross-repo exempt); (g) locks the overnight same-repo path.
- **Pattern consistency**: The helper's both-operands-resolve matches `resolve_worktree_root`'s `.resolve()` intent and closes its asymmetry; the dash re-resolve matches create's materialized directory `interactive-{slug}`; `relative_to` over resolved operands aligns with the project's CVE-class avoidance of `startswith`/`commonprefix`. The `${CLAUDE_SKILL_DIR}/references/` sidecar form (SP001/SP002) is preserved (2 occurrences), and no `import cortex_command` was introduced into implement.md (L201).

## Requirements Drift
**State**: detected
**Findings**:
- `create_worktree` now enforces an inside-repo containment invariant (`worktree_escapes_repo`) on EVERY same-repo return path — fresh create AND both idempotent early-returns. Per the spec's Risk/Changes section this guard governs the overnight orchestrator's same-repo `create_worktree` path (`repo_path=None`, `session_id` set), not just the interactive picker path (locked by `test_containment_overnight_same_repo_override_escape`). project.md's Architectural Constraints document the `EnterWorktree` authorization surface (L41) and the destructive-op uncommitted-state skip (L58) but record no worktree path-containment / `CORTEX_WORKTREE_ROOT`-escape invariant; this new enforced contract is uncaptured. (Observation only — does not affect the verdict; the spec's Proposed ADR section deliberately judged this below the ADR gate, but project.md records constraints of comparable granularity, e.g. SP001/SP002 and the wheel-binstub invocation rule.)
**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: Architectural Constraints (append as a new bullet, near the `EnterWorktree` authorization surface bullet, L41)
**Content**:
```markdown
- **Worktree containment invariant**: `create_worktree` (`cortex_command/pipeline/worktree.py`) enforces that a same-repo worktree resolves inside the repo root. The check (`_is_worktree_inside_repo`, resolving BOTH operands and deciding via `relative_to` — never `startswith`/`commonprefix`) runs BEFORE the idempotent `worktree_path.exists()` early-returns and the `git worktree add` branch, so it gates every same-repo return path; an out-of-repo `CORTEX_WORKTREE_ROOT` override (stale or fresh) raises a containment-specific `worktree_escapes_repo` ValueError → CLI exit 1, leaving nothing on disk. The cross-repo / `$TMPDIR` overnight branch (`repo_path` set) is legitimately outside the repo and is exempt; the same-repo overnight path (`repo_path=None`, `session_id` set) is NOT exempt and is governed by the guard. Contract is pinned by the `test_containment_*` block in `tests/test_worktree.py`.
```

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
