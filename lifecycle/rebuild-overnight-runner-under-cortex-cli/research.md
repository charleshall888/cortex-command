# Research: Rebuild the overnight runner under a new `cortex overnight` CLI

## Epic Reference

Epic context: [research/overnight-layer-distribution/research.md](../../research/overnight-layer-distribution/research.md). That epic covers the full overnight-layer-distribution decomposition (tickets 112, 113, 114, 115, 116, 117, 120, and more). This research is scoped to ticket 115 only — the `cortex overnight` CLI rebuild. Epic content is referenced, not reproduced.

Scope anchor (from Clarify): Rebuild the overnight execution framework behind a `cortex overnight` CLI (`start`, `status`, `cancel`, `logs`) installed via `uv tool install -e .`, preserving all load-bearing guarantees from `runner.sh` and the full `requirements/pipeline.md` must-have surface, while resolving three deferred design forks in planning: bash-subprocess vs. pure-Python orchestration, path-resolution semantics under `uv tool install -e`, and orchestrator-round prompt-template path classification.

## Codebase Analysis

### Ticket body inventory vs. actual measurements

| Item | Ticket 115 body | Measured | Delta |
|------|-----------------|----------|-------|
| `runner.sh` line count | 1,362 | 1,694 | +24% — ticket body is stale; re-price estimates |
| Inline Python snippets in runner.sh | 50 | 50 verified (by line-range mapping below) | match |
| `REPO_ROOT` sites in runner.sh | 23 | verified (plus un-inventoried `CORTEX_COMMAND_ROOT` and `$PYTHONPATH` sites) | match |
| Atomic-write sites | 25 across 7 files | 25+ across 9 Python files + 15 inline in runner.sh | match |
| `set -m` process-group sites | 4 at lines 644, 649, 715, 725 | 4 at lines 640-644 (orchestrator), 645-646 (watchdog), 711-720 (batch_runner), 721-722 (batch watchdog) | match |
| `~/.claude/notify.sh` call sites | 13 | 13 plus 1 availability check in `report.py:1449` | match |
| Test migration scope | "~13,300 LOC across `cortex_command/overnight/tests/` + `cortex_command/pipeline/tests/`" | 14,680 LOC across those + 35 `runner.sh` references in top-level `tests/` (4 load-bearing test files: `test_runner_pr_gating.py`, `test_runner_signal.py`, `test_runner_resume.py`, `test_runner_followup_commit.py`, plus `test_runner_auth.sh`, plus `test_fill_prompt.py` which **sources `fill_prompt()` from runner.sh** — breaks if that function is extracted as a Fork-3 POC) | materially wider than ticket body |

### Current module inventory (`cortex_command/overnight/`, ~11,000 LOC)

| Module | LOC | Ownership |
|--------|-----|-----------|
| `report.py` | 1,618 | Morning report generation (markdown+HTML, async agent dispatch, metrics) |
| `backlog.py` | 1,130 | Backlog item reconciliation and status updates post-session |
| `outcome_router.py` | 1,122 | Route test/merge outcomes to recovery (conflict, merge-failure, review) |
| `feature_executor.py` | 758 | Dispatch feature agents, track execution, call outcome_router |
| `state.py` | 722 | `OvernightState` / `OvernightFeatureStatus` dataclasses, atomic persist |
| `plan.py` | 674 | Session plan generation, feature scheduling |
| `daytime_pipeline.py` | 574 | Daytime worker dispatch and result polling |
| `deferral.py` | 496 | Write deferred-question files atomically |
| `orchestrator.py` | 427 | Round-by-round feature selection and dispatch logic |
| `status.py` | 385 | Query session state for CLI status command |
| `auth.py` | 338 | OAuth token resolution via apiKeyHelper |
| `smoke_test.py` | 314 | Post-merge test verification |
| `events.py` | 283 | Structured JSONL event logging |
| `integration_recovery.py` | 274 | Recover from merge/test failures automatically |
| `throttle.py` | 271 | Concurrency limits and tier-based rate limiting |
| `brain.py` | 267 | Agent brain selection (Sonnet vs Opus escalation) |
| `map_results.py` | 257 | Process batch results and update state |
| `daytime_result_reader.py` | 252 | Parse daytime worker output |
| `batch_plan.py` | 176 | Generate batch task plan from orchestrator |
| `interrupt.py` | 164 | Reset interrupted features on session resume |
| `strategy.py` | 102 | Feature execution strategy selection |
| `orchestrator_io.py`, `constants.py`, `__init__.py` | 83 total | Exports / helpers |

`cortex_command/pipeline/` adds ~5,500 LOC across 10 modules (pipeline state, review dispatch, conflict resolution, post-merge sync, etc.) called by the overnight layer.

### Path resolution sites (`REPO_ROOT`, `CORTEX_COMMAND_ROOT`, `PYTHONPATH`)

Critical call sites in `runner.sh`:

| Line(s) | Usage |
|---------|-------|
| 26–32 | `REPO_ROOT` discovery (`git rev-parse --git-common-dir` with fallback to `$_SCRIPT_DIR/../..`) |
| 35–40 | `.venv` activation (`source "$REPO_ROOT/.venv/bin/activate"`) and `PYTHONPATH` export |
| 68 | `PROMPT_TEMPLATE="$REPO_ROOT/cortex_command/overnight/prompts/orchestrator-round.md"` |
| 123 | `OVERNIGHT_LIFECYCLE="$REPO_ROOT/lifecycle"` |
| 275, 490, 500 | `HOME_PROJECT_ROOT` / `TARGET_PROJECT_ROOT` derivation |
| 1451, 1513, 1631 | `REPO_ROOT` for report writing and git operations |

The `$_SCRIPT_DIR/../..` fallback is load-bearing. Under `uv tool install -e`, hatchling's PEP 660 editable install symlinks/hooks the source tree, so `$_SCRIPT_DIR` resolves inside the source repo and `../..` yields the repo root → `.venv/bin/activate` exists. **Under a non-editable wheel install, `$_SCRIPT_DIR` is inside site-packages; `../..` is site-packages itself; `.venv/bin/activate` does not exist; runner hard-aborts at line 35**. (See Adversarial Review for why this matters.)

### The 50 inline Python snippets in `runner.sh`

Each serves state/event I/O. Grouped by purpose:

