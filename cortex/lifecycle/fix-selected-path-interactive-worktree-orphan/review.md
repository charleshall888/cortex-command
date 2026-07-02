# Review: fix-selected-path-interactive-worktree-orphan

Commits reviewed: `edb3e52f` (reorder + scrub + mirror + test) and `a46cae6` (follow-up ticket #356). Read-only review; no source file modified.

## Stage 1: Spec Compliance

### Requirement R1/R7: Author a discriminating structural regression test, red on the pre-fix tree, green after the fix
- **Expected**: `test_selected_path_acquire_unified_at_1a_ii` passes now; its three assertions genuinely red on the pre-fix tree and on a dead-arm half-fix.
- **Actual**:
  - Committed test run — `.venv/bin/pytest tests/test_implement_worktree_interactive_contract.py … -q` → `74 passed in 0.06s` (includes the new test).
  - **Discriminating power** (reconstructed with the test's exact regex/find logic; note the task's suggested `git show edb3e52f:…` returns the POST-fix file since `edb3e52f` IS the fix commit — I used the true pre-fix `edb3e52f^`, confirmed to still contain "Step B" ×4):
    - TRUE PRE-FIX (`edb3e52f^`): `(i) §1 has no acquire: False → RED`; `(iii) acquire in step_ii=True, no-mode=False → RED (modes named: ['selected','suppressed'])`. `OVERALL test would FAIL (RED)`. Both discriminators fire; assertion (ii) stays green (expected — it is the forward-guard, already green pre-fix).
    - CURRENT (post-fix): `(i) True`, `(ii) acquire@1309 > sidecar@553: True`, `(iii) True, modes=[]`. `OVERALL PASS`.
    - DEAD-ARM HALF-FIX (simulated: §1a.ii re-worded to name modes): `(iii) no-mode=False → RED (modes: ['selected','suppressed'])`. `OVERALL FAIL`.
- **Verdict**: PASS
- **Notes**: Assertion (iii) is the true unconditionality discriminator — it reds on both the pre-fix per-mode branch and the "for picker-selected … no acquire; for suppressed … acquire" B2 half-fix, because either must name a mode. The correct unified step ("both entry modes") names neither literal `selected`/`suppressed`, so no false-red.

### Requirement R2: Reorder the selected-path acquire into §1a.ii (unconditional)
- **Expected**: `grep -niEc "step b|steps a and b|two interactive preflight guards|either guard rejects"` = 0; `grep -c "cortex-interactive-lock acquire"` = 1 (in §1a.ii only); §1a.ii names neither "selected" nor "suppressed".
- **Actual**: step-b/two-guard grep = `0`; acquire count = `1` at line 97; the single acquire sits inside §1a.ii (step begins line 94); §1a.ii text = "…acquire the real lock … **unconditionally for both entry modes**, and only **after** the overnight guard (i) has passed…" — names neither mode literal. §1 contains no acquire (assertion (i) green).
- **Verdict**: PASS

### Requirement R3: Scrub every dangling Step B / two-guard reference
- **Expected**: the token AND the two-guard prose gone; §1 reads as one preflight guard.
- **Actual**: enumerated sites all fixed — line ~19 recorded-choice branch drops the "and Step B" clause; line ~63 → "run the interactive preflight guard below (Step A) … If it rejects"; Step A exit-code prose → "proceed to §1a" (not "proceed to Step B"); §1a.ii selected-arm removed. Independent whole-file grep for `already acquired|acquire again|second same-session|proceed to step|step b` → `(none)`.
- **Verdict**: PASS

### Requirement R4: Preserve `Step A` label, entry-mode marker, Step v branching
- **Expected**: `grep -c "§1 Step A"` ≥ 1; both `record entry mode selected` / `suppressed` present; `test_lifecycle_step_v_ordering` passes.
- **Actual**: `§1 Step A` = `1` (line 92 back-ref "semantics as §1 Step A" resolves; Step A label kept at §1 line 65); `record entry mode \`selected\`` = `2`, `record entry mode \`suppressed\`` = `1`; `test_lifecycle_step_v_ordering.py` in the green run; `just test` = 7/7 suite groups pass. Step v marker branch (cd-shim vs EnterWorktree, ADR-0008) untouched.
- **Verdict**: PASS

### Requirement R5: Regenerate + stage mirror in the same commit
- **Expected**: `diff` canonical↔mirror exits 0 (byte-identical); `test_dual_source_reference_parity` passes.
- **Actual**: `diff skills/lifecycle/references/implement.md plugins/cortex-core/skills/lifecycle/references/implement.md` → exit `0` (no output); `test_dual_source_reference_parity.py` green; both edits in commit `edb3e52f`.
- **Verdict**: PASS

### Requirement R6: Preserve existing tested contracts
- **Expected**: `test_implement_worktree_interactive_contract.py test_lifecycle_step_v_ordering.py test_dual_source_reference_parity.py` all pass.
- **Actual**:
```
........................................................................ [ 97%]
..                                                                       [100%]
74 passed in 0.06s
```
`test_sidecar_invocation_form_bash_s_count` (exactly 2 `bash -s --`), `test_overnight_guard_sidecar_called_at_least_twice` (≥2), and `test_gate_and_gated_path_use_same_binary` (its `**iii.` extraction still resolves) all green. Full `just test` → `Test suite: 7/7 passed`.
- **Verdict**: PASS

### Requirement R7: Phase-1 test passes after the reorder
- Covered under R1 above — the committed tree is green; the red-on-pre-fix is reconstructable at `edb3e52f^`. **Verdict**: PASS

## Does the reorder actually fix the orphan (not just move text)?
Yes. Traced control flow on the picker-`selected` path: §1 picker → **record entry mode `selected`** → **Step A** (overnight pre-check, no lock) → §1a.i (**overnight guard** re-runs the sidecar; exit 1 → exit §1a) → §1a.ii (**acquire**, line 97). The acquire (§1a index 1309) is strictly after the last §1a sidecar (index 553), so a rejecting §1a.i guard exits §1a *before* any lock is written — the orphan window described in the Problem Statement is closed. Step A (pre-check) → §1a.i (guard) → §1a.ii (acquire) ordering holds. The residual §1a.iii worktree-create-failure orphan is post-acquire and unreachable by any acquire reorder (correctly deferred).

## #356 follow-up ticket assessment
Accurate and well-scoped. It captures the deferred §1a.iii orphan on **both** entry modes (unified post-#355), post-acquire, requiring an **owner-checked** release. The technical premise is verified against source: `release_lock(feature_slug)` in `cortex_command/interactive_lock.py` (line 461) reads `current_session_id` only for the event payload and calls `lock_path.unlink()` guarded solely by existence — no owner comparison — so a naive release-on-abort would clobber a racing session's lock under the non-atomic `acquire_lock` double-pass. Deferral is defensible per the spec's Non-Requirements (the safe fix is a genuine multi-call design task, not a one-line addition) and the project's Solution-horizon principle (a deliberately-scoped phase filed as a durable follow-up, not a stop-gap — the follow-up exists, is committed at `a46cae6`, and references parent #355 + precedent #348). `just backlog-index` exits 0.

## Stage 2: Code Quality
- **Naming conventions**: The new `test_selected_path_acquire_unified_at_1a_ii` mirrors the section-extraction idiom of the sibling `test_gate_and_gated_path_use_same_binary` (same `### 1\. Pre-Flight Check.*?(?=### 1a\.)` regex; `.find("**ii.")`/`.find("**iii.")` narrowing paralleling that test's `**iii.`/`**iv.` narrowing). Consistent with the file.
- **Error handling**: N/A for a structural test/doc change; every extraction step has an assert-with-message guard so a mis-extract fails loud rather than silently green.
- **Test coverage**: Robust. §1a is bounded at `### 2.` (not `\Z`/EOF), so §2's builder-template text cannot leak into the section — strictly more precise than the sibling test's `(?=### 1b\.|\Z)`. The `**ii.`→`**iii.` narrowing depends on markers the reorder deliberately preserves. Assertion (ii) uses first-acquire (`find`) vs last-sidecar (`rfind`) — correct forward-guard even under future multi-occurrence edits. False-green risk is limited to the accepted literal-substring contract style (a differently-worded re-introduced acquire would evade), consistent with the rest of the file; assertion (iii)'s no-mode check does not false-red because the unified phrasing ("both entry modes") contains neither `selected` nor `suppressed`.
- **Pattern consistency**: Prose coherence verified — §1 now reads as ONE preflight guard (Step A only); no dangling Step B / two-guard / "already acquired" back-references remain (independent grep clean); the §1a.i back-ref "semantics as §1 Step A" still resolves. The #356 ticket follows the Why/Role/Integration/Edges/Touch-points template with valid frontmatter and a technically accurate, source-verified body.

## Requirements Drift
**State**: none
**Findings**:
- None. The change is a pure reorder + prose scrub + regression test + follow-up ticket; it introduces no behavior beyond the stated requirements. It extends #348's already-established guard-then-acquire pattern (not a new project-level constraint) and defers the §1a.iii residual as a durable follow-up consistent with the existing Solution-horizon principle. The only adjacent project.md constraint (the "Worktree containment invariant") concerns `create_worktree` containment, not lock-acquire ordering, and is unaffected.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
