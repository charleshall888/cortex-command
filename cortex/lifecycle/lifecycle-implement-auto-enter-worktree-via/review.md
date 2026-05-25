# Review: lifecycle-implement-auto-enter-worktree-via

## Stage 1: Spec Compliance

### R1 — ADR-0004 promotion: PASS
`grep -c '^status: accepted$' cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` = 1; `grep -c '^status: proposed$'` = 0. Promoted from proposed to accepted (lowercase per ADR-README convention).

### R2 — ADR-0006 introduction: PASS
File exists at `cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md` with `status: accepted` (count = 1). All four required sections are present: (a) three-criteria-gate section, (b) fenced-block shape section with `version=N` attribute documented, (c) lifecycle-of-the-clause section containing the literal word `uninstall` (the section both recommends running `--revoke-worktree-auth` pre-uninstall AND explicitly declares the dead-clause state as accepted post-uninstall), and (d) "Alternatives considered" section recording the `.claude/cortex-authorizations.md` sibling rejection citing the live `EnterWorktree` schema.

### R3 — Doc-drift fix in implement.md: PASS
`grep -c 'cortex-worktrees' skills/lifecycle/references/implement.md` = 0. §1a step iii correctly references `<repo>/.claude/worktrees/interactive-{slug}/`.

### R4 — Doc-drift fix in complete.md: PASS
`grep -c 'cortex-worktrees' skills/lifecycle/references/complete.md` = 0.

### R5 — `cortex init` writes CLAUDE.md authorization clause: PASS
`ensure_claude_md_authorization()` in `cortex_command/init/scaffold.py:554` implements the additive-idempotent shape; the function is wired between Step 6 (`ensure_gitignore`) and Step 7 (`settings_merge.register`) at `cortex_command/init/handler.py:291` (Step 6b per inline comment). All four branches (absent → append, present-and-current → no-op, present-and-stale → replace, user-edited-in-fence → replaced/no-op-per-version) are exercised by `tests/test_init_claude_md_authorization.py` (11 tests pass).

### R6 — CLAUDE.md clause body contains "worktree" at least twice: PASS
`cortex_command/init/templates/claude_md_authorization.md` contains 8 occurrences of "worktree" (heading "Lifecycle worktree authorization" + clause body references). Well over the ≥2 requirement.

### R7 — `cortex init --revoke-worktree-auth` removes the clause: PASS
Subcommand wired at `cortex_command/cli.py:778-787` and dispatched at `cortex_command/init/handler.py:152-192`. Live-session pre-condition uses `scaffold.live_interactive_sessions()` (returns exit 2 with diagnostic listing pid files) unless `--force` bypasses. All four required branches (round-trip, no-op when absent, refuses with live session, proceeds with --force) verified by `tests/test_init_claude_md_authorization.py::TestRevokeRoundTrip`, `TestRevokeWhenFenceAbsent`, `TestRevokeWithLiveSession`. Also covers stale-PID case.

### R8 — `EnterWorktree(path=...)` call in implement.md §1a: PASS
`grep -cE 'EnterWorktree\s*\(' skills/lifecycle/references/implement.md` = 1. The call appears in step v after `create_worktree` (step iii) and after the verify-worktree-auth + already-in-worktree probes, and before `interactive_worktree_entered` emission. Step-v ordering parity test verifies the exact sequence.

### R9 — Already-in-worktree precondition probe: PASS
`grep -c 'show-toplevel\|git-common-dir' skills/lifecycle/references/implement.md` = 3. Shim implemented at `cortex_command/worktree_precondition.py` with `is_in_worktree()` comparing `git rev-parse --show-toplevel` vs `git rev-parse --git-common-dir`'s parent. Both branches exercised in `tests/test_worktree_precondition.py` (6 tests covering main-checkout, linked-worktree, outside-any-repo, subdirectory cases, and usage error).

### R10 — Graceful `EnterWorktree` fallback covering all failure modes: PASS
`grep -c 'EnterWorktree skipped' skills/lifecycle/references/implement.md` = 1. The fallback paragraph at implement.md:201 enumerates failure modes (probe non-zero, tool error, silent non-invocation) and routes all to the `cd $(cortex-worktree-resolve interactive/{slug})` shim with diagnostics.