- **State reads** (load phase, session-id, worktree, integration-branch, paused-reason, merged-count, round-number, flipped-once marker): lines 198, 209, 223, 266, 275–279, 285, 538–545, 605–612, 618–625, 754, 774–781, 794, 817–824, 857–864, 1135–1142, 1151–1158, 1164, 1228–1235, 1538–1545, 1602–1615
- **State writes** (paused transition, round increment, flipped-once marker, session metadata): 660–670, 817–824, 1282–1289, 1315–1343, 1338–1345, 1639–1646, 1675–1682
- **Event log appends** (session_started, feature_started, stall_timeout, orchestrator_started, session_paused, batch_plan, orchestrator_failed, circuit_breaker, session_complete, integration_recovery_complete, pr_created, session_ended): 233–243, 342–350, 353, 424–431, 460–466, 472–480, 490–523, 674–681, 872–879, 887–894, 929–936, 1384–1391, 1639–1646
- **Timestamp/elapsed parsing**: 399–406, 411–414
- **Prompt substitution `fill_prompt()`**: 366–375
- **Module invocations** (`python3 -m cortex_command.overnight.{auth, interrupt, batch_runner, map_results, integration_recovery}`): lines 50, 562, 712–719, 764, 919–926
- **PR body composition and metadata**: 1047–1054, 1059–1066, 1124–1131, 1315–1351, 1367–1374, 1421–1428, 1437–1451, 1472–1479, 1529–1536, 1569–1576

