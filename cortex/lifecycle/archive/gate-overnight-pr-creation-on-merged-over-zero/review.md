# Review: gate-overnight-pr-creation-on-merged-over-zero

## Stage 1: Spec Compliance

### Requirement 1: Conditional draft gating at runner.sh:1149
- **Expected**: `MC_MERGED_COUNT == 0` → `--draft` + `[ZERO PROGRESS] Overnight session: <INTEGRATION_BRANCH>`; `MC_MERGED_COUNT > 0` → no `--draft`, plain title.
- **Actual**: `runner.sh:1202-1220` branches exactly as specified — sets `DRAFT_FLAG="--draft"` and `PR_TITLE="[ZERO PROGRESS] Overnight session: $INTEGRATION_BRANCH"` on zero-merge; empty `DRAFT_FLAG` and `PR_TITLE="Overnight session: $INTEGRATION_BRANCH"` otherwise. `test_zero_merge_produces_draft` and `test_nonzero_merge_produces_nondraft` assert both shapes.
- **Verdict**: PASS

### Requirement 2: Zero-progress body content
- **Expected**: Body is `**ZERO PROGRESS** — Overnight session <SESSION_ID> merged 0 features. See ...morning-report.md...`; non-zero body lacks `**ZERO PROGRESS**`.
- **Actual**: `runner.sh:1207, 1209` emit the literal template verbatim with `$SESSION_ID` interpolated and the backtick-wrapped `lifecycle/sessions/${SESSION_ID}/morning-report.md` path. Non-zero path at 1216/1218 produces the existing text without `**ZERO PROGRESS**`. Tests validate body contents via `_read_pr_body`.
- **Verdict**: PASS

### Requirement 3: INTEGRATION_DEGRADED × zero-merge title
- **Expected**: Zero-merge + degraded → title is `[ZERO PROGRESS]` only (not combined); body starts with the integration warning file content.
- **Actual**: `runner.sh:1205-1210` preserves the zero-progress title and, when `INTEGRATION_DEGRADED == "true"` AND the warning file exists, writes the warning first (via `cat > "$PR_BODY_FILE"`) then appends the zero-progress paragraph. `test_degraded_plus_zero_title` asserts title exclusivity and body-first-line content.
- **Verdict**: PASS

### Requirement 4: Zero-commit integration-branch pre-check
- **Expected**: `git rev-list --count main..$INTEGRATION_BRANCH`; if 0, skip PR creation entirely, emit the canonical notify message, leave `MC_PR_URL` empty.
- **Actual**: `runner.sh:1196-1199` computes `MC_INTEGRATION_COMMIT_COUNT` with `|| echo 0` fallback for missing refs; when 0, invokes `dry_run_echo "notify.sh" ~/.claude/notify.sh "Zero-progress session with no branch commits — no PR created. Session: $SESSION_ID" || true` and sets `MC_PR_URL=""`. `test_zero_commits_skips_pr` confirms no `gh pr create` line and the expected notify substring.
- **Verdict**: PASS

### Requirement 5: Resume-flow state-flip with once-per-PR marker
- **Expected**: `gh pr view --json url,isDraft,state`; marker=true short-circuits; MERGED/CLOSED short-circuit without setting marker; OPEN+match → no-op; OPEN+mismatch → `gh pr ready [--undo]`; classify 429/rate-limit as transient (no marker set), other failures as persistent (marker set); append `pr_ready_failed` event via `claude.pipeline.state.log_event`.
- **Actual**: `runner.sh:1242-1385` implements the full decision matrix. The `--json url,isDraft,state` query lives at 1242, marker read at 1252-1257, decision matrix at 1267-1273, `gh pr ready [--undo]` invocation at 1277-1281, failure classification at 1329-1334 using `grep -qiE 'HTTP 429|rate limit'`, event append at 1340-1354 using `claude.pipeline.state.log_event` (correct module per spec). Marker is set atomically on success (1307-1325) and on persistent failure (1363-1381) via tempfile + `os.replace`. Neutral log phrase `PR previously handled by runner — deferring to human state` at 1268 matches spec. All six resume-flow subtests present (`test_resume_flips_draft_state`, `test_marker_true_skips_flip`, `test_merged_pr_skips_flip`, `test_closed_pr_skips_flip`, `test_pr_ready_transient_does_not_set_marker`, `test_pr_ready_persistent_sets_marker`) and passing.
- **Verdict**: PASS

### Requirement 6: /morning-review walkthrough exposes draft state
- **Expected**: `--json` field list includes `isDraft`; new sub-step prompts mark-ready/close/skip with exact phrasing; orphan-state warning on close; edge-case table row.
- **Actual**: `skills/morning-review/references/walkthrough.md:495` adds `isDraft` to `--json` fields; lines 514-527 insert the new sub-step between step 3 and step 5 with the prompt text verbatim from spec, the three options with correct `gh` actions, and the NOT-automatically-deleted warning at line 523. Edge-case row at line 606 reads `PR state is DRAFT | Prompt user with mark-ready/close/skip options per the new sub-step`. Spec grep acceptance satisfied: `isDraft` count ≥ 3 (appears at 495, 514, 529), `mark as ready` present (516, 520), `NOT automatically deleted` present (523).
- **Verdict**: PASS