### R11 — §1a step v event-ordering correctness: PASS
The five tokens `_origin_pwd`, `verify-worktree-auth`, `cortex-worktree-precondition`, `EnterWorktree(`, `interactive_worktree_entered` appear in order in the anchored block. `tests/test_lifecycle_step_v_ordering.py` (3 tests) verifies extraction, presence, and ordering. Anchor is `**Step v — Auto-enter sequence**` per spec.

### R12 — §1a step vi narrative re-author with session-exit safety guidance: PASS
`grep -c 'Variant A\|Variant B' skills/lifecycle/references/implement.md` = 0 (collapsed); `grep -c 'Interactive worktree auto-entry' skills/lifecycle/references/implement.md` = 1; `grep -c 'keep or remove' skills/lifecycle/references/implement.md` = 1. Paragraph at implement.md:205 names both restoration paths (`ExitWorktree action="keep"` preferred, `cd $(git rev-parse --show-toplevel)` alternative) and references ADR-0004 once.

### R13 — Complete-phase hard guard teaches the same-session exit path: PASS
`grep -c 'ExitWorktree action' skills/lifecycle/references/complete.md` = 1; `grep -c 'Do not auto-cd' skills/lifecycle/references/complete.md` = 1. Snapshot fixture at `tests/fixtures/complete_md_hard_guard.txt` matches the live paragraph byte-for-byte; `tests/test_complete_md_hard_guard_snapshot.py` enforces this.

### R14 — EnterWorktree call-site parity test: PASS
`tests/test_lifecycle_enterworktree_callsites.py` enumerates every `EnterWorktree\s*\(` match under `skills/lifecycle/` (1 match found) and asserts (a) the `create_worktree` token AND (b) at least one structural precondition token appears within ±60 lines. All 3 parametrized tests pass. The widened ±60 proximity is documented in the test docstring and called out in the implementation notes as a spec defect — the canonical §1a layout has ~61 line separation between `create_worktree` and `EnterWorktree(`, which is structurally correct.

### R15 — Cross-session Complete-phase behavior verification: PARTIAL
Deferred per user decision; empirical bet unverified at runtime. `events.log` contains a `manual_verification_deferred` row at line 20 covering tasks 17/18/19. The structural counterparts (R13 prose + snapshot fixture + parity tests) are in place.

### R16 — Kept-pauses inventory unchanged: PASS
`tests/test_lifecycle_kept_pauses_parity.py` passes (2 tests). SKILL.md inventory unchanged — auto-enter is non-interactive (no new `AskUserQuestion` site).

### R17 — ADR-0004 amendment recording resolved decisions: PASS
`grep -c '^## Approach A resolved decisions' cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` = 1. All three resolved decisions (1, 2a, 2b) are recorded in prose, citing the corresponding spec requirements (R13, R5/R6/R19/R20, R18).

### R18 — WorktreeCreate-bypass implementation verification: PASS
`tests/test_create_worktree_bypass.py` reads `create_worktree` source via `inspect.getsource` and asserts (positively) the `'git'`, `'worktree'`, `'add'` tokens are present AND (negatively) `'claude'`/`--worktree` tokens are absent. The defensive `hooks.json` grep is also present as a secondary check. Both tests pass.

### R19 — Picker-option label parity test: PASS
`tests/test_lifecycle_picker_label_pins_worktree.py` extracts the §1 picker block via the stable `**Branch selection**` anchor and asserts at least one bolded option label contains "worktree". All 3 tests pass.

### R20 — `cortex init --verify-worktree-auth` precondition probe: PASS
Subcommand wired at `cortex_command/cli.py:789-799` and dispatched at `cortex_command/init/handler.py:203-223`. Exit 0 / 1 / 2 contract implemented per spec (with future-version fence accepting as exit 0 per documented "superset commitment" reasoning). `tests/test_init_verify_worktree_auth.py` covers all three branches plus orphan-sigil and future-version edge cases (6 tests pass).

### R21 — Manual gate-firing verification: PARTIAL
Deferred per user decision; empirical bet unverified at runtime. The load-bearing assumption that Claude honors the tooling-authored CLAUDE.md fence as "project instructions" remains unproven. Spec language explicitly flags this as "Live-empirical bet" — closure of the spec without this verification is acknowledged by the implementation notes.

### R22 — Session-exit safety acceptance: PARTIAL
Deferred per user decision; empirical bet unverified at runtime. The narrative warning in R12's paragraph stands, but the runtime behavior of the harness's keep/remove prompt is not verified against the deployed Claude Code version.

## Stage 2: Code Quality

