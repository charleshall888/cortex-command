# Review: manage-interactive-feature-worktree-lifecycle-creation

**Loaded requirements files**:
- `cortex/requirements/project.md` — project-level architecture, philosophy, conditional-loading map
- `cortex/requirements/pipeline.md` — overnight runner, atomicity invariants (referenced by R17), pipeline events
- `cortex/requirements/multi-agent.md` — worktree-isolation contract (matches `worktrees` substring in Conditional Loading for tag `worktree-interactive`)
- `cortex/requirements/observability.md` — statusline rendering contract (R15)
- `cortex/requirements/glossary.md` — listed in `## Global Context`; file absent on disk (skipped: file absent)

## Stage 1: Spec Compliance

### Requirement 1: `cleanup_worktree()` removes silent `--force` fallback; adds explicit `force` parameter
- **Expected**: Signature includes `force: bool = False`; only the `_orphan_guard` site passes `force=True` with a comment naming SIGKILL-recovery rationale.
- **Actual**: `cortex_command/pipeline/worktree.py:349-356` defines `force: bool = False` (keyword-only). Only call site with `force=True` is `cortex_command/overnight/daytime_pipeline.py:262`, prefixed by the comment "SIGKILL-recovery path: force=True is required because the worktree may have uncommitted state from the killed process." Silent `--force` retry removed.
- **Verdict**: PASS

### Requirement 2: `cleanup_worktree()` pins subprocess cwd to main worktree
- **Expected**: New `_main_worktree_root(repo: Path | None = None)` helper; subprocess cwd is `repo_path` when set, else `_main_worktree_root()`.
- **Actual**: `_main_worktree_root` at `cortex_command/pipeline/worktree.py:59-84` parses `git worktree list --porcelain` first entry, falling back to `_repo_root()` on failure. Line 382 routes cwd: `repo = repo_path if repo_path is not None else _main_worktree_root(repo_path)`. Subprocess calls use `cwd=str(repo)`.
- **Verdict**: PASS

### Requirement 3: `cleanup_worktree()` accepts branch as required parameter; all callers updated in lockstep
- **Expected**: `branch` required keyword param with no default; all 11+ call sites pass `branch=` explicitly; new parity test asserts `TypeError` when omitted.
- **Actual**: Signature `def cleanup_worktree(feature: str, *, branch: str, force: bool = False, ...)` at line 349. All 11 call sites in `daytime_pipeline.py`, `smoke_test.py`, `outcome_router.py`, plus 2 in `test_worktree.py` and 2 in `test_worktree_seatbelt.py` pass `branch=`. `tests/test_cleanup_worktree_caller_parity.py` asserts `TypeError` when omitted.
- **Verdict**: PASS

### Requirement 4: ADR documents the design
- **Expected**: ADR file exists with `status: proposed|accepted`, ≥4 "rejected alternative" mentions.
- **Actual**: `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` exists with `status: proposed`. `grep -c -i "rejected alternative"` returns 4. Covers (a) multi-step Complete, (b) WorktreeCreate-hook bypass, (c) SessionStart PATH bootstrap, plus all four rejected alternatives R1–R4.
- **Verdict**: PASS

### Requirement 5: Morning-review Section 5 ordering fixed
- **Expected**: `cortex-update-item status=complete` moves from Section 5 to Section 6b (after merge).
- **Actual**: `skills/morning-review/references/walkthrough.md:526` is `## Section 6b — Close Backlog Tickets`, with `cortex-update-item ... status=complete` at line 538. Section 5 at line 424 is now a stub pointer redirecting to 6b. Section 6 (merge) is at line 434 with `gh pr merge` at line 486. Ordering invariant: close-literal (538) appears after merge-literal (486). `tests/test_morning_review_status_close_ordering.py` validates structural ordering and Section 6b conditioning.
- **Verdict**: PASS

### Requirement 6: `feature_complete` event schema gains `merge_anchor` field
- **Expected**: Registry row documents field; both `review_dispatch.py` producers emit `"review"`; readers default to `"review"` on absence.
- **Actual**: `bin/.events-registry.md:12` row rationale documents schema: `Schema field: merge_anchor: "review" | "merge" ... Readers use event.get("merge_anchor", "review") for backwards compatibility`. `review_dispatch.py:289` and `:538` both emit `"merge_anchor": "review"`. `metrics.py:226` uses `final_complete.get("merge_anchor", "review")`. `report.py:1682` defines `_read_feature_complete_merge_anchor()` helper returning `"review"` default.
- **Verdict**: PASS