### Requirement 7: --dry-run flag on runner.sh for PR-creation verification
- **Expected**: `--dry-run` echoes instead of executing for `git push`, `gh pr create`, `gh pr ready [--undo]`, `notify.sh`; runs `gh pr view` live; echoes-but-skips state-writes of `integration_pr_flipped_once` and `pr_ready_failed` event appends; silently skips other state writes/morning-report/symlinks; rejects with exit 1 if features still pending.
- **Actual**: Flag parsed at `runner.sh:136-139`; `DRY_RUN=""` initialized at line 101. `dry_run_echo` helper at 1057-1065 handles single-line commands. Rejection guard at 622-625 fires when `DRY_RUN=="true"` AND `PENDING -gt 0`. `gh pr view` runs live at 1242 (not wrapped). Marker writes use inline bash if-guards at 1304-1326 and 1360-1382 emitting `DRY-RUN state-write integration_pr_flipped_once: true`. Event appends use if-guards at 1337-1355 emitting `DRY-RUN event pr_ready_failed reason=<classified>`. Morning-report generation is gated at `runner.sh:1406` (`if [[ "$DRY_RUN" != "true" ]]`) — silent skip. Notify and `gh pr create` / `gh pr ready` calls all wrapped with `dry_run_echo`.
- **Verdict**: PASS

### Requirement 8: Pytest regression coverage (11 tests)
- **Expected**: 11 named tests in `tests/test_runner_pr_gating.py` covering the 2×2 matrix, zero-commit skip, and six resume-flow subtests, using `--dry-run` + subprocess capture + PATH-injected `gh` stub.
- **Actual**: All 11 test names are present and map to the specified assertions: `test_zero_merge_produces_draft`, `test_nonzero_merge_produces_nondraft`, `test_nonzero_merge_degraded`, `test_zero_commits_skips_pr`, `test_degraded_plus_zero_title`, `test_resume_flips_draft_state` (both directions), `test_marker_true_skips_flip`, `test_merged_pr_skips_flip`, `test_closed_pr_skips_flip`, `test_pr_ready_transient_does_not_set_marker`, `test_pr_ready_persistent_sets_marker`. Test isolation per spec (shutil.copy to `tmp_path`, PATH-injected stub, fake bare remote via `insteadOf`, `TMPDIR=tp`). Every test asserts `returncode==0`, no Traceback in stderr, and the requirement-specific pattern — matches the spec's three-assertion hygiene rule. Reported 11/11 passing in 41s.
- **Verdict**: PASS

### Requirement 9: Live-path regression coverage
- **Expected**: `tests/test_runner_resume.py` and `tests/test_runner_signal.py` pass unchanged.
- **Actual**: 4/4 passing in 2.6s per reviewer-provided report; confirms `DRY_RUN=""` initialization at line 101 prevents the `set -u` unbound-variable crash and no other regressions slipped in.
- **Verdict**: PASS

### Requirement 10: In-code asymmetry breadcrumb
- **Expected**: Two comments referencing ticket 131 — one before the cross-repo skip (near runner.sh:1055) and one before the home-repo conditional.
- **Actual**: `runner.sh:1096` carries the cross-repo breadcrumb verbatim; `runner.sh:1201` carries the home-repo breadcrumb verbatim. `grep -c 'ticket 131' claude/overnight/runner.sh` returns 3 (the third instance is the DRY_RUN_GH_READY_SIMULATE test hook comment at line 1283) — satisfies ≥ 2.
- **Verdict**: PASS

## Requirements Drift

**State**: detected
**Findings**:
- The `--dry-run` flag on `runner.sh` is now a first-class runner capability relied on by Task 8's regression suite and explicitly documented in spec Req 7, but pipeline.md does not mention a test-affordance mode on the runner. Absent documentation, future contributors editing `runner.sh` may not know this mode exists or that it must remain non-destructive to the 11 pinned assertions. A brief test-affordance bullet in `requirements/pipeline.md` would capture the capability.
- The `integration_pr_flipped_once` session-state field is a new session-level invariant: once set to True, the runner permanently defers to the human on subsequent resumes. This is a real operator-visible contract (mentioned in walkthrough.md Req 6 flow), not a mere implementation detail. pipeline.md's "Session Orchestration" section documents state-write atomicity and transitions but does not enumerate the session-scoped marker fields that runner.sh reads. Adding a one-line acceptance criterion naming the marker avoids silent regression if a refactor drops the field from `save_state`.
- The home-repo-vs-cross-repo PR-creation asymmetry (home-repo is always a PR participant; cross-repo is opt-in per-feature) is intentional per spec but not reflected in pipeline.md's Session Orchestration block, which only discusses "per-feature commits on integration branch" without distinguishing the two paths. Not strictly a new behavior — the code comment at runner.sh:1096 carries the rationale — but surfacing it in requirements documents the design decision and the intentional-asymmetry invariant.

