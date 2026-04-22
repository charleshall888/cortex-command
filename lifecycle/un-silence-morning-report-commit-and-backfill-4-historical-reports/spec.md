# Specification: Un-silence morning-report commit and backfill historical reports

> Epic reference: `research/orchestrator-worktree-escape/research.md` RQ3 / Fact-Section Correction #4. Full ticket-specific analysis: `lifecycle/un-silence-morning-report-commit-and-backfill-4-historical-reports/research.md`.

## Problem Statement

Only 1 of 5 overnight sessions on this machine has ever committed its morning report to `main`. Session `overnight-2026-04-01-2112` committed successfully (sha `85e87aa`); sessions `overnight-2026-04-07-0008`, `overnight-2026-04-11-1443`, and `overnight-2026-04-21-1708` silently failed to update `lifecycle/morning-report.md`. The ticket's original mechanism hypothesis (`.gitignore` silently skips per-session file) is insufficient: the top-level path is NOT gitignored, the writer (`report.py:generate_and_write_report`) does write to it, and the commit subshell would commit it if it had changed. Direct inspection shows the top-level write itself silently failed for 3 sessions — root cause unidentified. Most plausible candidate: the `try/except Exception` at `report.py:1467-1474` swallowing a write error; but three other candidates remain possible (worktree sys.path resolution, wrong-path write, filesystem race). The operator has lost 3 weeks of morning-report audit trail under the requirement that morning reports are the only tracked runner output on `main` (`requirements/pipeline.md:24`).

This spec implements the user's directed approach: **speculative fix plus backfill, in one PR**. Because the root cause is unverified, the spec emphasizes (a) instrumentation strong enough to discriminate all four candidate mechanisms, (b) a post-landing behavioral validation, and (c) a rollback criterion if the next session shows the fix did not work.

## Requirements

All 10 requirements are must-have. This ticket has high criticality and complex tier; no should-haves or won't-dos are present. The ticket does not land unless all 10 pass.

1. **Unmask silent write failures in report.py**: Replace the try/except at `claude/overnight/report.py:1467-1474` so that any exception from `write_report(report, path=latest_copy_path)` is either re-raised after event logging OR propagates freely. The exception must be observable outside stderr.
   - Acceptance: `grep -c 'warning: failed to write latest-copy' claude/overnight/report.py` = 0.
   - Acceptance: `python3 -c "import claude.overnight.report as r; import inspect, ast; src = inspect.getsource(r.generate_and_write_report); tree = ast.parse(src); tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]; assert all(any(isinstance(h.body[-1], ast.Raise) for h in t.handlers) or not t.handlers for t in tries)"` exits 0.

2. **Register new event names in `events.py:EVENT_TYPES`**: Add two constants to `claude/overnight/events.py` and include them in the `EVENT_TYPES` tuple so that `log_event` does not raise `ValueError` when the runner emits them: `MORNING_REPORT_GENERATE_RESULT = "morning_report_generate_result"` and `MORNING_REPORT_COMMIT_RESULT = "morning_report_commit_result"`.
   - Acceptance: `grep -c '^MORNING_REPORT_GENERATE_RESULT\|^MORNING_REPORT_COMMIT_RESULT' claude/overnight/events.py` = 2.
   - Acceptance: `python3 -c "from claude.overnight.events import EVENT_TYPES; assert 'morning_report_generate_result' in EVENT_TYPES and 'morning_report_commit_result' in EVENT_TYPES"` exits 0.

3. **Structured generate-result event**: Emit a `morning_report_generate_result` event to `lifecycle/sessions/{sid}/overnight-events.log` after the Python `generate_and_write_report` invocation at `runner.sh:1180-1214` completes (both branches). Event fires on success and on failure:
   - On success, `details` = `{"status": "success", "per_session_path": "<abs>", "latest_copy_path": "<abs>", "per_session_sha256": "<hex>", "latest_copy_sha256": "<hex>", "per_session_bytes": <int>, "latest_copy_bytes": <int>}`.
   - On failure (Python block exits non-zero), `details` = `{"status": "failed", "stderr_tail": "<last ~500 chars of stderr>"}`. Bash catches via `|| log_event morning_report_generate_result ...` instead of `|| echo "Warning..."`.
   - Purpose: distinguishes wrong-path writes (`per_session_sha256 != latest_copy_sha256`), identical-content no-ops (both shas equal a prior blob), and silent upstream failures (status=failed).
   - Acceptance: `grep -c 'morning_report_generate_result' lifecycle/sessions/overnight-*/overnight-events.log` ≥ 1 after a test session.
   - Acceptance: `python3 -c "import json; events=[json.loads(l) for l in open(p) for p in __import__('glob').glob('lifecycle/sessions/overnight-*/overnight-events.log')]; assert any('per_session_sha256' in e.get('details',{}) for e in events if e.get('event')=='morning_report_generate_result')"` — interactive/session-dependent: requires a session to have run with the new code; not a pre-landing check.

