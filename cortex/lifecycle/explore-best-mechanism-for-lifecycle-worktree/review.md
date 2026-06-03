# Review: explore-best-mechanism-for-lifecycle-worktree

## Stage 1: Spec Compliance

### R1 — `cortex init` writes no authorization clause to consumer `CLAUDE.md`
- **Expected**: After `cortex init` in a fence-free repo, `grep -c "lifecycle-worktree-auth" CLAUDE.md` = 0 (file untouched by init).
- **Actual**: `grep -c "lifecycle-worktree-auth" CLAUDE.md` = 0 in this repo (own fence removed); handler.py no longer calls any fence-writing step (`grep -cE "ensure_claude_md_authorization|..." handler.py` = 0).
- **Verdict**: PASS
- **Notes**: The sole write surface (`ensure_claude_md_authorization`) is deleted from scaffold.py and unreferenced in handler.py; init can no longer touch any consumer `CLAUDE.md`.

### R2 — Fence functions, constants, and revoke-only liveness helpers removed from scaffold.py
- **Expected**: `grep -cE "ensure_claude_md_authorization|revoke_claude_md_authorization|_find_claude_md_auth_fence|_render_claude_md_auth_block|_read_claude_md_auth_template|_CLAUDE_MD_AUTH|def live_interactive_sessions|def _pid_is_live" scaffold.py` = 0; `live_interactive_sessions`/`_pid_is_live` have no other caller.
- **Actual**: grep = 0. Whole-tree check `grep -rn "live_interactive_sessions|_pid_is_live" cortex_command/ --include="*.py"` returns nothing (their only caller, the revoke precondition in handler.py, was removed in Task 1 before deletion).
- **Verdict**: PASS

### R3 — Two CLI verbs removed; init mutex group is 3 verbs; `--force` help drops the revoke reference
- **Expected**: `grep -cE "verify-worktree-auth|revoke-worktree-auth" cli.py` = 0; `cortex init --verify-worktree-auth` exits non-zero.
- **Actual**: cli.py grep = 0; init_ensure.py namespace fields removed (grep = 0). The mutex group `init.add_mutually_exclusive_group()` now holds exactly `--update`, `--unregister`, `--ensure`. `--force` help text reads "no effect with --update or --unregister" — the revoke reference is gone. `cortex init --verify-worktree-auth` exits 2 (argparse "unrecognized arguments").
- **Verdict**: PASS

### R4 — Template deleted and removed from init-artifacts hash inputs
- **Expected**: `test -f .../claude_md_authorization.md` non-zero (absent); `grep -c "claude_md_authorization.md" scaffold.py` = 0.
- **Actual**: Template file absent (test exit 1); scaffold.py reference count = 0. `test_init_artifacts_hash_inputs.py` passes — the entry drops symmetrically from both `declared` (`_HASH_INPUT_TEMPLATES`) and `discovered` (os.walk), no golden hash to edit.
- **Verdict**: PASS

### R5 — handler.py steps 0b/0c/6b and the `_run_ensure` fence call removed
- **Expected**: `grep -cE "ensure_claude_md_authorization|revoke_worktree_auth|verify_worktree_auth" handler.py` = 0.
- **Actual**: grep = 0.
- **Verdict**: PASS

### R6 — Fence/verify tests deleted; dependent tests updated; suite green
- **Expected**: Deleted modules absent; updated tests pass; `just test` exits 0.
- **Actual**: `test_init_claude_md_authorization.py` and `test_init_verify_worktree_auth.py` are absent. `test_init_artifacts_hash_inputs.py`, `test_handler_ensure.py`, `test_init_ensure.py` pass. The reviewed subset (57 tests across the lifecycle/init/snapshot suites) passed; no `.py` file references a deleted symbol.
- **Verdict**: PASS

### R7 — Existing consumer fences handled per §4 (default: left-stranded); init-hash flip is the migration carrier
- **Expected**: Chosen behavior implemented + documented; if left-stranded, no code path removes a consumer fence (`grep -rc "revoke_claude_md_authorization" cortex_command/` = 0).
- **Actual**: `revoke_claude_md_authorization` is fully deleted (no removal path survives), consistent with the left-stranded default. This repo's OWN fence was deleted directly (Task 5, our own tree — distinct from the consumer left-stranded path). ADR-0008 records the model; the suppressed-picker edge case documents the stranded-fence handling.
- **Verdict**: PASS