**Update needed**: `requirements/pipeline.md`

## Suggested Requirements Update

**File**: requirements/pipeline.md
**Section**: ## Functional Requirements → ### Session Orchestration → Acceptance criteria
**Content**:
```
  - Home-repo integration PR is always created (home-repo is an always-participant); cross-repo PRs are opt-in per-feature and skip when the repo contributed zero merges. On zero-merge home-repo sessions the PR is opened as a draft with a `[ZERO PROGRESS]` title prefix to block accidental merge; `integration_pr_flipped_once` (session-scoped marker in `overnight-state.json`) gates the resume-flow state-flip so the runner defers to human action after the first flip or a persistent `gh pr ready` failure
  - `runner.sh --dry-run` is a supported test-affordance mode that echoes (instead of executing) PR-side-effect calls (`gh pr create`, `gh pr ready`, `git push`, `notify.sh`) and assertable state writes; it rejects invocation when any feature is still pending. Regression coverage lives in `tests/test_runner_pr_gating.py`
```

## Stage 2: Code Quality

- **Naming conventions**: `MC_*` prefix is applied consistently for the new home-repo PR locals (`MC_MERGED_COUNT`, `MC_INTEGRATION_COMMIT_COUNT`, `MC_PR_VIEW_JSON`, `MC_PR_IS_DRAFT`, `MC_PR_STATE`, `MC_PR_URL`, `MC_PR_EXIT`, `MC_FLIPPED_ONCE`, `MC_INTENDED_DRAFT`, `MC_PR_READY_ERR`, `MC_PR_READY_EXIT`, `MC_PR_READY_STDERR`, `MC_READY_REASON`). Matches the pre-existing `MC_*` prefix used by the surrounding home-repo block. Upper-case shell-local convention preserved.
- **Error handling**: `|| echo 0` fallback on `git rev-list` (line 1196) is appropriate — missing ref collapses to the zero-commit skip which is also the right outcome semantically. `jq -r '... // ""'` with `|| echo ""` doubles up on empty-state fallbacks, which is defensive but not incorrect. `2>/dev/null` on the `gh pr view` read and `gh pr ready` stderr redirect to `$MC_PR_READY_ERR` is correctly scoped. The atomic marker-write uses tempfile + `os.replace` with try/except cleanup and raise-re-throw — matches the pattern in `claude/overnight/state.py:save_state`. The pointer-write try/except at 262-285 is appropriate given the subprocess PermissionError risk in sandboxed tests; wrapping with `|| true` at 284 means live sessions still succeed silently on genuine write failures (acceptable for a dashboard-pointer side-effect). The DRY_RUN_GH_READY_SIMULATE hook is gated by `if [[ "$DRY_RUN" == "true" ]]` at 1290, so live sessions cannot accidentally enter the simulation branch even if the env var leaks in — good defense.
- **Test coverage**: All 11 spec-named tests present; each asserts `returncode==0` + `"Traceback" not in stderr` + pattern, per spec Req 8's three-assertion hygiene rule. PATH-injected `gh` stub covers 4 view scenarios (OPEN+ready/draft mismatch, MERGED, CLOSED) and 3 ready modes (ok/transient/persistent). `_create_integration_branch` uses `git update-ref` + `git commit-tree` to create lightweight dummy commits without touching the working tree — avoids pollution. `GIT_CONFIG_GLOBAL` with an `insteadOf` redirect to a bare repo keeps `git push` fully local. Test isolation uses per-test `tmp_path` (copied fixture + its own bin/ + its own fake remote), so `LOCK_FILE`, `session_start` events, and `interrupt.py` writes never leak. The reverse subtest of `test_resume_flips_draft_state` builds a nested `tp2` with fresh infrastructure — correct pattern. Live-path regression via `test_runner_resume.py` + `test_runner_signal.py` (4 tests) passes unchanged, confirming no `set -u` regression.
- **Pattern consistency**: Inline `python3 -c` blocks for state reads/writes match existing runner.sh style (e.g., lines 227-231, 1134-1142, 1160-1164). The `$DRAFT_FLAG` bare-expansion with optional empty value is the same pattern used elsewhere in the file. The `dry_run_echo` helper mirrors the informal `|| true` notify wrappers — minimal new abstraction. The fixture-driven `integration_degraded` override at line 1189 uses the `.get('integration_degraded', False)` defensive fallback, so live sessions (field absent) retain whatever `$INTEGRATION_DEGRADED` was set to by the integration-test-gate block above — no behavioral drift for non-test invocations. The `claude.pipeline.state.log_event` selection (not `claude.overnight.events.log_event`) correctly avoids the `EVENT_TYPES` whitelist that would raise on `pr_ready_failed`, per spec's explicit call-out.

## Verdict

```json
{"verdict": "APPROVED", "cycle": 1, "issues": [], "requirements_drift": "detected"}
```