### Requirement 7: `metrics.py` segments aggregates by `merge_anchor`
- **Expected**: Phase-duration aggregates partition by anchor; test fixture asserts segmentation.
- **Actual**: `cortex_command/pipeline/metrics.py:1003-1023` adds `avg_phase_durations_by_anchor: dict[str, dict[str, float | None]]` keyed by anchor, preserving the legacy `avg_phase_durations` baseline. `test_metrics.py:1573-1700+` (`test_compute_aggregates_phase_durations_segmented_by_merge_anchor`) exercises mixed-anchor fixtures (review, merge, absent-defaults-to-review) and asserts independent bucket accumulation.
- **Verdict**: PASS

### Requirement 8: `pr_opened` event registered with producer + 2 consumers in same commit
- **Expected**: Registry row with ≥1 producer + ≥2 consumers; `bin/cortex-check-events-registry --audit` exits 0.
- **Actual**: `bin/.events-registry.md:136` registers `pr_opened` with producer `skills/lifecycle/references/complete.md` and consumers `claude/statusline.sh; hooks/cortex-scan-lifecycle.sh`. Audit gate exits 0. Schema documented in rationale matches spec §8. All three landed in same Phase 2 commit window (`57d64d37`, `42a519d0`, `e039700b`).
- **Verdict**: PASS

