# Plan: lifecycle-implement-auto-enter-worktree-via

## Overview

Land Approach A — mid-session auto-enter of the `interactive/{slug}` worktree via the platform `EnterWorktree(path=...)` tool — across 19 tasks in 4 phases mapped 1:1 to the spec's Phase declarations. Phase 1 ships the ADR foundations and doc-drift cleanup; Phase 2 adds the `cortex init` CLAUDE.md authorization plumbing with three subcommands (write/revoke/verify); Phase 3 wires `EnterWorktree` into `implement.md` §1a with precondition probes and re-authored handoff narrative, and updates `complete.md` Step 8 to teach both exit paths; Phase 4 lands the parity tests and the manual gate-firing verification that confirms the load-bearing empirical bet (Claude honoring the tooling-authored fence as satisfying the schema's "project instructions" clause).

## Outline

### Phase 1: Foundations (tasks: 1, 2, 3, 4)
**Goal**: Promote ADR-0004 to `accepted` with the resolved-decisions amendment, introduce ADR-0006 for the CLAUDE.md surface extension, and fix the `cortex-worktrees/` → `.claude/worktrees/` path drift in implement.md and complete.md so subsequent phases have a clean substrate.
**Checkpoint**: ADR-0004 status is `accepted`, ADR-0006 exists at `accepted`, `grep -c 'cortex-worktrees' skills/lifecycle/references/{implement,complete}.md` = 0 for both files.

> Note: Numbering collision resolved — what the spec/plan originally called "ADR-0005" was renumbered to ADR-0006 because `cortex/adr/0005-repo-relative-worktree-placement.md` already exists. The `status:` field was also normalized to lowercase across both new ADR-0006 and the promoted ADR-0004 to match ADR-README convention.

### Phase 2: Authorization plumbing (tasks: 5, 6, 7, 8)
**Goal**: Extend `cortex init` with the `ensure_claude_md_authorization()` write-path, the `--revoke-worktree-auth` rollback subcommand (refusing on live session without `--force`), and the `--verify-worktree-auth` precondition probe with three exit codes (0 OK / 1 absent / 2 stale).
**Checkpoint**: `just test tests/test_init_claude_md_authorization.py tests/test_init_verify_worktree_auth.py` exits 0 covering write/replace/no-op/revoke/refuse-on-live-session/verify branches.

### Phase 3: Auto-enter wiring (tasks: 9, 10, 11, 12, 13)
**Goal**: Add the auto-enter sequence (precondition probes + EnterWorktree call + event-emission re-ordering) to `implement.md` §1a, re-author §1a step vi with session-exit safety guidance, and update `complete.md` Step 8 hard guard prose to teach both exit paths.
**Checkpoint**: `grep -cE 'EnterWorktree\s*\(' skills/lifecycle/references/implement.md` ≥ 1; `grep -c 'ExitWorktree action' skills/lifecycle/references/complete.md` ≥ 1; `grep -c 'keep or remove' skills/lifecycle/references/implement.md` ≥ 1; `grep -c 'Variant A\|Variant B' skills/lifecycle/references/implement.md` = 0.

### Phase 4: Tests and observability (tasks: 13, 14, 15, 16, 17, 18, 19)
**Goal**: Land the four parity / behavior tests (call-site enumerator, picker-label pin, WorktreeCreate-bypass implementation check, kept-pauses inventory regression), and execute the two manual verifications (R21 gate-firing + R22 session-exit-prompt) recording an `auto_enter_smoke_test` event row with `gate_fires` and `session_exit_prompt_fires` fields.
**Checkpoint**: `just test` exits 0 and `grep -c 'auto_enter_smoke_test' cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log` ≥ 1 with both `gate_fires: true` and `session_exit_prompt_fires: true` in the payload.

## Tasks