### R8 — implement.md §1a: keep `EnterWorktree` on picker-fired path, drop only the verify probe, retain the precondition probe, route suppressed-picker structurally to cd-shim
- **Expected**: `grep -c "EnterWorktree"` ≥ 1; `grep -c "verify-worktree-auth"` = 0; `grep -c "cortex-worktree-precondition"` ≥ 1; §1a contains an explicit suppressed-picker→cd-shim branch.
- **Actual**: EnterWorktree = 11; verify-worktree-auth = 0; cortex-worktree-precondition = 3; suppressed-picker = 2. The §1a header (line 99) is generalized to two entry modes. Step v operation 2 ("Suppressed-picker structural branch") is a genuine STRUCTURAL skip keyed on the carried entry-mode value recorded at §1 ("**record entry mode `suppressed`**" / "**record entry mode `selected`**"): when the carried mode is `suppressed` it skips BOTH the `cortex-worktree-precondition` probe and the `EnterWorktree` call and routes to `cd $(cortex-worktree-resolve ...)`, emitting the stable marker `EnterWorktree skipped: suppressed-picker (branch-mode worktree-interactive)`. The prose explicitly states this is "a carried control-flow value threaded from §1, not a runtime decline." Operations i–iv (incl. worktree creation) run unconditionally first so the cd-shim target exists. The `selected` path retains the precondition probe + EnterWorktree.
- **Verdict**: PASS
- **Notes**: This is the spec's headline requirement and it is implemented as a structural branch on a threaded entry-mode signal, not a soft-gate runtime decline.

### R9 — §1 picker option label retains literal "worktree"
- **Expected**: `test_lifecycle_picker_label_pins_worktree.py` passes.
- **Actual**: Test present and passing. §1 option label "Implement on feature branch with worktree" is intact.
- **Verdict**: PASS

### R10 — step-v ordering test rewritten (drop verify token, keep precondition→EnterWorktree); callsites test passes on surviving anchors
- **Expected**: Both tests pass; required-order list includes `cortex-worktree-precondition` and `EnterWorktree`, excludes `verify-worktree-auth`.
- **Actual**: `test_lifecycle_step_v_ordering.py` `_REQUIRED_ORDER` = (`_origin_pwd`, `cortex-worktree-precondition`, `EnterWorktree(`, `interactive_worktree_entered`); a dedicated `test_step_v_omits_removed_verify_probe` asserts the verify token is ABSENT; `test_step_v_pins_suppressed_picker_skip` pins the structural skip marker. `test_lifecycle_enterworktree_callsites.py` passes on `show-toplevel`/`git-common-dir`/`EnterWorktree skipped` anchors (no longer references the deleted verify token). Both pass.
- **Verdict**: PASS

### R11 — complete.md / sdk.md exit prose update + snapshot regenerate (confirmed no-op under Option B)
- **Expected**: `test_complete_md_hard_guard_snapshot.py` passes.
- **Actual**: `git diff 3eada4ab..HEAD -- skills/lifecycle/references/complete.md docs/internals/sdk.md tests/fixtures/complete_md_hard_guard.txt` is EMPTY — all three unchanged. The snapshot test passes. Confirmed no-op: under Option B `EnterWorktree`/`ExitWorktree` survive, complete.md:197's reference is already conditional ("preferred while the session is live"), and sdk.md carries no exit prose. The plan's R11-deviation reasoning (Risks) is sound.
- **Verdict**: PASS

### R12 — dual-source mirror regenerated; canonical + mirror byte-identical
- **Expected**: `diff -q skills/.../implement.md plugins/cortex-core/skills/.../implement.md` identical; drift gate passes.
- **Actual**: `diff -q` reports IDENTICAL.
- **Verdict**: PASS

### R13 — ADR-0006 superseded (not amended); new ADR records picker-selection model
- **Expected**: `grep -c "status: superseded" 0006` = 1 and `grep -c "superseded_by:" 0006` = 1; new ADR exists describing the picker-selection authorization model.
- **Actual**: 0006 frontmatter: `status: superseded` + `superseded_by: 0008`, with a one-line supersession blockquote and the decision body retained as historical record. `cortex/adr/0008-picker-selection-authorizes-enterworktree.md` exists, `status: accepted`, with Context (cites the empirical gate test), Decision (picker-fired + suppressed-picker→cd-shim), Trade-off, three-criteria gate clearance, ADR-0003 relation, and Alternatives (incl. the rejected soft-gate-runtime-decline).
- **Verdict**: PASS

### R14 — ADR-0004 line-49 mis-citation fixed
- **Expected**: `grep -c "ADR-0005" 0004` = 0 in the fence-shape citation context.
- **Actual**: `grep -c "ADR-0005" 0004` = 0. Both fence references annotated: Decision 2a (line 49) carries "[Superseded in part by ADR-0008...]" + a supersession note; section (c)(i) (line 37) is repointed to ADR-0008. The plan's "two fence references, not one" risk was handled.
- **Verdict**: PASS

### R15 — ADR-0003 reconciled; invariant restored for consumers
- **Expected**: ADR-0003 contains a note that the consumer-`CLAUDE.md` write was removed (ADR-0008); no `accepted` ADR's body asserts the fence write as a live decision.
- **Actual**: ADR-0003 has a "Reconciliation: the consumer-`CLAUDE.md` fence write (ADR-0006 → ADR-0008)" section (references ADR-0008 twice) stating the fence write was removed and the "only write outside our tree" invariant holds again. ADR-0006 is `superseded`; ADR-0004's 2a is explicitly marked historical-not-live. No accepted ADR body asserts the fence as a live decision.
- **Verdict**: PASS

