# Research: Build daytime pipeline module and CLI

**Backlog**: [078-build-daytime-pipeline-module-and-cli](../../backlog/078-build-daytime-pipeline-module-and-cli.md)
**Date**: 2026-04-14
**Phase**: Research

## Epic Reference

Background context lives in `research/implement-in-autonomous-worktree-overnight-component-reuse/research.md` (the #074 epic research). This ticket implements Phase 5 of that epic — the thin daytime driver that consumes `feature_executor` and `outcome_router` after their extraction in #075 and #076.

---

## Codebase Analysis

### Files that will be created or modified

**New files:**
- `claude/overnight/daytime_pipeline.py` (~150–200 LOC) — the driver module and CLI entry point

  > **Note**: The backlog item says `claude/lifecycle/daytime_pipeline.py`, but `claude/lifecycle/` does not exist as a Python module directory. The correct home is `claude/overnight/`, alongside `feature_executor.py` and `outcome_router.py`. The CLI invocation `python3 -m cortex_command.overnight.daytime_pipeline` replaces the backlog's proposed `python3 -m claude.lifecycle.daytime_pipeline`.

**Possibly modified:**
- `claude/overnight/feature_executor.py` — only if deferral namespacing (DR-4) is implemented (see Open Question #1)
- `claude/overnight/outcome_router.py` — only if deferral namespacing or OutcomeContext interface changes are needed
- `claude/overnight/tests/test_daytime_pipeline.py` — new unit tests (mocking feature_executor / outcome_router)
- `hooks/cortex-cleanup-session.sh` — only if a new worktree prefix is chosen (see Open Question #3)

### Actual interfaces of the modules being consumed

**`feature_executor.execute_feature` (line 345–354):**
```python
async def execute_feature(
    feature: str,
    worktree_path: Path,
    config: BatchConfig,
    spec_path: Optional[str] = None,
    manager: Optional[ConcurrencyManager] = None,
    consecutive_pauses_ref: Optional[list[int]] = None,
    repo_path: Path | None = None,
    integration_branches: dict[str, str] | None = None,
) -> FeatureResult
```
`manager` and `consecutive_pauses_ref` can be `None` — the function defaults gracefully. `repo_path=None` means "default repo" (main checkout). All daytime-optional fields are truly optional.

**`outcome_router.apply_feature_result` (line 760–774):**
```python
async def apply_feature_result(
    name: str,
    result: FeatureResult,
    ctx: OutcomeContext,
) -> None
```

**`OutcomeContext` dataclass (lines 64–78):**
```python
@dataclass
class OutcomeContext:
    batch_result: BatchResult
    lock: asyncio.Lock
    consecutive_pauses_ref: list[int]
    recovery_attempts_map: dict[str, int]
    worktree_paths: dict[str, Path]
    worktree_branches: dict[str, str]
    repo_path_map: dict[str, Path | None]
    integration_worktrees: dict[str, Path]
    integration_branches: dict[str, str]
    session_id: str
    backlog_ids: dict[str, int | None]
    feature_names: list[str]
    config: BatchConfig
```

For a single-feature daytime run: `consecutive_pauses_ref=[0]`, `integration_worktrees={}`, `integration_branches={}`, `feature_names=[feature]`, `repo_path_map={feature: None}`. Construction is ~15 lines with no I/O. The circuit-breaker threshold is 3 — a single pause will not trigger it.

### CLI pattern to mirror (`batch_runner.py:408–456`)
```python
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python3 -m cortex_command.overnight.batch_runner", ...)
    p.add_argument("--plan", required=True)
    p.add_argument("--batch-id", type=int, required=True)
    p.add_argument("--events-path", default="lifecycle/sessions/latest-overnight/overnight-events.log")
    ...
    return p

def _run() -> None:
    args = build_parser().parse_args()
    config = BatchConfig(...)
    asyncio.run(run_batch(config))

if __name__ == "__main__":
    _run()
```

### CWD constraint — critical operational requirement

`feature_executor` and `outcome_router` build all `lifecycle/{feature}/` paths as bare relative paths (e.g., `Path(f"lifecycle/{feature}/plan.md")`). None are derived from an absolute base or from `config`. Similarly, `escalations_path = Path("lifecycle/escalations.jsonl")` is hardcoded relative in both modules. The daytime CLI **must be launched from the repo root** or all artifact I/O silently fails or creates files in wrong locations.

The CLI should enforce this at startup: check that `lifecycle/` exists in CWD, and abort with a clear error if not.

### Events.log path threading

Events are written via `log_event()` from `events.py` using `config.overnight_events_path` (from `BatchConfig`). This path IS threaded through config — it is not hardcoded. Passing an absolute `--events-log-path` via CLI and using it to construct `BatchConfig` is the correct approach and will work for the daytime case. The path should be passed as an absolute value (derived from `Path.cwd() / "lifecycle/{feature}/events.log"` at CLI startup).

### Deferral — implementation gap vs DR-4

`write_deferral()` in `deferral.py` defaults to `DEFAULT_DEFERRED_DIR = Path("deferred")`. Both `feature_executor.py` and `outcome_router.py` call it at every deferral site using that default — neither accepts nor passes a custom deferral directory. Implementing DR-4 (per-feature `lifecycle/{feature}/deferred/`) requires either:
- Patching call sites in `feature_executor` and `outcome_router` (overnight-code change; violates zero-regression constraint unless tests cover all paths)
- Accepting shared `deferred/` at repo root (violates DR-4 but avoids overnight-code change)
- Post-write relocation: the daytime CLI moves files from `deferred/` to `lifecycle/{feature}/deferred/` after `apply_feature_result` returns

This is an Open Question for spec. See OQ-1.

### Overnight state file dependency

`feature_executor` calls `load_state(config.overnight_state_path)` to check prior conflict events. On file-not-found it swallows the error and sets `_skip_repair = True`. For daytime use, there is no overnight session state file. The function degrades silently — conflict recovery is disabled. The daytime driver should either:
- Synthesize a minimal state JSON at the path before calling `execute_feature`
- Pass a path to a nonexistent file and accept the silent skip

### Worktree management

Current pattern (from `claude/pipeline/worktree.py`):
- **Path**: `.claude/worktrees/{feature}/`
- **Branch**: `pipeline/{feature}` (with `-2`, `-3` collision suffixes)
- **Cleanup**: `cleanup_worktree(feature)` — idempotent; `git worktree remove --force` + `git worktree prune` + branch delete

The `cortex-cleanup-session.sh` hook only cleans `worktree/agent-*` branches (lifecycle Agent tool worktrees). `pipeline/{feature}` branches are NOT cleaned by this hook — they persist until `apply_feature_result` calls `cleanup_worktree` on the happy path. On crash (SIGKILL), these worktrees remain.

### `_backlog_dir` global state

`outcome_router.py` has `set_backlog_dir(path)` which sets a module-global `_backlog_dir`. For overnight with multi-repo features, `run_batch` calls this before dispatching. For daytime, it is never called — backlog write-backs default to the repo's own `backlog/` directory. This is probably correct but should be documented.

---

## Web Research

### Subprocess lifecycle patterns

**PID file stale detection:**
```python
def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
```
`os.kill(pid, 0)` raises `errno.ESRCH` if dead, `PermissionError` if alive-but-not-owned. This is the canonical pattern. PID files are not cleaned by SIGKILL (atexit handlers don't run) — stale detection is the recovery mechanism.

**Orphan prevention — macOS specific:**
- Linux: `prctl(PR_SET_PDEATHSIG, SIGTERM)` via `preexec_fn` — not available on macOS
- macOS: child polls `os.getppid() == 1` (reparented to launchd indicates parent died). Simple, pure-Python, good enough for this use case.
- `pyprctl` library wraps `prctl` but is Linux-only

**asyncio subprocess:**
```python
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    start_new_session=True,  # own process group for killpg
)
stdout, stderr = await proc.communicate()  # safe: no deadlock
```
`start_new_session=True` enables `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` to kill the entire process tree. Never use `await proc.wait()` + `stdout=PIPE` together — deadlocks when pipe buffer fills.

**SIGKILL recovery sequence:**
```python
# In main repo CWD
if (worktree_path / ".git" / "MERGE_HEAD").exists():
    subprocess.run(["git", "merge", "--abort"], cwd=worktree_path, check=False)
for lock in worktree_path.rglob("*.lock"):
    lock.unlink(missing_ok=True)
subprocess.run(["git", "worktree", "remove", "--force", "--force", str(worktree_path)], check=False)
subprocess.run(["git", "worktree", "prune"], check=False)
```
`git worktree remove --force` alone may fail on locked worktrees; `--force --force` (double-force) removes regardless.

**Anti-patterns:**
- `preexec_fn` is thread-unsafe in multi-threaded parents — use `start_new_session=True` instead where possible
- `git -C <path>` is prohibited by project sandbox rules; use `cwd=` parameter
- `shell=True` with `os.killpg` kills the shell, not the child command

---

## Requirements & Constraints

### Relevant requirements

**requirements/project.md:**
- Simplicity is preferred; complexity must earn its place
- All state uses plain files (markdown, JSON, YAML); no database
- File-based state is the architectural baseline

**requirements/pipeline.md:**
- Feature statuses: `pending → running → merged` (success); `running → paused` (recoverable); `running → deferred` (human decision required); `running → failed` (unrecoverable)
- Deferral files must include severity, context, question, options considered, pipeline action attempted, optional default choice
- Repair attempt cap is a fixed architectural constraint (Sonnet → Opus escalation for merge conflicts; 2 attempts max for test failures)
- All state writes must be atomic (tempfile + `os.replace()`)

**requirements/multi-agent.md:**
- Worktree naming: `pipeline/{feature}` branches with `-2`, `-3` collision detection
- Default repo worktrees at `.claude/worktrees/{feature}/`
- Permission mode is always `bypassPermissions` for pipeline agents

**lifecycle.config.md:**
- Test command: `just test`
- Commit artifacts: true

### Hard constraints on this ticket

1. **Zero regression on overnight behavior** — scope explicitly excludes changes to `batch_runner.py`, `orchestrator.py`, or any overnight test behavior
2. **CWD must equal repo root** — all path construction in consumed modules is CWD-relative
3. **Events.log to main repo CWD** (DR-3) — not inside the daytime worktree
4. **Test gate + auto-revert on merge failure** — must match overnight's acceptance behavior
5. **Worktree + branch cleanup on exit** — success or failure; orphaned state must be recoverable

---

## Tradeoffs & Alternatives

### Module location

| Option | Pros | Cons |
|--------|------|------|
| `claude/overnight/daytime_pipeline.py` | Sibling to consumed modules; clean import path; consistent with batch_runner.py | "overnight/" name is slightly misleading for a daytime tool |
| `claude/lifecycle/daytime_pipeline.py` (backlog item) | Semantically "lifecycle tool" | Directory doesn't exist as Python module; requires cross-package imports |

**Decision**: `claude/overnight/daytime_pipeline.py`. The backlog item's path is incorrect — `claude/lifecycle/` is not a Python package.

### Worktree prefix

| Option | Pros | Cons |
|--------|------|------|
| `pipeline/{feature}` (existing pattern) | No hook changes; already handled by `create_worktree()`; cleanup works today | Hook won't clean on session kill (same as overnight — pre-existing gap) |
| `worktree/daytime-*` (new prefix) | Clear semantic distinction; enables daytime-specific hook cleanup | Requires modifying `cortex-cleanup-session.sh` and `cortex-worktree-create.sh`; adds scope |
| `worktree/agent-*` (lifecycle pattern) | Session-kill hook already cleans these | Ambiguous with lifecycle Agent worktrees; potential collision |

**Recommended**: `pipeline/{feature}` — reuse the existing create_worktree/cleanup_worktree path, accept the same cleanup gap that overnight has. Adding a new prefix is additional scope that the zero-regression constraint makes risky; the gap can be addressed in a later ticket.

### Events.log path

**Recommended**: CLI `--events-log-path` argument (absolute path). The daytime CLI derives the absolute path at startup: `Path.cwd() / f"lifecycle/{feature}/events.log"`. This path is passed into `BatchConfig.overnight_events_path`. The CWD enforcement guard (check that `lifecycle/` exists) ensures the path is correct.

### OutcomeContext construction

**Recommended**: Construct `OutcomeContext` directly with single-feature defaults. The 12-field dataclass is ~15 lines of construction code with no I/O. The unused fields (`integration_worktrees={}`, `integration_branches={}`) are genuinely no-ops for the daytime case. Add a comment documenting which fields are semantically unused.

### Brain-triage

**Recommended**: Inherit from `feature_executor` unchanged. Brain dispatch is ~15–30s; daytime overall latency is already 30+ min for any real feature. The consistency benefit outweighs the marginal time cost. Add an `--no-brain` flag for users who want fast-fail behavior without a separate code path.

---

## Adversarial Review

### DR-4 (per-feature deferral namespace) conflicts with zero-regression constraint

`write_deferral()` defaults to `DEFAULT_DEFERRED_DIR = Path("deferred")` — a CWD-relative path. Both `feature_executor` and `outcome_router` call it with this default at every deferral site. Implementing DR-4 without touching those files requires a post-write relocation strategy: the daytime driver moves files from `deferred/{feature}-q*.md` to `lifecycle/{feature}/deferred/` after `apply_feature_result` returns. This is fragile (files could accumulate in shared `deferred/` if the driver crashes). Alternatively, DR-4 can be implemented by passing `deferred_dir` into a thin wrapper that calls the existing functions, but that requires touching `feature_executor` and `outcome_router`. Spec must resolve this (OQ-1).

### `escalations_path` is hardcoded relative — not in config

Unlike `overnight_events_path`, `escalations_path = Path("lifecycle/escalations.jsonl")` is hardcoded inside `feature_executor` and `outcome_router` at the call sites. The CWD enforcement guard (check `lifecycle/` exists in CWD) is the only mitigation — if CWD is wrong, escalations land in the wrong directory. There is no config field to override this today.

### Concurrent daytime + overnight — no inter-process locking on main

`asyncio.Lock()` in `OutcomeContext` is process-local. If overnight and daytime both call `merge_feature()` concurrently into the same `base_branch`, there is no file-level coordination. Two concurrent fast-forward merges can succeed in sequence but with incorrect ordering, or one will fail with `fatal: Not possible to fast-forward`. Spec must address this: either document the limitation and prohibit concurrent use, or implement a lock-file (`lifecycle/.merge-lock`) checked before and released after each merge.

### SIGKILL recovery — PID file must be written before worktree creation

If the daytime CLI is killed after creating the worktree but before writing the PID file, stale detection fails. The PID file must be written before any worktree creation so recovery code can always find it. Design: write PID file → create worktree → run feature → cleanup worktree → remove PID file.

### `load_state` silently disables conflict recovery for daytime

`feature_executor` calls `load_state(config.overnight_state_path)` at line 369. If the file doesn't exist, the exception is swallowed and `_skip_repair = True` — conflict recovery is permanently disabled for this run. The daytime CLI must synthesize a minimal state JSON (with at minimum an empty `features` dict and a valid `session_id`) and write it to `config.overnight_state_path` before calling `execute_feature`. Otherwise merge conflicts in the daytime worktree will not trigger repair agents.

### macOS orphan prevention — polling cadence

The recommended macOS approach (`os.getppid() == 1`) requires a polling loop in the subprocess. If polling cadence is too slow (e.g., 5-second intervals), the subprocess may continue running for up to 5 seconds after the parent dies — leaving git operations mid-flight. Recommended cadence: 1 second, running in a background asyncio task inside the subprocess.

---

## Open Questions

- **OQ-1 (DR-4 deferred namespacing)**: Per-feature `lifecycle/{feature}/deferred/` requires either (a) modifying `feature_executor`/`outcome_router` call sites, (b) post-write file relocation by the daytime driver, or (c) accepting shared `deferred/` at repo root. Option (a) touches overnight code; option (b) is fragile if the driver crashes; option (c) violates the backlog spec. **Spec must choose.** Deferred: will be resolved in Spec by asking the user.

- **OQ-2 (Concurrent daytime + overnight)**: Should the daytime CLI enforce mutual exclusion with overnight via a lock file? Or should this be a documented limitation ("do not run daytime and overnight simultaneously")? Deferred: will be resolved in Spec by asking the user.

- **OQ-3 (Budget caps and `_ALLOWED_TOOLS`)**: Should daytime agents use the same budget and tool allowlist as overnight (`["Read","Write","Edit","Bash","Glob","Grep"]`), or should daytime allow additional tools (e.g., `WebFetch`)? The epic research mentions this as a spec-time decision. Deferred: will be resolved in Spec.

- **OQ-4 (Minimal overnight-state.json for conflict recovery)**: Does the daytime driver synthesize a minimal state file to keep conflict recovery active, or is silently-disabled conflict recovery acceptable for the V1? Deferred: will be resolved in Spec.
