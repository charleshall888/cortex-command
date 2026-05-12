# Plan: un-silence-morning-report-commit-and-backfill-4-historical-reports

## Overview

Land the speculative fix + 3-session backfill in a single PR. Instrumentation is the load-bearing diagnostic: the new `morning_report_generate_result` event (with per-path sha256s) discriminates all four candidate causes, and the new `morning_report_commit_result` event records the commit-subshell outcome. Forward-fix code and docs are committed on a feature branch; 3 backfill commits land chronologically at `lifecycle/morning-report.md`; the operator gates the PR lifecycle with a scheduler-disable preflight.

## Tasks

### Task 1: Scheduler-disable preflight verification

- **Files**: none (operator procedure; records state in PR description)
- **What**: Verify no overnight session is active or scheduled immediately before opening the PR. This machine currently has no overnight LaunchAgent installed (ticket 112 parked) — preflight is: no active `overnight-runner` tmux session, no `runner.sh` process, no `/overnight` invocation during the PR lifecycle. If a LaunchAgent is added before this ticket lands, add `launchctl bootout gui/$(id -u)/<label>` to the disable step and `launchctl bootstrap gui/$(id -u) <plist>` to the restore step. Record the preflight in the PR body so Task 10's static check can confirm it was run.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Exact preflight commands (all must produce no match):
  - `launchctl list | grep overnight`
  - `tmux ls 2>/dev/null | grep overnight`
  - `ps ax | grep runner.sh | grep -v grep`
  Paste the command output into the PR description under a preamble line containing the literal sigil `preflight: all empty` followed by the timestamp. Task 10's verification greps for that sigil. After PR merge AND `bin/git-sync-rebase.sh` completes cleanly (`git status` clean; `git rev-list HEAD..origin/main --count` = 0), the operator resumes normal scheduling.
