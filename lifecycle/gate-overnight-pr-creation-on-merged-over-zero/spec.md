# Specification: Gate overnight PR creation on merged>0 (draft on zero-merge)

> **Epic reference**: This ticket is a sibling — not a child — of the [`orchestrator-worktree-escape`](../../research/orchestrator-worktree-escape/research.md) epic (DR-2). The epic (parent #126, children 127–130) addresses home-vs-worktree invariant violations; ticket 131 is an independent PR-gating defect that surfaced in the same failed session by coincidence. Background context only; no shared implementation.

## Problem Statement

The home-repo integration-branch PR is created unconditionally at `claude/overnight/runner.sh:1149` whenever `INTEGRATION_BRANCH` is set. When a session fails with zero features merged (a "zero-progress" session), the result is a zombie PR — `OPEN, MERGEABLE, CLEAN` against main, visible in the auto-merge queue, and containing whatever incidental frontmatter mutations happened to commit to the branch. Session `overnight-2026-04-21-1708` produced PR #4 in exactly this state. Operators must manually close such PRs, and the risk of accidental merge is non-zero. `MC_MERGED_COUNT` is already computed at `runner.sh:1134-1142` but is used only in the PR body — never as a gate.

The fix branches the home-repo PR creation on `MC_MERGED_COUNT`: zero → `--draft` with a `[ZERO PROGRESS]` title; non-zero → existing behavior. The cross-repo path at `runner.sh:1055-1058` already skips on zero-merge and is intentionally left asymmetric — cross-repo targets are opt-in per-feature, while the home-repo integration branch is always a session participant.

## Requirements

1. **Conditional draft gating at runner.sh:1149.** When `MC_MERGED_COUNT == 0`, the home-repo PR is created with `--draft` and with title `[ZERO PROGRESS] Overnight session: <INTEGRATION_BRANCH>`. When `MC_MERGED_COUNT > 0`, the PR is created without `--draft` and with the existing title `Overnight session: <INTEGRATION_BRANCH>`.
   Acceptance: `bash claude/overnight/runner.sh --dry-run --state-path tests/fixtures/state-zero-merge.json` prints a `gh pr create` invocation whose argument list contains exactly one occurrence of `--draft` and whose `--title` value starts with `[ZERO PROGRESS]`. `bash claude/overnight/runner.sh --dry-run --state-path tests/fixtures/state-nonzero-merge.json` prints a `gh pr create` invocation with no `--draft` occurrence and whose `--title` value starts with `Overnight session:` (no bracket prefix). Pass if both invocations match.

2. **Zero-progress body content.** When `MC_MERGED_COUNT == 0`, the PR body is:
   ```
   **ZERO PROGRESS** — Overnight session <SESSION_ID> merged 0 features. See `lifecycle/sessions/<SESSION_ID>/morning-report.md` for failure analysis.
   ```
   (Where `<SESSION_ID>` is substituted from `$SESSION_ID`.)
   Acceptance: the `--dry-run` output for the zero-merge fixture, when captured, contains the literal string `**ZERO PROGRESS**` and the substring `lifecycle/sessions/` followed by the session ID. Non-zero fixture: body does NOT contain `**ZERO PROGRESS**`.

3. **INTEGRATION_DEGRADED × zero-merge title.** When both `INTEGRATION_DEGRADED == "true"` AND `MC_MERGED_COUNT == 0`, the title is `[ZERO PROGRESS] Overnight session: <INTEGRATION_BRANCH>` (zero-progress dominates). The integration-gate warning is still prepended to the body via the existing `INTEGRATION_WARNING_FILE` mechanism (lines 1143-1148 behavior), so both signals are visible — but the title carries only the zero-progress marker.
   Acceptance: `--dry-run` against a fixture with `INTEGRATION_DEGRADED=true` and `MC_MERGED_COUNT=0` prints a title starting with `[ZERO PROGRESS]` (not `[ZERO PROGRESS + GATE FAILED]` or `[GATE FAILED]`) and a body whose first line is the integration warning content.

4. **Zero-commit integration-branch pre-check.** Before calling `gh pr create`, run `git rev-list --count main..$INTEGRATION_BRANCH`. If the count is `0`, skip the `gh pr create` call entirely and emit a notification via `~/.claude/notify.sh` with message `Zero-progress session with no branch commits — no PR created. Session: <SESSION_ID>`. In this case `MC_PR_URL` stays empty and the existing `if [[ -n "$MC_PR_URL" ]]` guard at line 1167 already skips URL persistence.
   Acceptance: `--dry-run --state-path tests/fixtures/state-zero-merge-zero-commits.json` prints no `gh pr create` invocation and prints a line matching `notify.sh.*Zero-progress session with no branch commits`. Exit code 0.

5. **Resume-flow state-flip in the recovery path (safely guarded, once-per-PR).** Extend the "PR already exists" recovery at `runner.sh:1157` so `gh pr view --head` includes both `isDraft` and `state` in its JSON output (i.e., `--json url,isDraft,state`). Behavior gates on a persisted state marker `integration_pr_flipped_once: true | false` read from the session's `overnight-state.json` at `$STATE_PATH` (session-level field, default `false`).

   Decision matrix:
   - **`integration_pr_flipped_once == true`** → skip flip entirely regardless of state-match (log `PR previously handled by runner — deferring to human state`); treat recovery as successful. This preserves deliberate operator `gh pr ready` / `gh pr close` actions taken after the first resume, and also applies when a prior persistent failure terminated retry. The log phrasing is intentionally neutral ("handled", not "flipped") because the marker is set for both successful flips and persistent-failure give-ups — forensic detail is in `lifecycle/pipeline-events.log`.
   - **`integration_pr_flipped_once == false` AND `state == "OPEN"` AND `isDraft` matches intended state** → no action beyond URL assignment; do NOT set the marker (no flip occurred).
   - **`integration_pr_flipped_once == false` AND `state == "OPEN"` AND `isDraft` does NOT match intended state** (intended = `true` when `MC_MERGED_COUNT == 0`, `false` otherwise) → invoke `gh pr ready --undo <url>` (ready → draft) or `gh pr ready <url>` (draft → ready); handle per the classification rule below.
   - **`state == "MERGED"` OR `state == "CLOSED"`** → skip the flip entirely; log `PR already <state> — runner yielding to human action`; treat recovery as successful. The marker is NOT set (no flip attempted on an actionable OPEN PR).
   - **Post-`gh pr ready` handling**:
     - **On success (exit 0)**: set `integration_pr_flipped_once: true` in the session state via atomic write (tempfile + `os.replace`).
     - **On non-zero exit — classification**: match stderr substrings case-insensitively: `HTTP 429` OR `rate limit` → `reason: transient`; any other non-zero exit (HTTP 401, HTTP 403, HTTP 5xx, network errors, unspecified errors) → `reason: persistent`.
     - **On `reason: transient`**: append a `pr_ready_failed` event to `lifecycle/pipeline-events.log` with `{event: "pr_ready_failed", session_id, reason: "transient", pr_url, intended_is_draft}`; **do NOT set the marker** — next resume retries the flip naturally (bounded by session lifetime; integration branches are session-scoped and short-lived, so retry storms are self-limiting). Log a warning; treat recovery as successful (URL is valid; state-flip is best-effort).
     - **On `reason: persistent`**: append the event (same shape, `reason: "persistent"`) AND set `integration_pr_flipped_once: true` — retry is pointless for persistent failures (auth revoked, permission denied, etc.); operator is expected to surface via morning-review (Req 6). Log a warning; treat recovery as successful.
     - Event append uses `claude.pipeline.state.log_event(log_path: Path, event_dict: dict)` at `claude/pipeline/state.py:288` (the correct owner of `pipeline-events.log` — no event-type whitelist); **NOT** `claude.overnight.events.log_event` (which whitelists `EVENT_TYPES` and would raise on `pr_ready_failed`).

   Acceptance: the following pytest subtests in Req 8 pass — `test_resume_flips_draft_state` (happy-path both directions, asserts marker flips to true), `test_marker_true_skips_flip` (marker=true, OPEN PR with mismatched isDraft → no `gh pr ready` invocation, log line contains `PR previously handled by runner`), `test_merged_pr_skips_flip` (state=MERGED → no `gh pr ready` invocation, marker unchanged), `test_closed_pr_skips_flip` (state=CLOSED → no `gh pr ready` invocation, marker unchanged), `test_pr_ready_transient_does_not_set_marker` (mocked 429 stderr → `pipeline-events.log` gets `pr_ready_failed` event with `reason: transient`, marker stays false so next resume retries), `test_pr_ready_persistent_sets_marker` (mocked 401 stderr → event with `reason: persistent`, marker set to true).

6. **`/morning-review` walkthrough exposes draft state.** Modify `skills/morning-review/references/walkthrough.md`:
   - Line 495: change `--json number,url,state,title` → `--json number,url,state,title,isDraft`
   - Insert a new sub-step between current step 3 and step 4: "If `isDraft` is true, inform the user: 'PR is in DRAFT state (zero-progress session means the overnight runner produced no merged features). Direct merge will fail because GitHub blocks draft-PR merges. Choose one: mark as ready and merge, close the PR, or skip for manual follow-up.'"
   - Add three options matching that prompt, each taking the appropriate `gh` action: (a) `gh pr ready <number>` then `gh pr merge`, (b) `gh pr close <number>` AND display warning `WARNING: the integration branch <branch> and its worktree are NOT automatically deleted when you choose "close". Run \`git push origin --delete <branch>\` and check \`git worktree list\` for orphan worktrees manually.`, (c) skip with note in the morning-review summary.
   - Update the edge-case table (line 589 area) to add an entry: `PR state is DRAFT | Prompt user with mark-ready/close/skip options per the new sub-step`.
   Acceptance: `grep -c 'isDraft' skills/morning-review/references/walkthrough.md` ≥ 3. `grep 'mark as ready' skills/morning-review/references/walkthrough.md` returns ≥ 1 match. `grep 'NOT automatically deleted' skills/morning-review/references/walkthrough.md` returns ≥ 1 match.

7. **`--dry-run` flag on runner.sh for PR-creation verification.** Add a `--dry-run` flag to `claude/overnight/runner.sh`. When set, the script:
   - **Skips and echoes** (prints a `DRY-RUN <command>` line instead of executing): `git push -u origin`, `gh pr create`, `gh pr ready` / `gh pr ready --undo`, `notify.sh` invocations.
   - **Runs live** (read-only): `gh pr view --head` (needed for the resume-flow recovery path to discover existing PRs during the test).
   - **Skips and echoes for assertable state** (prints a line but does NOT mutate disk): the `integration_pr_flipped_once` marker write in Req 5 → emit `DRY-RUN state-write integration_pr_flipped_once: true` to stdout. The `pr_ready_failed` event append in Req 5 → emit `DRY-RUN event pr_ready_failed reason=<classified_reason>` to stdout.
   - **Skips silently** (no stdout echo — preserves pre-test behavior shape): all other state writes to `$STATE_PATH`, event-log appends to `$EVENTS_PATH` not covered above, artifact commits, morning-report generation, symlink swaps.
   Other state-mutating operations in the end-of-session block not explicitly listed above are skipped silently by default. The flag is scoped to the end-of-session PR block only; earlier runner logic (feature dispatch, round loop) is not gated and the flag MUST be rejected with exit code 1 and an error message if set before the session reaches the end-of-session block.
   Acceptance: `bash claude/overnight/runner.sh --dry-run --state-path tests/fixtures/state-nonzero-merge.json` exits 0 and stdout contains a line beginning with `DRY-RUN gh pr create`. Stdout contains no `ERROR` lines. No side effects to `$STATE_PATH`, `$EVENTS_PATH`, `lifecycle/sessions/`, or integration-branch remote state after the test completes.

8. **Pytest regression coverage.** Add `tests/test_runner_pr_gating.py` with these tests (all using `--dry-run` and subprocess capture):
   - `test_zero_merge_produces_draft`: fixture `state-zero-merge.json` → assert `--draft` present, title starts with `[ZERO PROGRESS]`, body contains `**ZERO PROGRESS**`.
   - `test_nonzero_merge_produces_nondraft`: fixture `state-nonzero-merge.json` → assert `--draft` absent, title starts with `Overnight session:`, body lacks `**ZERO PROGRESS**`.
   - `test_nonzero_merge_degraded`: fixture with `INTEGRATION_DEGRADED=true` and `MC_MERGED_COUNT > 0` → assert title is plain `Overnight session:` (no bracket prefix), body begins with integration warning content, `--draft` absent. This covers the (merge>0, DEGRADED=true) cell of the 2×2.
   - `test_zero_commits_skips_pr`: fixture `state-zero-merge-zero-commits.json` → assert no `gh pr create` in stdout; assert `notify.sh.*no branch commits` in stdout.
   - `test_degraded_plus_zero_title`: fixture with `INTEGRATION_DEGRADED=true` and zero merges → title `[ZERO PROGRESS]` (not combined); body includes integration warning.
   - `test_resume_flips_draft_state`: mocked `gh pr view` returns `{url, isDraft:false, state:"OPEN"}` with `MC_MERGED_COUNT=0` and `integration_pr_flipped_once=false` → assert stdout contains `DRY-RUN gh pr ready --undo <url>` AND stdout contains `DRY-RUN state-write integration_pr_flipped_once: true`. Reverse subtest: mocked PR returns `{isDraft:true, state:"OPEN"}` with `MC_MERGED_COUNT>0` → assert stdout contains `DRY-RUN gh pr ready <url>` AND the marker-write line.
   - `test_marker_true_skips_flip`: fixture has `integration_pr_flipped_once=true`; mocked `gh pr view` returns `{isDraft:false, state:"OPEN"}` with `MC_MERGED_COUNT=0` (would be mismatched if marker were false) → assert `gh pr ready` is NOT invoked; assert log line contains `PR previously handled by runner — deferring to human state`.
   - `test_merged_pr_skips_flip`: mocked `gh pr view` returns `state:"MERGED"` → assert `gh pr ready` is NOT invoked (no `DRY-RUN gh pr ready` line in stdout); assert log line `PR already MERGED — runner yielding to human action`; assert marker is unchanged.
   - `test_closed_pr_skips_flip`: mocked `gh pr view` returns `state:"CLOSED"` → same shape as above with `CLOSED`; marker unchanged.
   - `test_pr_ready_transient_does_not_set_marker`: mock simulates `gh pr ready` non-zero exit with `HTTP 429` in stderr (isDraft mismatched, OPEN PR) → assert stdout contains `DRY-RUN event pr_ready_failed reason=transient` AND stdout does NOT contain `DRY-RUN state-write integration_pr_flipped_once: true` (marker stays false; next resume retries).
   - `test_pr_ready_persistent_sets_marker`: mock simulates `gh pr ready` non-zero exit with `HTTP 401` in stderr (isDraft mismatched, OPEN PR) → assert stdout contains `DRY-RUN event pr_ready_failed reason=persistent` AND `DRY-RUN state-write integration_pr_flipped_once: true` (marker set; no more retries).
   Acceptance: `pytest tests/test_runner_pr_gating.py` exits 0 with all 11 tests passing.

9. **Live-path regression coverage.** After the changes, existing runner tests must still pass unchanged. This catches the live-path `$DRY_RUN` unbound-variable / `set -euo pipefail` interaction risk — the existing tests exercise the non-`--dry-run` paths.
   Acceptance: `pytest tests/test_runner_resume.py tests/test_runner_signal.py` exits 0 with no test modifications required.

10. **In-code asymmetry breadcrumb.** Add a bash comment block immediately before `runner.sh:1055` (cross-repo skip) and a matching one immediately before `runner.sh:1149` (home-repo conditional draft). Both comments cross-reference ticket 131 and state the asymmetry rationale:
    - Before line 1055: `# Cross-repo: skip PR creation on MERGED_COUNT==0. Cross-repo targets are opt-in per-feature — a repo with zero merges did not participate in the session. See lifecycle/gate-overnight-pr-creation-on-merged-over-zero/spec.md (ticket 131) for the home-repo/cross-repo asymmetry rationale.`
    - Before line 1149: `# Home-repo: ALWAYS create a PR. When MC_MERGED_COUNT==0, create as --draft with [ZERO PROGRESS] title (self-enforcing merge block). Home-repo is always-a-participant (integration branch is always created + is the morning-review entry point), so asymmetry with cross-repo skip is intentional. See lifecycle/gate-overnight-pr-creation-on-merged-over-zero/spec.md (ticket 131).`
    Acceptance: `grep -c 'ticket 131' claude/overnight/runner.sh` ≥ 2. Both comments verified to exist at or near the specified line numbers (exact line numbers may shift during implementation due to added conditionals).

## Non-Requirements

- Cross-repo PR path at `runner.sh:1020-1115` is NOT modified. Its existing `continue` behavior when `MERGED_COUNT == 0` is retained; the home-repo/cross-repo asymmetry is intentional (cross-repo targets are opt-in per-feature; home-repo is always-participant).
- Long-tail cleanup of stale zero-progress drafts is NOT in scope. A separate follow-up ticket will design sweep/expiry if needed.
- The runner does NOT rewrite pre-existing non-draft PRs from before this ticket landed. Legacy zombie PRs (like #4) remain the operator's responsibility to close manually.
- The underlying causes of zero-progress sessions (agent timeouts, plan-parse failures, etc.) are NOT addressed here; those belong to the parent worktree-escape epic (#126) and other tickets.
- No changes to `claude/overnight/report.py` morning-report rendering — PR URLs are already captured draft-agnostically and the report will render draft PR links identically to non-draft links.
- No changes to `bin/git-sync-rebase.sh` or `claude/overnight/sync-allowlist.conf` — post-merge sync is unaffected by pre-merge draft state.
- Concurrent-session safety (two overnight sessions targeting the same integration branch) is NOT addressed. Session IDs are generated fresh per invocation, making this scenario require either a bug in ID generation or manual intervention — both out of scope.

## Edge Cases

- **Zero commits on integration branch**: handled explicitly by Requirement 4 — pre-check + notify + clean skip.
- **Resume with changed merge count + OPEN PR**: handled by Requirement 5 — recovery path reads `isDraft` + `state` and flips via `gh pr ready [--undo]` when state is OPEN.
- **Resume when PR was already merged/closed by a human**: handled by Requirement 5 — `state == "MERGED"` or `"CLOSED"` short-circuits the flip; logs an informational "runner yielding to human action" line; recovery still succeeds.
- **`gh pr ready` flip fails with transient error (HTTP 429 / rate limit)**: handled by Requirement 5 — `pr_ready_failed` event appended to `pipeline-events.log` with `reason: transient`; marker is NOT set so the next resume retries the flip naturally. Integration branches are session-scoped and short-lived, so retry storms are bounded by session lifetime.
- **`gh pr ready` flip fails with persistent error (HTTP 401/403, HTTP 5xx, network, or unspecified)**: handled by Requirement 5 — event appended with `reason: persistent`; marker IS set to prevent pointless retry. Operator surfaces the issue via morning-review (Req 6), which exposes the PR's `isDraft` state and offers mark-ready / close / skip options.
- **`MC_MERGED_COUNT` is stale due to state drift**: if state was truncated or corrupted mid-flight, the count may be wrong. This is an existing data-integrity concern outside this ticket's scope. The state-flip in Req 5 slightly amplifies the blast radius (previously wrong body line → now possibly wrong draft state), but the `state == "MERGED"` / `"CLOSED"` guards bound the harm: a drift-corrupted resume cannot reopen or reverse a merge/close.
- **`INTEGRATION_DEGRADED == "true"` with `MC_MERGED_COUNT > 0`**: title stays `Overnight session: <INTEGRATION_BRANCH>` (no bracket prefix); body prepends the integration warning (existing behavior at lines 1143-1148). Covered by Requirement 8's `test_nonzero_merge_degraded`.
- **Operator manually marks a zero-progress draft as ready, then the session resumes**: handled by Requirement 5's `integration_pr_flipped_once` marker. First resume: runner is authoritative (flips to match `MC_MERGED_COUNT`, sets marker). Subsequent resumes: marker-gated short-circuit (no flip; log "deferring to human state"). Preserves runner's first-resume fix for the common case (session resumes before any human touches the PR) while protecting deliberate operator actions on later resumes. Same handling applies to the operator-marks-ready-but-merge-failed path.
- **`--dry-run` flag live-path regression**: handled by Requirement 9 — existing test suites must still pass, catching any `set -euo pipefail` × unbound `$DRY_RUN` interaction.
- **Pre-existing non-draft PR from a prior session + resume with `MC_MERGED_COUNT == 0`**: the PR is OPEN (not closed), `isDraft` is false, intended state is draft. The runner flips it to draft. This is intentional per Requirement 5 — the prior session's PR is part of this session's resumed scope. Distinct from the operator-mark-ready-without-merging case above (which is the unresolved tension).

## Changes to Existing Behavior

- **MODIFIED**: `claude/overnight/runner.sh` end-of-session PR block (lines 1117–1177) — home-repo PR creation now branches on `MC_MERGED_COUNT` with draft flag, title prefix, and body template. Recovery path extended to read `isDraft` + `state` and conditionally flip.
- **MODIFIED**: `claude/overnight/runner.sh` — new `--dry-run` flag scoped to the end-of-session block for test harness use.
- **MODIFIED**: `claude/overnight/runner.sh` — in-code comments added at the cross-repo skip (line 1055 area) and home-repo PR-creation (line 1149 area) cross-referencing ticket 131.
- **MODIFIED**: `skills/morning-review/references/walkthrough.md` — `gh pr list --json` now includes `isDraft`; new sub-step prompts operator on draft PRs with three options; orphan-state warning on the "close" option; edge-case table adds draft-state row.
- **ADDED**: `tests/test_runner_pr_gating.py` — new regression suite (9 tests) for PR gating behavior, including state-flip guards and failure-classification.
- **ADDED**: `tests/fixtures/state-zero-merge.json`, `tests/fixtures/state-nonzero-merge.json`, `tests/fixtures/state-zero-merge-zero-commits.json`, `tests/fixtures/state-nonzero-merge-degraded.json` — fixture state files backing the tests.

## Technical Constraints

- Bash style must follow the existing conventions in `runner.sh`: quoted variables in `[[ ]]`, `set -euo pipefail` still active, `$DRAFT_FLAG`-style expansion for conditional flags, `notify.sh "<msg>" || true` pattern for non-critical notifications.
- `set -euo pipefail` requires that any new variable introduced by `--dry-run` (e.g., `$DRY_RUN`) be initialized explicitly at the top of the end-of-session block — otherwise unbound-variable references crash live sessions. Requirement 9's regression check catches this.
- `gh pr create --draft`, `gh pr ready`, `gh pr ready --undo`, and the `--json url,isDraft,state` query must all function under GitHub's current API semantics (verified in research: platform-enforced, no workflow/action required, available on all repo tiers as of May 2025).
- The `--dry-run` flag must not affect any code path before the end-of-session block begins (pre-check at flag-parse time: error if flag is set but session hasn't reached end-of-session).
- `LIFECYCLE_SESSION_ID` is set during the overnight session and must not affect `--dry-run` execution — the test harness may or may not have this env var set, and either must work.
- The pytest tests use subprocess capture of `runner.sh --dry-run`; they must not require a live `gh` CLI for the write operations. `gh pr view` is invoked live (read-only) — tests mock it via `PATH` injection of a stub `gh` wrapper.
- Failure classification for `gh pr ready` uses stderr substring matching (case-insensitive): `HTTP 429` OR `rate limit` → `reason: transient` (marker stays false; next resume retries); any other non-zero exit (HTTP 401, HTTP 403, HTTP 5xx, network errors, unspecified) → `reason: persistent` (marker set to true; retry stops). Not a perfect classifier; tuned for the practical operational split between recoverable rate-limits and final auth/permission failures.
- GPG signing / `excludedCommands` interaction: runner.sh changes commit via the normal `/commit` path (via the calling lifecycle/implementation). No direct `git commit` from runner.sh for this ticket.

## Open Decisions

None. All substantive design choices surfaced during research, critical review, and the spec interview have been resolved.