### Task 1: Promote ADR-0004 + append resolved-decisions amendment
- **Files**: `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md`
- **What**: Change `status: proposed` to `status: accepted`. Append a new `## Approach A resolved decisions` section recording the three decisions per R17 (1 cross-session-exit interaction model, 2a authorization shape, 2b WorktreeCreate-bypass non-expansion verification).
- **Depends on**: none
- **Complexity**: simple
- **Context**: ADR-0004 lives at the named path. The amendment is appended after the existing `## branch-mode default (Approach C) + Approach A deferred design surface` section (currently around lines 27–41). Each of the three resolved decisions is one paragraph naming the decision, the load-bearing schema clause or constraint, and the spec requirement(s) that codify the resolution. Per ADR-README, an ADR amendment landing on a `proposed` ADR co-promotes it to `accepted` if the merge happens in the same commit.
- **Verification**: `grep -c '^status: accepted$' cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` = 1 AND `grep -c '^## Approach A resolved decisions' cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` = 1 — pass if both counts match.
- **Status**: [x] completed

### Task 2: Create ADR-0006
- **Files**: `cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md`
- **What**: Author ADR-0006 with `status: accepted` and the four required sections per spec R2: (a) three-criteria-gate rationale, (b) fenced-block shape with `version=N` attribute, (c) lifecycle of the clause (write / verify / revoke / uninstall), (d) alternatives considered and rejected.
- **Depends on**: none
- **Complexity**: simple
- **Context**: ADR-README's three-criteria gate (`cortex/adr/README.md:19-27`) defines the test (Hard to reverse + Surprising without context + Real trade-off). The spec's Proposed ADR section contains the canonical body — Task 2 transcribes it into ADR-0006 file with appropriate ADR frontmatter (Date, Authors). Section (c) MUST literally contain the word `uninstall` per R2 acceptance.
- **Verification**: file exists AND `grep -c '^status: accepted$' cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md` = 1 AND `grep -ci 'uninstall' cortex/adr/0006-cortex-init-consumer-claude-md-authorization-surface.md` ≥ 1 — pass if all three checks match.
- **Status**: [x] completed (renumbered from 0005 due to collision)

### Task 3: Doc-drift fix in implement.md
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Replace `$TMPDIR/cortex-worktrees/interactive-{slug}/` with `<repo>/.claude/worktrees/{slug}` references in §1a step iii prose; ensure step v uses `cortex-worktree-resolve interactive/{slug}` to obtain the path rather than hardcoding a literal.
- **Depends on**: none
- **Complexity**: simple
- **Context**: `cortex_command/pipeline/worktree.py:167` returns `(repo / ".claude" / "worktrees" / feature).resolve()`. Today's §1a step iii (around lines 122–130) mentions the stale path. The resolver shim `cortex-worktree-resolve interactive/{slug}` is the canonical lookup — used elsewhere in §1a step v (lines 184–198).
- **Verification**: `grep -c 'cortex-worktrees' skills/lifecycle/references/implement.md` = 0 — pass if count is 0.
- **Status**: [x] completed (no-op — file was already canonical)

### Task 4: Doc-drift fix in complete.md
- **Files**: `skills/lifecycle/references/complete.md`
- **What**: Remove residual `cortex-worktrees/`-prefix mentions in Step 8's prefix check and any Step 3 detection paragraph; replace with `<repo>/.claude/worktrees/` or, when appropriate, a `cortex-worktree-resolve interactive/{slug}` shim invocation.
- **Depends on**: none
- **Complexity**: simple
- **Context**: complete.md Step 8 prefix check (line ~183) reads "checking `git worktree list --porcelain` for a path matching `.claude/worktrees/interactive-{slug}` (or the resolved worktree root)" — verify this matches the current convention and remove any stale prefix mentions elsewhere.
- **Verification**: `grep -c 'cortex-worktrees' skills/lifecycle/references/complete.md` = 0 — pass if count is 0.
- **Status**: [x] completed (no-op — file was already canonical)