4. **Structured commit-result event**: Emit `morning_report_commit_result` event after the commit subshell at `runner.sh:1220-1226`, with `details` = `{"status": "committed|no_changes|failed", "commit_sha": "<sha_or_null>"}`. The `staged_files` field is explicitly dropped (no bash precedent for JSON-array interpolation via `log_event`). Also emit from the target-worktree commit block at `runner.sh:1229-1248` with an additional `"target": "<target_project_root>"` field.
   - Acceptance: `grep -c 'morning_report_commit_result' lifecycle/sessions/overnight-*/overnight-events.log` ≥ 1 after a test session. Interactive/session-dependent: field-shape validation requires a live session's events file.
   - Note: the EXISTING `morning_report_commit_failed` event at `runner.sh:1256, 1266` fires on PUSH failures and is kept as-is. The division of responsibility is: `morning_report_commit_result` covers the commit-subshell outcome (commit/no_changes/failed); `morning_report_commit_failed` covers the subsequent push outcome. Both may fire in one session; they are not redundant.

5. **Remove dead code in runner.sh first-commit subshell**: Delete the line `git add "lifecycle/sessions/${SESSION_ID}/morning-report.md" 2>/dev/null || true` at `runner.sh:1223`. Do NOT modify `runner.sh:1241-1242` (target-worktree block).
   - Acceptance: `grep -c 'git add "lifecycle/sessions/.*morning-report.md"' claude/overnight/runner.sh` = 1.

6. **Remove dead entry from sync-allowlist.conf**: Delete line 36 `lifecycle/sessions/*/morning-report.md`. Per-session path stays gitignored; never conflicts. Keep line 37 `lifecycle/morning-report.md`.
   - Acceptance: `grep -c '^lifecycle/sessions/\*/morning-report\.md$' claude/overnight/sync-allowlist.conf` = 0.
   - Acceptance: `grep -c '^lifecycle/morning-report\.md$' claude/overnight/sync-allowlist.conf` = 1.

7. **Reconcile morning-report documentation in the owning doc and linked docs**: Per CLAUDE.md's overnight-docs source-of-truth convention, primary edits land in `docs/overnight-operations.md`. Non-owning docs are corrected to link/reference rather than duplicate.
   - **`docs/overnight-operations.md:327`** (file-inventory table entry for `lifecycle/morning-report.md`): update the "Purpose" column to mention both the new `morning_report_generate_result` and `morning_report_commit_result` events.
   - **`docs/overnight-operations.md:411-413`**: no text change required — the fix makes the existing "only runner commit that stays on local `main`" claim true going forward. Add a one-line parenthetical note that historical reports were backfilled in commit sha TBD (filled in during implementation).
   - **`docs/agentic-layer.md:311`**: rewrite the inaccurate sentence "`morning-report.md` is a symlink to the latest archive". Correct framing: `lifecycle/morning-report.md` is a regular file overwritten by the writer each session; `lifecycle/sessions/latest-overnight` is a symlink to the current session directory. Keep the sentence brief; link to `docs/overnight-operations.md` for full detail.
   - **`docs/overnight.md:225`**: verify the reference to `lifecycle/morning-report.md` is accurate post-fix; tweak only if the existing wording is misleading.
   - **`skills/overnight/SKILL.md:12, 288, 301`**: verify the morning-report references are accurate post-fix; tweak only if misleading. Line 12 describes the per-session output (gitignored — correct); lines 288/301 reference the top-level path (now reliably populated post-fix — correct).
   - Acceptance: `grep -F 'morning-report.md is a symlink' docs/agentic-layer.md` exits non-zero (incorrect claim removed).
   - Acceptance: `grep -F 'lifecycle/sessions/latest-overnight' docs/agentic-layer.md` ≥ 1 AND `grep -F 'regular file' docs/agentic-layer.md` ≥ 1 — both the symlink mechanism AND the regular-file correction are present, guarding against sloppy rewrites.
   - Acceptance: `grep -c 'morning_report_generate_result\|morning_report_commit_result' docs/overnight-operations.md` ≥ 2.

