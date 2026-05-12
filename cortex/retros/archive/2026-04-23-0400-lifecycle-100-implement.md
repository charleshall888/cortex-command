# Retro — lifecycle 100 implement phase (2026-04-22 → 2026-04-23)

Session-level problem log. Not for celebrating; for not repeating.

## What went wrong

### 1. Parallel session clobbered my plan commit on main

- I committed plan artifacts as `1a3eaad` at 21:12. A concurrent session reset main to drop that commit and land its own work. I re-landed from the dangling tree (`4fd4d8e`). My own events.log went from 39 lines back to 2 lines mid-session (working tree got stomped somewhere in that sequence — mechanism not determined).
- Cost: ~15 min of salvage work, some confusion reading reflog.
- Root fix: backlog #128 (pre-commit hook rejecting main commits during overnight sessions) would have prevented this.

### 2. Parallel Agent dispatch for probe tasks rate-limited badly

- Dispatched Tasks 3, 4, 5 in parallel via `Agent(isolation: "worktree")`. 3 concurrent Opus 4.7 `claude -p` calls → rate limit. Task 3 (5 trials) took 2h, Task 5 (5 trials) took 2h, Task 4 (30 trials) completed only 2/30 before the agent self-terminated with "Now I'll wait for the background task to finish."
- When I later serialized Task 4 via a single bash loop (`run-r1-hedge.sh`), 30 trials finished in **6 min**. 20× faster than the parallel attempt.
- Don't parallel-dispatch probe batches that all hit Opus. Serialize.

### 3. Daytime pipeline worktree path broken by Seatbelt sandbox

- `claude/pipeline/worktree.py` hardcoded worktrees at `.claude/worktrees/{feature}`. Seatbelt blocks writes under `.claude/`, so `git worktree add` failed at `.mcp.json` checkout.
- Fixed in `f1caec4` via opt-in `CORTEX_WORKTREE_ROOT` env var → route to `$TMPDIR/cortex-worktrees/{feature}`.
- Knowledge that needs to transfer to future sessions: **always set `CORTEX_WORKTREE_ROOT=$TMPDIR/cortex-worktrees` when launching the daytime pipeline from an interactive Claude Code session**. The default `.claude/worktrees/` path only works when launched via overnight runner (different sandbox context).

### 4. SDK auth + parser bugs blocked the pipeline (#140 surfaced)

- First pipeline run: `claude` CLI subprocess returned "Not logged in" because SDK didn't inherit auth from the parent Claude Code session. Fixed by `ensure_sdk_auth` module that resolves `~/.claude/personal-oauth-token`.
- Same run: pipeline picked Task 2 despite `[x] complete` in Status line. Parser regex `re.search(r"\[x\]")` matched `[x]` anywhere in the line; my mixed `[x] complete` + `[ ] pending` across different tasks happened to confuse it. Fixed by `3e3d3b8` anchoring `re.match` at start of Status value.
- Both fixes were done out-of-band by the user; I surfaced and ticketed them (#140).

### 5. Pipeline's max_turns=20 can't execute scripted-loop tasks

- Task 4 (30 probes), Task 11 (5 probes), Task 12 (30 probes), Task 13 (5 probes) are deterministic for-loops. Each probe = 1+ agent tool call. 30 probes won't fit in 20 turns.
- Pipeline ran Task 4 once, agent spent 4 turns planning, committed nothing, pipeline classified "deferred", exited. $1.87 wasted on no output.
- Fix: those tasks belong in bash, not agents. Plan authorship assumed a human or scripted loop runs the batteries; pipeline misinterpreted as agent work.
- Follow-up already filed in #140 as "pipeline can't natively express scripted-loop tasks."

### 6. Pipeline's Task 6 dispatch crashed 3 times via SDK exit 1

- Each retry: agent did ~50 turns of real analysis work on probe-log.md, then `claude_agent_sdk/_internal/query.py:611` raised `Exception: Command failed with exit code 1. Error output: Check stderr output for details.`
- Cost: $12.53 burned across 3 retries (attempts 1–3: $4.65 + $5.17 + $2.71).
- All 3 attempts' WORK survived in the worktree's uncommitted `probe-log.md` (400 lines) — but `new_commit_count: 0` because the SDK crashed before the agent's `/commit` step completed.
- The pipeline's `cleanup_worktree` is supposed to drop unsaved work, but the "paused" outcome path didn't clean up, so I could salvage the file. Lucky; not reliable.
- Root cause of the SDK crash: unknown. Worth tracking — add to #140 or a new ticket.

### 7. Agent wrote §Decision: D with wrong mechanism framing

- The agent's §Decision rationale cited "apparatus shortfall" and "rail inconsistently applied even when loaded." Direct inspection of every trial's first tool-use action showed the actual mechanism: **skill routing bypasses the rail's conditional-load trigger** (14/40 trials first-actioned `Skill: pr`, 5/40 `Skill: commit`; the lone canonical/trial-1 fire came from `Read verification-mindset.md` as first action).
- The D-branch conclusion (stop #100 rewrite; hook-based intervention) happens to be correct, but the reason is different. Task 19's handoff.md needs to cite skill-routing as the mechanism and should propose both a PreToolUse hook AND a skill-side fix (make `/pr`/`/commit` SKILL.md explicitly invoke the rail).
- Post-hoc §Root Cause Analysis section now appended to `probe-log.md` so a resumed session has the correct framing.

## Costs

| Bucket | Spend |
|---|---|
| R1 canonical (5 trials, Agent-tool) | $1.55 |
| R1 control (5 trials, Agent-tool) | $0.95 |
| R1 hedge (30 trials, bash loop) | $6.87 |
| Task 6 pipeline retries (3 crashes, no commit) | $12.53 |
| Pipeline startup / misc | ~$2 |
| **Total lifecycle 100 implementation so far** | **~$24** |

## What a resumed session needs to know

1. Phase = implement. Next pickable task = **Task 7** (write §Decision).
2. §Decision is already drafted in probe-log.md (D-branch). The new §Root Cause Analysis section contains the corrected mechanism framing — use that, not the "apparatus confound note" paragraph above it.
3. Tasks 11, 12, 13 (R5 battery) are **NOT** applicable in D-branch — they're A-branch gated. D-branch's only remaining work is Task 19 (handoff.md + new backlog item for hook/skill-side fix).
4. Task 19's prompt template should include the skill-routing finding as rationale. The backlog item it creates should propose EITHER a PreToolUse hook OR a skill SKILL.md audit, and the user picks.
5. If launching the pipeline for Task 19: set `CORTEX_WORKTREE_ROOT=$TMPDIR/cortex-worktrees`, use `.venv/bin/python3`, and be ready for the SDK-crash pattern (salvage worktree's uncommitted work if it happens).

## What went right

- Hand-running Task 4 via bash (~6 min, $6.87) validated the pipeline-vs-bash-loop split for battery tasks.
- Salvaging 400 lines of agent work from the crashed worktree preserved $12.53 of spend.
- Direct inspection of the stream-json files surfaced the skill-routing mechanism the agent missed.
