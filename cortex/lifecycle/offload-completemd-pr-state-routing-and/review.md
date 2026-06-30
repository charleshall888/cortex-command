# Review: offload-completemd-pr-state-routing-and

Reviewed against `spec.md`, applying the three approved Phase-3 reconciliations
recorded in `plan.md` Risks R1 (only `feature_complete` migrates; `pr_opened`
stays hand-written per ADR-0020; interface is `--set`/`--set-json`; bug-1
emission-ordering fix split to #339 — emission stays in place at Step 11).

## Stage 1: Spec Compliance

### Requirement 1: Routing classifier with bounded side-effects
- **Expected**: `cortex-lifecycle-complete-route <slug>` classifies the route, emits one JSON line with `{route, terminal, message, pr_state, ...}`, writes no `events.log` rows; only side effects are the Branch-3 `pr.json` reconstruction and `gh` network calls.
- **Actual**: `complete_route.classify` emits the full dict via `json.dumps(separators=(",",":")) + "\n"`; `_base_result` carries all spec keys plus `continue_to` (plan addition). The only write is `_reconstruct_pr_json` (Branch-3 single match). `test_golden_route_table` asserts zero `events.log` line-count delta on every route.
- **Verdict**: PASS

### Requirement 2: Strict-order branch state machine preserved
- **Expected**: Branch 1 `feature_wontfix` → Branch 2 `feature_complete` (shape-agnostic) → Branch 3 orphan probe → Branch 4 (4a-4g), first-match-wins; parametrized golden table over 12 branches.
- **Actual**: `classify` evaluates wontfix → complete_seen → on-main/Branch-3 → Branch 4 in order; Branch 2 matches on the `event` key only (line 437-440, shape-agnostic). `test_complete_route.py::test_golden_route_table` pins the exact `{route, terminal, continue_to, pr_state}` tuple for all 12 routes; `test_lifecycle_complete_state_routing.py` covers the same 12 + precedence behaviorally (`test_wontfix_precedes_complete_and_open_pr`, `test_feature_complete_precedes_pr_state`). All green.
- **Verdict**: PASS

### Requirement 3: Verb owns the routing contract; routing test migrated in full
- **Expected**: terminal strings move into the verb; every assertion in `test_lifecycle_complete_state_routing.py` that read `complete.md` prose now targets the verb, with only intentional structural residuals.
- **Actual**: All ~10 terminal strings live in `complete_route.py` (`_route_4a/4b`, `_branch4`, wontfix block). The migrated test asserts verb `{route, message, pr_state}` output for messages, verb module source for command/order tokens, and behavioral routes for the orphan-probe prose; only two residual `complete.md` reads remain (`test_step_7_heading_present`, `test_step7_invokes_verb_and_drops_terminal_messages` — the persisted narration-removal wiring guard). `_VERB_OWNED_TERMINAL_STRINGS` guard confirms the Step-7 region carries none of the moved strings.
- **Verdict**: PASS

### Requirement 4: gh-absent / no-network degrades gracefully
- **Expected**: missing `gh`, `gh auth status` non-zero, or `gh pr view` network/auth error → Branch 4a `pr_state: unknown`, verbatim message, exit 0.
- **Actual**: `_branch4` checks `shutil.which("gh")` → 4a, then `gh auth status` non-zero → 4a, then `gh pr view` non-zero with non-"could not resolve" stderr → 4a. `main` returns 0 on all routes. `test_gh_absent_routes_unknown_exit_zero` and `test_auth_failure_routes_unknown` both pass.
- **Verdict**: PASS

### Requirement 5: on-main route bypasses the orphan probe
- **Expected**: on `main`/`master` with no `pr.json`, return `on_main` and run no `gh pr list`.
- **Actual**: `classify` resolves `_current_branch()` and, when `pr.json` absent and branch ∈ {main,master}, returns `on_main` before `_orphan_probe`. `_build_on_main` installs a stub that *would* report 5 PRs; the route is still `on_main`, proving the probe was bypassed.
- **Verdict**: PASS

### Requirement 6: Branch-3 recovery and ambiguity preserved
- **Expected**: single match → atomic `pr.json` reconstruction then Branch 4; multiple → `orphan_ambiguous` with `candidates`, no write, user pick stays in prose.
- **Actual**: `_reconstruct_pr_json` writes via `_atomic_write_json` (tempfile + `os.replace`) then `_branch4`; multi-match sets `route=orphan_ambiguous`, `candidates=matches`, no write. `test_branch3_single_match_reconstructs_pr_json_then_routes` and `test_branch3_multi_match_no_write_with_candidates` pass.
- **Verdict**: PASS

### Requirement 7: CWD-based root resolution
- **Expected**: resolve via the physical CWD (`_resolve_user_project_root_from_cwd`), not `CORTEX_REPO_ROOT`.
- **Actual**: `main` calls `_resolve_user_project_root_from_cwd()`. `test_worktree_cwd_resolution_ignores_env` sets a divergent `CORTEX_REPO_ROOT` (which would route `already_complete`) and confirms the worktree-CWD `events.log` (wontfix) wins and the main-repo artifacts are untouched.
- **Verdict**: PASS

### Requirement 7a: Speculative-caller boundary enforced structurally
- **Expected**: no render/observability surface references the verb; `grep` over statusline/dashboard/hooks = 0.
- **Actual**: `test_no_speculative_callers_grep_guard` greps `claude/statusline.sh`, `cortex_command/dashboard/`, `hooks/` and asserts 0; the module docstring documents the boundary. Passes.
- **Verdict**: PASS

### Requirement 8: complete.md Step 7 prose collapses to a verb call
- **Expected**: Branch 1-4/4a-4g narration replaced by "run it, act on route"; on-main short-circuit and precedence preserved; routing tokens removed from the Step-7 region.
- **Actual**: Step 7 (complete.md:82-98) is the verb call + route/continue_to dispatch; `grep -c complete-route` ≥ 1; the Step-7-region awk slice carries no `gh pr view`/`merge-base`/`Branch 4[a-g]` tokens (guarded by `test_step7_invokes_verb_and_drops_terminal_messages`).
- **Verdict**: PASS

### Requirement 9: Shared staging verb with per-phase path sets
- **Expected**: `--phase {complete|refine}` stages the exact per-phase set over one explicit-path engine.
- **Actual**: `stage_artifacts.collect_paths` builds the complete set (lifecycle md + events.log + drift File + narrowed backlog) and the refine set (research/spec/index/events.log + backlog ticket, spec omitted on cancel). `test_complete_full_set_*`, `test_refine_approval_stages_spec`, `test_refine_cancel_omits_spec_even_when_present` assert the live `git diff --cached --name-only` equals the hardcoded expected set AND the verb's self-reported `staged_paths` (cross-checked).
- **Verdict**: PASS

### Requirement 10: refine approval/cancel sub-mode auto-detected
- **Expected**: bottom-up scan for `phase_transition specify→plan` (approval) vs `lifecycle_cancelled` (cancel); cancel omits `spec.md`.
- **Actual**: `_detect_refine_submode` reverses the parsed events and returns cancel/approval. The cancel test writes `spec.md` on disk yet confirms it is NOT staged — a discriminating control.
- **Verdict**: PASS

### Requirement 11: Backlog write-back narrowed; drops the `-u` sweep (bug 2)
- **Expected**: stage exactly the resolver-filename ticket + `index.md` explicitly; drop `git add -u cortex/backlog/`; resolver exit-3 silently skips; never a `{slug}.md` glob.
- **Actual**: `collect_paths` (complete) appends `cortex/backlog/{resolved_name}` (via `_resolve_backlog_filename` → `resolve_item.resolve`, `status=="ok"` only) and `cortex/backlog/index.md`; no directory/`-u` add anywhere. `test_complete_exit3_stages_no_backlog_and_succeeds` confirms exit-3 stages neither and the verb still exits 0. The fixture ticket (`007-my-feature-with-extra-detail.md` resolving via `lifecycle_slug:` frontmatter for slug `my-feature`) exercises the truncated-prefix case the spec calls out.
- **Verdict**: PASS

### Requirement 12: Stage-first guard and halt-on-commit-failure preserved
- **Expected**: verb reports a `nothing_staged`/`staged` signal matching `git diff --cached --quiet`; caller skips or commits accordingly.
- **Actual**: `stage` derives `signal` from the live `git diff --cached --name-only`. `test_signal_staged_then_nothing_staged_on_noop_rerun` asserts `staged`→quiet exit 1, then commit→`nothing_staged`→quiet exit 0. complete.md:174-179 and post-refine-commit.md:22-27 keep the stage-first guard + halt-on-failure as prose control flow.
- **Verdict**: PASS

### Requirement 13: Negative-token controls ported 1:1, plus the no-sweep control
- **Expected**: the `test_complete_md_finalization_commit.py:21-35` negative guards become staged-set exclusions with dirty tracked controls under `cortex/lifecycle/`, `cortex/requirements/`, plus the bug-2 `cortex/backlog/OTHER.md` no-sweep control.
- **Actual**: `test_complete_full_set_with_negative_and_no_sweep_controls` dirties tracked `residue.md`, `requirements/project.md`, `backlog/OTHER.md`, asserts each is genuinely dirty (a `-u` sweep WOULD catch it) yet absent from the index — behavioral, not string-grep.
- **Verdict**: PASS

### Requirement 14: complete.md Step 11a and post-refine-commit.md staging prose collapse
- **Expected**: both sections replaced by the verb call + residual control-flow prose.
- **Actual**: complete.md:166-172 and post-refine-commit.md:14-20 invoke `cortex-lifecycle-stage-artifacts`; `grep -c stage-artifacts` ≥ 1 in each.
- **Verdict**: PASS

### Requirement 15: Finalization-region guard updated
- **Expected**: positive token = the verb invocation; `git add -u cortex/backlog/` flips to absent; negative-token intent migrates to the behavioral test.
- **Actual**: `test_complete_md_finalization_commit.py` asserts `cortex-lifecycle-stage-artifacts` present, keeps the residual control-flow positives (`cortex-read-commit-artifacts`, `/cortex-core:commit`, `git diff --cached --quiet`, halt, main/master), flips `git add -u cortex/backlog/` to a negative, and keeps all original negatives. Passes.
- **Verdict**: PASS

### Requirement 16: feature_complete emission migrated (RECONCILED)
- **Expected (reconciled)**: only `feature_complete` migrates to `cortex-lifecycle-event log` via `--set`/`--set-json`; `pr_opened` stays hand-written raw JSON (ADR-0020 exemption); emission stays IN PLACE at Step 11 before the commit (bug-1 ordering fix split to #339).
- **Actual**: complete.md:152 uses `cortex-lifecycle-event log --event feature_complete --feature {slug} --set-json tasks_total={N} --set-json rework_cycles={N} --set merge_anchor=merge`. `pr_opened` raw JSON retained at complete.md:65 (`grep` = 1). The verb call sits inside the Step-11 region, before the `<!-- finalization-commit-step -->` marker (awk confirms 1 hit), so the row is still staged+committed by Step 11a — today's ordering, no regression. Retained `pr_opened` raw JSON and pre-commit emission are the approved behavior, NOT defects.
- **Verdict**: PASS

### Requirement 17: Field-set + values invariant pinned per event type
- **Expected (reconciled)**: `feature_complete` carries exactly `{ts, event, feature, tasks_total(int), rework_cycles(int), merge_anchor="merge"}`, no `schema_version`/`worktree_path`; round-trip + real-consumer classification; `pr_opened` exemption regression-guarded.
- **Actual**: `test_complete_feature_complete_emission.py` drives the verb in-process (frozen `ts`), asserts the exact key-set, int types (with bool exclusion), `merge_anchor=="merge"`, no `schema_version`/`worktree_path`, and feeds the row through real consumers `detect_lifecycle_phase` (→complete), `extract_feature_metrics` (carries `merge_anchor`, reads `feature`/`ts` without KeyError), and `compute_aggregates`/`avg_phase_durations_by_anchor` (buckets under "merge", not "review"). A guard asserts the `pr_opened` literal still carries `schema_version`. All green.
- **Verdict**: PASS

### Requirement 18: Events-registry producer rows updated
- **Expected**: `feature_complete`/`pr_opened` rows reflect the migrated path; no new event types; registry gates green.
- **Actual**: `feature_complete` row (line 12) still lists `complete.md` as producer — correct, since the scanner recognizes `--event <name>` from the verb call; `pr_opened` row (line 137) unchanged (still hand-written). `just check-events-registry` exits 0. (See Stage 2 note on the `-audit` gate.)
- **Verdict**: PASS

### Requirement 19: Verbs registered and mirrored; gates pass at every phase boundary
- **Expected**: both verbs console-script-registered (no `bin/` wrapper); parity no E002; mirrors in sync; `just test` and audits green per phase.
- **Actual**: `pyproject.toml` registers `cortex-lifecycle-complete-route` (line 53) and `cortex-lifecycle-stage-artifacts` (line 59), alpha-ordered, console-script-only. `parity_check --json` returns `[]` (no drift, no E002). Both canonical→mirror `complete.md`/`post-refine-commit.md` pairs are byte-identical. The full #331 test set (86 tests across the 7 affected files incl. `test_runner_pr_gating.py`) plus kept-pauses + phase parity (53 tests) are green. NOTE: `just check-events-registry-audit` exits 1, but exclusively on pre-existing STALE_DEPRECATION rows (confidence_check, discovery_reference, orchestrator_*, seatbelt_probe, etc.) whose deprecation dates passed today (2026-06-29) — none are `feature_complete`/`pr_opened`, and #331 does not touch `bin/.events-registry.md` (last modified by #330). This is time-based environmental drift, not a #331 regression.
- **Verdict**: PASS

### Requirement 20: Kept-pauses parity serviced
- **Expected**: Step-6 merge-wait pause and the Branch-3 multi-match pick preserved as "ask the user" prose, no `AskUserQuestion` literal; parity tests green.
- **Actual**: `grep -c AskUserQuestion complete.md` = 0; complete.md:98 phrases the multi-match pick as "ask the user which to use" with the write-pr.json + re-run continuation tail intact. `test_lifecycle_kept_pauses_parity.py` + `test_lifecycle_phase_parity.py` pass.
- **Verdict**: PASS

## Stage 2: Code Quality
- **Naming conventions**: Strong adherence to the `detect_lifecycle_phase`/`_cli_detect_phase` precedent — pure `classify(slug, root) -> dict` / `stage(phase, slug, root) -> dict` + thin `main(argv) -> int` that serializes with `json.dumps(separators=(",",":")) + "\n"`. Helpers consistently underscore-prefixed (`_run`, `_git_out`, `_branch4`, `_collect_paths` analogues). Compact-JSON and exit-code contracts match the package idiom.
- **Error handling**: gh/git failures route safely — `_run` swallows `OSError`/`SubprocessError` → None, and every degraded path returns a valid route with exit 0; `main` returns non-zero only on argparse usage error or `CortexProjectRootError`. Conservative dirty-default (`status is None` counts as dirty) prevents auto-cleanup on a failed status check. `stage` ignores the `git add` returncode but derives the honest signal from the live index (`git diff --cached`), which is the source of truth — consistent with the graceful-degradation contract and behavior-preserving versus the old prose `git diff --cached --quiet` guard.
- **Test coverage**: Genuinely discriminating. The golden table pins the full 4-tuple per route; negative controls are behavioral (dirty-then-assert-absent, not source greps) and verified to be catchable by the dropped sweep; the cancel test writes `spec.md` on disk to prove omission; the staged-set tests cross-check the live index against the verb's self-report so neither assertion trusts the other; the emission test classifies through three real consumers (no mock/self-seal). The on-main fixture uses a stub that *would* report orphans as a negative control for probe bypass.
- **Pattern consistency**: Explicit-path staging only (`git add -- <paths>`, no directory/`-u`), console-script-only registration (no `bin/` wrapper), canonical+mirror byte-identical. Atomic `pr.json` write via tempfile-in-parent + `os.replace` matches the complete.md Step-4 invariant.
- **Idempotency**: complete.md Step 7 dispatches on `route`/`continue_to`, not a binary `terminal` switch — `already_complete` → Step 12 (no re-cleanup, no duplicate `feature_complete`, no second `pr.json`), pinned by `test_feature_complete_precedes_pr_state` (`continue_to=="step12"`). The Branch-3 reconstruction is idempotent across re-invocations (once `pr.json` exists Branch 3 no longer fires). The stage verb no-ops cleanly on re-run (`nothing_staged`).

## Requirements Drift
**State**: none
**Findings**:
- None. The two new verbs are a behavior-preserving offload; the bug-2 backlog-staging narrowing is documented in the spec's Changes-to-Existing-Behavior; the `feature_complete` emission via `cortex-lifecycle-event` with `merge_anchor: "merge"` matches `project.md`'s Multi-step-lifecycle requirement (finalization tail commits artifacts + backlog write-back via a flag-gated stage-first step; merge is the terminal anchor). No uncaptured behavior introduced.
**Update needed**: None

## Verdict
```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "none"}
```