8. **Backfill 3 historical morning reports as chronological commits at `lifecycle/morning-report.md`**: one commit per session in order (04-07-0008, 04-11-1443, 04-21-1708). Each commit:
   - Copies `lifecycle/sessions/{sid}/morning-report.md` to `lifecycle/morning-report.md` before staging.
   - Uses subject `Overnight session {sid}: add morning report (backfill)`.
   - Uses the operator's normal git author identity and today's commit timestamp (backdating dropped per Plan-phase amendment on 2026-04-22; the session date is preserved by the report heading and the commit subject).
   - Acceptance: `git log --oneline -- lifecycle/morning-report.md | wc -l` = 4.
   - Acceptance: `git log --format='%s' -- lifecycle/morning-report.md | grep -c '(backfill)$'` = 3.
   - Acceptance (blob content): for each of the 3 backfill commit shas, `git show <sha>:lifecycle/morning-report.md` must equal the corresponding `lifecycle/sessions/{sid}/morning-report.md` file byte-for-byte. Concretely: `python3 -c "import subprocess; shas = subprocess.check_output(['git','log','--format=%H','-3','--','lifecycle/morning-report.md']).decode().split(); sources = ['lifecycle/sessions/overnight-2026-04-21-1708/morning-report.md','lifecycle/sessions/overnight-2026-04-11-1443/morning-report.md','lifecycle/sessions/overnight-2026-04-07-0008/morning-report.md']; [exec('import hashlib; a=hashlib.sha256(subprocess.check_output([\"git\",\"show\",f\"{sha}:lifecycle/morning-report.md\"])).hexdigest(); b=hashlib.sha256(open(src,\"rb\").read()).hexdigest(); assert a==b, f\"{sha} != {src}\"') for sha, src in zip(shas, sources)]"` exits 0.
   - Acceptance: session `overnight-2026-04-01-1650` is NOT backfilled — `git log --format='%s' -- lifecycle/morning-report.md | grep -c '2026-04-01-1650'` = 0.

9. **Preflight sequencing guard against concurrent overnight runs during backfill PR lifecycle**: The backfill must not race with scheduled overnight runs. The race window spans from backfill-PR-creation through post-merge-sync-complete.
   - Before opening the backfill PR, the operator must unload/disable the scheduled overnight LaunchAgent (or equivalent scheduling mechanism) so no session starts during the PR lifecycle. Concrete commands vary by install — the implementation step must verify no session starts by running: `launchctl list | grep overnight`, `tmux ls 2>/dev/null | grep overnight`, and `ps -ef | grep runner.sh | grep -v grep` — all must be empty before proceeding.
   - After the PR merges and `bin/git-sync-rebase.sh` completes cleanly (`git status` clean; `git rev-list HEAD..origin/main --count` = 0), the operator restores the scheduled LaunchAgent.
   - Acceptance: Interactive/session-dependent — this is an operator procedure documented in the implementation plan. No static command substitutes for the manual sequencing. The plan task for this step must include the exact commands to disable/restore the scheduler for this machine.

10. **Post-landing behavioral validation + rollback criterion**: After the PR merges, the next overnight session is the behavioral test. If the fix works, that session's `morning_report_generate_result` event shows `status: success`, and a new commit lands at `lifecycle/morning-report.md` on `main` within 5 minutes of `session_complete`. If the fix does not work, the next session's events show either a `generate_result` with `status: failed` (good — speculative fix unmasked a different cause; diagnose using the event payload) OR a `generate_result` with `status: success` but no follow-up commit (bad — means the wrong-path write hypothesis is realized; events.log will show divergent `per_session_sha256` vs `latest_copy_sha256`, revealing the location mismatch).
   - Acceptance (pre-landing — check that the rollback criterion is documented in the implementation plan): the plan's verification step includes: "After the next overnight session completes, inspect `lifecycle/sessions/{next_sid}/overnight-events.log` for `morning_report_generate_result` AND `morning_report_commit_result` events. If `generate_result.status == success` AND `commit_result.status == committed` AND `git log -1 -- lifecycle/morning-report.md` points at a commit from the new session, the fix is validated. Otherwise, surface the event payload and escalate to diagnose-first."
   - Acceptance: the plan task for this validation step is present and references `morning_report_generate_result` and `morning_report_commit_result` by name.

## Non-Requirements

- **Does NOT diagnose the root cause pre-fix**. User chose speculative-fix-now. Requirements 3 and 10 combined provide the diagnostic signal if the speculative fix misses.
- **Does NOT un-gitignore `lifecycle/sessions/*/morning-report.md`**. The `.gitignore:45` session-archive rule stays as-is.
- **Does NOT use `git add -f`** anywhere.
- **Does NOT modify `report.py`'s `write_report` function** — atomic write is already correct.
- **Does NOT modify `runner.sh:505-521`** (interrupted-session heredoc) beyond propagating Req 1's try/except change. The heredoc calls `write_report` directly; it's out of this ticket.
- **Does NOT modify `runner.sh:1229-1248`** (target-worktree commit block) beyond emitting the commit_result event per Req 4.
- **Does NOT backfill session `overnight-2026-04-01-1650`** (aborted; no report file).
- **Does NOT change cross-repo branch behavior** at `runner.sh:1180-1198` beyond threading the new event emissions.
- **Does NOT introduce a new automation author identity** for backfill commits.
- **Does NOT modify `sync-allowlist.conf` semantics or `bin/git-sync-rebase.sh` conflict-resolution logic**. Requirement 9 (scheduler disable during PR lifecycle) is the mechanism that avoids divergence; rewriting the sync layer to be backfill-aware is out of scope.
- **Does NOT auto-generate rollback PRs**. Requirement 10 documents the diagnostic steps the operator takes if validation fails; any rollback is an operator decision.

