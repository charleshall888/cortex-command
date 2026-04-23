# Research: Integrate autonomous worktree option into lifecycle pre-flight

**Epic Reference**: `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md` — broader epic covering the #074 batch_runner decomposition and daytime pipeline motivation. DR-2 (co-exist, not replace) and DR-3 (events.log writes to main repo CWD) are the load-bearing decisions from the epic that apply to this ticket.

## Codebase Analysis

### Files That Will Change

**Primary:**
- `skills/lifecycle/references/implement.md` — add fourth pre-flight option, guard checks, result surfacing, invocation protocol

**Possible secondary:**
- `hooks/cortex-cleanup-session.sh` — if the worktree prefix decision chooses `worktree/daytime-*` over the pipeline's existing `pipeline/{feature}` naming (see Tradeoffs section)
- New test files under `tests/` or `tests/scenarios/lifecycle/` — skill-level behavior tests for the four-option decision tree

**No changes needed to:**
- `claude/overnight/daytime_pipeline.py` — CLI is complete (#078 closed)
- `skills/lifecycle/SKILL.md` — the Step 2 `.dispatching` check must be supplemented (not changed) to also check `daytime.pid` for the daytime path

### Pre-Flight Structure Today

`implement.md §1 Branch Selection` presents **three options** via `AskUserQuestion`:
1. Implement in worktree (Agent isolation, §1a dispatch path)
2. Implement on main (trunk-based)
3. Create feature branch (`feature/{slug}`)

Guards already in place:
- Branch detection: only prompts if on `main`/`master`
- Dependency cycle detection runs before dispatch in all paths
- `.dispatching` noclobber atomic write guard (§1a step i) prevents double-dispatch for single-agent worktree path

### Daytime Pipeline CLI Interface

```
python3 -m cortex_command.overnight.daytime_pipeline --feature {slug}
```

- CWD must be repo root (`_check_cwd()` enforces; exits 1 with `"must be run from repo root"`)
- Prerequisite: `lifecycle/{feature}/plan.md` must exist (exits 1 with `"plan.md not found"` otherwise)
- Exit codes: 0 = merged successfully, 1 = deferred/paused/failed/startup guard failure
- Stdout distinguishes outcomes: `"merged successfully"`, `"deferred — check lifecycle/{feature}/deferred/"`, `"paused — check events.log"`, `"failed: {error}"`
- **Does NOT accept**: spec path, plan path, complexity, criticality, base-branch, test-command, events-log path — all derived internally from disk artifacts

`build_config()` reads `test-command` from `lifecycle.config.md` frontmatter, hardcodes `base_branch="main"`, derives `overnight_events_path` from `Path.cwd() / f"lifecycle/{feature}/events.log"`.

### `.dispatching` Mechanism

Lives in `SKILL.md` Step 2 and `implement.md §1a step i`:
- File: `lifecycle/{feature}/.dispatching` — 3 lines: PID (`$$`), `LIFECYCLE_SESSION_ID`, ISO timestamp
- Written with `set -C` (bash noclobber) for atomic claim
- PID is the shell's `$$` — a transient process that lives milliseconds. Any subsequent skill invocation finds a `.dispatching` file with a dead PID and cleans it up, defeating the guard for daytime runs

**Critical**: The `.dispatching` mechanism is designed for single-agent worktree dispatch where the guard window matches the Agent tool's execution duration. It is NOT suitable as a daytime dispatch guard because `$$` dies before the daytime subprocess is even spawned.

### Daytime PID Mechanism

`lifecycle/{feature}/daytime.pid` — single-line PID file written by `daytime_pipeline.py`:
- Written at startup in `_write_pid()` before worktree creation
- Removed in `finally` block (and by `_orphan_guard` if reparented to PID 1)
- Liveness check: `os.kill(pid, 0)` with `PermissionError` treated as alive
- Recovery: stale PID triggers `_recover_stale()` (abort merge, remove locks, force-remove worktree, prune)
- SIGKILL invariant: Python `finally` blocks do NOT run on SIGKILL. But the `_orphan_guard` coroutine explicitly calls `pid_path.unlink()` before `os._exit(1)`. On plain SIGKILL (no reparenting), the `daytime.pid` persists → next run detects stale PID → calls `_recover_stale()` → proceeds safely.

### Overnight Detection Mechanism

Two complementary signals (same as `bin/overnight-status`):
1. `~/.local/share/overnight-sessions/active-session.json` — global pointer with `session_id`, `repo_path`, `state_path`, `phase`. Must filter by `repo_path == CWD` (multi-repo machines).
2. `lifecycle/sessions/{session_id}/.runner.lock` — single-line PID; liveness-checked with `kill -0 $PID`

Correct combined check:
1. Read `active-session.json` → get `repo_path`, `state_path`, `phase`
2. Verify `repo_path` matches current CWD and `phase == "executing"`
3. Derive session dir from `state_path`
4. Read `.runner.lock` PID → `kill -0 $PID` → alive = overnight running; dead = stale pointer

**False-positive risk**: Historical session directories may retain `.runner.lock` files if the runner was killed without cleanup. Glob of ALL `lifecycle/sessions/*/.runner.lock` would falsely match stale lock files from old sessions. Must use `active-session.json` as the first filter, not a raw glob.

### Worktree Branch Naming

`create_worktree()` in `claude/pipeline/worktree.py` uses `pipeline/{feature}` branch naming and `.claude/worktrees/{feature}` path. This is distinct from:
- `worktree/agent-{lifecycle-slug}` — used by `Agent(isolation: "worktree")` tool
- The `cortex-cleanup-session.sh` hook targets `worktree/agent-*` only — never fires for `pipeline/*` branches

The existing single-agent worktree cleanup hook is therefore NOT relevant to the daytime pipeline's worktree lifecycle. The daytime pipeline handles its own cleanup via `cleanup_worktree()` in the `finally` block.

**Bug in #078 (minor)**: `cleanup_worktree()` hardcodes `branch = f"pipeline/{feature}"` for branch deletion. But `create_worktree()` may have created `pipeline/{feature}-2` on collision. On collision, cleanup fails to delete the `-2` branch. This accumulates orphaned branches across restarts.

### Tests

No existing tests for the implement phase pre-flight decision tree. What exists:
- `tests/test_lifecycle_state.py` — phase detection, not pre-flight
- `tests/scenarios/lifecycle/` — phase ordering, not option selection
- `claude/overnight/tests/test_daytime_pipeline.py` — subprocess layer, not skill layer

New tests needed: scenario YAML for four-option decision tree, concurrent guard rejection scenarios, integration test for skill-to-CLI invocation contract.

---

## Web Research

### Subprocess Blocking Architecture (Critical Finding)

**The Bash tool has a hard 10-minute maximum timeout**. The daytime pipeline runs execute_feature → Claude SDK dispatch → per-task agents, which takes 30–90 minutes. Synchronous blocking via `subprocess.run()` or `proc.communicate()` will time out in a Bash tool call.

**Correct architecture for long-running subprocesses from a skill:**
- Launch subprocess in background: `nohup python3 -m cortex_command.overnight.daytime_pipeline --feature {slug} > {log} 2>&1 &; echo $!`
- Skill receives PID immediately
- Skill periodically polls for completion (via `kill -0 $PID` liveness check or reading events.log)
- When complete, read results from stdout log or events.log

Alternatively: run via `run_in_background=True` on the Bash tool, then use the Monitor tool or repeated Read calls on events.log to detect completion.

**Comparison with single-agent worktree**: `Agent(isolation: "worktree")` has its own progress mechanism; it is not subject to the 10-minute Bash timeout. The daytime pipeline subprocess is different — it must be backgrounded.

### Concurrent Guard Patterns

**Recommended (flock over PID)**: `fcntl.LOCK_EX | fcntl.LOCK_NB` auto-releases on process death — no stale cleanup needed, no PID reuse risk. But since the daytime pipeline already implements `daytime.pid` with liveness probing, and the skill layer cannot run Python directly, the practical approach is:

**Shell-level guard**:
```bash
kill -0 $(cat lifecycle/{feature}/daytime.pid 2>/dev/null) 2>/dev/null && echo "running" || echo "not-running"
```

**Known anti-patterns** (from web research):
- `kill -0 $(cat pidfile)` alone is unreliable for general use due to PID reuse, but acceptable for short-lived intra-session guards on single-user machines
- `ps aux | grep name` — unreliable (matches unrelated processes)
- `shell=True` in subprocess — prevents clean kill on timeout

### Result Surfacing Pattern

Canonical approach: exit code (0/1) + human-readable stdout. For the three-way deferred/paused/failed distinction, parse stdout first line for key phrases (`"merged"`, `"deferred"`, `"paused"`, `"failed"`). For deferred outcomes, supplement with deferred file content from `lifecycle/{feature}/deferred/*.md`.

---

## Requirements & Constraints

### From `requirements/pipeline.md`

- All state writes must be atomic (`tempfile + os.replace()`) — applies to any new lock/marker files
- `.runner.lock` pattern: write PID, verify liveness with `kill -0`; same model this ticket extends
- Feature terminal outcomes: `merged` (success), `deferred` (human decision needed), `paused` (recoverable), `failed` (unrecoverable)

### From `requirements/multi-agent.md`

- Single-orchestrator model: agents do not spawn peer agents. Corollary: the skill must not invoke daytime pipeline while overnight is dispatching on the same repo
- Worktrees at `.claude/worktrees/{feature}/` — daytime pipeline uses this same path

### From `skills/lifecycle/SKILL.md`

- SKILL.md Step 2 `.dispatching` check: reads PID from line 1, runs `ps -p $PID`. This check is designed for single-agent worktree dispatch. The `daytime.pid` guard must be added separately (either as an additional check in Step 2, or as a pre-flight check within the new implement.md §1d path)
- SKILL.md Step 2 skip conditions: write-backs skip when current branch matches `^worktree/agent-`. Daytime pipeline does NOT change the main session's branch (subprocess runs separately), so skip conditions are NOT triggered
- Implement.md dispatch guard: `.dispatching` mechanism does NOT work for daytime (PID `$$` is ephemeral). The skill must use `daytime.pid` liveness instead

### From `claude/rules/sandbox-behaviors.md`

- No compound `&&`/`;`/`|` bash commands — each Bash call must be a single independent command
- No `git -C` — all git calls direct from repo root CWD

---

## Tradeoffs & Alternatives

### Sub-decision 1 — Double-Dispatch Guard Mechanism

**Option A — Check `daytime.pid` directly (recommended)**
- Skill reads `lifecycle/{feature}/daytime.pid`, checks liveness with `kill -0 $PID`
- Pro: Pipeline owns its own PID file; no new file types; same mechanism as subprocess's own guard
- Pro: SIGKILL-safe (stale PID is detected and triggers recovery)
- Con: Narrow TOCTOU gap (seconds); acceptable on single-user machine
- Con: Skill must know `lifecycle/{feature}/daytime.pid` path convention

**Option B — Reuse `.dispatching` for daytime**
- Con: `$$` PID is ephemeral — dies within milliseconds. Subsequent skill invocations find a dead PID and clean up the marker, defeating the guard entirely.
- **Not viable** for daytime dispatch.

**Option C — New lockfile**
- Con: Third marker type when `daytime.pid` already exists with full liveness semantics.

**Option D — Rely solely on #078's internal guard**
- Pro: Zero skill-layer work
- Con: User sees subprocess error instead of clean pre-launch rejection; slightly worse UX

**Recommendation: Option A.** Read `daytime.pid` before spawning; check PID liveness; reject if alive with "autonomous daytime run already in progress (PID X)".

---

### Sub-decision 2 — Concurrent Overnight+Daytime Guard

**Option A — Parse `active-session.json` only**
- Con: SIGKILL'd runner leaves `phase: "executing"` in pointer (false positive). Phase field is only reliable combined with PID liveness.

**Option B — Glob all `.runner.lock` files + PID probe (not recommended as written)**
- Con: Historical stale `.runner.lock` files cause false positives if cleanup didn't run on old sessions.

**Recommended combined approach:**
1. Read `~/.local/share/overnight-sessions/active-session.json`
2. Check `repo_path == CWD` and `phase == "executing"`
3. Derive session dir, read `.runner.lock`, check `kill -0 $PID`
4. All three conditions must be true to block; any false means overnight is not active

This mirrors `bin/overnight-status` exactly and avoids scanning all historical sessions.

**Option D — No guard / document as limitation**
- Explicit acceptance criterion requires the guard; not acceptable.

---

### Sub-decision 3 — Result Surfacing

**Option D (recommended) — Subprocess stdout + deferred file for deferred path:**
- Exit 0: surface stdout directly (`"Feature X merged successfully."`)
- Exit 1: parse stdout prefix to distinguish deferred/paused/failed; supplement deferred path with content of `lifecycle/{feature}/deferred/*.md`
- Pro: Zero coupling to internal state files; robust to schema evolution
- Con: Must document stdout parsing rules explicitly in implement.md

**Option A — Read events.log tail:**
- Pro: Machine-readable NDJSON
- Con: Noisy internal events; requires filtering for terminal event types

**Option B — Parse `daytime-state.json`:**
- Con: `BatchResult` (which carries `features_deferred`, `features_failed`) is not persisted to disk; only stdout carries that data

---

## Adversarial Review

### Critical: Bash Tool Timeout Makes Synchronous Blocking Infeasible

The Bash tool has a 10-minute maximum timeout. The daytime pipeline runs 30–90 minutes. The skill CANNOT block on `python3 -m cortex_command.overnight.daytime_pipeline` via a synchronous Bash call. The proposed "block on subprocess exit" architecture is infeasible as stated.

**Required mitigation**: Background execution model:
1. Launch subprocess with `nohup ... & echo $!` (or Bash `run_in_background=True`)
2. Skill receives PID immediately; writes it to a result-check file
3. Skill polls completion via `kill -0 $PID` + checking events.log for terminal event
4. Surface results when process exits

Alternatively: the skill could be fire-and-forget with explicit instruction to use `overnight-status` or the dashboard to monitor progress. This is simpler but loses the skill-layer result surfacing goal.

### Critical: `.dispatching` PID `$$` Is Ephemeral — Unsuitable for Daytime

The shell's `$$` in the `.dispatching` file dies milliseconds after the Bash tool call returns. Any re-invocation finds a dead PID and cleans up the marker. The `.dispatching` mechanism cannot guard the daytime path. Use `daytime.pid` exclusively for the daytime double-dispatch guard.

### High: Overnight Detection Must Filter by `repo_path`

`active-session.json` is global (not repo-scoped). On a multi-repo machine, another repo's overnight session would falsely block daytime dispatch. Check `repo_path` field matches CWD before treating the session as active.

### High: `.runner.lock` Glob Approach Has Stale-File False Positives

Globbing all `lifecycle/sessions/*/.runner.lock` catches stale lock files from old sessions that didn't clean up on crash. Use `active-session.json` as the first filter (get the current session's path), then probe only that session's lock file.