### Task 5: Implement `ensure_claude_md_authorization()` + canonical fence body
- **Files**: `cortex_command/init/scaffold.py`, `cortex_command/init/templates/claude_md_authorization.md` (new), `cortex_command/init/handler.py`
- **What**: Add `ensure_claude_md_authorization(repo_root)` modeled on `ensure_gitignore()` (scaffold.py:374). Scan consumer `CLAUDE.md` for `<!-- cortex-managed: lifecycle-worktree-auth version=N -->` ... `<!-- cortex-managed end -->`; if absent, append canonical clause + version sigil; if present with `version<canonical`, replace; if present with `version==canonical`, no-op. Canonical clause body lives in a new template file. Wire into `handler.py::_run()` between Step 6 (ensure_gitignore) and Step 7 (settings_merge.register).
- **Depends on**: [2]
- **Complexity**: complex
- **Context**: Pattern reference: `cortex_command/init/scaffold.py:374-443` (`ensure_gitignore` — atomic read/mutate/write with line-exact membership checks). Function returns a bool indicating whether the file was written. The fence comment opens with a stable sigil naming the cortex-managed surface and the canonical clause version (incremented when the clause body changes); the exact comment syntax and regex are implementer choices within the constraint that the predicate must parse both the sigil and the version cleanly. The canonical version starts at `1`. Template file pattern: see existing templates under `cortex_command/init/templates/cortex/`. Body content invariant: must contain the literal word "worktree" (R6 enforces ≥ 2 occurrences).
- **Verification**: `just test tests/test_init_claude_md_authorization.py` exits 0. Test file is authored in Task 8; the test exercises a tmp_path consumer repo through write/no-op/replace/in-fence-edit-replaced branches against actual filesystem state (independent oracle).
- **Status**: [x] completed (manual branches verified; pytest deferred to T8)

### Task 6: Add `cortex init --revoke-worktree-auth` subcommand
- **Files**: `cortex_command/init/handler.py`, `cortex_command/init/scaffold.py`, `cortex_command/init/__main__.py` (or equivalent CLI entry)
- **What**: Add `--revoke-worktree-auth` and `--force` flags to the `cortex init` CLI. When `--revoke-worktree-auth` is passed: scan consumer CLAUDE.md for the fence; if absent, exit 0 (no-op); if present AND `cortex/lifecycle/sessions/*.interactive.pid` is non-empty AND `--force` is NOT passed, exit 2 with a diagnostic listing the live pid files; otherwise remove the fence atomically and exit 0.
- **Depends on**: [5]
- **Complexity**: simple
- **Context**: Live-session detection uses `glob.glob(repo_root / 'cortex/lifecycle/sessions/*.interactive.pid')` filtered for files whose contents map to live PIDs (per the existing liveness check pattern — search the codebase for `is_pid_alive` or similar). Removal mirrors `ensure_gitignore`'s atomic-write pattern. Exit code convention: 0 success, 2 refused-pre-condition.
- **Verification**: `just test tests/test_init_claude_md_authorization.py::test_revoke_round_trip` exits 0 (test file authored in Task 8 covers all four branches).
- **Status**: [ ] pending

### Task 7: Add `cortex init --verify-worktree-auth` subcommand
- **Files**: `cortex_command/init/handler.py`, `cortex_command/init/__main__.py`
- **What**: Add `--verify-worktree-auth` flag. When passed: scan consumer CLAUDE.md for the cortex-managed fence; exit 0 if present at current canonical version, exit 1 if absent, exit 2 if present but stale (`version < canonical`).
- **Depends on**: [5, 6]
- **Complexity**: simple
- **Context**: Parsing logic shares the sigil-parser introduced in Task 5 (extract from the same module rather than re-deriving). No file mutation — read-only probe. Serialized after Task 6 to avoid concurrent edits to `handler.py` and `__main__.py`.
- **Verification**: `just test tests/test_init_verify_worktree_auth.py` exits 0 covering (a) absent fence → exit 1, (b) current fence → exit 0, (c) stale fence → exit 2.
- **Status**: [ ] pending