### Naming conventions
Consistent with project patterns: `ensure_*` / `revoke_*` mirror `ensure_gitignore`'s shape (R5 acceptance criterion); console script `cortex-worktree-precondition` matches the established `cortex-<skill>` idiom; the `_CLAUDE_MD_AUTH_*` constants are namespaced under a single prefix. Sigil prefix and regex are factored as module-level constants (`_CLAUDE_MD_AUTH_FENCE_OPEN_PREFIX`, `_CLAUDE_MD_AUTH_FENCE_OPEN_RE`, `_CLAUDE_MD_AUTH_FENCE_CLOSE`) and reused from tests, avoiding sigil-literal duplication.

### Error handling
Appropriate for context. `_find_claude_md_auth_fence` returns `None` for malformed inputs (orphan opening sigil, missing close) so callers no-op-and-rewrite cleanly. `_git_output` in `worktree_precondition.py` swallows `OSError`/`SubprocessError` and returns `None`, treating "outside any repo" as "safe to proceed" per the probe's stated contract. The handler's `--revoke-worktree-auth` branch reads CLAUDE.md only when present (no IOError leak path).

### Test coverage
Comprehensive structural coverage: 37 new tests across 8 files, all passing. Each requirement that names a `just test`/pytest acceptance criterion has a corresponding test file. The parity tests use stable markdown anchors (`**Branch selection**`, `**Step v — Auto-enter sequence**`, `**Hard guard**:`) so future docs reshuffling surfaces the regression at the test level. R15/R21/R22 manual checklists are not test-eligible (live-empirical) and the deferral is documented in events.log.

### Pattern consistency
Mirrors `ensure_gitignore`'s additive-idempotent shape (the spec's stated precedent). The handler's early-branch pattern (unregister → revoke → verify → default flow) follows the existing structure cleanly. `tests/fixtures/complete_md_hard_guard.txt` snapshot pattern is novel for this repo but the test docstring explains the update protocol; future drift surfaces deterministically.

### Minor quality observations (not blocking)
- `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md:49` references "ADR-0005" in Decision (2a) prose; the new ADR is at `0006-…` (renumbered due to the collision with `0005-repo-relative-worktree-placement.md`). The reference is stale — a one-line cleanup, not blocking the requirement (R17's acceptance criterion is purely structural). Worth fixing in a follow-up commit.
- Implementation notes flag commit `e06f954d` swept in 8 unrelated files from parallel-session lifecycles. Commit hygiene gap, but not a correctness issue for this lifecycle's surfaces.

## Requirements Drift
**State**: detected
**Findings**:
- ADR-0003 stated `~/.claude/settings.local.json::sandbox.filesystem.allowWrite` was "the only write cortex-command makes outside its own tree." This lifecycle introduces a second consumer write surface: `cortex init` now appends a cortex-managed fenced clause to consumer `CLAUDE.md`. ADR-0006 (newly accepted in Phase 1) records the rationale, but the project-level `cortex/requirements/project.md` does not yet mention the CLAUDE.md write surface or list ADR-0006 alongside ADR-0001/0002/0003 in the Architectural Constraints section.
- The CLI surface gains two new verbs (`cortex init --revoke-worktree-auth`, `cortex init --verify-worktree-auth`) with documented exit-code contracts. The requirements doc enumerates "skills, lifecycle, pipeline" but does not surface the cortex-init verb expansion or the new console script `cortex-worktree-precondition`.

**Update needed**: `cortex/requirements/project.md` — add ADR-0006 to the Architectural Decision Records reference (around line 40), and either expand the In-Scope bullet on overnight execution to acknowledge the CLAUDE.md authorization surface or add a short paragraph in Architectural Constraints linking to ADR-0006.

## Suggested Requirements Update

In `cortex/requirements/project.md` Architectural Constraints section, add a bullet near the existing ADR references (line ~40):

> **Consumer CLAUDE.md authorization surface**: `cortex init` now appends a cortex-managed fenced `EnterWorktree` authorization clause to consumer `CLAUDE.md`. Three subcommands manage the clause lifetime (`cortex init` writes/replaces by version, `--revoke-worktree-auth` removes, `--verify-worktree-auth` probes). → ADR-0006: cortex-init consumer CLAUDE.md authorization surface.

This makes the second consumer-write surface visible at the project-requirements level (a contributor reading the requirements doc would otherwise still see ADR-0003's "only write" claim without context).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
