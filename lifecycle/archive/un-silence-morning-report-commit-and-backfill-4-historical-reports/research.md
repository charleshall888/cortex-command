# Research: Un-silence morning-report commit and backfill historical reports

## Epic Reference

This ticket is scoped from the discovery epic `research/orchestrator-worktree-escape/research.md` (RQ3, Fact-Section Correction #4). The epic originally framed this as a "gitignore silently skips per-session file → commit skipped" bug. Direct verification during this research (see below) shows the mechanism is more nuanced: the top-level `lifecycle/morning-report.md` is NOT gitignored, the writer actively writes to it, and one session (2026-04-01-2112, commit `85e87aa`) did commit successfully. The silent-failure of the OTHER 3 sessions has a different, still-unidentified cause. Do not rely on the epic's framing as the mechanism — use this ticket's direct verification.

## Clarified Intent

Fix the overnight-runner commit step so every session's morning report lands in git history at `lifecycle/morning-report.md` on local `main`, and backfill 3 historical sessions whose reports exist locally but were never committed. A pre-requisite is diagnosing why sessions 2026-04-07-0008, 2026-04-11-1443, and 2026-04-21-1708 silently failed to update the top-level file — the ticket's original mechanism hypothesis does not match observed data.

## Codebase Analysis

### Files touched by the forward fix (range subject to change once root cause is diagnosed)

- `claude/overnight/runner.sh:1180-1215` — two-branch `generate_and_write_report` invocation (cross-repo vs single-repo).
- `claude/overnight/runner.sh:1220-1226` — commit subshell in `REPO_ROOT`. Contains dead `git add "lifecycle/sessions/${SESSION_ID}/morning-report.md"` (always gitignored).
- `claude/overnight/runner.sh:505-521` — interrupted-session trap heredoc; same double-write pattern.
- `claude/overnight/runner.sh:1229-1248` — second commit block targeting `TARGET_INTEGRATION_WORKTREE` on the target repo's integration branch.
- `claude/overnight/report.py:1398-1489` — `generate_and_write_report`; does per-session write + try/except-wrapped latest-copy write. The try/except at 1467-1474 silently swallows ALL `Exception` during latest-copy write.
- `claude/overnight/report.py:1353-1386` — `write_report` atomic tempfile+`os.replace`. Parent dir is created via `mkdir(parents=True, exist_ok=True)`.
- `claude/overnight/sync-allowlist.conf:36` — dead entry `lifecycle/sessions/*/morning-report.md` (per-session path gitignored → never conflicts). Line 37 `lifecycle/morning-report.md` is correct once commits actually land.
- `.gitignore:45` — `lifecycle/sessions/` (directory form; whole tree ignored). Top-level `lifecycle/morning-report.md` is NOT covered.
- `docs/overnight-operations.md:327, 399, 411, 413` — references to the morning-report commit (line 413's "only runner commit that stays on local main" is the aspirational statement).
- `docs/agentic-layer.md:311` — conflicting claim: "`morning-report.md` is a symlink to the latest archive" (not true on disk; the file is a regular file).
- `skills/morning-review/SKILL.md:82-84` — reader priority: `latest-overnight` symlink → top-level `lifecycle/morning-report.md`.

### Verified mechanism (direct inspection)

1. `.gitignore:45` is `lifecycle/sessions/` (directory form). `git check-ignore -v lifecycle/morning-report.md` returns nothing (not ignored). `git check-ignore -v lifecycle/sessions/overnight-2026-04-01-2112/morning-report.md` returns the match on `.gitignore:45`.

2. `DEFAULT_REPORT_PATH = _LIFECYCLE_ROOT / "morning-report.md"` where `_LIFECYCLE_ROOT = Path(__file__).resolve().parents[2] / "lifecycle"` from `claude/overnight/state.py:28`. So when invoked in-repo, `_LIFECYCLE_ROOT` resolves to `<cortex-command>/lifecycle/`.

3. `generate_and_write_report(project_root=None)` → latest-copy goes to `_LIFECYCLE_ROOT/morning-report.md` (home repo). `generate_and_write_report(project_root=X)` → latest-copy goes to `X/lifecycle/morning-report.md`.

4. `runner.sh:1180` branches on `TARGET_INTEGRATION_WORKTREE`, which at 312-333 is populated from `state.json.integration_worktrees[TARGET_PROJECT_ROOT]` — ONLY if `integration_worktrees` has a matching entry AND the path exists on disk. Empty dict → empty variable → else-branch taken.

5. **Verified historical session state** (all 5 sessions on this machine):

   | Session | integration_branches | integration_worktrees | Branch taken | Top-level committed? |
   |---|---|---|---|---|
   | overnight-2026-04-01-1650 | `{wild-light: ...}` | `{}` | single-repo | no report generated (aborted) |
   | overnight-2026-04-01-2112 | `{wild-light: ...}` | `{}` | single-repo | **YES (commit 85e87aa)** |
   | overnight-2026-04-07-0008 | `{cortex-command: ...}` | `{}` | single-repo | NO |
   | overnight-2026-04-11-1443 | `{cortex-command: ...}` | `{}` | single-repo | NO |
   | overnight-2026-04-21-1708 | `{cortex-command: ...}` | `{}` | single-repo | NO |

6. **Per-session files on disk**: all 4 completed sessions have their per-session `lifecycle/sessions/{sid}/morning-report.md` file (8-10 KB each) with session-matching content. Session 1650 has no per-session file (aborted before report generation).

7. **Top-level file mtime**: `lifecycle/morning-report.md` = `Apr 1 17:49:51` — identical to 04-01-2112's per-session file. The top-level file has NOT been overwritten since 2026-04-01. Since `os.replace` always updates mtime (even for identical content), this proves `write_report(report, path=latest_copy_path)` did NOT execute successfully for sessions 04-07, 04-11, 04-21.

8. **Single-repo branch mechanics are correct in isolation**: for cortex-command-targeting sessions, both `report_dir` (per-session) and `_LIFECYCLE_ROOT` (latest-copy) resolve to paths inside `<cortex-command>/lifecycle/`. The per-session write succeeded; the latest-copy write did not. Same process, same function, same disk — **root cause unknown**.

9. **Candidate silent-failure mechanisms** (none confirmed):
   - (a) `report.py:1467-1474` try/except swallowed an exception during latest-copy write (most likely; but what exception?).
   - (b) Python import resolved `claude.overnight.report` from a different copy (e.g., via worktree's sys.path), so `_LIFECYCLE_ROOT` resolved elsewhere. No evidence but plausible with worktree-per-feature overnight pipeline.
   - (c) The latest-copy write succeeded to a different path (e.g., TARGET_PROJECT_ROOT/lifecycle/morning-report.md when TARGET_PROJECT_ROOT != REPO_ROOT). Cross-repo mode risk if `TARGET_PROJECT_ROOT` was set but `TARGET_INTEGRATION_WORKTREE` was empty. Needs check.
   - (d) Some filesystem race / lock / permission issue (implausible on a dev machine).

10. **The runner commit subshell at 1220-1226** runs `cd "$REPO_ROOT"; git add X; git add Y; git diff --cached --quiet || git commit`. `set +e` above; silent-skip on gitignored files via `2>/dev/null || true`. If the top-level file content didn't change (because write_report silently failed), `git add lifecycle/morning-report.md` stages nothing → commit short-circuits. No `morning_report_commit_failed` event is written on this path; only on push failure at 1254-1268.

### Consumers (who reads what)

- `lifecycle/morning-report.md` (top-level): morning-review skill (SKILL.md:82-84 fallback #3); overnight skill docs; overnight-operations docs; `sync-allowlist.conf:37`.
- `lifecycle/sessions/*/morning-report.md` (per-session): morning-review skill via `latest-overnight` filesystem symlink (runner.sh:1301-1307 maintains the symlink); NOT read via git history.
- **Worktree copy `TIW/lifecycle/morning-report.md`** (written when `project_root=TIW` is passed): agent 5 flagged `claude/dashboard/data.py:942` as a potential consumer — needs a closer read, but for the current historical-session failures this path was never taken (all sessions took single-repo).

### Backfill inventory (corrected: 3 sessions, not 4)

| Session | Path on disk | Lines | Heading | Ready to copy? |
|---|---|---|---|---|
| 2026-04-07-0008 | `lifecycle/sessions/overnight-2026-04-07-0008/morning-report.md` | 211 | `# Morning Report: 2026-04-07` | yes |
| 2026-04-11-1443 | `lifecycle/sessions/overnight-2026-04-11-1443/morning-report.md` | 97 | `# Morning Report: 2026-04-11` | yes |
| 2026-04-21-1708 | `lifecycle/sessions/overnight-2026-04-21-1708/morning-report.md` | 110 | `# Morning Report: 2026-04-21` | yes |

Session 1650 has no report (aborted). Session 2112 is already committed as `85e87aa`. Ticket says "4 historical reports"; real count is **3**. Content grep confirms no secrets (no API keys, bearer tokens, corp email traces) — safe to publish.

### Patterns to follow

- Atomic writes via `write_report` (tempfile + `os.replace`) — already correct.
- `git add` without `-f` — keeps gitignore as the storage contract.
- `sync-allowlist.conf` entries should reference paths that are actually tracked.
- Event logging convention: structured JSONL to `overnight-events.log` for every pipeline-relevant action.

## Web Research

### Gitignore re-inclusion semantics (canonical answer)

Direct quote from `git-scm.com/docs/gitignore` PATTERN FORMAT:

> An optional prefix "`!`" which negates the pattern; any matching file excluded by a previous pattern will become included again. **It is not possible to re-include a file if a parent directory of that file is excluded. Git doesn't list excluded directories for performance reasons, so any patterns on contained files have no effect, no matter where they are defined.**

**Consequence**: `.gitignore:45` `lifecycle/sessions/` followed by `!lifecycle/sessions/*/morning-report.md` DOES NOT work. Canonical workaround requires multi-level `dir/*` + `!dir/*/` at each nesting level:

```
lifecycle/sessions/*
!lifecycle/sessions/*/
!lifecycle/sessions/*/morning-report.md
```

This is a known-but-subtle pattern. Readers unfamiliar with the trick will misread it.

### Prior art: "latest-copy + per-run archive" layouts

- **dbt / Orchestra**: `target/` (ephemeral) + `latest_production/` (canonical) + per-run archive saved only on main branch. Exact analog to this project's design (`lifecycle/morning-report.md` = latest canonical; `lifecycle/sessions/{sid}/` = per-run archive).
- **Sphinx/MkDocs/GitHub Pages**: `gh-pages` branch holds "latest"; history on that branch IS the per-run archive.
- **Release/changelog pattern**: canonical tracked `CHANGELOG.md` + per-release tags as archive.

### Backfill best practices

- `git commit --date=...` sets only `GIT_AUTHOR_DATE`, NOT `GIT_COMMITTER_DATE`. Views ordered by committer date (the default for many views) will show backfill commits at "now" unless both are set.
- Correct form: `GIT_COMMITTER_DATE="2026-04-07T08:00:00Z" git commit --date="2026-04-07T08:00:00Z" -m "..."`.
- Tool: `rixx/git-backdate` handles both variables automatically.
- Use automation identity for author (preserves "produced by pipeline" semantics); committer can be the backfiller.
- Explicit `backfill` marker in the subject line enables `git log --grep=Backfill`.
- Safety: only append new commits with backdated dates; never rewrite published history.

### Anti-patterns for committing generated files

- Repo bloat (mitigation: the single-canonical-file pattern avoids per-run growth).
- Diff noise in `git log -p --all` (mitigation: reviewers filter by path).
- Merge conflict hotspots on single canonical file (mitigation: only automation writes it, never humans).
- Misleading activity graphs (mitigation: dedicated bot identity).
- Secret leakage (mitigation: sanitize in generator).

## Requirements & Constraints

### Relevant requirements (verbatim)

- `requirements/pipeline.md:23` (Session Orchestration): "Artifact commits (lifecycle files, backlog status updates, session data) land on the integration branch, not local `main` — they travel with the PR"
- `requirements/pipeline.md:24`: "The morning report commit is the only runner commit that stays on local `main` (needed before PR merge for morning review to read)"
- `requirements/pipeline.md:108-119` (Post-Session Sync): `sync-allowlist.conf` patterns are auto-resolved `--theirs` during post-merge rebase; `--merge` PR merge strategy is a load-bearing dependency.
- `requirements/pipeline.md:123`: "All session state writes use tempfile + `os.replace()`" (atomicity).
- `requirements/project.md:15` (Philosophy — Failure handling): "Surface all failures in the morning report."
- `requirements/project.md:25` (Architectural Constraints — File-based state): "No database or server."
- `requirements/multi-agent.md:29, 35, 74`: Cross-repo worktrees live in `$TMPDIR`, NOT in home repo. Establishes the distinction that single-repo vs cross-repo session state IS a real branching concern.

### Key constraint: cross-repo mode

`requirements/multi-agent.md` establishes that cross-repo mode is a genuine branching surface — worktrees, integration branches, and sync all behave differently. The runner.sh branching at 1180 is consistent with this design. But the historical sessions on this machine never exercised cross-repo mode (empty `integration_worktrees`), so the cross-repo branch is untested against production data here.

### No constraint prohibits un-gitignoring per-session files

No requirement file explicitly prohibits carving out `morning-report.md` from the `lifecycle/sessions/` ignore rule. The `.gitignore:44` comment "Overnight session archives" signals policy intent (session state ephemeral) but is not a hard requirement.

### Epic discovery research alignment

`research/orchestrator-worktree-escape/research.md` RQ3 left the storage decision open (line 264). DR-1 originally scoped backfill as a separate ticket from the forward fix. Ticket 129 bundles both. This research confirms DR-1's instinct was correct: the forward fix and the backfill have independent mechanisms and can land as separate PRs.

## Tradeoffs & Alternatives

### Forward-fix approaches

| Approach | Description | Complexity | Pros | Cons |
|---|---|---|---|---|
| **A. Top-level canonical (fix unknown root cause)** | Keep the existing design (latest-copy at `lifecycle/morning-report.md`). First diagnose why sessions 04-07/04-11/04-21 silently failed to write; then fix that specific mechanism. | Low-to-medium, depends on root cause | Preserves existing design intent. Aligns with dbt/Orchestra "latest + archive" pattern. Minimal `.gitignore` change. | Requires diagnostic step before fix. Root cause still unidentified. |
| **B. Un-gitignore per-session path** | Restructure `.gitignore:45` with multi-level `dir/*` + `!dir/*/` pattern; commit per-session archives. | Medium | Tracks every session as a separate file; no collision on canonical path. | `.gitignore` becomes semantically murky; slippery slope (why this file not others?); doesn't fix the actual write bug if the bug is in the writer. |
| **C. Track both paths** | Both top-level AND per-session committed. | Medium-high | Best audit trail. | Duplicate blobs, doubled sync-allowlist surface, dual-write failure modes, repo bloat. |
| **D. `git add -f`** | Force-stage the per-session file in runner. | Trivial | Two-char edit. | Code smell; bypasses gitignore policy; doesn't fix the actual write bug. |
| **E. Dedicated `reports/` directory** | Move morning-reports to a separate always-tracked path. | High | Cleanest long-term. | Over-engineering for this bug; migration of consumers needed. |

### Why all the above miss the point

Approaches B/C/D assume the bug is the `git add` of the per-session path being silently skipped. But the DIRECT verification shows: sessions 04-07/04-11/04-21 silently failed to WRITE the top-level file, not to ADD it. The commit subshell at 1220-1226 behaves correctly given what's on disk: nothing new to stage → no commit. Fixing the commit step is treating the symptom.

The real question: why did `write_report(report, path=latest_copy_path)` fail silently three times? Until that's answered, no forward fix is load-bearing.

### Recommended forward approach (diagnose-before-fix)

**Step 1 (separate small PR): Add diagnostics to surface the silent failure.**
- Replace the try/except at `report.py:1467-1474` with either: re-raise after logging, OR write a sentinel file `~/.local/share/morning-report-failures/{sid}.json` capturing the exception type + path attempted.
- Add a `morning_report_generate_result` event to `overnight-events.log` after the Python invocation, capturing: `{"path_per_session": ..., "path_latest_copy": ..., "per_session_sha1": ..., "latest_copy_sha1": ..., "per_session_size": ..., "latest_copy_size": ...}`. A sha1 of `null` for the latest-copy indicates the write failed; identical sha1s indicate duplicate content.
- Add a `morning_report_commit_result` event after the commit subshell: `{"status": "committed|skipped_no_changes|stage_failed", "staged_files": [...], "commit_sha": ...}`.

**Step 2 (sequential, after diagnostics land): Run the next overnight session, inspect diagnostic output, identify the actual root cause.**

**Step 3 (separate PR): Implement the narrowly-scoped fix for the identified cause.**

This ordering ensures the fix is evidence-driven, not speculative. Total forward-path scope is still small (~20 LOC net across steps 1 and 3).

### Backfill approaches

| Approach | Description | Pros | Cons |
|---|---|---|---|
| **(i) Snapshot at execution time** | `git add lifecycle/morning-report.md` captures whatever's on disk; one commit. | Simple. | Non-deterministic; only the latest report ends up in history; misses the 2 earlier sessions. |
| **(ii) Fixed list of 3 named files** | Explicit list, 3 separate commits. | Deterministic; reviewable. | Requires copying content to top-level path per-commit. |
| **(iii) Chronological replay** | 1 commit per session in timestamp order, each at top-level path, backdated. | Clean git log; reproduces what would have happened. | More setup (date handling per commit). |

**Recommended backfill**: (ii) + (iii) hybrid — explicit list of 3 sessions, committed chronologically at the top-level path with `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` both set to the session's `session_complete` timestamp. Matches commit message format of `85e87aa` with explicit `(backfill)` suffix. Backfill is a SEPARATE PR from the forward fix; merge forward fix first, then backfill.

## Adversarial Review

### Failure modes and edge cases

1. **Agent 1's cross-repo-misrouting diagnosis does not explain the historical data.** All historical sessions had `integration_worktrees={}` and took the single-repo branch. The proposed "drop `project_root=Path(tiw)`" fix would not have committed sessions 04-07/04-11/04-21. The real root cause is unidentified.

2. **Silent-failure pattern pervades the commit path**: `2>/dev/null || true` on `git add`, `try/except: print(..., file=sys.stderr)` in report.py, `|| echo "Warning"` on report generation. No single point of truth for "why didn't the report commit." Mitigation: structured events as described in the diagnostic step above.

3. **Backfill count is 3, not 4** (verified above). Ticket is imprecise. Do not manufacture a report for session 1650 — it was aborted before report generation.

4. **Race between forward-fix merge and in-flight overnight session**. If an overnight session starts after the backfill merges but before the forward-fix merges, the runner's push may non-fast-forward. Current runner only logs; does not retry. Mitigation: run backfill only when no overnight session is active (check `~/.local/share/overnight-sessions/active-session.json`).

5. **`try/except` in report.py:1467-1474 silently swallows EVERY Exception.** Filesystem issues, permission denied, transient OS errors — all go to stderr only. Likely a contributor to the failures. Mitigation covered by diagnostic step.

6. **Commit subshell uses `cd "$REPO_ROOT"` then relative `git add`.** If `REPO_ROOT` resolution is ever wrong (e.g., called from a worktree without proper resolution), stages from outside the intended tree. Current resolution at runner.sh:24-33 uses `git rev-parse --path-format=absolute --git-common-dir` — correct, but fragile under unusual worktree/submodule setups. Mitigation: assert `is-inside-work-tree`.

7. **No validation that committed blob matches generated content.** Stale or partial file could be committed unnoticed. Mitigation: post-commit verification `git show HEAD:lifecycle/morning-report.md | diff -q - "$report_path"`.

8. **Interrupted-session heredoc (runner.sh:505-521) runs in a signal trap** with limited error handling; uses `write_report` directly (not `generate_and_write_report`). If REPO_ROOT is inconsistent at trap time, both writes can fail silently. Mitigation: wrap the heredoc Python in its own try/except; log `morning_report_write_failed` on any write failure.

9. **Second commit block at runner.sh:1229-1248 stages files on the TARGET repo's integration branch.** The `lifecycle/morning-report.md` stage here is live only if the target repo's `.gitignore` permits it AND the cross-repo Python block wrote the file to that worktree. Target repos may have different gitignore policies; removing this stage without checking risks silent regression for the target-repo operator. Mitigation: do NOT drop this stage as part of the home-repo fix; treat target-repo commit as separate scope.

10. **`docs/agentic-layer.md:311`** claims "`morning-report.md` is a symlink to the latest archive" — NOT TRUE on disk (regular file). Docs drift. Reconcile in the PR.

### Security concerns

- **Historical report content grep is clean** (no API keys, no bearer tokens, no corp email traces). Safe to publish.
- **Future reports could leak agent stderr**; confirm `render_tool_failures` sanitization is in place.

### Assumptions the other agents made that may not hold

- **Agent 1**: "Dropping the dead `git add lifecycle/sessions/...` at 1223 is safe — no consumer reads via git history." Agree for the home-repo stage. DO NOT apply this reasoning to the target-repo stage at 1241-1242.
- **Agent 1**: "Single-repo branch correctly commits; 2112 proves it." Correct for 2112, but then why did 04-07/04-11/04-21 not commit? Agent 1's model doesn't explain this gap.
- **Agent 3**: "`requirements/pipeline.md:24` has the morning-report-stays-on-main criterion." Correct quote but be cautious — the same sentence appears in `docs/overnight-operations.md:413`; don't confuse them when citing.

### Recommended mitigations (diff-level)

1. **Do NOT land a speculative forward-fix patch.** The cross-repo-misrouting patch from Agent 1 would not have changed behavior for any of the failed historical sessions.
2. **Land diagnostic instrumentation first** (small PR, ~20-30 LOC):
   - `report.py:1467-1474`: either raise on failure, or write a sentinel file.
   - `runner.sh:1180-1226`: emit `morning_report_generate_result` and `morning_report_commit_result` events with sha1s and commit sha.
3. **Run next overnight session**, inspect diagnostic output.
4. **Implement the narrowly-scoped fix** for the identified cause.
5. **Backfill as separate PR** with 3 (not 4) sessions, chronological commits, backdated `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE`, explicit `(backfill)` marker.
6. **Reject the `.gitignore` un-ignore option** (ticket's option a). Not the root cause, introduces policy creep.
7. **Leave `sync-allowlist.conf:36` in place for now.** If the diagnosed fix ends up committing the per-session file (any reason), that entry becomes live again. Cleanup is cheap later.
8. **Correct `docs/overnight-operations.md:413`** wording to reflect reality: the commit is intended to stay on local main; has been unreliable; this fix makes it reliable.
9. **Correct `docs/agentic-layer.md:311`** — morning-report.md is NOT a symlink.

## Open Questions

All of the following are research-answerable (code or inspection), not user-answerable — they flow into Spec for investigation, not user Q&A:

- **Q1 (load-bearing): What actually caused the latest-copy write to silently fail for sessions 2026-04-07-0008, 2026-04-11-1443, and 2026-04-21-1708?** Deferred to the diagnostic-first approach above. Spec should prescribe Step 1 (instrumentation) before Step 3 (fix) — the fix is blocked on this data.

- **Q2**: Does `claude/dashboard/data.py:942` (per agent 5) or any other consumer read `TARGET_INTEGRATION_WORKTREE/lifecycle/morning-report.md`? If yes, the cross-repo fix must preserve that write. Deferred: Spec to include a concrete grep check.

- **Q3**: Should the runner surface the `|| echo "Warning: morning report generation failed"` (runner.sh:1198, 1214) via an `overnight-events.log` event, not just stdout? Likely yes; bundle into diagnostic step.

- **Q4**: For the backfill commits, what author identity is appropriate? Options: (i) the operator's normal identity with `(backfill)` marker in subject, (ii) a dedicated `Overnight Backfill <automation@cortex-command>` identity. Convention TBD. Deferred to Spec.

- **Q5**: Should the `docs/agentic-layer.md:311` "symlink" claim be rewritten to describe the actual design (regular file + `latest-overnight` symlink at `lifecycle/sessions/latest-overnight`)? Almost certainly yes; include in the docs-reconciliation pass.

- **Q6**: Is there a case where the target-repo second commit block (runner.sh:1229-1248) silently drops real updates? Specifically, does the target repo's `.gitignore` typically cover `lifecycle/sessions/`? Deferred: Spec to include a one-time check against known target repos (wild-light).