All snippets import from `cortex_command.overnight.*` — they rely on `PYTHONPATH=$REPO_ROOT` and the activated `.venv` having `cortex_command` importable. Both assumptions hold today only because cortex-command is developed-in-place. Under "tool installed against a different project," both break silently (see Adversarial #10).

### The 25+ atomic-write sites

**`cortex_command/overnight/`**:
- `state.py:397–435` (`save_state()`), `state.py:449–515` (`save_batch_result()`), `state.py:517–545` (`transition()`)
- `plan.py:547`, `orchestrator.py:255, 386, 397`, `outcome_router.py:1015`, `feature_executor.py:462`
- `map_results.py:144, 174`, `daytime_pipeline.py:239`, `interrupt.py:145`
- `deferral.py:162–186` (`O_CREAT | O_EXCL` loop — a separate atomic idiom for deferral question files)

**`runner.sh` inline** (all using tempfile + `os.replace` via `python3 -c` heredocs):
- Event log appends at 233–243, 353, 460–466, 472–480 (counts ~15 distinct state-write sites)
- `integration_pr_flipped_once` marker writes at 1282–1289, 1315–1343
- Session-ended metadata at 1639–1646

All 25+ sites use `tempfile + os.replace` semantics. This is a `requirements/pipeline.md:22` non-negotiable — partial-write corruption is not possible.

### The 4 `set -m` process-group sites

| Lines | Spawns | Tracked PID var | Watchdog |
|-------|--------|-----------------|----------|
| 640–644 | orchestrator (`claude -p "$FILLED_PROMPT"`) | `CLAUDE_PID` | yes (645–646, `WATCHDOG_PID`) |
| 711–720 | batch runner (`python3 -m cortex_command.overnight.batch_runner`) | `BATCH_PID` | yes (721–722, `BATCH_WATCHDOG_PID`) |

Each `set -m` + `&` job is placed in its own PGID. The cleanup trap at `runner.sh:518` (triggered by `trap cleanup SIGINT SIGTERM SIGHUP`, line 526) explicitly kills each PGID via `kill -- -$WATCHDOG_PID` / `kill -- -$BATCH_WATCHDOG_PID` (lines 651, 727). **These are grandchild PGIDs relative to a Python wrapper — not children of bash's own PGID**. A Python wrapper that naively SIGTERMs bash's PGID alone will leave orphans. (See Adversarial #6.)

### The 13 `~/.claude/notify.sh` call sites

| Line | Signal |
|------|--------|
| 514 | Session killed by signal |
| 671 | Orchestrator stalled (30+ min) |
| 746 | Batch runner stalled |
| 796 | No progress in 2 rounds |
| 1012 | Artifact commit failed |
| 1089 | Git push failed (feature branch) |
| 1114 | PR creation failed |
| 1147 | Integration branch push failed |
| 1173 | Zero-progress session (dry-run detect) |
| 1585 | Morning report push failed (home repo) |
| 1595 | Morning report push failed (target repo) |
| 1615 | Budget exhausted |
| 1617 | Session complete |

Plus `report.py:1449` availability check (`Path.home() / ".claude" / "notify.sh"`).

Post-ticket-117, `~/.claude/notify.sh` is machine-config's responsibility — cortex-command does not deploy it. The rebuild must decide: depend on machine-config (`|| true` fallback already present); provide local fallback when path missing; or route through a cortex-CLI mechanism (e.g., `cortex notify`). See Open Questions.

### `~/.claude/settings.json` `apiKeyHelper` coupling

- `auth.py:71–95` (`get_api_key_helper()`): reads `~/.claude/settings.json` or `~/.claude/settings.local.json`
- `auth.py:139–217` (`resolve_api_key()`): ANTHROPIC_API_KEY → apiKeyHelper → OAuth token
- `smoke_test.py:170–191`: availability check, logs to stdout
- `runner.sh:45–50`: documentation comment only (bash orchestrator does not read it directly; the `claude` CLI does)

Post-117, `settings.json` is user-owned. The rebuild must decide whether to keep reading the literal path or route through cortex-CLI config lookup.

### Orchestrator-round prompt template substitution (`runner.sh:362–376`, `fill_prompt()`)

Six substitutions:

| Placeholder | Source env var | Classification |
|-------------|---------------|----------------|
| `{state_path}` | `$STATE_PATH` = `lifecycle/sessions/{session_id}/overnight-state.json` | **user-repo-internal** |
| `{session_plan_path}` | `$PLAN_PATH` = `lifecycle/sessions/{session_id}/overnight-plan.md` | **user-repo-internal** |
| `{events_path}` | `$EVENTS_PATH` = `lifecycle/sessions/{session_id}/overnight-events.log` | **user-repo-internal** |
| `{session_dir}` | `$SESSION_DIR` = `lifecycle/sessions/{session_id}/` | **user-repo-internal** |
| `{round_number}` | `$ROUND_NUM` | scalar (not a path) |
| `{tier}` | `$TIER` | scalar (not a path) |

The template file itself (`cortex_command/overnight/prompts/orchestrator-round.md`) is **package-internal**. The filled prompt is piped to `claude -p` stdin; all paths inside it must resolve on the host filesystem.

### `--dry-run` mode

- Line 72: `DRY_RUN=""` init
- Lines 107–108: parse `--dry-run` flag
- Lines 593–594: reject `--dry-run` if pending features exist
- Lines 1027–1038: `dry_run_echo()` helper prints `DRY-RUN <label> <args...>`
- Lines 1173, 1196–1197, 1253–1280, 1312–1343, 1381: call sites using `dry_run_echo` or `DRY_RUN` conditional
- Lines 1258–1279: `DRY_RUN_GH_READY_SIMULATE` test-only failure simulation

Regression coverage at `tests/test_runner_pr_gating.py:159–169` invokes `bash cortex_command/overnight/runner.sh --dry-run --state-path <tmp>` directly; 11 subtests assert on DRY-RUN markers in stdout. This test's invocation form is a Fork-1 decision input — see Adversarial #4.

### Zero-merge PR draft / `integration_pr_flipped_once` marker

- `runner.sh:1231`: read marker from state
- `runner.sh:1280, 1287`: write marker = true after `gh pr ready --undo` (zero → draft)
- `runner.sh:1336, 1343`: write marker = true after `gh pr ready` (nonzero → ready)
- `state.py:229, 262, 392`: field definition and load
- `runner.sh:1179`: `[ZERO PROGRESS]` title prefix construction

`requirements/pipeline.md:26` names all three behaviors as must-have.

### Cortex CLI skeleton (ticket 114, shipped)

- `cortex_command/cli.py:49–54`: `overnight` subparser stub (currently raises "not yet implemented")
- `pyproject.toml`: `cortex = "cortex_command.cli:main"` entry point; build backend `hatchling>=1.27`; `[tool.hatch.build.targets.wheel] packages = ["cortex_command"]`

`[project.scripts]` entries trigger `uv tool install --force` requirements on change; **argparse subparsers under `cortex overnight` do not** — subcommand evolution is free. This is a point the tradeoffs-phase analysis initially missed and the adversarial pass corrected.

### Session directory layout

```
lifecycle/sessions/{session_id}/
├── overnight-state.json            # Main state (OvernightState), atomic writes
├── overnight-plan.md               # Round assignments
├── overnight-events.log            # JSONL event log (append-only)
├── overnight-strategy.json
├── session.json                    # Metadata
├── morning-report.md
├── batch-plan-round-*.md
├── batch-*-results.json
├── .runner.lock                    # Contains bare PID (runner.sh:332)
└── {feature_slug}/
```

`.runner.lock` today contains a bare PID. `bin/overnight-status:100–106` reads and `kill -0`-checks it. The adversarial pass surfaced this as insufficient for safe `cortex overnight cancel` (PID reuse, attacker-writable file, no start-time verification). See Open Questions.

`~/.local/share/overnight-sessions/active-session.json` (written at `runner.sh:476`) tracks **one** session at a time — not session-id-keyed. Multi-session hosts cannot look up "cancel this session" from this file alone.

### Dashboard state-file schema (must preserve)

Dashboard reads `lifecycle/overnight-state.json` and `lifecycle/sessions/{id}/overnight-state.json`. Fields consumed (inferred):

- `session_id`, `phase`, `current_round`
- `features: {name: {status, round_assigned, error, recovery_attempts}}`
- `started_at`, `updated_at`, `paused_reason`
- `integration_branch`, `integration_branches`
- `round_history: [{features_attempted, features_merged, features_paused, ...}]`
- `integration_pr_flipped_once`

Changing any field name or nesting structure without dashboard migration breaks observability silently. `requirements/observability.md:27,33,85` codifies dashboard-stays-unchanged.

### `bin/` shims to retire

- `bin/overnight-start` (69 lines): allocates tmux session, launches `bash runner.sh`, parses `--time-limit`/`--max-rounds`/`--tier`, verifies session live, prints attach commands
- `bin/overnight-status` (191 lines): discovers active session, `kill -0` liveness check, parses `overnight-state.json` and events log tail
- `bin/overnight-schedule`: **out of scope for 115** (ticket 112 migrates to LaunchAgents)

Their replacement by `cortex overnight start/status` is scoped in 115; `bin/overnight-schedule` retirement is 112's job.

### Files the rebuild will modify or create

**Create:**
- `cortex_command/overnight/cli_handler.py` (or integrate into existing modules) — `start`, `status`, `cancel`, `logs` handlers
- New entry-point wiring in `cortex_command/cli.py` for `overnight` subparser + four subparsers

**Modify:**
- `cortex_command/cli.py` — expand `overnight` stub
- `cortex_command/overnight/runner.sh` — Fork-1 choice determines whether it remains (wrapper invokes it), is partially extracted (hybrid), or is retired (pure-Python rewrite)
- `cortex_command/overnight/status.py` — make CLI-consumable
- `cortex_command/overnight/state.py` — add schema version field; optionally add PID/PGID/start-time fields (see Open Questions)
- `pyproject.toml` — ensure entry points, package data (shipping `runner.sh` as executable resource if Fork-1 Alt A)

**Retire:**
- `bin/overnight-start`, `bin/overnight-status`

**Test files affected (~14,680 LOC plus 35 `runner.sh` references in top-level `tests/`):**
- `tests/test_runner_pr_gating.py` — 11 subprocess dry-run tests
- `tests/test_runner_signal.py` — SIGHUP cleanup test (load-bearing for Fork 1)
- `tests/test_runner_resume.py:82` — hardwired `grep` on `runner.sh` source with `cwd=REAL_REPO_ROOT`
- `tests/test_runner_followup_commit.py`
- `tests/test_runner_auth.sh` — **verbatim line-range extract** from runner.sh; silently breaks on line-number shift
- `tests/test_fill_prompt.py` — **sources `fill_prompt()` from runner.sh**; breaks if Fork 3 POC extracts this function
- `cortex_command/overnight/tests/` (9,506 LOC) — mostly unchanged under Alt A; substantial rework under Alt B
- `cortex_command/pipeline/tests/` (5,174 LOC) — mostly unchanged

## Web Research

### `uv tool install -e` semantics and PEP 660 implications

- `uv tool install -e .` creates a tool-specific venv at `~/.local/share/uv/tools/<name>/`; the shim binary on `$PATH` is a thin Python entry point. Only entry points declared by the installed package are exposed. `pyproject.toml` changes to `[project.scripts]` require `uv tool install --force` to take effect ([uv docs](https://docs.astral.sh/uv/concepts/tools/)).
- PEP 660 editable installs use dynamic import hooks via a generated `__editable__.<pkg>.pth` file plus a `__editable__.<pkg>_finder.py` with a `MAPPING` dict ([PEP 660](https://peps.python.org/pep-0660/), [astral-sh/uv#3898](https://github.com/astral-sh/uv/issues/3898)). This is **not** legacy `egg-link`.
- PEP 660 explicitly warns: **`__path__` and `__file__` are not guaranteed to correspond to the source tree** under editable installs. `Path(__file__).parent` is fragile by spec. `importlib.resources.files("package")` is the canonical API — returns a real `PosixPath` under hatchling's `.pth`-backed editable, but may return `MultiplexedPath` or `Traversable` under other backends, which **has no `__fspath__`** and will silently stringify wrongly in `subprocess.run([bash, str(path)])`.
- Known bug: `importlib_resources.files()` raises `NotADirectoryError` under some editable-install finder paths ([python/importlib_resources#311](https://github.com/python/importlib_resources/issues/311)); fixed but the lesson is real — editable-install layout leaks into `importlib.resources` behavior.
- Hatchling (this repo's build backend) + `uv tool install -e` uses `.pth`-backed editable install today. File permissions on shipped data (like `runner.sh`) are preserved because the import hook points at source. **Under a non-editable wheel built from this `pyproject.toml`, `runner.sh` ships as a data file without the executable bit set** (no `[tool.hatch.build.targets.wheel.shared-data]` config). Invocation must always be `bash <path>`, never `./<path>`.

### Process-group management in Python (replacing `set -m` / `kill -- -$PID`)

- Python 3.11+: `subprocess.Popen(..., process_group=0)` for explicit `setpgid()`. Since 3.2: `start_new_session=True` for `setsid()`.
- `os.killpg(os.getpgid(p.pid), SIGTERM)` is exact equivalent of bash `kill -- -$PID`.
- Ruff `PLW1509` flags `preexec_fn=os.setsid` as thread-unsafe. Use `start_new_session=True` instead.
- Canonical escalation pattern: `.terminate()` → `.wait(timeout=N)` → `os.killpg(..., SIGKILL)`.
- macOS-specific edge case: once a PGID leader exits, `killpg` may return `ESRCH` even if other processes remain in the PGID (orphaned-process-group rules differ from Linux). The bash orchestrator's current cleanup trap assumes this.

### Signal handling prior art

Two mainstream patterns:

1. **Synchronous** ([Alexandra Zaharia](https://alexandra-zaharia.github.io/posts/stopping-python-systemd-service-cleanly/)): register `signal.signal(sig, handler)` per signal; handler flips a shutdown flag; main loop checks the flag.
2. **Asyncio** (roguelynn): `loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))` with late-binding fix; inside `shutdown`, gather-cancel with `return_exceptions=True`, then `loop.stop()`.

For critical-section shielding (atomic-write commit, PID-file cleanup): [wbenny/python-graceful-shutdown](https://github.com/wbenny/python-graceful-shutdown)'s `DelayedKeyboardInterrupt` context-manager pattern swaps a no-op handler in on enter, stashes any received signal, re-raises on exit.

### Atomic state writes

- Write to `NamedTemporaryFile(dir=target_dir, delete=False)` in the **same directory** (atomicity requires same filesystem). `os.fsync()` for durability. `os.replace(tmp, dest)` — atomic since Python 3.3, POSIX + Windows.
- Stdlib does not provide an `atomic_write()` helper; community package `python-atomicwrites` is unmaintained. A ~10-line helper is standard.

### Append-only JSONL

- One JSON object per line. Writers `open(mode='a')` + `flush()`. Readers either `f.seek(0, 2)` and poll, or track byte offset as cursor. `flush()` is load-bearing for readers tailing with byte-offset cursors.

### `logs --since` cursor protocols

| System | Cursor type | Trade-off |
|--------|-------------|-----------|
| `tail -f` | Byte offset (implicit) | Trivial; breaks on log rotation |
| `kubectl logs` | RFC3339 timestamp (`--since-time`) or duration (`--since=1h`) | Stateless; no resumption |
| `journalctl` | Opaque cursor token (`--cursor-file`) | Resumable; format private |
| supervisord RPC | Explicit `(offset, length)` with `overflow` flag | Cleanest "did I fall behind" protocol |

For a single-session overnight runner with no log rotation within a session, byte-offset with overflow flag is the lowest-friction choice; RFC3339 timestamp is simpler for users.

### start/status/cancel/logs CLI shape

- **supervisord**: supervisord daemon + supervisorctl client over XML-RPC UNIX socket. **Architectural lesson: split daemon from client from the start** — cancel semantics force the split anyway.
- **circus**: ZeroMQ-based; programmatic control + pub/sub events.
- **honcho/foreman**: Procfile-based, foreground dev-only; pluggable exporter (supervisord/systemd/upstart/runit).
- **daemoncmd / pid**: minimalist pidfile discipline — refuse to start if PID file exists and named process is alive; clean stale pidfiles if PID is dead.
- **start-stop-daemon**: `--make-pidfile --pidfile --start --exec` canonical pattern.

XDG conventions: `$XDG_STATE_HOME` (`~/.local/state`) for persistent state; `$XDG_RUNTIME_DIR` for PIDs/sockets (ephemeral). Cortex-command currently uses `~/.local/share/overnight-sessions/` — close enough to `$XDG_DATA_HOME` conventions.

### When to keep bash vs. rewrite

- `uv tool install -e` ships Python entry points, not bash scripts. A bash orchestrator can only be invoked *from* a Python entry point via `subprocess.run(["bash", "runner.sh", ...])`.
- **`python3 -c "..."` embedded in bash is the canonical anti-smell** — indicates either bash needs a data structure requiring Python, or the author wanted Python but started in bash. The refactor target is a proper Python module with a CLI entry point. ([Red Hat](https://www.redhat.com/sysadmin/python-subprocess-module), [ninjaaron](https://github.com/ninjaaron/replacing-bash-scripting-with-python).)
- The ninjaaron guide: past ~200 bash lines with inline Python, Python pays for itself; once you have inline Python, you're paying the abstraction cost twice.
- For a script the team *owns* whose complexity is already Python-shaped, the mainstream prior-art conclusion is a pure-Python rewrite. Bash-under-Python-wrapper is prior art for wrapping *opaque* (third-party) bash, not scripts the team owns.

### Anti-patterns from prior art

- `Path(__file__).parent` under editable installs (fragile by PEP 660).
- `preexec_fn=os.setsid` (Ruff PLW1509, thread-unsafe).
- `proc.terminate()` without `wait()` / zombie reaping.
- JSONL writes without `flush()` when readers tail via byte offset.
- Daemon-is-CLI-process coupling (supervisord/circus/systemd all split them).

### Key references

- [uv Tools docs](https://docs.astral.sh/uv/concepts/tools/)
- [PEP 660](https://peps.python.org/pep-0660/)
- [astral-sh/uv#3898 on PEP 660 finder](https://github.com/astral-sh/uv/issues/3898)
- [setuptools editable installs & importlib.resources caveat](https://setuptools.pypa.io/en/latest/userguide/development_mode.html)
- [python/importlib_resources#311](https://github.com/python/importlib_resources/issues/311)
- [importlib.resources stdlib docs](https://docs.python.org/3/library/importlib.resources.html)
- [Scientific Python: Including data files](https://learn.scientific-python.org/development/patterns/data-files/)
- [Simon Willison — uv CLI apps](https://til.simonwillison.net/uv/uv-cli-apps)
- [Python subprocess docs — start_new_session, process_group](https://docs.python.org/3/library/subprocess.html)
- [Ruff PLW1509](https://docs.astral.sh/ruff/rules/subprocess-popen-preexec-fn/)
- [wbenny/python-graceful-shutdown](https://github.com/wbenny/python-graceful-shutdown)
- [Supervisor XML-RPC API — log tail with offset/overflow](https://supervisord.org/api.html)
- [kubectl logs reference](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/)
- [journalctl cursor docs](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html)
- [ninjaaron/replacing-bash-scripting-with-python](https://github.com/ninjaaron/replacing-bash-scripting-with-python)

## Requirements & Constraints

### `requirements/pipeline.md` must-haves the rebuild must preserve

**Ticket 115's body names only 3 of these** (atomic writes, process-group management, signal-based shutdown). The remaining 15+ must-haves are pipeline.md-required preservation but absent from the ticket body — the spec phase must pull them into the preservation contract explicitly.

| Requirement | Source (pipeline.md line) | In ticket body? |
|-------------|--------------------------|-----------------|
| Atomic state writes (tempfile + `os.replace()`) | L22 | ✅ |
| Process-group management (4 `set -m` sites + `kill -- -$PID`) | implicit (L22-27) | ✅ |
| Signal-based shutdown (`trap cleanup SIGINT SIGTERM SIGHUP`) | implicit | ✅ |
| Forward-only phase transitions (`planning → executing → complete`, any → `paused`) | L22 | ❌ |
| Paused sessions resume from paused phase | L22 | ❌ |
| Integration branch persistence (not auto-deleted) | L22 | ❌ |
| Artifact commits on integration branch (not local main) | L23 | ❌ |
| Morning report commit exception (stays on local main) | L24 | ❌ |
| Budget exhaustion → paused without aborting in-flight | L25 | ❌ |
| Zero-merge draft PR with `[ZERO PROGRESS]` prefix | L26 | ❌ |
| `integration_pr_flipped_once` gate | L26 | ❌ |
| `--dry-run` mode rejects invocation with pending features | L27 | ❌ (flagged in Clarify) |
| Regression coverage at `tests/test_runner_pr_gating.py` | L27 | ❌ |
| Feature status lifecycle (pending/running/merged/paused/deferred/failed) | L36-37 | ❌ |
| Paused auto-retry on resume | L37 | ❌ |
| Deferred (human decision) — no auto-retry | L38 | ❌ |
| Fail-forward (one feature's failure doesn't abort others) | L40 | ❌ |
| `recovery_attempts` + `recovery_depth` counters | L41 | ❌ |
| Conflict fast-path (≤3 files, no hot files) | L49 | ❌ |
| Sonnet repair dispatch + Opus escalation (merge conflicts) | L50-52 | ❌ |
| Single-escalation cap (merge conflicts) — architectural constraint | L52 | ❌ |
| Test gate after any resolution | L54 | ❌ |
| Post-merge review gating matrix (complex any crit → review; simple high/crit → review; simple low/med → skip) | L63 | ❌ |
| `dispatch_review()` in `review_dispatch.py`; `batch_runner` owns events.log writes | L64 | ❌ |
| 2-cycle rework loop with `orchestrator-note.md` + SHA circuit breaker | L65 | ❌ |
| Non-APPROVED → deferred; deferral file for morning triage | L66 | ❌ |
| APPROVED → `review_verdict`, `phase_transition`, `feature_complete` events | L67 | ❌ |
| Flaky guard (re-merge with no feature changes) | L77 | ❌ |
| Test-failure repair: Sonnet → Opus, max 2 attempts — architectural constraint | L78-79 | ❌ |
| SHA circuit breaker (no new commits → immediate pause) | L80 | ❌ |
| Learnings log at `lifecycle/{feature}/learnings/progress.txt` | L81 | ❌ |
| Recovery outcome at `lifecycle/{feature}/recovery-log.md` | L82 | ❌ |
| Deferral files written atomically | L91 | ❌ |
| Blocking vs. non-blocking deferrals (with `default_choice`) | L92 | ❌ |
| Deferral file schema (severity/context/question/options/pipeline_action/default_choice) | L93 | ❌ |
| Post-session sync via `bin/git-sync-rebase.sh` with `sync-allowlist.conf` | L113 | ❌ |
| `--merge` PR strategy (load-bearing for `--theirs` rebase semantics) | L120 | ❌ |
| Orchestrator rationale convention (on non-obvious decisions) | L129 | ❌ |
| State file reads without locks (forward-only transitions are idempotent) | L133-134 | ❌ |
| Repair attempt cap (permanent architectural constraint) | L134 | ❌ |
| Integration branch persistence (permanent architectural constraint) | L135 | ❌ |

### `requirements/multi-agent.md` constraints

- Worktree isolation at `.claude/worktrees/{feature}/` (default) or `$TMPDIR/overnight-worktrees/{session_id}/{feature}/` (cross-repo) — permanent.
- Adaptive concurrency 1–3 agents; reduces on rate limits; restores on successes.
- Circuit breaker after 3 consecutive feature pauses.
- Fail-forward dispatch; `intra_session_blocked_by` filtered at round-planning time (orchestrator prompt), not dispatch time.
- Dual-layer prompt substitution contract: session-level single-brace `{token}` via bash `fill_prompt()`; per-feature double-brace `{{feature_X}}` substituted by orchestrator agent at dispatch time. **Single-layer prompts (batch-brain.md, repair-agent.md, pipeline prompts) remain single-brace.**
- Pre-deploy no-active-runner check (operator discipline only, no automated gate).
- Model matrix (trivial/simple/complex × low/medium/high/critical): base selection + escalation ladder (haiku → sonnet → opus; no downgrade); budget caps ($5/$25/$50); turn limits (15/20/30).
- `ConcurrencyManager` hard limit (not runtime-overridable).

### `requirements/observability.md` constraints

- Dashboard stays unchanged; reads `lifecycle/*` state within 7s.
- Statusline renders without error when no lifecycle feature active; <500ms latency.
- In-session status CLI inputs: `~/.local/share/overnight-sessions/active-session.json`, `lifecycle/sessions/{id}/overnight-state.json`, `lifecycle/sessions/{id}/.runner.lock`, `lifecycle/sessions/{id}/overnight-events.log`. Liveness via `kill -0` on PID from `.runner.lock`. Fallback to most recent session dir when active-session.json absent or shows `phase: complete`.

### `requirements/project.md`

- File-based state — permanent architectural constraint.
- Graceful partial failure — individual tasks may fail; system retries, hands off, or fails gracefully while completing the rest.
- Maintainability through simplicity — iteratively trim; navigable by Claude as it grows.
- Defense-in-depth for permissions — overnight uses `--dangerously-skip-permissions`; sandbox is critical security surface. (This raises the stakes on the `cortex overnight cancel` session-id validation — see Open Questions.)

### Scope boundaries

**115 must preserve**: all 25+ atomic writes; all 4 `set -m` + `kill -- -$PID` semantics; `trap cleanup SIGINT SIGTERM SIGHUP` contract; all 13 `notify.sh` sites; all 50 inline snippet behaviors (regardless of migration mechanism); all 23 `REPO_ROOT` + un-inventoried `CORTEX_COMMAND_ROOT` / `$PYTHONPATH` sites; `--dry-run` + `test_runner_pr_gating.py`; `integration_pr_flipped_once`; `[ZERO PROGRESS]` prefix; all repair caps; all concurrency constraints; post-merge sync; dashboard state-file schema.

**115 must retire**: `bin/overnight-start`, `bin/overnight-status` shims.

**115 must NOT touch**: MCP server / IPC contract implementation (ticket 116); LaunchAgents scheduler (ticket 112); dashboard code (stays); plugin distribution (ticket 120).

### Boundaries vs. adjacent tickets

- **vs. 114 (CLI skeleton, complete)**: 115 fills in the `cortex overnight` subparser stub.
- **vs. 117 (cortex setup, complete)**: 115 inherits the `~/.claude/*` deploy shape 117 established; `notify.sh` and `settings.json` are machine-config-owned.
- **vs. 116 (MCP control-plane server)**: **116 is `blocked_by: [115]`** (verified via `backlog/116-*.md` frontmatter). 116 requires 115's CLI subcommands to exist and requires a stable IPC contract (state `schema_version`, `runner.pid` for PID/PGID, cursor-based log tailing). **115 must design the IPC contract upfront** so 116 can build on it. See Adversarial #2.
- **vs. 112 (LaunchAgent scheduler)**: parked; lands after 115 on its new shape.

### Open decisions flagged in ticket body

1. `notify.sh` resolution strategy post-117: depend on machine-config with `|| true` fallback; local fallback when missing; or route through cortex-CLI mechanism.
2. `apiKeyHelper` reading: keep reading `~/.claude/settings.json` literal, or route through cortex-CLI config lookup.
3. Prompt-template path classification (Fork 3).

## Tradeoffs & Alternatives

### Fork 1 — bash-subprocess vs. pure-Python orchestration

**Alt A: Bash-as-subprocess wrapper.** Python CLI resolves host paths, sets env vars, locates `runner.sh` via `importlib.resources.files(...)`, and `subprocess.Popen(['bash', path, ...], start_new_session=True)`. `status`/`cancel`/`logs` are native Python reading session-dir artifacts and signalling the PID file.

- Pros: minimal rewrite; 14,680 LOC of tests survive with near-zero change *if they keep invoking bash directly*; mature bash process-group/signal code preserved; ships 115 fast; unblocks 116/112 (in naming); reversible.
- Cons: retains 50 inline snippet coupling; `importlib.resources.files()` + bash interop is fragile under non-editable installs (see Adversarial #1); runner's `$_SCRIPT_DIR/../..` fallback silently assumes editable-install layout; 1,694 lines of bash remain public debug surface; IPC contract for 116 is deferred, not designed; signal forwarding from Python wrapper to bash + grandchild PGIDs is non-trivial (Adversarial #6).

**Alt B: Pure-Python orchestration rewrite.** Reimplement `runner.sh` in `cortex_command/overnight/runner.py`. `asyncio.subprocess` + `start_new_session=True` + `os.killpg()` + `signal` handlers + `tempfile`+`os.replace`.

- Pros: eliminates bash; real tracebacks + `logging`; one language for the overnight layer; tight alignment with existing `cortex_command/*` idioms; path resolution trivial (no env-var handoff); designs the IPC contract cleanly from scratch — exactly what 116 needs; observability wins.
- Cons: largest rewrite (est. 800–1,100 Python lines replacing 1,694 bash); signal/PGID semantic drift risk is real (macOS vs. Linux orphaned-PGID rules differ); `test_runner_*.py` rewrites non-trivial; async-vs-sync is itself a load-bearing decision; 115 becomes XL+; delays 116/112 on calendar.

**Alt C: Hybrid — bash loop, extracted snippet modules.** Keep `runner.sh` as orchestration loop + signal/PGID boss; replace 50 inline snippets with `python3 -m cortex_command.overnight.snippets.*` invocations.

- Pros: reduces bash/Python coupling materially; snippets become unit-testable; preserves mature bash signal code.
- Cons: per-snippet `python3 -m` cold-start overhead (~100–300ms × 50+ invocations per round = 5–30s of pure startup latency; acceptable for overnight but not free); two-language maintenance continues; doesn't solve the 1,694-line bash debug-surface complaint; same install-mode fragility as Alt A.

**Alt D: Alt A now, migrate snippet-by-snippet later.** Ship Alt A; follow-up tickets extract snippets; eventually Alt B.

- Pros: fastest ship for 115.
- Cons: **Adversarial #5 rebutted this approach specifically for this repo**: "later" migrations in this repo's history have always been argued re-tickets, never automatic follow-through. After 116 builds on Alt A's incidental contract, migrating to Alt B becomes strictly harder (116's assumptions become a consumer lock-in). No forcing function exists.

| Alt | Impl complexity (inverse) | Maintainability | Performance | Pattern alignment | IPC contract for 116 |
|-----|---------------------------|-----------------|-------------|-------------------|---------------------|
| A (bash wrapper) | 5 | 2 | 4 | 2 | 1 (deferred) |
| B (pure Python) | 1 | 5 | 4 | 5 | 5 (designed) |
| C (hybrid) | 3 | 3 | 3 (snippet overhead) | 3 | 2 |
| D (A-now, B-later) | 5 now / 2 total | 2→5 | 4 | 2→5 | 1 (deferred, locked-in) |

### Fork 2 — path resolution under `uv tool install -e`

**Alt A: editable-install location shortcut.** `importlib.resources.files('cortex_command').parent` walk-up to find `pyproject.toml` / `.git`.

- Pros: zero config; works today.
- Cons: install-mode dependent; silent breakage risk under wheel or alternate build backend.

**Alt B: `importlib.resources` for package-internal only; user-repo paths explicit from CLI.**

- Pros: install-mode independent; CLI is the single site of host-path resolution; all `REPO_ROOT` sites become consumers of CLI-injected env; testable.
- Cons: requires touching every `$REPO_ROOT/lifecycle/...` site in runner.sh to receive env values; CLI needs auto-discovery heuristic (replicate `_auto_discover_state` logic at 122–163).

**Alt C: Explicit config + env var.** `CORTEX_COMMAND_ROOT` + `~/.cortex/config.toml` set by `cortex setup` / `cortex init`.

- Pros: no magic; debuggable.
- Cons: user setup burden; silent failure on stale env.

**Alt D: cwd / session-dir discovery.**

- Pros: matches user mental model.
- Cons: ambiguous under cross-repo sessions (home vs. target).

| Alt | Impl complexity (inverse) | Maintainability | Performance | Pattern alignment |
|-----|---------------------------|-----------------|-------------|-------------------|
| A (editable shortcut) | 5 | 2 | 5 | 2 |
| B (resources + explicit) | 3 | 5 | 5 | 5 |
| C (env var / config) | 4 | 4 | 5 | 3 |
| D (cwd / session-dir) | 4 | 2 | 5 | 2 |

### Fork 3 — prompt template path classification

**Alt A: All paths resolve to absolute host paths; CLI passes them in.**
**Alt B: Prompt template loaded via `importlib.resources`; substitution + `claude -p` handoff in Python.**
**Alt C: Explicit split — package-internal via `importlib.resources`, user-repo via absolute host paths.**

Alt B and Alt C are functionally identical; Alt C differs only in framing.

| Alt | Impl complexity (inverse) | Maintainability | Performance | Pattern alignment |
|-----|---------------------------|-----------------|-------------|-------------------|
| A (all host paths) | 5 | 3 | 5 | 3 |
| B/C (resources + host split) | 4 | 5 | 5 | 5 |

### Cross-cutting: cancel best-effort mechanism

- **Repurpose `.runner.lock`** (recommended by tradeoffs agent): write PID at start; cancel reads, `kill -0`, `os.killpg()`. **Adversarial #3 invalidates this without additional schema** — bare PID is vulnerable to PID reuse, stale locks, and attacker-writable-file scenarios. Required enhancements: include `pgid`, `start_time`, `schema_version`, `session_id`, and a magic sentinel (`"cortex-runner-v1"`); verify start-time before signalling; `0o600` permissions.
- **`pgrep` discovery**: fragile; PID reuse risk; doesn't distinguish sessions.
- **LaunchAgent (ticket 112)**: best long-term answer; not available for 115.

### Cross-cutting: `--dry-run` preservation

- **Under Alt A**: `cortex overnight start --dry-run` passes through to `bash runner.sh --dry-run`. Tests like `test_runner_pr_gating.py:162` keep calling `bash cortex_command/overnight/runner.sh` directly — works **only under editable install**. **Adversarial #4**: `test_runner_resume.py` hardwires `grep` on runner.sh source (breaks under non-editable), `test_runner_auth.sh` extracts a verbatim line range (breaks on any line shift), `test_fill_prompt.py` sources `fill_prompt()` from runner.sh (breaks if Fork-3 POC extracts the function). "One-line test change" is misleading; 5–10 test files need structural edits.
- **Under Alt B**: `--dry-run` becomes a Python CLI flag; orchestration short-circuits round-spawning. Tests rewrite to call `cortex overnight start --dry-run` or use a Python API directly (eliminates subprocess, speeds tests). Honest rewrite cost — but eliminates editable-install coupling.
- **Under Alt C**: identical to Alt A for `--dry-run`; snippet extraction is orthogonal.

### Recommended approach (revised after Adversarial Review)

**The tradeoffs-phase recommendation was Alt A for Fork 1. The Adversarial pass substantially undermined this**:

1. Alt A silently assumes editable-install-only (non-editable install breaks at `runner.sh:35`).
2. The IPC contract 116 requires is deferred, not designed — 116 would be building on accidental bash-incidental contract.
3. `.runner.lock` cancel mechanism has PID-reuse race + attacker-writable-file security issue unrequired by today's use but exposed once `cortex overnight cancel <sid>` is a published CLI.
4. Signal forwarding from Python wrapper to bash + grandchild PGIDs is non-trivial and incompletely specified in Alt A.
5. `test_runner_*.py` changes are 5–10 structural edits, not "one line".
6. Inline `python3 -c` snippets silently break the moment cortex-command is used as a tool against a different project (the entire point of ticket 113/115).

**Net**: Alt A is shippable but requires the following to be non-optional, not best-effort:

- PID file schema (`{pid, pgid, start_time, schema_version, session_id, magic}`) — serves both cancel safety and 116's IPC contract.
- State file `schema_version` field — serves 116.
- Log cursor protocol choice documented (recommend byte-offset with rotation token) — serves 116.
- Session-id validation regex + `realpath` containment — security.
- Explicit CLI-side override of `REPO_ROOT`, `PYTHONPATH`, `CORTEX_COMMAND_ROOT` — install-mode independence within reason.
- Signal forwarding: Python wrapper installs SIGTERM/SIGINT/SIGHUP handlers that forward to bash's PGID *and* to the 4 grandchild PGIDs (read from state or maintained by the wrapper).
- Test migration: explicit structural fixes to `test_runner_resume.py`, `test_runner_auth.sh`, `test_fill_prompt.py` (if Fork-3 POC extracts `fill_prompt()`) — not "one-line".
- Fork 3 POC (extracting `fill_prompt()`) is contingent on updating `test_fill_prompt.py` in the same patch.
- A follow-up ticket for the pure-Python rewrite (Alt B) must be filed before 115 merges, with acknowledgement that 116's consumption of Alt A's contract makes Alt B strictly harder later.

**With these guardrails in place, Alt A is defensible. Without them, Alt B becomes the lower-risk choice** despite its larger rewrite — precisely because Alt B forces the IPC contract and install-mode independence to be designed, not inherited.

The spec phase must decide: does the user accept the non-optional guardrails on top of Alt A, or prefer Alt B's cleaner-but-larger rewrite? See Open Questions.

**Fork 2 recommendation: Alt B** (unchanged) — `importlib.resources` for package-internal, explicit paths from CLI for user-repo. Install-mode independent.

**Fork 3 recommendation: Alt B/C** (unchanged) — package-internal prompt loaded via `importlib.resources`; user-repo paths absolute from CLI. The POC extraction of `fill_prompt()` is contingent on updating `test_fill_prompt.py`.

**Cancel: PID file with full schema** (`{pid, pgid, start_time, schema_version, session_id, magic}`), validated session-id, `realpath` containment, start-time re-verification before signalling, `0o600` permissions.

**Dry-run**: Preserve regression coverage at `tests/test_runner_pr_gating.py` with whatever migration path Fork 1 dictates; accept that `test_runner_resume.py`, `test_runner_auth.sh`, and possibly `test_fill_prompt.py` need structural edits under any option.

## Adversarial Review

1. **`runner.sh` is 1,694 lines, not 1,362** — ticket body is stale by ~25%. Re-price estimates.

2. **Alt A silently depends on editable-install layout.** Under a non-editable wheel built from the current `pyproject.toml`: (a) `runner.sh` ships without the executable bit (no `shared-data` hatch config); (b) `$_SCRIPT_DIR/../..` points at site-packages, where `.venv/bin/activate` does not exist → runner aborts at line 35; (c) `importlib.resources.files()` may return `MultiplexedPath` (no `__fspath__`) that silently stringifies wrongly in `subprocess`. Alt A works today only because `uv tool install -e` + hatchling + editable happens to collapse all three issues. If any dimension changes, silent breakage.

3. **IPC contract for 116 is deferred, not designed, under Alt A.** 116 is `blocked_by: [115]` because 116 requires `lifecycle/overnight-state.json` to have a `schema_version`, `runner.pid` to have defined PID/PGID/start-time fields, and a cursor-based log tail protocol to exist. Alt A's "ship fast with bash incidentals" delivers none of these. Unless 115 commits to designing these in-scope, 116 either has to take on the contract-design work (scope expansion) or build MCP tooling on accidental contract.

4. **`.runner.lock` repurpose has a live PID-reuse race.** Scenario: runner crashes without clearing lock → PID N reused by unrelated process → `cortex overnight cancel <session-id>` → reads lock → `kill -0 N` succeeds → `os.killpg(os.getpgid(N), SIGTERM)` → nukes unrelated process's PGID (e.g., npm install, or the user's shell session tree). Current lock file is bare PID; required enhancement: `{pid, pgid, start_time, schema_version, session_id, magic}` with start-time verification.

5. **`.runner.lock` attacker-writable scenario**: session directory has 644 permissions; if any shared path or multi-user host exposes it, an attacker can overwrite the lock with `1` (init PID). `cortex overnight cancel` would then `killpg(getpgid(1), SIGTERM)` — SIGTERMs init (blocked on macOS by SIP; real risk on Linux). Required: `0o600` permissions + magic sentinel verification.

6. **Signal forwarding under Python-wraps-bash is non-trivial.** The 4 `set -m` sites create **grandchild PGIDs** — siblings under bash's session, not children of bash's PGID. A Python wrapper that SIGTERMs bash's PGID alone leaves orphans. Explicit forwarding to each grandchild PGID (`CLAUDE_PID`, `BATCH_PID`, `WATCHDOG_PID`, `BATCH_WATCHDOG_PID`) is required. Python must also not close bash's stdout/stderr before bash's cleanup trap writes its final state.

7. **Hatchling wheel doesn't set executable bits on `runner.sh` automatically** — no `shared-data` or equivalent in `pyproject.toml`. The wrapper must always `bash <path>`, never `./<path>`. Document this commitment in the spec.

8. **Cross-session concurrency**: two overnight sessions on different repos on the same host have no shared PID registry; `~/.local/share/overnight-sessions/active-session.json` tracks one session at a time. Second session overwrites the pointer; cancel of the first can't find it. Required: session-id → repo-root registry, or walk all `lifecycle/sessions/*/` across known roots.

9. **Path-traversal / security.** `cortex overnight cancel <session-id>` takes a user-provided arg. Without validation: `cortex overnight cancel "../../../etc"` resolves to a traversal; `cortex overnight cancel "; rm -rf ~"` if ever passed to a shell. Required: strict regex validation (`^[a-zA-Z0-9._-]{1,128}$`) + `realpath` containment check.

10. **Env var shadowing**: users with pre-existing `REPO_ROOT` / `PYTHONPATH` in their shell. Alt A doesn't specify override behavior. Silent data loss if overwrite is wrong.

11. **Inline `python3 -c` PATH resolution**: under "cortex-command installed as tool against a different project," `$REPO_ROOT` becomes the other project → `PYTHONPATH=<other project>` → `cortex_command` not importable → inline imports fail. Today this is hidden because dev and consumption are the same repo.

12. **`[project.scripts]` uninstall/reinstall churn does NOT apply** to argparse subparsers under `cortex overnight`. Subcommand evolution is free. This was initially flagged as a concern; adversarial verification confirmed it's a non-issue for 115.

13. **Test-migration count understated**. 35 `runner.sh` references in top-level `tests/`. Structural edits needed (beyond one-line path changes): `test_runner_resume.py` (hardwired source grep), `test_runner_auth.sh` (verbatim line range), `test_fill_prompt.py` (sources the function — breaks under Fork-3 POC).

14. **"Alt A now, Alt B later" has no forcing function in this repo's history**. Every prior "later" migration has been an argued new ticket, not automatic follow-through. 116 building on Alt A's contract makes Alt B strictly harder, not easier.

## Open Questions

Items the spec phase must resolve (most require user decision; some can be research-phase-resolved further):

1. **Fork 1 final choice (Alt A with guardrails vs. Alt B).** The tradeoffs agent recommended Alt A; the adversarial pass showed Alt A is defensible only with mandatory guardrails (PID schema, state schema_version, log cursor protocol, signal forwarding, install-mode override, test structural fixes, follow-up ticket). Without those, Alt B is the lower-risk choice. The user must decide whether to accept the guardrails on Alt A or pay Alt B's rewrite cost.

2. **IPC contract design (for 116).** Regardless of Fork-1 choice, 115 must ship: state `schema_version` field + read-side compat policy; PID file JSON schema (`{pid, pgid, start_time, schema_version, session_id, magic}`); log cursor protocol choice (byte-offset with rotation token vs. RFC3339 timestamp vs. opaque). Proposed default: byte-offset-with-overflow-flag (supervisord-style), documented in the spec. Confirm with user.

3. **`notify.sh` resolution strategy post-117.** Options: (a) depend on machine-config with `|| true` fallback; (b) provide local fallback (stdout/no-op); (c) route through `cortex notify` subcommand. Proposed default: (a) + (b) — keep `|| true` fallback, add a stdout fallback when the path is absent so runs in minimal environments don't lose notifications entirely.

4. **`apiKeyHelper` reading.** Options: keep `~/.claude/settings.json` literal read (brittle but simple); route through cortex-CLI config lookup. Proposed default: keep literal — 117 made this user-owned; adding a CLI lookup would re-introduce indirection the ticket retired.

5. **Install-mode support.** Does 115 commit to editable-install-only (explicitly documented) or must support non-editable wheel installs? The latter materially expands work: CLI must inject `REPO_ROOT` unconditionally; `runner.sh` cannot rely on self-discovery; `.venv` activation can't assume `$REPO_ROOT/.venv`. Proposed default: editable-install-only for 115; file a follow-up ticket for wheel-install support.

6. **Cross-session registry.** Does 115 ship host-wide `cortex overnight cancel <session-id>` that discovers sessions across projects, or scope cancel to sessions discoverable from the current cwd? Proposed default: current cwd only + explicit session-path flag (`--session-dir <path>`). Host-wide registry is a follow-up.

7. **Fork-3 POC scope.** Does 115 extract `fill_prompt()` as a proof-of-concept snippet migration (updating `test_fill_prompt.py` in the same patch), or defer all snippet extraction to post-115? Proposed default: yes, extract `fill_prompt()` — it's the cleanest target, de-risks Fork 3, and establishes the pattern. Required: update `test_fill_prompt.py` atomically.

8. **Pure-Python rewrite follow-up.** Should 115 file a follow-up backlog item for the eventual pure-Python rewrite now (so there's a named successor and 116 knows what's coming) or treat 115 as terminal? Proposed default: file the follow-up in-scope for 115 — the adversarial pass surfaced that repo history shows no forcing function without a named ticket.

9. **Signal-forwarding strategy under Alt A.** Exact mechanism the wrapper uses to track the 4 grandchild PGIDs (read from state file that runner.sh writes on spawn? wrapper-maintained registry via stderr protocol?). Proposed default: runner.sh writes PGIDs to `$SESSION_DIR/.runner.pgids.json` atomically as each PGID is created; wrapper reads on signal and forwards. Confirm.

10. **`test_runner_auth.sh` verbatim line-range extract.** Fragile under any line shift. Should 115 take on restructuring this test to use a semantic marker (e.g., `# AUTH_BLOCK_BEGIN` / `# AUTH_BLOCK_END` fences in runner.sh), or leave fragile? Proposed default: add the fences in 115 and update the test extractor.

11. **Budget exhaustion and paused-auto-retry preservation checklist.** `requirements/pipeline.md` lists 30+ must-haves that ticket 115's body does not name. Does the spec phase want a line-by-line preservation checklist in spec.md (verbose but authoritative) or a reference-only "preserve everything in pipeline.md" clause (tight but weaker)? Proposed default: line-by-line checklist — the ticket-body vs. pipeline.md gap is material.

12. **Deferred research: non-editable wheel install.** Not resolving this blocks any future wheel-install ticket. Proposed default: deferred to follow-up ticket per #5. Confirm user preference.