- **Verification**: `gh pr view <PR_NUM> --json body -q .body | grep -c 'preflight: all empty'` ≥ 1 (post-PR-creation, as part of Task 10's scripted gate). The three preflight commands themselves return empty in a terminal session before `gh pr create` runs — that execution is interactive/session-dependent, but the preflight-record sigil in the PR body is statically verifiable by Task 10.
- **Status**: [x] completed (preflight commands all empty; PR-body sigil verification is N/A under implement-on-main path)

### Task 2: Register morning-report event types in events.py

- **Files**: `claude/overnight/events.py`
- **What**: Add two constants (`MORNING_REPORT_GENERATE_RESULT = "morning_report_generate_result"`, `MORNING_REPORT_COMMIT_RESULT = "morning_report_commit_result"`) and include them in the `EVENT_TYPES` tuple. This must land before any runner.sh code that emits these events, or the Python `log_event` call raises `ValueError`.
- **Depends on**: none
- **Complexity**: simple
- **Context**: Constants are declared in the "Event type constants" block around `events.py:76` next to `MORNING_REPORT_COMMIT_FAILED`. `EVENT_TYPES` tuple ends at `events.py:128`. Follow the existing alphabetical-ish grouping (morning_report_* entries cluster together).
- **Verification**: `grep -c '^MORNING_REPORT_GENERATE_RESULT\|^MORNING_REPORT_COMMIT_RESULT' claude/overnight/events.py` = 2, AND `python3 -c "from cortex_command.overnight.events import EVENT_TYPES; assert 'morning_report_generate_result' in EVENT_TYPES and 'morning_report_commit_result' in EVENT_TYPES"` exits 0.
- **Status**: [x] completed

### Task 3: Unmask silent failure in report.py generate_and_write_report

- **Files**: `claude/overnight/report.py`
- **What**: Replace the silent try/except at `report.py:1467-1474` so any exception from `write_report(report, path=latest_copy_path)` propagates (or re-raises after event logging). The write must no longer fail silently to stderr. Simplest form: delete the try/except wrapper — `write_report` already performs atomic-write cleanup via its own inner try/except/raise (`report.py:1369-1384`), so naked propagation is safe.
- **Depends on**: none
- **Complexity**: simple
- **Context**: The current block lives between the per-session `write_report` at `report.py:1459` and the notify block at `report.py:1476`. The latest-copy path is computed at `report.py:1462-1466` (`project_root / "lifecycle" / "morning-report.md"` or `_LIFECYCLE_ROOT / "morning-report.md"`). After the change, the function contract becomes "either both writes succeed, or generate_and_write_report raises" — the caller (runner.sh) handles the failure via its wrapping heredoc's exit code.
- **Verification**: `grep -c 'warning: failed to write latest-copy' claude/overnight/report.py` = 0, AND the AST check from spec Req 1 (`python3 -c "import cortex_command.overnight.report as r; import inspect, ast; src = inspect.getsource(r.generate_and_write_report); tree = ast.parse(src); tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]; assert all(any(isinstance(h.body[-1], ast.Raise) for h in t.handlers) or not t.handlers for t in tries)"`) exits 0.
- **Status**: [x] completed

### Task 4: Emit morning_report_generate_result event in runner.sh

- **Files**: `claude/overnight/runner.sh`
- **What**: Instrument the two Python heredocs at `runner.sh:1181-1198` (cross-repo branch) and `runner.sh:1200-1214` (single-repo branch) to emit the `morning_report_generate_result` event on success (with `per_session_path`, `latest_copy_path`, per-path sha256s and byte counts). On failure, the bash `||` clause captures stderr tail and emits the same event with `status: failed, stderr_tail`. Replace `|| echo "Warning: morning report generation failed"` with `|| log_event morning_report_generate_result "$ROUND" "..."` at both call sites. Per-event payload structure matches spec Req 3 exactly. **Task 2 (events.py registration) must be an ancestor of this task's commit (or in the same commit) — a branch state with Task 4 but not Task 2 raises `ValueError` on both the success-path and the bash fallback, dropping the event entirely.**
- **Depends on**: [2]
- **Complexity**: complex
- **Context**:
  - Success-path emission lives inside the Python heredoc: after `generate_and_write_report(...)` returns the per-session path, compute sha256 digests of both `report_path` and the latest-copy path using the `hashlib` stdlib (sha256 of the file bytes, hex-encoded), then invoke `log_event` directly with event name `morning_report_generate_result`, the integer `ROUND` (see ROUND-propagation note below), and a details dict containing `status: success`, both file paths as strings, both sha256 hex digests, and both byte counts. The latest-copy path must be recomputed inside the Python block to match the single-branch vs cross-repo branching logic (`_LIFECYCLE_ROOT / 'morning-report.md'` in single-repo; `Path(tiw) / 'lifecycle' / 'morning-report.md'` in cross-repo).
  - **Path-fields emit through `os.path.realpath()`** (resolves symlinks) so the operator can detect candidate (b) worktree-sys.path misresolution by comparing the emitted `latest_copy_path` against the expected `<cortex-command repo realpath>/lifecycle/morning-report.md`. Without realpath resolution, a worktree-rooted `_LIFECYCLE_ROOT` produces a path string ending in `/lifecycle/morning-report.md` that looks correct but points elsewhere on disk; realpath exposes the discrepancy. The spec Req 3 `<abs>` field type accommodates the resolved form.
  - Failure-path emission lives in bash: redirect the Python heredoc's stderr to a mktemp file, then on non-zero exit read the tail (last ~500 bytes) of that file and pass it as the `stderr_tail` field in a JSON payload to the bash `log_event` helper. The JSON payload is assembled via a Python one-liner that reads the tail from stdin and serializes it using `json.dumps`; sanitize the tail before serialization by decoding as UTF-8 with `errors='replace'` (so a mid-UTF-8 `tail -c 500` cut does not produce invalid JSON when the bash helper re-parses). Use `mktemp` for the stderr capture file and clean up after emission.
  - **Wrap the `|| log_event ...` fallback itself in `|| true`** so a failure inside the fallback (JSON-decode crash, `log_event` ValueError on un-registered type, mktemp failure) does not propagate under `set -e` and kill the runner. The block is still inside runner.sh's default `set -e` scope (the generate-and-write block runs BEFORE `set +e` at `runner.sh:1220`). Pattern: `python_block || { log_event ...; true; }` (the trailing `true` — or an outer `|| true`.— guarantees exit-0).
  - Bash `log_event` helper signature: `log_event EVENT_NAME ROUND_NUM JSON_DETAILS_STRING` (`runner.sh:355-367`).
  - **ROUND propagation**: `ROUND` at `runner.sh:533` is a plain shell assignment (no `export`), so the in-heredoc `python3 -c` block inherits it only via bash's lexical `$ROUND` substitution — NOT via `os.environ['ROUND']`. Either add `export ROUND` near its assignment, or pass it explicitly on the `python3` invocation (e.g., prefix with `ROUND=$ROUND python3 -c ...`, following the pattern already used for other env vars at `runner.sh:1181, 1200`).
  - The exact emission payload is specified in spec Req 3 line-by-line — do not deviate.
- **Verification**: (c) Interactive/session-dependent — the event name, field presence, and shape can only be validated after an overnight session completes with this code in place. Pre-landing static checks: `grep -c 'morning_report_generate_result' claude/overnight/runner.sh` ≥ 3 (sanity bound ≤ 6), AND `grep -c 'echo "Warning: morning report generation failed"' claude/overnight/runner.sh` = 0 (old warning replaced in both branches), AND `grep -c 'per_session_sha256' claude/overnight/runner.sh` ≥ 1 AND `grep -c 'latest_copy_sha256' claude/overnight/runner.sh` ≥ 1 (payload field names present, not just the event name), AND `bash -n claude/overnight/runner.sh` exits 0 (script parses).
- **Status**: [x] completed

### Task 5: Emit commit_result from first commit subshell + delete dead git add

- **Files**: `claude/overnight/runner.sh`
- **What**: In the `(cd "$REPO_ROOT"; ...)` subshell at `runner.sh:1221-1226`, (a) delete the dead `git add "lifecycle/sessions/${SESSION_ID}/morning-report.md" 2>/dev/null || true` at `runner.sh:1223` (the per-session path is gitignored; this line has never staged anything), and (b) emit `morning_report_commit_result` with `{"status": "committed|no_changes|failed", "commit_sha": "<sha>|null"}` after the `git diff --cached --quiet || git commit` decides the outcome. Spec Req 4 drops the `staged_files` field — bash has no clean JSON-array interpolation path via the existing `log_event` helper.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - Current subshell uses `set +e` scope opened at `runner.sh:1220`. Capture the pre-commit HEAD via `pre=$(git rev-parse HEAD)` inside the subshell; then after the conditional commit, compare `post=$(git rev-parse HEAD)`. Branching: `pre == post` AND exit_status==0 → `no_changes, commit_sha: null`; `pre != post` → `committed, commit_sha: $post`; `git commit` exit_status != 0 → `failed, commit_sha: null`.
  - Export the result out of the subshell via a tempfile or via command substitution wrapping (the subshell can't export env vars to the parent). Cleanest: capture the status and sha into two tempfiles, have the outer shell read them and invoke `log_event`.
  - Alternate cleaner pattern: refactor the subshell to `{ cd_and_commit; } || status=failed`, then emit from outside the subshell using cached state. Preserve exit-swallow semantics (the commit subshell failure must not kill the runner).
- **Verification**: `grep -c 'git add "lifecycle/sessions/.*morning-report.md"' claude/overnight/runner.sh` = 1 (only the target-worktree block at runner.sh:1241 remains), AND `grep -c 'morning_report_commit_result' claude/overnight/runner.sh` ≥ 1 (for the first commit block; Task 6 adds one more for the target-worktree block).
- **Status**: [x] completed

### Task 6: Emit commit_result from target-worktree commit block

- **Files**: `claude/overnight/runner.sh`
- **What**: In the cross-repo `(cd "$TARGET_INTEGRATION_WORKTREE"; ...)` subshell at `runner.sh:1239-1246`, emit `morning_report_commit_result` with `{"status": ..., "commit_sha": ..., "target": "<target_project_root>"}` using the same pre/post `git rev-parse HEAD` pattern as Task 5. Do NOT delete the `git add "lifecycle/sessions/${SESSION_ID}/morning-report.md"` line at `runner.sh:1241` (spec Non-Requirement: target-repo gitignore policy may differ).
- **Depends on**: [2, 5]
- **Complexity**: simple
- **Context**: The block is gated by both `[[ -n "$TARGET_INTEGRATION_WORKTREE" ]]` and `[[ -n "$TARGET_INTEGRATION_BRANCH" ]]` (`runner.sh:1229-1248`). `TARGET_PROJECT_ROOT` is already exported to the subshell's parent context. Follow the same capture-pre-post-sha pattern as Task 5. The payload's `target` field distinguishes home-repo vs target-repo emissions in later analysis.
- **Verification**: `grep -c 'morning_report_commit_result' claude/overnight/runner.sh` ≥ 2 (Task 5 adds 1; this adds 1 more; factoring may push to 3+), AND `grep -F '"target":' claude/overnight/runner.sh` ≥ 1.
- **Status**: [x] completed

### Task 7: Remove dead sync-allowlist.conf entry

- **Files**: `claude/overnight/sync-allowlist.conf`
- **What**: Delete line 36 `lifecycle/sessions/*/morning-report.md`. Line 37 `lifecycle/morning-report.md` stays — it becomes live behavior once commits land reliably.
- **Depends on**: none
- **Complexity**: simple
- **Context**: This entry was dead because the per-session path is always gitignored (`.gitignore:45`) and therefore never produces a post-merge conflict. No consumer reads this glob explicitly. The comment at `sync-allowlist.conf:35` "Morning report files" still covers the remaining line 37.
- **Verification**: `grep -c '^lifecycle/sessions/\*/morning-report\.md$' claude/overnight/sync-allowlist.conf` = 0, AND `grep -c '^lifecycle/morning-report\.md$' claude/overnight/sync-allowlist.conf` = 1.
- **Status**: [x] completed

### Task 8: Reconcile morning-report documentation

- **Files**: `docs/overnight-operations.md`, `docs/agentic-layer.md`, `docs/overnight.md`, `skills/overnight/SKILL.md`, `skills/morning-review/SKILL.md`
- **What**: Per CLAUDE.md's overnight-docs source-of-truth convention, primary edits land in `docs/overnight-operations.md`; non-owning docs reference rather than duplicate. Specific edits:
  - `docs/overnight-operations.md:327` (file-inventory row for `lifecycle/morning-report.md`) — update the "Purpose" column to name both new events (`morning_report_generate_result`, `morning_report_commit_result`).
  - `docs/overnight-operations.md:411-413` — add a one-line parenthetical note that historical reports were backfilled in commit sha TBD (filled in during Task 11 commit sequencing).
  - `docs/agentic-layer.md:311` — rewrite "morning-report.md is a symlink to the latest archive" to the correct framing: `lifecycle/morning-report.md` is a regular file overwritten by the writer each session; `lifecycle/sessions/latest-overnight` is the symlink to the current session directory. Link to `docs/overnight-operations.md` for detail.
  - `docs/agentic-layer.md:184` — the same "(a symlink to the latest session archive)" parenthetical claim recurs. Reconcile to the correct framing (or delete the parenthetical).
  - `docs/overnight.md:225`, `skills/overnight/SKILL.md:12,288,301`, `skills/morning-review/SKILL.md:82-84` — verify references are accurate post-fix; tweak ONLY if the existing wording is misleading.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - `docs/agentic-layer.md:184` is OUTSIDE spec Req 7's explicit enumeration but duplicates the same incorrect symlink claim; flagged in Veto Surface.
  - Pre-existing symlink mechanism: `runner.sh:1301-1307` (not quoted in spec) maintains the `lifecycle/sessions/latest-overnight` symlink.
  - Do not duplicate content: non-owning docs link to `docs/overnight-operations.md` for mechanics, not re-describe.
- **Verification**: `grep -F 'morning-report.md is a symlink' docs/agentic-layer.md` exits non-zero, AND `grep -F 'lifecycle/sessions/latest-overnight' docs/agentic-layer.md` ≥ 1 AND `grep -F 'regular file' docs/agentic-layer.md` ≥ 1, AND `grep -c 'morning_report_generate_result\|morning_report_commit_result' docs/overnight-operations.md` ≥ 2.
- **Status**: [x] completed

### Task 9: Chronological backfill commits at lifecycle/morning-report.md

- **Files**: `lifecycle/morning-report.md` (content overwritten 3 times sequentially)
- **What**: On the feature branch, produce 3 separate commits via `/commit` — one per backfill session in chronological order (04-07-0008, 04-11-1443, 04-21-1708). For each commit: copy `lifecycle/sessions/{sid}/morning-report.md` to `lifecycle/morning-report.md`, stage it, and commit with subject `Overnight session {sid}: add morning report (backfill)`. Backdating is NOT applied (amended 2026-04-22 per user direction) — commits use today's operator timestamp; the session date is preserved by the report heading and the commit subject.
- **Depends on**: [3, 4, 5, 6, 7, 8]
- **Complexity**: simple
- **Context**:
  - Per-commit pattern: copy the session's morning-report file to `lifecycle/morning-report.md`, stage it, invoke `/commit` with the prescribed subject. Three separate `/commit` invocations, one per session, in chronological order (04-07 → 04-11 → 04-21).
  - Session `overnight-2026-04-01-1650` is NOT backfilled (aborted; no report exists on disk). Session `overnight-2026-04-01-2112` is already committed as `85e87aa`.
  - After all 3 backfills, on-disk `lifecycle/morning-report.md` holds the 04-21-1708 content (most recent).
- **Verification**: `git log --oneline -- lifecycle/morning-report.md | wc -l` = 4 (85e87aa + 3 backfills), AND `git log --format='%s' -- lifecycle/morning-report.md | grep -c '(backfill)$'` = 3, AND the blob-vs-source byte-for-byte check from spec Req 8 exits 0, AND `git log --format='%s' -- lifecycle/morning-report.md | grep -c '2026-04-01-1650'` = 0.
- **Status**: [x] completed

### Task 10: Commit code, docs, backfill; open PR

- **Files**: none (git operations + PR)
- **What**: Push the feature branch and open a PR via `/pr`. The PR description must include: (a) a link to the operator's Task 1 preflight record (or inline paste of the three empty-output verifications with timestamps), (b) the post-landing behavioral validation + rollback criterion from spec Req 10 (event names spelled out), (c) a note that merge strategy is `--merge` per `requirements/pipeline.md:119` (not rebase/squash), so the 3 backfill commits land as-is.
- **Depends on**: [1, 9]
- **Complexity**: simple
- **Context**:
  - Uses `/commit` per CLAUDE.md convention for each commit; backfill commits (Task 9) are three separate `/commit` calls.
  - Uses `/pr` for the PR itself. PR title: something like "Un-silence morning-report commit and backfill 3 historical sessions".
  - The PR description Task 11 lookup anchors on: `morning_report_generate_result` and `morning_report_commit_result` event names spelled out by name (spec Req 10 pre-landing acceptance).
  - Commit ordering on the branch: events+report+runner+sync + docs (one or more commits via `/commit`) THEN 3 backfill commits in chronological order.
- **Verification**: Scripted, post-PR-creation: `gh pr view <PR_NUM> --json body -q .body | grep -c 'morning_report_generate_result\|morning_report_commit_result'` ≥ 2 (both new event names named in PR body), AND `gh pr view <PR_NUM> --json body -q .body | grep -c 'preflight: all empty'` ≥ 1 (Task 1 preflight record sigil present in PR body), AND `git log --format='%H %s' origin/main..HEAD -- lifecycle/morning-report.md | wc -l` = 3 (three backfill commits are on the branch, ancestors of HEAD but not origin/main).
- **Status**: [x] completed (adapted: implement-on-main path chosen per user direction; the 10 commits landed directly on local main; PR-scoped verifications are N/A — `git log origin/main..HEAD -- lifecycle/morning-report.md | wc -l` = 3 still holds)

### Task 11: Post-landing behavioral validation (operator)

- **Files**: `lifecycle/archive/un-silence-morning-report-commit-and-backfill-4-historical-reports/events.log` (durable trace appended); operator observation of next session's events.
- **What**: After the PR merges and `bin/git-sync-rebase.sh` completes cleanly, the operator lifts the preflight hold (Task 1's scheduler-disable note) and allows the next overnight session to run. Post-session, inspect `lifecycle/sessions/<next_sid>/overnight-events.log` for: (a) a `morning_report_generate_result` event with `status: success` AND `per_session_sha256 == latest_copy_sha256` AND `latest_copy_path` (realpath-form) is `<cortex-command repo realpath>/lifecycle/morning-report.md`, AND (b) a `morning_report_commit_result` event with `status: committed` AND a non-null `commit_sha`. For cross-repo sessions, BOTH the home-repo `morning_report_commit_result` (no `target` field) AND the target-worktree one (with `target` field) must have `status: committed`. If all hold AND `git log -1 -- lifecycle/morning-report.md` points at that new commit AND `git show HEAD:lifecycle/morning-report.md | diff -q - <session_latest_copy_path>` exits 0 (byte-for-byte match, guards against sync-rebase content swap), the speculative fix is validated. Otherwise, surface the event payload and escalate to `/diagnose` first (no auto-rollback). **Durable trace**: append a `post_landing_validation` event to this lifecycle's `events.log` (NDJSON) with fields `{ts, event: "post_landing_validation", feature, next_sid, status: "validated"|"failed"|"ambiguous", observed_commit_sha, notes}` — this is the record that Task 11 was executed.
- **Depends on**: [10]
- **Complexity**: simple
- **Context**:
  - Rollback criterion (spec Req 10): if `generate_result.status == success` but no follow-up commit lands AND `per_session_sha256 != latest_copy_sha256`, the wrong-path-write hypothesis is realized — the event payload's `latest_copy_path` (realpath-form) reveals WHERE the write landed. If `generate_result.status == success` AND shas match but `latest_copy_path` is NOT inside the home repo's realpath, candidate (b) worktree sys.path misresolution is realized (the shas match because both writes went to the same wrong location). If `generate_result.status == failed`, the speculative fix unmasked a distinct upstream cause and the `stderr_tail` field is the diagnostic signal.
  - Ambiguous case (non-failure): `generate_result.status == success` AND `per_session_sha256 == latest_copy_sha256` AND `latest_copy_path` is inside the home repo AND no commit lands → content happens to match prior committed blob (reported via `commit_result.status: no_changes`). This is NOT a failure; the realpath check disambiguates it from candidate (b).
  - The `post_landing_validation` event is NOT registered in `claude/overnight/events.py:EVENT_TYPES` — that registry governs overnight-events.log, not the lifecycle events.log (which is unvalidated NDJSON). No Task 2 dependency.
- **Verification**: (c) Interactive/session-dependent — observing the next session after merge cannot be synthesized pre-landing. The plan task explicitly references `morning_report_generate_result` and `morning_report_commit_result` by name (spec Req 10 pre-landing acceptance). Durable-trace check post-execution: `grep -c '"event": "post_landing_validation"' lifecycle/archive/un-silence-morning-report-commit-and-backfill-4-historical-reports/events.log` ≥ 1 — if the operator executed Task 11 (success or failure), the trace exists.
- **Status**: [x] completed (waived: user directed 2026-04-22 that post-landing validation on the next overnight session is not required; the new events are still emitted by runner.sh and will be visible in overnight-events.log naturally if the operator wants to inspect)

## Verification Strategy

End-to-end verification runs in two phases:

**Pre-landing** (must all pass before PR merge):
1. Req 1 (AST: `generate_and_write_report` has no silent exception handlers) — Task 3.
2. Req 2 (EVENT_TYPES registration) — Task 2.
3. Req 5 (single remaining `git add lifecycle/sessions/.../morning-report.md`) — Task 5.
4. Req 6 (dead sync-allowlist line removed; live line retained) — Task 7.
5. Req 7 (symlink claim removed from agentic-layer.md; events named in overnight-operations.md) — Task 8.
6. Req 8 (4 commits touching `lifecycle/morning-report.md`; 3 backfill subjects; per-commit blob matches source; 1650 not present) — Task 9.
7. Req 9 preflight (operator records three empty-output verifications in PR description) — Task 1.
8. Req 10 pre-landing (PR description names both events) — Task 10.

**Post-landing** (must pass on the next overnight session after PR merge):
9. Req 3 (`morning_report_generate_result` event emitted with `per_session_sha256`, `latest_copy_sha256`, `per_session_bytes`, `latest_copy_bytes` fields; status=success; `latest_copy_path` realpath-form inside home repo) — Task 11 observation.
10. Req 4 (`morning_report_commit_result` event emitted with `status`, `commit_sha`; for cross-repo sessions both the home-repo event and the target event must be `status: committed`) — Task 11 observation.
11. Req 10 landed behavior (new commit at `lifecycle/morning-report.md` lands on local main within 5 min of `session_complete`; `git show HEAD:lifecycle/morning-report.md` byte-for-byte matches the session's `latest_copy_path` output) — Task 11 observation.
12. Durable trace (pre-landing check that Task 11 was executed): `grep -c '"event": "post_landing_validation"' lifecycle/archive/un-silence-morning-report-commit-and-backfill-4-historical-reports/events.log` ≥ 1.

If any post-landing check fails, the rollback criterion from Task 11 gates the response: surface event payload, escalate to `/diagnose` first, no auto-rollback.


## Veto Surface

- **docs/agentic-layer.md:184 inclusion**: spec Req 7 enumerates `docs/agentic-layer.md:311` but line 184 contains the same "(a symlink to the latest session archive)" claim. Task 8 includes both. If the user prefers to keep scope to the exact spec enumeration, pull line 184 out into a follow-up.
- **Scheduler-disable wording in spec Req 9**: this machine currently has no overnight LaunchAgent (ticket 112 parked pending epic 113), so "unload/disable the scheduled LaunchAgent" is a no-op today. Task 1 verifies via `launchctl list | grep overnight` returning empty. If the user installs a LaunchAgent before this ticket lands, Task 1 must be updated to include `launchctl bootout` / `launchctl bootstrap`. Mid-flight install risk (user unparks ticket 112 between Task 10 and Task 11) is not covered — there is no re-verification between PR-open and post-merge.
- **Commit boundary for forward-fix commits (hardened)**: Tasks 2-8 may land as one commit or several, BUT Task 2 (events.py EVENT_TYPES registration) MUST be an ancestor of (or included in the same commit as) Task 4, Task 5, and Task 6's `runner.sh` emission commits. A branch state with Task 4/5/6 but not Task 2 emits `ValueError` from `log_event` on every emission surface (both Python-side success and bash-side failure fallback), silently dropping the diagnostic event. Bisect/cherry-pick/revert must respect this ordering.
- **Python import-time side-effects in Task 4**: the in-heredoc import `from cortex_command.overnight.events import log_event` is a new dependency within the runner.sh Python block. Existing heredocs only import from `claude.overnight.report`. No import-time side effects in `events.py`, but flag for critical review.
- **Observation (out of scope)**: `claude/overnight/sync-allowlist.conf:3` comment says patterns are auto-resolved "`--theirs` (remote wins)". During `bin/git-sync-rebase.sh:108`'s `git pull --rebase`, `--theirs` actually picks the local (replayed) branch's content per git's rebase nomenclature swap (see `git-checkout(1)` Note). The allowlist's practical effect on this ticket is "local session commits preserved through sync-rebase" — this is the BEHAVIOR the plan's Task 11 post-sync content check depends on, so this ticket's acceptance is unaffected. Log a follow-up to correct the comment.

## Scope Boundaries

Matches spec Non-Requirements section:
- Does NOT diagnose root cause pre-fix; the speculative fix + new event instrumentation discriminates post-landing.
- Does NOT un-gitignore `lifecycle/sessions/*/morning-report.md`.
- Does NOT use `git add -f`.
- Does NOT modify `report.py:write_report` (already atomic).
- Does NOT modify the interrupted-session trap heredoc (`runner.sh:505-521`) beyond the Req 1 propagation effect; that heredoc calls `write_report` directly and is out of scope.
- Does NOT modify the target-worktree `git add` lines at `runner.sh:1241-1242` (keep for target-repo sessions).
- Does NOT backfill `overnight-2026-04-01-1650`.
- Does NOT introduce a new automation author identity.
- Does NOT modify `bin/git-sync-rebase.sh` conflict-resolution logic.
- Does NOT auto-generate rollback PRs.