### Medium: `cleanup_worktree` Branch Deletion Misses `-2` Suffix

`cleanup_worktree()` hardcodes `pipeline/{feature}` for branch deletion, but `_resolve_branch_name()` may have created `pipeline/{feature}-2`. Orphaned branches accumulate. This is a bug in #078's `claude/pipeline/worktree.py` — whether to fix it in #079 or a follow-on is a scoping decision for spec.

### Medium: Exit Code 1 Conflates Three Outcomes

`run_daytime()` returns 1 for deferred, paused, and failed. The skill must parse stdout to distinguish them. Document stdout parsing rules explicitly in implement.md.

### Medium: No Guard Against Daytime Invocation From Within a Worktree

If the user is inside `.claude/worktrees/agent-{slug}/` and invokes `/lifecycle implement`, the daytime option could fire against worktree-local artifacts. The `SKILL.md` branch prefix check (`^worktree/agent-`) should be extended to block the daytime option when running from within a worktree branch context.

### Low: State File Overwrite on Restart Loses Partial Progress

`build_config()` overwrites `daytime-state.json` on every invocation. Re-running after a kill re-executes all tasks. Document as known limitation (no overnight-style idempotency for daytime V1).

---

## Open Questions

1. **Blocking vs. background architecture**: Given the Bash tool 10-minute timeout, should the skill use background execution + polling (complexity: adds polling loop), fire-and-forget (simpler, but loses result surfacing), or a dedicated wrapper binary that tails progress? This fundamentally changes the implement.md §1d protocol design. **Deferred: to be resolved in Spec by asking the user.**

2. **`cleanup_worktree` `-2` suffix bug (scope)**: The `pipeline/{feature}-2` orphaned-branch issue is a bug in `claude/pipeline/worktree.py`, not in the skill layer. Should this be fixed as part of #079 (smallest safe fix: pass `worktree_info.branch` explicitly to `cleanup_worktree` in `run_daytime()`), or tracked as a separate follow-on ticket? **Deferred: to be resolved in Spec.**

3. **SKILL.md Step 2 update**: Should the `daytime.pid` check be added to SKILL.md Step 2 (Dispatching Marker Check) as a parallel guard, or handled entirely within implement.md's §1d path without modifying SKILL.md? Adding it to SKILL.md Step 2 would catch daytime-running state before any pre-flight prompt; handling it only in §1d is simpler but only fires if the user selects the daytime option. **Deferred: to be resolved in Spec.**