### R16 — Backlog + back-pointer reconciliation (#249/#250/#267/#288) + project.md rewrite
- **Expected**: #249 `status: complete` = 1; #250 carries a supersession note; `grep -c "revoke-worktree-auth|verify-worktree-auth" project.md` = 0; no deleted-symbol reference dangling under cortex/backlog/.
- **Actual**: #249 `status: complete` = 1. #250 carries a resolution note (`0008|resolved|superseded` ≥ 1) framed accurately as the deferred-decision ticket (per the plan's correction of the spec's "fence shipper" mislabel). #267 carries a top-of-file ADR-0008 reconciliation blockquote noting the fence writer was removed and the flock-on-fence follow-up is obsolete, BEFORE its historical touch-point reference. #288 carries a top-of-file ADR-0008 reconciliation blockquote marking its `live_interactive_sessions`/template/verify-probe touch-points historical, BEFORE those references. project.md grep = 0; line 41 bullet rewritten to the no-fence picker-selection model → ADR-0008. Both backlog files matched by the deleted-symbol grep (#267, #288) carry explicit reconciliation notes — no silent dangling references.
- **Verdict**: PASS
- **Notes**: The plan correctly diverged from the spec's R16 "#250 is the fence shipper" wording (verified false against the ticket) while still satisfying R16's acceptance — accurate note, correct grep result.

### Acceptance (spec/plan §Acceptance)
- **Expected**: No fence machinery in cortex_command/; implement phase auto-enters via EnterWorktree on selection and structurally falls back to cd-shim on suppressed-picker via a test-pinned carried signal; `just test` green; mirror byte-identical; ADR/backlog/project.md surface no longer asserts the deleted fence as live.
- **Actual**: All sub-conditions verified above. The reviewed test subset (57 tests incl. the rewritten step-v ordering test, the new suppressed-branch structural assertion, and the unchanged complete-md snapshot) is green; mirror is byte-identical; no deleted-symbol reference remains under cortex/backlog/ without a reconciliation note.
- **Verdict**: PASS

## Requirements Drift
- **State**: none
- **Findings**: None. The implementation aligns with `cortex/requirements/project.md`. The project.md line-41 "Consumer `EnterWorktree` authorization surface" bullet was itself updated under R16 to describe the new picker-selection model (→ ADR-0008), so the requirements doc and the implementation are mutually consistent. The destructive-ops principle (line 53) is honored — no fence-cleanup script was added (left-stranded default); the multi-step-lifecycle principle (line 25, → ADR-0004) is unaffected; the ADR-0003 "only write outside our tree" invariant is restored for consumers.
- **Update needed**: None

## Stage 2: Code Quality

- **Naming/pattern consistency**: The §1a structural branch reuses the existing `EnterWorktree skipped` anchor family (`EnterWorktree skipped: suppressed-picker (...)`) so the callsites parity test's `_PRECONDITION_TOKENS` continue to match — a clean reuse rather than a new marker vocabulary. The carried entry-mode marker (`selected`/`suppressed`) is threaded from §1's branch-mode preflight (where `should_fire_picker` already computes the `suppressed` reason) into §1a step v, matching the FIRE/REASON shell-value carrier the plan identified. ADR-0008 matches the existing ADR file shape (frontmatter `status:` + Context/Decision/Trade-off/three-criteria/Alternatives).
- **Test soundness**: The rewritten parity tests genuinely pin the new structural branch. `test_step_v_pins_suppressed_picker_skip` asserts the `EnterWorktree skipped: suppressed-picker` literal is present in the step-v block; its docstring states the contract explicitly — a soft-gate-only implementation (one that keeps the EnterWorktree call and declines only at runtime) omits this marker and FAILS. `test_step_v_omits_removed_verify_probe` independently pins the verify token's absence. The ordering test preserves `cortex-worktree-precondition` → `EnterWorktree(` for the selected path. These would fail a soft-gate regression.
- **Orphaned references / broken cross-refs**: None found. Whole-`.py`-tree grep for the seven deleted symbols returns nothing; the only `.py` mention of `verify-worktree-auth` is the negative assertion in the rewritten ordering test. No deleted-symbol references in docs/skills/plugins/claude markdown. The only backlog files matching the deleted-symbol grep (#267, #288) carry explicit reconciliation notes. ADR-0006's historical body retains the old subcommand names by design (preserved as historical record under a supersession banner).
- **Minor (non-blocking) observation**: `test_lifecycle_step_v_ordering.py` docstrings and a comment still say "five operation tokens" while `_REQUIRED_ORDER` now holds four (the verify token was removed). Cosmetic doc-vs-code drift inside a test file; the assertions are correct and pass. Worth a one-line cleanup but does not affect behavior or the verdict.

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