### Task 8: Author init-handler test suite
- **Files**: `tests/test_init_claude_md_authorization.py` (new), `tests/test_init_verify_worktree_auth.py` (new)
- **What**: Author the two pytest test files referenced by Tasks 5/6/7's Verification fields. Use `tmp_path` fixtures to spin up a consumer-repo scaffold with controlled CLAUDE.md content; exercise each branch (absent, present-current, present-stale, in-fence-user-edits) for both `ensure_claude_md_authorization` and the two CLI subcommands.
- **Depends on**: [5, 6, 7]
- **Complexity**: complex
- **Context**: Pytest fixture pattern: see existing init tests in `tests/` (e.g., `tests/test_init_*.py`). Each test creates a tmp_path consumer repo, writes a CLAUDE.md (or not), invokes the function/subcommand, asserts the post-state and exit code. For revoke-with-live-session, the test writes a fake `.interactive.pid` file with a live PID (current process PID is safe to use) and asserts exit 2; with `--force`, asserts exit 0 and fence removed.
- **Verification**: `just test tests/test_init_claude_md_authorization.py tests/test_init_verify_worktree_auth.py` exits 0.
- **Status**: [ ] pending

### Task 9: Create `cortex-worktree-precondition` shim
- **Files**: `cortex_command/worktree_precondition.py` (new), `pyproject.toml` (project.scripts entry), `tests/test_worktree_precondition.py` (new)
- **What**: Implement a shell-callable Python module exposing the already-in-worktree probe. Exit 0 when the current CWD is NOT inside a worktree (or is the main repo), exit 1 when CWD IS inside a worktree. Probe via `git rev-parse --show-toplevel` vs `git rev-parse --git-common-dir`. Register as a console-script entry (`cortex-worktree-precondition`).
- **Depends on**: none
- **Complexity**: simple
- **Context**: Pattern reference: existing console scripts under `cortex_command/` registered in `pyproject.toml`'s `[project.scripts]` section (e.g. `cortex-init`, `cortex-worktree-resolve`). The probe distinguishes "CWD is the main checkout" from "CWD is inside a linked worktree"; the implementer chooses the git interrogation strategy from `git rev-parse` (`--show-toplevel`, `--git-common-dir`, `--git-dir`, etc.). Test approach: exercise against tmp_path repos with both a main checkout and a `git worktree add`ed sibling — pattern reference: existing pytest fixtures under `tests/` that use `tmp_path` for git-state setup.
- **Verification**: `just test tests/test_worktree_precondition.py` exits 0; the test exercises real `git worktree add` ground truth (independent oracle, not self-sealing).
- **Status**: [x] completed