## Edge Cases

- **Write succeeds but content is identical to prior committed blob**: `morning_report_generate_result` fires with `status: success` and equal sha256s; `git add` stages nothing; `morning_report_commit_result` fires with `status: no_changes, commit_sha: null`. Both events are distinguishable from the no-content-write case by the generate-result payload.
- **Write fails after Req 1 change** (exception propagates): Python block exits non-zero; Bash catches via `|| log_event morning_report_generate_result '{"status":"failed","stderr_tail":"..."}'`. No commit subshell runs — but commit_result still fires with `status: failed, commit_sha: null`. Morning-report reader sees a structured failure with stderr context.
- **Wrong-path write** (candidate causes b/c from research): `generate_result.per_session_sha256 != generate_result.latest_copy_sha256` OR `latest_copy_path` does not resolve to `<cortex-command>/lifecycle/morning-report.md`. This event alone pinpoints the cause without a follow-up debugging session.
- **Backfill runs while a session is active**: explicitly prevented by Req 9. If operator ignores the sequencing guard, divergent commits on `lifecycle/morning-report.md` require manual conflict resolution during sync. Acceptance tests (Req 8) would fail on blob content — surfacing the problem loudly.
- **Backfill commit datetime**: (amended 2026-04-22) backdating dropped; commits use today's timestamp. Session date is preserved by the report heading (`# Morning Report: YYYY-MM-DD`) and the commit subject (`Overnight session <sid>: add morning report (backfill)`).
- **Post-landing validation reveals ambiguous result** (e.g., `generate_result.status == success` but no commit lands, and `per_session_sha256 == latest_copy_sha256`): this case is defined in Req 10 and means content happened to match a prior commit. Not a failure; the rollback criterion explicitly excludes it.

## Changes to Existing Behavior

- **MODIFIED: `claude/overnight/report.py:1467-1474`** — latest-copy write failure is no longer silent. Either propagates or logs a structured event (operator-visible, not stderr-only).
- **ADDED: `morning_report_generate_result` event** — structured payload distinguishing success / no-content / wrong-path / upstream-failure cases. Registered in `events.py:EVENT_TYPES`.
- **ADDED: `morning_report_commit_result` event** — commit-subshell outcome with status + sha. Registered in `events.py:EVENT_TYPES`.
- **KEPT: `morning_report_commit_failed` event** at `runner.sh:1256, 1266` — fires on push failure, unchanged. Division of responsibility is documented in Req 4.
- **REMOVED: dead `git add lifecycle/sessions/...` line** at `runner.sh:1223`.
- **REMOVED: dead `sync-allowlist.conf:36`** entry.
- **MODIFIED: `docs/agentic-layer.md:311`** — inaccurate symlink claim corrected.
- **MODIFIED: `docs/overnight-operations.md:327`** — file-inventory Purpose column names the new events.
- **MODIFIED: `lifecycle/morning-report.md` content on disk** — overwritten with 1708's content as part of backfill.

## Technical Constraints

- Atomic writes via tempfile + `os.replace()` (`requirements/pipeline.md:123`). Already correct in `write_report`.
- `.gitignore` policy unchanged: `lifecycle/sessions/` stays covered; no `!` negation patterns added.
- Backfill commits must not rewrite published history — only append new commits with today's timestamp (backdating dropped per Plan-phase amendment 2026-04-22).
- Commits authored as the operator.
- No new Python dependencies; no new packages; no changes to `requirements/pipeline.md`.
- Post-merge sync (`sync-allowlist.conf`) `--theirs` resolution semantics depend on `--merge` PR merge strategy (`requirements/pipeline.md:119`). Req 6 keeps the live entry (line 37). Req 9's scheduler-disable sequencing is the mechanism that prevents divergent commits during the backfill PR lifecycle.
- CLAUDE.md overnight-docs source-of-truth: primary doc edits in `docs/overnight-operations.md`; non-owning docs reference rather than duplicate (enforced by Req 7).
- `log_event` bash helper (`runner.sh:355-367`) requires the event name to be in `EVENT_TYPES`; Req 2 adds the two new names.
- Commit created via the `/commit` skill per project convention (CLAUDE.md).

## Open Decisions

None. All decisions resolved during Clarify, Research, and user direction during Research→Specify transition. Critical review surfaced interaction bugs that this spec revision addresses; no user-decidable tie-breaks remain.