### Requirement 9: implement.md option 2 creates the interactive worktree (DELIBERATELY EXPANDED scope absorbing epic #237 swap)
- **Expected**: Option 2 invokes `create_worktree(feature="interactive-" + slug, base_branch="main")`; pre-flight checks `interactive.pid` (via `kill -0`) and `active-session.json` for overnight-active rejection.
- **Actual**: `skills/lifecycle/references/implement.md:19` renames option 2 to "Implement on feature branch with worktree" with the daytime-pipeline §1a path removed/superseded. Section 1a at lines 54-96 describes:
  - **Liveness check (i)**: Two-call pattern — read `cortex/lifecycle/sessions/{slug}.interactive.pid`, then `kill -0 $pid`. Rejects with explicit error if alive.
  - **Overnight guard (ii)**: Two-call pattern — read `~/.local/share/overnight-sessions/active-session.json`, parse `repo_path`, reject if matches cwd.
  - **Creation (iii)**: `create_worktree(feature="interactive-{slug}", base_branch="main")`.
  - **Handoff (iv)**: Surfaces path + Variant A/B options (handoff dispatch owned by #240).
  - **Exit (v)**: Exits /cortex-core:lifecycle entirely.
  Three deprecated console scripts properly allowlisted in `bin/.parity-exceptions.md:21-23` as `deprecated-pending-removal` with `lifecycle_id=239`: `cortex-daytime-pipeline`, `cortex-daytime-dispatch-writer`, `cortex-daytime-result-reader`. Integration test `tests/test_implement_option2_worktree_creation.py` verifies worktree path, branch name `interactive/test-fixture`, settings copy, and `.venv` symlink.
- **Verdict**: PASS

### Requirement 10: Worktree creation copies settings and symlinks venv
- **Expected**: Existing `create_worktree()` behavior preserved for `interactive/` prefix (settings copy + `.venv` symlink).
- **Actual**: `cortex_command/pipeline/worktree.py:332-344` retains the copy + symlink logic; `_INTERACTIVE_SENTINEL` detection (lines 307-310) only changes branch-name resolution, not the post-creation steps. Test `test_settings_local_json_copied_to_worktree` and `test_venv_symlinked_into_worktree` (in `test_implement_option2_worktree_creation.py`) verify both behaviors for the interactive feature.
- **Verdict**: PASS

### Requirement 11: complete.md rewritten as 12-step multi-step phase
- **Expected**: 12 ordered steps with `pr_opened`, `merge_anchor`, atomic pr.json write, state-aware re-invocation routing.
- **Actual**: `skills/lifecycle/references/complete.md` has 12 numbered steps via `### Step N` headings: (1) Run Tests, (2) Commit, (3) Push+PR, (4) Write pr.json Atomically, (5) Emit pr_opened, (6) Phase-Exit Pause, (7) State-Aware Routing, (8) Worktree Cleanup, (9) Backlog Write-Back, (10) Backlog Index Sync, (11) Log feature_complete, (12) Summarize. `grep -cE "^### Step [0-9]+"` returns 12. Step 4 includes atomic-write pattern. Step 11 emits `"merge_anchor": "merge"`. On-main short-circuit in Step 2 preserves direct-to-main flow.
- **Verdict**: PASS

### Requirement 12: Step 7 idempotent + state-aware with strict evaluation order (9-branch routing)
- **Expected**: Strict order feature_wontfix → feature_complete → pr.json → gh pr view state matrix; each branch has exact spec exit message.
- **Actual**: `complete.md:91-153` documents the evaluation order as 4 branches with sub-routes:
  - **Branch 1 (feature_wontfix)**: Exit message matches spec "lifecycle was wontfix'd at `<ts>`; nothing to complete (worktree cleanup skipped)."
  - **Branch 2 (feature_complete)**: Short-circuits to Step 12; no duplicate event/cleanup/pr.json.
  - **Branch 3 (pr.json absent)**: Probes `gh pr list --head "interactive/{slug}"` with zero/one/multiple match handling.
  - **Branch 4 (pr.json present)**: Sub-routes 4a–4g cover Auth/network error, PR-not-found, OPEN, MERGED+dirty, MERGED+clean+ancestor, MERGED+clean+non-ancestor, CLOSED-unmerged. Each exit message is verbatim from spec §12. Tests at `tests/test_lifecycle_complete_state_routing.py` parametrize all 12 routing cases and assert verbatim substring presence in complete.md.
- **Verdict**: PASS

### Requirement 13: Worktree cleanup gates on local-truth merge + dirty + ancestor checks
- **Expected**: `git status --porcelain --ignored=traditional` empty; `git merge-base --is-ancestor` success; `cleanup_worktree(slug, branch=f"interactive/{slug}", force=False)` only; non-interactive features skip silently.
- **Actual**: `complete.md:157-178` documents Step 8: PWD hard-guard (`realpath PWD` comparison), `interactive/`-prefix gating, dirty-and-non-ancestor gates, explicit `force=False`. Tests `tests/test_complete_cleanup_gates.py:344` (`test_force_false_enforced`) asserts force=False; `test_non_interactive_prefix_skips_cleanup` covers option 1/3 silent skip. PWD guard prose: "cd out of the worktree before running cleanup; current PWD is the worktree being removed."
- **Verdict**: PASS

### Requirement 14: PATH bootstrap migrated to SessionStart hook with cortex-shape gate
- **Expected**: Canonical `claude/hooks/cortex-session-start-path-bootstrap.sh` absorbs PATH bootstrap; cortex-shape gate `[[ -d "$LIFECYCLE_DIR" ]] || exit 0` present; WorktreeCreate hook retains non-PATH concerns only; registered in `plugins/cortex-core/hooks/hooks.json` under `SessionStart`.
- **Actual**: `claude/hooks/cortex-session-start-path-bootstrap.sh` (35 lines) reads `$CWD` from stdin JSON, enforces shape gate at line 25 (`[[ -d "$LIFECYCLE_DIR" ]] || exit 0`), writes augmented PATH (`$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH:-}`) to `$CLAUDE_ENV_FILE`. `claude/hooks/cortex-worktree-create.sh` no longer references `.local/bin` or `opt/homebrew/bin` (grep returns 0); retains path resolution, `.venv` symlink, stdout emission. `plugins/cortex-core/hooks/hooks.json:3` registers `SessionStart`. Test `tests/test_session_start_path_bootstrap.sh` exercises cortex-shaped and non-cortex-shaped fixtures under `env -i HOME=$HOME PATH=/usr/bin:/bin`.
- **Verdict**: PASS

### Requirement 15: Statusline renders "Complete (awaiting merge)"
- **Expected**: Statusline + scan-lifecycle detect `pr_opened` present + `feature_complete`/`feature_wontfix` absent; render "Complete (awaiting merge)".
- **Actual**: `hooks/cortex-scan-lifecycle.sh:214` emits literal `"Complete (awaiting merge)"` for `complete:awaiting-merge` phase. Detection logic at lines 307-316 composes the three event-presence/absence checks via `grep -q '"event"...'`. `claude/statusline.sh:416-423` mirrors the detection, with rendering at lines 564 and 583. Test `tests/test_statusline_complete_awaiting_merge.sh` exercises three fixtures (pr_opened only; both present; wontfix precedence).
- **Verdict**: PASS

### Requirement 16: Kept-pauses inventory extended for phase-exit pause
- **Expected**: SKILL.md inventory adds entry for complete.md step 6; parity test recognizes "phase-exit pause" kind.
- **Actual**: `skills/lifecycle/SKILL.md:201` adds bullet `- skills/lifecycle/references/complete.md:73 — phase-exit pause: merge-wait pause inside the multi-step Complete phase; user re-invokes /cortex-core:lifecycle complete <slug> after merging on GitHub.` Parity test at `tests/test_lifecycle_kept_pauses_parity.py:36-40` defines `_PHASE_EXIT_PAUSE_TAG = "phase-exit pause"`; lines 124-164 implement the alternate validation path (step-heading proximity check instead of `AskUserQuestion`-site check). Anchor line 73 matches `### Step 6 — Phase-Exit Pause (Handoff Message)` in complete.md.
- **Verdict**: PASS

### Requirement 17: pr.json written atomically with documented schema (extended)
- **Expected**: tempfile + `os.replace` write; schema `{number, url, head_branch, opened_at, repo}` closed; `repo` matches `^[\w.-]+/[\w.-]+$`.
- **Actual**: `complete.md:49-63` documents the atomic-write pattern with code example using `tempfile.NamedTemporaryFile(... dir=pr_json_path.parent, delete=False, suffix=".tmp")` + `os.replace(tmp_path, pr_json_path)`. Schema closed at five fields. `tests/test_complete_pr_json_schema.py` covers atomicity (no observable partial-write), schema validity, ISO8601 parsing, owner/name regex, and rejects extra fields ("closed schema") via `test_schema_has_no_extra_fields`. Structural test class (`TestCompleteStepFourStructural`) anchors prose-level guarantees to the skill document.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- **Multi-step Complete phase concept**: The lifecycle Complete phase now supports multi-step execution with a mid-phase user-driven pause (the phase-exit pause). No requirements doc currently captures this lifecycle-shape variant (multi-step phase with re-invocation routing). The closest existing concept is `cortex/requirements/project.md`'s Philosophy of Work, but the multi-step + re-invocation pattern is a new lifecycle primitive that future phases or skills may want to reuse.
- **Phase-exit pause as a new pause kind**: The kept-pauses inventory previously enumerated only `AskUserQuestion`-site pauses; this lifecycle introduces "phase-exit pause" as a distinct kind. The CLAUDE.md "Kept user pauses" guidance in `skills/lifecycle/SKILL.md` documents the entry, but the higher-level requirements docs do not yet describe the existence of two pause kinds (interactive prompt vs. phase-exit handoff).
- **Deprecated-pending-removal allowlist category**: `bin/.parity-exceptions.md` introduces a third `category` enum value (`deprecated-pending-removal`) alongside the existing `maintainer-only-tool` and `library-internal`. The category is enforced by the parity linter but not yet described in the project requirements as a recognized lifecycle stage for scripts.
- **Merge as terminal lifecycle event**: The project requirements describe lifecycle phases up to Complete but do not state that "merge" (not "PR open") is the terminal event for the "Done" semantics. This shift aligns with industry convention (GitHub, Linear, Jira) and is now load-bearing in the implementation, but the project doc's Philosophy of Work or Quality Attributes section should record this stance.

**Update needed**: `cortex/requirements/project.md`

## Suggested Requirements Update
**File**: `cortex/requirements/project.md`
**Section**: `## Philosophy of Work`
**Content**:
```
**Multi-step lifecycle phases**: A lifecycle phase may be multi-step with a user-driven re-invocation point. The Complete phase is the canonical example — it creates a PR, exits with a handoff message, and finalizes only on re-invocation after the PR is merged on GitHub. Merge (not PR-open) is the terminal event for "Done"; this aligns with GitHub/Linear/Jira/GitLab conventions and is recorded in the `feature_complete` event with `merge_anchor: "merge"`. Re-invocation routing is state-aware and idempotent; consult `cortex/adr/0004-multi-step-complete-and-interactive-worktree-lifecycle.md` for the design rationale.

**Kept user pauses come in two kinds**: (a) `AskUserQuestion`-site pauses where a phase blocks for an interactive answer; (b) phase-exit pauses where a phase exits cleanly and waits for the user to re-invoke after performing an out-of-band action (e.g., merging a PR on GitHub). The `skills/lifecycle/SKILL.md` kept-pauses inventory and `tests/test_lifecycle_kept_pauses_parity.py` enforce both kinds.
```

## Stage 2: Code Quality

- **Naming conventions**: Consistent. `_main_worktree_root` follows the existing `_repo_root` private-helper convention. `_INTERACTIVE_SENTINEL` constant follows the file's existing constant style. The `interactive-` feature prefix is structurally distinct from the resulting `interactive/` branch prefix, which the code splits cleanly at `worktree.py:307-310`. Event-name `pr_opened` matches the `<noun>_<past-participle>` registry convention. Routing-branch labels (4a–4g) match the spec §12 mapping.
- **Error handling**: Appropriate. Atomic write uses `os.replace` (POSIX rename atomicity). The orphan-PR probe is interactive on slug-reuse (multi-match) rather than auto-selecting. PR-not-found and auth-error patterns are distinguished in routing so transient errors don't trigger destructive cleanup. The PWD hard-guard in Step 8 prevents the recipe-from-inside-worktree edge case. Force=True only available at the SIGKILL-recovery path with documented rationale.
- **Test coverage**: Strong overall. 9 new test files cover caller parity, metrics segmentation, morning-review ordering, SessionStart bootstrap, option-2 worktree creation, awaiting-merge rendering, Complete state routing, cleanup gates, and pr.json schema. Two flagged concerns:
  - **`_read_feature_complete_merge_anchor()` helper in report.py is unwired**: defined at line 1682 but called nowhere. This is a forward-staged helper for future report-rendering work; acceptable as a one-line forward stage given the reader-side default is already correctly applied at the existing read sites (`metrics.py:226`). However, an unwired helper has no test coverage and risks bit-rot. **Recommendation**: either wire it into report.py's existing `feature_complete` reader or remove it; spec R6 only requires reader-tolerance which is met at the actual usage sites. Acceptable for this cycle as PARTIAL self-sealing, but flag for follow-up cleanup.
  - **`TestAtomicWrite` group in `test_complete_pr_json_schema.py` reimplements the pattern**: `_write_pr_json_atomically()` is defined inline in the test, mirroring complete.md Step 4's documented pattern rather than calling extracted production code. This is genuinely self-sealing for the atomicity claim. **Mitigation**: the file's `TestCompleteStepFourStructural` class anchors the prose-level claims back to the actual skill document (asserts `os.replace`, `NamedTemporaryFile`, all five schema fields, ISO8601 wording, atomicity reference are present in complete.md). The structural assertions provide externally-anchored validation of the documented contract; the test re-implementation validates the pattern is mechanically correct. Acceptable as documented — Skill prose is inherently model-executed rather than runtime-executed, so structural assertions are the appropriate verification strategy for prose skills.
- **Pattern consistency**: Strong. SessionStart hook mirrors the existing scan-lifecycle hook's cortex-shape gate idiom exactly (`[[ -d "$LIFECYCLE_DIR" ]] || exit 0`). Events-registry row follows existing row schema (10 fields, 12 columns counting boundary pipes). Atomic pr.json write follows the same tempfile + `os.replace` pattern as `cortex/requirements/pipeline.md:124-130` invariant. ADR-0004 follows the existing ADR structure and three-criteria-gate convention from `cortex/adr/README.md`. Deprecated-pending-removal entries in parity-exceptions follow the documented schema with valid rationales (>30 chars, no forbidden literals).

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