### Task 10: Wire EnterWorktree + precondition probes in implement.md §1a
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Edit §1a step v ("Cd handoff") to a new `**Step v — Auto-enter sequence**` heading. Re-order operations: (i) capture `_origin_pwd`, (ii) call `cortex init --verify-worktree-auth`, (iii) call `cortex-worktree-precondition`, (iv) call `EnterWorktree(path=...)` if both probes exit 0 (using the path returned by `cortex-worktree-resolve interactive/{slug}`), (v) emit `cortex-lifecycle-event log --event interactive_worktree_entered`. On any probe failure, route to the R10 fallback path with structural marker `EnterWorktree skipped` and a diagnostic naming the cause.
- **Depends on**: [1, 3, 5, 7, 9]
- **Complexity**: complex
- **Context**: Today's §1a step v (lines 184–198) does three things: `_origin_pwd=$(pwd)`, `cd $(cortex-worktree-resolve ...)`, `cortex-lifecycle-event log --event interactive_worktree_entered`. The new sequence replaces only the middle step with the probe→EnterWorktree pair. Step heading delimiter `**Step v — Auto-enter sequence**` is the anchor R11's parity test scans between. R8 acceptance requires `grep -cE 'EnterWorktree\s*\(' skills/lifecycle/references/implement.md` ≥ 1; the call site uses the literal `EnterWorktree(path=...)` syntax in a fenced code block to distinguish it from narrative mentions. R10 fallback marker `EnterWorktree skipped` must appear in §1a prose. **T10 depends on T1** so ADR-0004 promotion lands structurally before any wiring per ADR-README consumer rules — the prose-only Risks-section mitigation is upgraded to a DAG edge.
- **Verification**: (a) `grep -cE 'EnterWorktree\s*\(' skills/lifecycle/references/implement.md` ≥ 1 AND `grep -c 'Step v — Auto-enter sequence' skills/lifecycle/references/implement.md` = 1 AND `grep -c 'EnterWorktree skipped' skills/lifecycle/references/implement.md` ≥ 1 (presence checks); AND (b) `just test tests/test_lifecycle_step_v_ordering.py` exits 0 — a new parity test that extracts the §1a step v block (between `**Step v — Auto-enter sequence**` and the next `**Step` heading) and asserts the five operations appear in the order: `_origin_pwd`, `verify-worktree-auth`, `cortex-worktree-precondition`, `EnterWorktree(`, `interactive_worktree_entered`. The ordering test catches regressions in operation sequence (covers Obj 4's load-bearing-ordering check; not satisfiable by tautological grep). The test file is authored in this same task (one small additional file in Files).
- **Files**: `skills/lifecycle/references/implement.md`, `tests/test_lifecycle_step_v_ordering.py`
- **Status**: [ ] pending

### Task 11: Re-author §1a step vi narrative with session-exit safety guidance
- **Files**: `skills/lifecycle/references/implement.md`
- **What**: Collapse the existing "Variant A (active) / Variant B (rejected)" narrative at §1a step vi (lines 200–212) into a single "Interactive worktree auto-entry" paragraph. The paragraph describes the post-`EnterWorktree` session state, the cache-clear side effect, the session-exit "keep or remove" warning, and the two user restoration paths (`ExitWorktree action="keep"` and `cd $(git rev-parse --show-toplevel)`). One reference to ADR-0004 for the design rationale.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Today's §1a step vi prose is the Variant A/B dispatch language owned by epic #240 — to be collapsed per R12. The new paragraph is ~6-10 lines of prose. The "keep or remove" phrase must appear verbatim (R12 acceptance grep). The `ExitWorktree action="keep"` token must appear as it's load-bearing for R14's parity-test co-location check (token list: `show-toplevel`, `git-common-dir`, `verify-worktree-auth`, `EnterWorktree skipped`).
- **Verification**: `grep -c 'Variant A\|Variant B' skills/lifecycle/references/implement.md` = 0 AND `grep -c 'Interactive worktree auto-entry' skills/lifecycle/references/implement.md` ≥ 1 AND `grep -c 'keep or remove' skills/lifecycle/references/implement.md` ≥ 1 — pass if all three checks match.
- **Status**: [ ] pending

### Task 12: Update complete.md Step 8 hard-guard prose + snapshot fixture
- **Files**: `skills/lifecycle/references/complete.md`, `tests/fixtures/complete_md_hard_guard.txt` (new), `tests/test_complete_md_hard_guard_snapshot.py` (new)
- **What**: Edit complete.md Step 8 hard-guard prose (lines 175–181) to teach both exit paths: `ExitWorktree action="keep"` (preferred when EnterWorktree session state is live) and `cd $(git rev-parse --show-toplevel)` (works in both same-session and cross-session contexts; defers keep/remove prompt to session end when state is live). Preserve "Do not auto-cd" sentence and "user must exit the worktree and re-invoke" instruction. Author a fixture file capturing the new hard-guard paragraph bytes; author a snapshot test reading both the file and the fixture and asserting byte equality (to catch future drift; intentional edits update the fixture in the same commit).
- **Depends on**: [4]
- **Complexity**: simple
- **Context**: Today's hard-guard prose (verified via `sed -n '170,200p' skills/lifecycle/references/complete.md`) is anchored by "**Hard guard**:". The new prose preserves the anchor and the structural "must exit" instruction; it adds a sentence enumerating both exit paths with the recommended one (`ExitWorktree action="keep"`) named first. Fixture format: the exact bytes of the paragraph between the `**Hard guard**:` heading and the next `**` boundary. Snapshot test pattern: `assert path.read_text() == fixture.read_text()` with a clear message naming the fixture path for intentional updates.
- **Verification**: `grep -c 'ExitWorktree action' skills/lifecycle/references/complete.md` ≥ 1 AND `grep -c 'Do not auto-cd' skills/lifecycle/references/complete.md` = 1 AND `just test tests/test_complete_md_hard_guard_snapshot.py` exits 0 — pass if all three checks match.
- **Status**: [x] completed

### Task 13: EnterWorktree call-site parity test
- **Files**: `tests/test_lifecycle_enterworktree_callsites.py` (new)
- **What**: Author a parity test that walks `skills/lifecycle/`, finds every match of `EnterWorktree\s*\(` (regex with open-paren to distinguish call sites from descriptive prose), and for each match asserts the surrounding ±20 lines contain (a) the `create_worktree` token AND (b) at least one of the precondition tokens (`show-toplevel`, `git-common-dir`, `verify-worktree-auth`, `EnterWorktree skipped`).
- **Depends on**: [10]
- **Complexity**: simple
- **Context**: Pattern reference: existing parity tests in `tests/test_lifecycle_*.py`. Use `pathlib.Path.rglob` to walk markdown files under `skills/lifecycle/`. For each file, `re.finditer(r'EnterWorktree\s*\(', content)`; for each match, slice ±20 lines and assert both required tokens are present.
- **Verification**: `just test tests/test_lifecycle_enterworktree_callsites.py` exits 0.
- **Status**: [ ] pending

### Task 14: Picker-label parity test
- **Files**: `tests/test_lifecycle_picker_label_pins_worktree.py` (new)
- **What**: Author a parity test extracting the §1 picker block from `skills/lifecycle/references/implement.md` (anchor: heading `**Branch selection**` to the next `**` boundary) and asserting at least one option label between those anchors contains the literal word `worktree`. This is the structural lock on the picker-fires path's authorization.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Today's picker option is "**Implement on feature branch with worktree**" — passes today. The test is forward-looking: catches label renames that would break the authorization gate. Pattern: `assert any('worktree' in opt.lower() for opt in extracted_option_labels)`.
- **Verification**: `just test tests/test_lifecycle_picker_label_pins_worktree.py` exits 0.
- **Status**: [x] completed

### Task 15: WorktreeCreate-bypass implementation test
- **Files**: `tests/test_create_worktree_bypass.py` (new)
- **What**: Author a test that reads `cortex_command/pipeline/worktree.py::create_worktree`'s source and asserts the function's subprocess invocation contains `'git', 'worktree', 'add'` and does NOT contain `'claude', '--worktree'`. Add a secondary defensive grep assertion: `grep -c 'EnterWorktree' plugins/cortex-core/hooks/hooks.json` = 0.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The actual invariant ADR-0004's bypass clause protects is that `create_worktree` invokes `git worktree add` directly via subprocess (not via the platform's `claude --worktree` launch path). Read the function source via `inspect.getsource(create_worktree)`; assert the relevant tokens appear / don't appear. The defensive hooks.json check catches a future hook registration on the EnterWorktree event but is not the load-bearing assertion.
- **Verification**: `just test tests/test_create_worktree_bypass.py` exits 0 and contains both assertions.
- **Status**: [x] completed

### Task 16: Kept-pauses inventory regression check (no edits expected)
- **Files**: `tests/test_lifecycle_kept_pauses_parity.py` (existing — no edits expected)
- **What**: Run the existing parity test to confirm auto-enter wiring did not invalidate the kept-pauses inventory. Auto-enter is non-interactive (no new AskUserQuestion site), so SKILL.md line 203 anchor for `implement.md:49` should still resolve via `read_branch_mode | lifecycle_config` marker proximity (±35 lines). If the test fails, the failure indicates the §1a structural marker was inadvertently displaced and the failing predecessor task (T3, T10, or T11) must be revisited.
- **Depends on**: [3, 10, 11]
- **Complexity**: trivial
- **Context**: This task is observational — the parity test exists today and is expected to continue passing. The task exists as a checkpoint so Phase 4 explicitly verifies the kept-pauses inventory was not broken by the §1a edits.
- **Verification**: `just test tests/test_lifecycle_kept_pauses_parity.py` exits 0.
- **Status**: [ ] pending

### Task 17: Run R21 manual gate-firing verification
- **Files**: `cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log`
- **What**: Manual verification performed by the developer once Phase 1–3 are merged AND T8's init-handler tests are green AND `cortex init` has been run on a test consumer repo. Steps: spawn a fresh Claude Code session in a consumer repo with `branch-mode: worktree-interactive` set; invoke `/cortex-core:lifecycle implement <test-slug>`; observe that EnterWorktree fires (the session's reported CWD changes to the worktree path — confirmed by Claude tool-call output, not by parent shell `pwd`) AND `interactive_worktree_entered` lands in events.log. Append an `auto_enter_smoke_test` event row with `gate_fires: true|false`. The spec is closed only if `gate_fires: true` is observed; on `gate_fires: false`, the spec re-opens.
- **Depends on**: [1, 2, 5, 6, 7, 8, 10, 11]
- **Complexity**: simple
- **Context**: This is an Interactive/session-dependent verification per R21. The auto_enter_smoke_test event row's JSON payload format: `{"ts": "<ISO 8601>", "event": "auto_enter_smoke_test", "feature": "lifecycle-implement-auto-enter-worktree-via", "gate_fires": true|false, "session_exit_prompt_fires": true|false, "complete_hard_guard_fires": true|false, "both_exit_paths_enumerated": true|false, "observed_in_version": "<claude-code-version>", "transcript_url_or_path": "<witness>", "notes": "<freeform>"}`. The `transcript_url_or_path` field is the third-party witness (transcript excerpt, screenshot path, or separate harness log) that lifts the row above pure self-attestation — required so the verification surface is not pure self-construction. **Disambiguation guidance**: `gate_fires: true` requires BOTH the post-call tool output reporting the session CWD as the worktree path AND the events.log row landing in the worktree's `cortex/lifecycle/.../events.log` (not the main repo's). Partial-pass modes — probe succeeded but EnterWorktree silently no-op'd — manifest as the post-call output reporting unchanged CWD; record `gate_fires: false` in that case. The `complete_hard_guard_fires` and `both_exit_paths_enumerated` fields are observed in T19.
- **Verification**: Interactive/session-dependent: `grep -cE '"event":\s*"auto_enter_smoke_test".*"gate_fires":\s*true' cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log` ≥ 1 — pass only when the row records `gate_fires: true` AND a non-empty `transcript_url_or_path` value is present.
- **Status**: [ ] pending

### Task 18: Run R22 session-exit-prompt verification + close lifecycle's spec
- **Files**: `cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log`
- **What**: After T19 has observed Complete hard guard, end the session (Ctrl-D, `/exit`, or terminal close — record which form was used) and observe whether the harness prompts "keep or remove" with the worktree path as context. Record `session_exit_prompt_fires: true|false` in the auto_enter_smoke_test row. If `false`, the R12 narrative paragraph's warning prose is revised in a follow-up commit before the lifecycle is closed.
- **Depends on**: [19]
- **Complexity**: simple
- **Context**: Interactive/session-dependent verification per R22. The event row's payload format is defined in T17's context. The "keep or remove" prompt is expected on all session-exit shapes (Ctrl-D, `/exit`, terminal close); record any divergence in the `notes` field for follow-up. All three load-bearing fields (`gate_fires`, `complete_hard_guard_fires`, `session_exit_prompt_fires`) must record `true` before the lifecycle Complete phase fires.
- **Verification**: Interactive/session-dependent: `grep -cE '"event":\s*"auto_enter_smoke_test".*"session_exit_prompt_fires":\s*true' cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log` ≥ 1 — pass only when the row records `session_exit_prompt_fires: true`.
- **Status**: [ ] pending

### Task 19: Run R15 manual Complete hard-guard verification
- **Files**: `cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log`
- **What**: While in the same session used for T17 (after observing auto-enter fired and the session is inside the worktree), invoke `/cortex-core:lifecycle complete <test-slug>`. Observe that Step 8 hard guard fires AND the printed message enumerates BOTH exit paths (`ExitWorktree action="keep"` named as preferred, `cd $(git rev-parse --show-toplevel)` named as fallback). Record `complete_hard_guard_fires: true|false` AND `both_exit_paths_enumerated: true|false` in the auto_enter_smoke_test row. If either is `false`, T13's Complete prose is revised in a follow-up commit before the lifecycle is closed.
- **Depends on**: [12, 17]
- **Complexity**: simple
- **Context**: Interactive/session-dependent verification per R15. T19 closes the previously-orphaned R15 coverage gap surfaced in plan critical review. The user-facing string "cd out of the worktree before running cleanup" must remain visible (preserved by T12); the new addition is enumeration of BOTH exit paths. After observing the hard guard message, the developer does NOT type `ExitWorktree action="keep"` here (T18 still needs the EnterWorktree session state live for the session-exit prompt to test); instead, ack the hard-guard observation, leave the session inside the worktree, and proceed to T18 with the session intact.
- **Verification**: Interactive/session-dependent: `grep -cE '"event":\s*"auto_enter_smoke_test".*"complete_hard_guard_fires":\s*true' cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log` ≥ 1 AND `grep -cE '"event":\s*"auto_enter_smoke_test".*"both_exit_paths_enumerated":\s*true' cortex/lifecycle/lifecycle-implement-auto-enter-worktree-via/events.log` ≥ 1 — pass only when both fields record `true`.
- **Status**: [ ] pending

## Risks

- **R21/R22/R15 empirical bet may fail**: the load-bearing assumption that Claude honors a tooling-authored cortex-managed CLAUDE.md fence as satisfying the schema's "project instructions" clause is unverified until T17 lands. If `gate_fires: false`, the spec re-opens — likely requiring a revised authorization shape (e.g., switching to a different memory surface, or surfacing an explicit prompt). Plan to fall back to a documented manual instruction path if the empirical bet fails twice.
- **ADR-0004 promotion sequencing**: encoded as DAG edge T10 → T1 (resolves the prior prose-only mitigation per plan critical review). ADR-0006 cross-references T6/T7 subcommands in its body; T6/T7 land in this same lifecycle but a split PR carries the risk that ADR-0006 documents subcommands that don't exist yet. Mitigation: bundle T2/T5/T6/T7 in a single commit train (Phase 1 commits 1–2, Phase 2 commits 1–3) or land T2 last within Phase 1 so ADR-0006's authoritative claims align with deployed code.
- **In-fence user edits silently overwritten**: by design (R5's "latest writer wins" policy). Users who customize the cortex-managed clause lose their edits on the next `cortex init` run. Document this in the ADR-0006 rollback section and the clause itself ("This clause is regenerated by `cortex init` — do not edit inline").
- **Snapshot-fixture drift**: Task 12's snapshot test fixture must be updated when intentional hard-guard prose edits land. Document the update protocol in the test file's docstring; the fixture path is referenced in `complete.md` for discoverability.
- **`cortex-worktree-precondition` shim cross-platform behavior**: the shim relies on `git rev-parse` outputs which are git-version-sensitive. Test against the project's pinned git version and document the minimum-git-version assumption in the shim.

## Acceptance

The lifecycle's whole-feature acceptance: a user with `branch-mode: worktree-interactive` invoking `/cortex-core:lifecycle implement <slug>` on a consumer repo where `cortex init` has been run observes the session auto-entering the `interactive/{slug}` worktree without a manual `cd` step; the implement → review window proceeds inside the worktree; the Complete phase's hard guard fires with both exit-path options enumerated when invoked from inside the worktree; the cortex-managed CLAUDE.md clause round-trips cleanly through write/verify/revoke; and the `auto_enter_smoke_test` event row in events.log carries `gate_fires: true` and `session_exit_prompt_fires: true`.
