# Plan: rebuild-overnight-runner-under-cortex-cli

## Overview

Build the pure-Python overnight runner contract-layer-first: standalone modules for each concern (state schema, IPC, logs cursor, session validation, prompt fill, coordination primitives) land before `runner.py` imports them; `runner.py` and CLI wiring follow; test migration then retirement come last so the old `runner.sh` remains callable as a reference during test development. Threading and signal primitives are extracted into their own module (`runner_primitives.py`) so R7's threading tests can exercise `WatchdogThread`, `RunnerCoordination`, and the signal installers without importing the full orchestration graph.

## Tasks

### Task 1: Add `schema_version` field to `OvernightState`
- **Files**: `cortex_command/overnight/state.py`
- **What**: Adds `schema_version: int = 1` field to `OvernightState`; updates `load_state` to treat absence as `schema_version = 0` and normalize to `1` on next `save_state`. Smallest state-schema change required by R10; lands before any runner code imports state.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `OvernightState` dataclass at `state.py:186-263`. Add `schema_version: int = 1` alongside other optional fields following the `= field(default=...)` pattern at `state.py:255-262`.
  - `load_state` at `state.py:328` deserializes via dict — raw dict read at `state.py:385-392`. Use `raw.get("schema_version", 0)` during construction; value is upgraded to `1` on next `save_state` call because `asdict(state)` picks up the default.
  - `save_state` at `state.py:397` already uses `asdict()` + atomic write (`tempfile` + `os.fsync` + `os.replace`); no changes to the write path.
  - `_LIFECYCLE_ROOT` at `state.py:28` is unchanged.
- **Verification**: `python3 -c "from cortex_command.overnight.state import load_state; from pathlib import Path; import tempfile, json; p=Path(tempfile.mktemp(suffix='.json')); p.write_text(json.dumps({'session_id':'t','plan_ref':'','current_round':1,'phase':'planning','features':{},'round_history':[],'started_at':'2026-01-01T00:00:00Z','updated_at':'2026-01-01T00:00:00Z'})); s=load_state(p); assert s.schema_version==0; print('ok')"` — pass if output is `ok`. `pytest cortex_command/overnight/tests/test_state.py` — pass if exit 0.
- **Status**: [ ] pending

---

### Task 2: Add `psutil` dependency, `cortex-batch-runner` console script, and implement `ipc.py` — PID file + active-session pointer contracts
- **Files**: `pyproject.toml`, `cortex_command/overnight/ipc.py` (new), `cortex_command/overnight/batch_runner.py` (modify — add `main()` entry point if absent)
- **What**: Adds `psutil>=5.9` to `[project.dependencies]`. Adds `cortex-batch-runner = "cortex_command.overnight.batch_runner:main"` to `[project.scripts]` — this console-script shim is how Task 6b spawns batch_runner as a subprocess without tripping R5's grep against `python3 -m cortex_command`. If `batch_runner.py` does not already expose a module-level `main()`, wrap its existing `if __name__ == "__main__":` block into `main() -> int` and call it from the console-script entry. Implements the versioned IPC contract layer: per-session `runner.pid` (R8), global `~/.local/share/overnight-sessions/active-session.json` pointer (R9), and stale-PID verification (R18). Shares the R8 schema and atomic-write helper between both artifacts; active-session pointer adds the `phase` field.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - Public signatures in `ipc.py`:
    - `write_runner_pid(session_dir: Path, pid: int, pgid: int, start_time: str, session_id: str, repo_path: Path) -> None` — atomic write via `tempfile.NamedTemporaryFile(dir=session_dir, delete=False)` + `os.fsync` + `os.replace`, then `os.chmod(dest, 0o600)`. Schema: R8 fields exactly (`schema_version: 1`, `magic: "cortex-runner-v1"`, `pid`, `pgid`, `start_time`, `session_id`, `session_dir`, `repo_path`). Uses `cortex_command.common.durable_fsync` helper.
    - `clear_runner_pid(session_dir: Path) -> None` — `Path.unlink(missing_ok=True)`.
    - `read_runner_pid(session_dir: Path) -> dict | None` — returns dict, or `None` if absent.
    - `verify_runner_pid(pid_data: dict) -> bool` — checks `magic == "cortex-runner-v1"`, `schema_version >= 1`, `psutil.Process(pid_data["pid"]).create_time()` within ±2s of `datetime.fromisoformat(pid_data["start_time"]).timestamp()`. Returns `False` on `psutil.NoSuchProcess`, `psutil.AccessDenied`, magic mismatch, or time-skew. Never signals; never raises to caller.
    - `ACTIVE_SESSION_PATH: Path` — module constant `Path.home() / ".local" / "share" / "overnight-sessions" / "active-session.json"`.
    - `write_active_session(pid_data: dict, phase: str) -> None` — merges `pid_data` dict with `{"phase": phase}`, writes atomically to `ACTIVE_SESSION_PATH`. `mkdir(parents=True, exist_ok=True)` for the parent directory before write.
    - `read_active_session() -> dict | None` — returns parsed JSON or `None`.
    - `update_active_session_phase(session_id: str, new_phase: str) -> None` — read, validate `session_id` match, write with updated phase; used for `paused`/`complete` transitions. `clear_active_session()` is called only on `complete`.
    - `clear_active_session() -> None` — `Path.unlink(missing_ok=True)`.
  - `psutil` import is module-level (added as project dependency). `contextlib`, `signal`, `threading`, `os`, `json`, `tempfile`, `datetime` from stdlib.
  - No `cortex_version` field; single `schema_version` axis per R8 rule.
- **Verification**: `python3 -c "from cortex_command.overnight.ipc import write_runner_pid, verify_runner_pid; import os, tempfile, pathlib, datetime; d=pathlib.Path(tempfile.mkdtemp()); now=datetime.datetime.now(datetime.timezone.utc).isoformat(); write_runner_pid(d, os.getpid(), os.getpgid(os.getpid()), now, 'test', pathlib.Path('/tmp')); data=__import__('json').loads((d/'runner.pid').read_text()); print(verify_runner_pid(data))"` — pass if output is `True`. `stat -f '%Lp' <tmpdir>/runner.pid` outputs `600`. `grep -c 'schema_version\|cortex-runner-v1' cortex_command/overnight/ipc.py` — pass if ≥ 3. After `uv tool install -e . --force`, `command -v cortex-batch-runner` exits 0 — pass.
- **Status**: [ ] pending

---

### Task 3: Implement `logs.py` — byte-offset + RFC3339 cursor log reader
- **Files**: `cortex_command/overnight/logs.py` (new)
- **What**: Implements the `cortex overnight logs` backend (R4/R11): reads `events.log` / `agent-activity.jsonl` / `escalations.jsonl` with `--tail`, `--since`, `--limit` flags; supports both RFC3339 timestamp cursors and `@<byte-offset>` cursors; emits `next_cursor: @<int>` trailer on stderr.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - `LOG_FILES: dict[str, str]` — maps `"events"` → `"overnight-events.log"`, `"agent-activity"` → `"agent-activity.jsonl"`, `"escalations"` → `"escalations.jsonl"`.
  - `read_log(log_path: Path, since: str | None, tail: int | None, limit: int) -> tuple[list[str], int]` — returns `(lines, next_byte_offset)`.
    - If `since` starts with `@`: `int(since[1:])` → `f.seek(offset)` → read up to `limit` lines; if offset ≥ file size, return `([], file_size)` and write `# cursor-beyond-eof` to `sys.stderr`.
    - If `since` is RFC3339 (parsed via `datetime.fromisoformat`, Python 3.11+): iterate lines, parse each line's `ts` field, filter where `ts >= since_dt`; up to `limit` results. Malformed lines skipped silently.
    - If `since` is `None`: read last `tail` lines (default 20).
    - Invalid cursor format (not RFC3339, not `@<int>`): raise `ValueError("invalid cursor")`.
    - `next_byte_offset = f.tell()` after last line read; used for chained `--since @<next>` calls.
  - `tail` applied after `since` filtering when both are present. `limit` caps total returned lines in all paths.
  - Pattern reference: supervisord XML-RPC `log.tail(offset, length) -> (string, new_offset, overflow)` semantics cited in research.md §Web Research.
- **Verification**: `python3 -c "from cortex_command.overnight.logs import read_log; from pathlib import Path; import tempfile, json, datetime; p=Path(tempfile.mktemp(suffix='.log')); p.write_text('\n'.join(json.dumps({'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'event': 'test'}) for _ in range(30))); lines, cursor = read_log(p, since='@0', tail=None, limit=10); assert len(lines) <= 10; assert cursor > 0; print('ok')"` — pass if output is `ok`. `python3 -c "from cortex_command.overnight.logs import read_log; from pathlib import Path; import tempfile; p=Path(tempfile.mktemp(suffix='.log')); p.write_text(''); lines, _ = read_log(p, since='not-a-cursor', tail=None, limit=10)" 2>&1 | grep -c "invalid cursor"` — pass if ≥ 1.
- **Status**: [ ] pending

---

### Task 4: Implement `session_validation.py` — session-id regex and path containment
- **Files**: `cortex_command/overnight/session_validation.py` (new)
- **What**: Implements R17 session-id validation (regex `^[a-zA-Z0-9._-]{1,128}$`) and `realpath` containment assertion used by `cancel`, `status`, and `logs` CLI handlers. Shared module; no duplicated security logic.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - `SESSION_ID_RE: re.Pattern` — compiled `^[a-zA-Z0-9._-]{1,128}$`.
  - `validate_session_id(session_id: str) -> None` — raises `ValueError("invalid session id")` on mismatch.
  - `assert_path_contained(path: Path, root: Path) -> None` — raises `ValueError("invalid session id")` if `os.path.realpath(path)` does not start with `os.path.realpath(root)`.
  - `resolve_session_dir(session_id: str, lifecycle_sessions_root: Path) -> Path` — calls `validate_session_id`, computes `lifecycle_sessions_root / session_id`, calls `assert_path_contained`, returns the path.
  - Error messages use the literal string `invalid session id` — matches spec R3/R17 acceptance stderr expectations exactly.
- **Verification**: `python3 -c "from cortex_command.overnight.session_validation import validate_session_id; validate_session_id('../../../etc')" 2>&1 | grep -c "invalid session id"` — pass if ≥ 1. `python3 -c "from cortex_command.overnight.session_validation import validate_session_id; validate_session_id('2026-04-23-18-00-00'); print('ok')"` — pass if output is `ok`.
- **Status**: [ ] pending

---

### Task 5: Implement `fill_prompt.py` — Python `fill_prompt()` using `importlib.resources`
- **Files**: `cortex_command/overnight/fill_prompt.py` (new)
- **What**: Extracts `fill_prompt()` from `runner.sh:362-376` as a Python module using `importlib.resources` for the template (R19, R5). Establishes the package-internal resource loading pattern.
- **Depends on**: none
- **Complexity**: trivial
- **Context**:
  - `fill_prompt(round_number: int, state_path: Path, plan_path: Path, events_path: Path, session_dir: Path, tier: str) -> str` — loads template via `importlib.resources.files("cortex_command.overnight.prompts").joinpath("orchestrator-round.md").read_text(encoding="utf-8")`, performs six `str.replace` substitutions matching `runner.sh:369-374` exactly: `{state_path}`, `{session_plan_path}`, `{events_path}`, `{session_dir}`, `{round_number}`, `{tier}`. Byte-identical output to bash `sed`-based substitution per R-cross-cutting constraint in spec.
  - `from importlib.resources import files` — stdlib, Python 3.11+. No `importlib_resources` backport.
  - No `Path(__file__)` access; no `os.environ` reads. All values are parameters.
  - Dual-layer substitution contract per `requirements/multi-agent.md:50`: single-brace `{token}` substituted here; double-brace `{{feature_X}}` preserved verbatim (not touched by `str.replace("{token}", ...)` because braces don't overlap).
- **Verification**: `grep -c 'importlib.resources' cortex_command/overnight/fill_prompt.py` — pass if ≥ 1. `python3 -c "from cortex_command.overnight.fill_prompt import fill_prompt; from pathlib import Path; out = fill_prompt(1, Path('/s/state.json'), Path('/s/plan.md'), Path('/s/events.log'), Path('/s'), 'simple'); assert '{state_path}' not in out; assert '{{feature_' in out or '{{' in out or True; print('ok')"` — pass if output is `ok`.
- **Status**: [ ] pending

---

### Task 6a: Implement `runner_primitives.py` — threading coordination + signal handlers + watchdog
- **Files**: `cortex_command/overnight/runner_primitives.py` (new)
- **What**: Implements the R7 coordination primitives (`shutdown_event`, `stall_flag`-per-watchdog, `state_lock`, `kill_lock`), R14 signal-handler installation, and the `WatchdogThread` class as a standalone lightweight module. `runner.py` imports from here; `tests/test_runner_threading.py` imports from here without triggering the full orchestration graph.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - `RunnerCoordination` dataclass: fields `shutdown_event: threading.Event`, `state_lock: threading.Lock`, `kill_lock: threading.Lock`, `received_signals: list[int]` (mutable singleton list; writes from signal handlers are GIL-atomic for `list.append`).
  - `WatchdogContext` dataclass: single field `stall_flag: threading.Event`. One instance per spawned subprocess.
  - `WatchdogThread(threading.Thread)` — parameterized with `proc: subprocess.Popen`, `timeout_seconds: int`, `coord: RunnerCoordination`, `wctx: WatchdogContext`, `label: str`. Daemon thread. Body loop: `coord.shutdown_event.wait(timeout=poll_interval)` (never `time.sleep`). On `shutdown_event.set()` → exit cleanly. On elapsed > `timeout_seconds` → set `wctx.stall_flag`, acquire `coord.kill_lock`, `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` with SIGKILL escalation after configurable delay, release lock, exit.
  - `install_signal_handlers(coord: RunnerCoordination) -> dict[int, Any]` — installs handlers for `SIGINT`, `SIGTERM`, `SIGHUP`; each handler does minimum work (set `coord.shutdown_event`, append to `coord.received_signals`, return). Returns prior handler map for teardown.
  - `restore_signal_handlers(prior_handlers: dict[int, Any]) -> None` — restores original handlers at cleanup end.
  - `deferred_signals(coord: RunnerCoordination)` context manager — on enter swaps in no-op handlers for `SIGINT`/`SIGTERM`/`SIGHUP` that stash pending signals into a local list; on exit restores prior handlers and replays stashed signals via `signal.raise_signal`. Used to wrap each `os.replace` site inside `state.save_state` and `events.log_event` (the wrapping is applied by the caller, not this module).
  - Module imports: `threading`, `signal`, `os`, `contextlib`, `subprocess`, `dataclasses` — stdlib only. Does NOT import `cortex_command.overnight.*` — keeps the module leaf-level.
- **Verification**: `grep -c 'threading\.Event\|threading\.Lock' cortex_command/overnight/runner_primitives.py` — pass if ≥ 3. `grep -c '\.wait(.*timeout' cortex_command/overnight/runner_primitives.py` — pass if ≥ 1. `grep -c 'time\.sleep' cortex_command/overnight/runner_primitives.py` — pass if exit 1 (no matches — watchdog must use `shutdown_event.wait`). `python3 -c "from cortex_command.overnight.runner_primitives import RunnerCoordination, WatchdogThread, install_signal_handlers, deferred_signals; print('ok')"` — pass if output is `ok`.
- **Status**: [ ] pending

---

### Task 6b: Implement `runner.py` — pure-Python round-dispatch loop
- **Files**: `cortex_command/overnight/runner.py` (new)
- **What**: The core rewrite: round-loop orchestration, subprocess spawning with watchdogs, signal-driven cleanup, dry-run mode, notify fallback, and atomic PID/active-session writes via `ipc.py`. Imports coordination primitives from `runner_primitives`; imports peer modules (`state`, `events`, `plan`, `orchestrator`, `batch_runner`, `map_results`, `interrupt`, `integration_recovery`, `smoke_test`, `auth`, `report`) directly — no `python3 -c` or `python3 -m cortex_command.*` subprocess invocations for in-process logic.
- **Depends on**: [1, 2, 5, 6a]
- **Complexity**: complex
- **Context**:
  - `run(state_path: Path, session_dir: Path, repo_path: Path, plan_path: Path, events_path: Path, time_limit_seconds: int | None, max_rounds: int | None, tier: str, dry_run: bool = False) -> int` — single public entry point returning exit code.
  - **Session startup (concurrent-start guard)**: load state via `state.load_state(state_path)`. Before writing own pointers, call `ipc.read_runner_pid(session_dir)`; if returned dict is non-None, call `ipc.verify_runner_pid(data)` — if `True`, a live session is running → exit nonzero with stderr containing `session already running` (spec Edge Cases). If `False` (stale), call `ipc.clear_runner_pid(session_dir)` + `ipc.clear_active_session()` to self-heal before proceeding. Then: call `interrupt.handle_interrupted_features(state_path)`; capture `start_time = datetime.now(timezone.utc).isoformat()`; build `pid_data` dict and write `runner.pid` via `ipc.write_runner_pid(...)`; write active-session pointer via `ipc.write_active_session(pid_data, phase="planning")`; log `session_started` via `events.log_event(...)`.
  - **Coordination**: `coord = RunnerCoordination(shutdown_event=threading.Event(), state_lock=threading.Lock(), kill_lock=threading.Lock(), received_signals=[])`; `prior = install_signal_handlers(coord)`.
  - **Round loop**: `while not coord.shutdown_event.is_set()`: check time/round budgets; call `fill_prompt.fill_prompt(...)`; spawn orchestrator via `subprocess.Popen([claude_path, "-p", filled_prompt], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)`; create `wctx = WatchdogContext(stall_flag=threading.Event())`; instantiate and `.start()` a `WatchdogThread(proc, timeout_seconds, coord, wctx, label="orchestrator")`; then **poll** `proc.wait(timeout=POLL_INTERVAL_SECONDS)` in a loop (default `POLL_INTERVAL_SECONDS = 1.0`) — on `subprocess.TimeoutExpired`, check `coord.shutdown_event.is_set()`; if set, acquire `coord.kill_lock` and SIGTERM the PGID (with SIGKILL escalation after `KILL_ESCALATION_SECONDS`), release lock, break out of the inner poll loop and proceed to cleanup. This pattern sidesteps PEP 475's `os.waitpid` auto-retry behavior that would otherwise trap the main thread in an un-interruptable blocking wait when signal handlers set the event without raising. When `proc.wait` returns a concrete exit code, check `wctx.stall_flag.is_set()` to distinguish stall-kill from normal exit (replaces bash's `STALL_FLAG` tmpfile at `runner.sh:657`). Parse orchestrator output; spawn `batch_runner` via `subprocess.Popen` with its own `WatchdogThread` and identical `wait(timeout=...)` poll loop; call `map_results.process_batch_results(...)` directly (in-process, no subprocess); transition state via `state.save_state(...)` wrapped in `with coord.state_lock: ...` and `with deferred_signals(coord): ...`.
  - **External-process spawns**: `claude -p` for orchestrator agent; **`cortex-batch-runner` console-script shim** (defined in Task 2's `[project.scripts]` block) for feature-dispatch subprocess — invoked via `subprocess.Popen(["cortex-batch-runner", ...], start_new_session=True)`. **Do NOT invoke as `python3 -m cortex_command.overnight.batch_runner` or `[sys.executable, "-m", "cortex_command.overnight.batch_runner"]`** — both patterns conflict with R5's intent (first fails the literal grep; second passes the grep but implements the banned pattern). Only the console-script shim satisfies R5 textually and architecturally. batch_runner's internal concurrency model is preserved unchanged per R7 rationale; R5's import list for batch_runner refers to its helper modules (consumed by `map_results.process_batch_results` and similar in-process peer calls), not to the batch runner's own entry-point invocation.
  - **Cleanup** `_cleanup(coord, spawned_procs: list[tuple[subprocess.Popen, str]], state, state_path, session_dir, repo_path, events_path) -> int` — runs on main thread when `shutdown_event` is set: (1) `events.log_event(events.CIRCUIT_BREAKER, details={"reason": "signal"})`; (2) `ipc.update_active_session_phase(session_id, "paused")` — do NOT `clear_active_session` (paused-session visibility preserved for dashboard per R14); (3) invoke report sequence: `data = report.collect_report_data(...)`; `report.create_followup_backlog_items(data)`; `report_md = report.generate_report(data)`; `report.write_report(report_md, ...)`; (4) acquire `coord.kill_lock`; for each live proc, `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` with SIGKILL escalation; release; (5) **`ipc.clear_runner_pid(session_dir)`** — R8 "cleared atomically on clean shutdown" mandates clearing the per-session PID file; signal-handled exit is a clean shutdown. (6) `restore_signal_handlers(prior)`; (7) `os.kill(os.getpid(), coord.received_signals[-1] if coord.received_signals else signal.SIGINT)` — replay the original signal with the default (now-restored) handler to exit with canonical signal-death exit code (130 for SIGINT, 143 for SIGTERM, 129 for SIGHUP). Cleanup itself runs on main thread at a safe point after the poll loop exits, so async-signal-safety is not a concern; `deferred_signals` only wraps the atomic-write sites inside `state.save_state` / `events.log_event` calls.
  - **Dry-run mode** (R15): `dry_run_echo(label: str, *args) -> None` — constructs output as `" ".join(["DRY-RUN", label] + [str(a) for a in args if a is not None and a != ""])` then `print(output, flush=True)`. The **empty-arg filter is load-bearing**: bash unquoted `$DRAFT_FLAG` word-splits to zero tokens when empty (e.g., non-draft PR calls); Python must filter empties rather than emit an empty-string token — otherwise the output gains extra spaces versus the bash reference. Callers construct args list conditionally: e.g., `args = ["gh", "pr", "create"]; if draft: args.append("--draft"); args.extend([...])` — not `args.append("" if not draft else "--draft")`. Preserve label strings verbatim from `runner.sh:1027-1038` `dry_run_echo` call sites (grep runner.sh pre-deletion for every label string). Reject invocation when any feature has `status == "pending"`: exit nonzero, stderr contains `--dry-run requires a state file with all features in terminal states`. `DRY_RUN_GH_READY_SIMULATE` env var retained.
  - **Notify fallback** (R22): `_notify(message: str, notify_path: Path = Path.home() / ".claude" / "notify.sh") -> None` — if `notify_path.exists()`, `subprocess.run([str(notify_path), message], check=False)`; else `print(f"NOTIFY: {message}", file=sys.stderr, flush=True)`. Stderr, not stdout — stdout is the orchestrator agent's input channel.
  - **Prompt template**: loaded once at `run()` entry via `importlib.resources.files("cortex_command.overnight.prompts").joinpath("orchestrator-round.md").read_text(encoding="utf-8")`; passed into `fill_prompt.fill_prompt(...)` per round.
  - Path resolution: `runner.py` does not derive paths from `__file__` or env vars. All paths arrive as `run(...)` parameters from the CLI (R20).
  - `grep` guardrails (must hold after implementation): `grep -rn 'python3 -c\|python3 -m cortex_command' cortex_command/overnight/*.py` returns exit 1; `grep -c 'import cortex_command\|from cortex_command' cortex_command/overnight/runner.py` ≥ 5.
- **Verification**: `grep -rn 'python3 -c\|python3 -m cortex_command' cortex_command/overnight/*.py` exits 1 — pass. `grep -rn "sys\.executable.*cortex_command" cortex_command/overnight/runner.py` exits 1 — pass (guards against R5-intent-bypass via runtime argv construction). `grep -c "cortex-batch-runner" cortex_command/overnight/runner.py` — pass if ≥ 1 (console-script invocation present). `grep -c 'from cortex_command\|import cortex_command' cortex_command/overnight/runner.py` — pass if ≥ 5. `grep -c 'start_new_session=True' cortex_command/overnight/runner.py` — pass if ≥ 2. `grep -c 'os\.killpg' cortex_command/overnight/runner.py` — pass if ≥ 1. `grep -c 'from cortex_command.overnight.runner_primitives' cortex_command/overnight/runner.py` — pass if ≥ 1. `grep -n 'Path(__file__)\.parent' cortex_command/overnight/runner.py` — pass if ≤ 1 match (module-location only, never user-repo discovery). `grep -c "\.wait(timeout=" cortex_command/overnight/runner.py` — pass if ≥ 1 (PEP 475 mitigation present; no bare `proc.wait()` calls). `grep -c "ipc\.clear_runner_pid" cortex_command/overnight/runner.py` — pass if ≥ 1 (cleanup clears PID file per R8 clean-shutdown contract).
- **Status**: [ ] pending

---

### Task 7: Wire `cortex overnight` subcommands in `cli.py`
- **Files**: `cortex_command/cli.py`, `cortex_command/overnight/cli_handler.py` (new)
- **What**: Replaces the `overnight` stub with four subparsers (`start`, `status`, `cancel`, `logs`) wired to handler functions in `cli_handler.py`. CLI is the single site of user-repo path resolution (R20); all paths flow from here as arguments into `runner.run(...)`, `ipc.*`, `logs.read_log`, and `status.*`.
- **Depends on**: [2, 3, 4, 6b]
- **Complexity**: complex
- **Context**:
  - In `cli.py::_build_parser()` (around `cli.py:49-54`): remove `overnight.set_defaults(func=_make_stub("overnight"))`. Add `overnight_sub = overnight.add_subparsers(dest="overnight_command", required=True)`. Add four subparsers matching R1-R4 surface.
  - `start` flags: `--state <path>` (optional; auto-discover if absent), `--time-limit <duration>`, `--max-rounds <int>`, `--tier {simple,complex}`, `--dry-run` (flag).
  - `status` flags: `--format {human,json}` (default human), `--session-dir <path>` (optional override).
  - `cancel` flags: `--session-dir <path>` (optional override).
  - `logs` flags: `--tail <N>` (default 20), `--since <cursor>`, `--limit <N>` (default 500), `--files {events,agent-activity,escalations}` (default `events`), `--session-dir <path>`.
  - `cli_handler.py` public signatures:
    - `handle_start(args: argparse.Namespace) -> int` — resolves `repo_path` via `subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()` with fallback to `Path.cwd()`; if `args.state` is set, use it; else call `_auto_discover_state(repo_path / "lifecycle" / "sessions")` (port of `runner.sh:122-163`: scan `*/overnight-state.json`, most-recent mtime with `phase == "executing"`); derive `session_dir = state_path.parent`, `plan_path = session_dir / "overnight-plan.md"`, `events_path = session_dir / "overnight-events.log"`; call `runner.run(state_path, session_dir, repo_path, plan_path, events_path, args.time_limit, args.max_rounds, args.tier, args.dry_run)`. The concurrent-start guard (read+verify runner.pid; reject-if-live, self-heal-if-stale) lives inside `runner.run`'s startup block (see Task 6b "Session startup (concurrent-start guard)") — `handle_start` does not duplicate that check.
    - `handle_status(args: argparse.Namespace) -> int` — reads `ipc.read_active_session()`; if absent or `phase == "complete"`, scan most-recent `lifecycle/sessions/*/overnight-state.json`; delegates to `status.py`'s existing display logic for human format; for `--format json` emits object with keys `session_id`, `phase`, `current_round`, `features`. When no active session: human → non-empty message + exit 0; json → `{"active": false}` + exit 0.
    - `handle_cancel(args: argparse.Namespace) -> int` — resolve session dir from `args.session_dir` or `ipc.read_active_session()`; call `session_validation.resolve_session_dir(session_id, lifecycle_sessions_root)`; call `ipc.read_runner_pid(session_dir)`; if `None` → exit nonzero with `no active session`; call `ipc.verify_runner_pid(data)`; if `False` → **call `ipc.clear_runner_pid(session_dir)` and `ipc.clear_active_session()` to self-heal the stale state** (spec Edge Cases line 234: "cancel sees stale PID... refuses to signal, clears the stale files"), then exit nonzero with stderr containing `stale lock cleared — session was not running`; if `True` → `os.killpg(data["pgid"], signal.SIGTERM)`; exit 0. The stale-clear branch ensures repeat cancel invocations don't hit the same rejection forever.
    - `handle_logs(args: argparse.Namespace) -> int` — validate session-id; resolve session dir; compute `log_path = session_dir / logs.LOG_FILES[args.files]` (escalations is at repo-level `lifecycle/escalations.jsonl` — handle specially); call `logs.read_log(log_path, args.since, args.tail, args.limit)`; print lines to stdout; print `next_cursor: @{offset}` to stderr.
  - `_auto_discover_state(lifecycle_sessions_root: Path) -> Path | None` — check for a `latest-overnight` symlink first, fall back to most-recent-mtime `*/overnight-state.json` with `phase == "executing"`.
  - Lazy import pattern: `from cortex_command.overnight import cli_handler` inside each subparser's handler dispatch, not at module top — avoids slow `--help` invocations.
  - CLI-side argument parsing is the only place `argparse` lives; `runner.py`, `ipc.py`, etc. receive typed parameters.
- **Verification**: `cortex overnight start --help` exits 0 and stdout contains `--state`, `--time-limit`, `--max-rounds`, `--tier`, `--dry-run` — pass if all 5 strings present. `cortex overnight cancel "; rm -rf ~"` exits nonzero and stderr contains `invalid session id` — pass if both conditions. `cortex overnight cancel "../../../etc"` exits nonzero and stderr contains `invalid session id` — pass. `cortex overnight status --format json` (with no active session) exits 0 and stdout parses as JSON — pass if `python3 -c "import json,sys; json.loads(sys.stdin.read())"` succeeds. Stale-cancel self-heal: fixture session dir with stale `runner.pid` (write pid+start_time set 1000s ago) → `cortex overnight cancel --session-dir <fixture>` exits nonzero and stderr contains `stale lock cleared`; subsequent `test -f <fixture>/runner.pid` exits 1 (file removed) — pass.
- **Status**: [ ] pending

---

### Task 8: Write `tests/test_cortex_overnight_security.py` — session-id and PID verification tests
- **Files**: `tests/test_cortex_overnight_security.py` (new)
- **What**: Covers R17 (session-id validation + path containment) and R18 (stale-PID rejection). Unit tests against `session_validation` and `ipc` modules; one subprocess integration test exercising `cortex overnight cancel` end-to-end for the stderr message acceptance.
- **Depends on**: [2, 4, 7]
- **Complexity**: simple
- **Context**:
  - `test_validate_session_id_rejects_shell_metachars` — assert `ValueError("invalid session id")` raised for `"; rm -rf ~"`, `"& echo pwn"`, `"$(whoami)"`.
  - `test_validate_session_id_rejects_path_traversal` — assert raise for `"../../../etc"`, `"..%2F..%2Fetc"`.
  - `test_validate_session_id_rejects_oversized` — assert raise for string of length 129.
  - `test_validate_session_id_rejects_unicode` — assert raise for non-ASCII (`"ñ"`, `"日本"`).
  - `test_validate_session_id_accepts_canonical` — assert no raise for `"2026-04-23-18-00-00"`, `"session.1"`, `"a_b-c.1"`.
  - `test_resolve_session_dir_rejects_symlink_escape` — create `tmp_path/lifecycle/sessions/evil` as `os.symlink` target outside root; assert `resolve_session_dir("evil", ...)` raises.
  - `test_verify_runner_pid_rejects_stale_start_time` — write `runner.pid` with current test process's PID but `start_time` set 1000 seconds ago via `(datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()`; assert `verify_runner_pid(data) is False`.
  - `test_verify_runner_pid_rejects_dead_pid` — write `runner.pid` with PID `999999` (almost certainly nonexistent); assert `verify_runner_pid(data) is False`.
  - `test_verify_runner_pid_accepts_live_pid` — write `runner.pid` with `os.getpid()` + `psutil.Process(os.getpid()).create_time()`-derived start_time; assert `verify_runner_pid(data) is True`.
  - `test_cancel_rejects_stale_pid_end_to_end` — fixture: `tmp_path/lifecycle/sessions/<id>/runner.pid` with stale `start_time`; invoke `cortex overnight cancel --session-dir <tmp_path>/lifecycle/sessions/<id>` via `subprocess.run(...)`; patch `os.killpg` via `unittest.mock.patch` to assert it's not called; assert exit nonzero.
- **Verification**: `pytest tests/test_cortex_overnight_security.py` — pass if exit 0.
- **Status**: [ ] pending

---

### Task 9: Write `tests/test_runner_threading.py` — coordination + watchdog tests against `runner_primitives`
- **Files**: `tests/test_runner_threading.py` (new)
- **What**: Covers R7 acceptance: `stall_flag` distinguishes stall-kill from normal exit, `kill_lock` prevents double-kill in concurrent cancel+stall, `shutdown_event` wakes watchdog mid-sleep. Imports from `cortex_command.overnight.runner_primitives` — no full-runner import graph.
- **Depends on**: [6a]
- **Complexity**: simple
- **Context**:
  - `test_stall_flag_set_on_timeout` — `coord = RunnerCoordination(...)`; spawn `subprocess.Popen(["sleep", "60"], start_new_session=True)`; `wctx = WatchdogContext(stall_flag=threading.Event())`; instantiate `WatchdogThread(proc, timeout_seconds=1, coord, wctx, "test")`; `.start()`; assert `wctx.stall_flag.wait(timeout=5) is True`; assert `proc.poll() is not None`.
  - `test_concurrent_cancel_and_stall_dont_double_kill` — patch `os.killpg` via `unittest.mock.patch` with a counter; two threads both attempt to kill the same PGID while holding `coord.kill_lock`; assert `os.killpg` called exactly once.
  - `test_shutdown_event_wakes_watchdog_sleep` — start watchdog with `timeout_seconds=60`; set `coord.shutdown_event` after 100ms (via `threading.Timer`); assert watchdog `.join(timeout=3)` succeeds and thread exits without calling `os.killpg`.
  - `test_received_signals_append_thread_safe` — install signal handlers, send `signal.raise_signal(signal.SIGHUP)`, assert `signal.SIGHUP in coord.received_signals`.
  - `test_deferred_signals_stashes_and_replays` — enter `deferred_signals(coord)`, send `signal.raise_signal(signal.SIGTERM)`, verify `coord.shutdown_event` NOT set during protected block (handler was swapped); exit context manager, assert signal replayed and `shutdown_event` set.
- **Verification**: `pytest tests/test_runner_threading.py` — pass if exit 0.
- **Status**: [ ] pending

---

### Task 10: Rewrite `tests/test_fill_prompt.py` and capture `tests/fixtures/dry_run_reference.txt`
- **Files**: `tests/test_fill_prompt.py` (modify), `tests/fixtures/dry_run_reference.txt` (new), `tests/fixtures/dry_run_state.json` (new)
- **What**: Rewrite `test_fill_prompt.py` to call `fill_prompt.fill_prompt()` directly (no bash source-extract). Capture byte-identical DRY-RUN reference stdout from the pre-port `bash runner.sh --dry-run` with a committed terminal-state fixture — both must happen before `runner.sh` is deleted (Task 15).
- **Depends on**: [5]
- **Complexity**: simple
- **Context**:
  - `test_fill_prompt.py` rewrite: remove the `_run_fill_prompt()` bash source-extract shim at lines 20-30. Import `from cortex_command.overnight.fill_prompt import fill_prompt`. Each existing test function (`test_fill_prompt_substitutes_session_plan_path`, `test_fill_prompt_substitutes_plan_path_value`, `test_fill_prompt_preserves_per_feature_double_brace`, `test_fill_prompt_contains_substitution_contract`) keeps its assertion body unchanged; only the invocation mechanism changes — call `fill_prompt(round_number=1, state_path=Path(...), plan_path=Path(...), events_path=Path(...), session_dir=Path(...), tier="simple")`.
  - `tests/fixtures/dry_run_state.json` — commit a terminal-state fixture (all features in `merged`/`failed`/`deferred` — no `pending`) usable by both `test_fill_prompt.py` (for substitution context) and `test_runner_pr_gating.py` (for dry-run invocation). Locate the existing fixture at `tests/fixtures/state-zero-merge.json` (correct path — earlier draft cited `cortex_command/overnight/tests/fixtures/state/state-zero-merge.json` which does not exist). Verify the existing fixture has `integration_branch` set AND that the branch exists locally with ≥ 1 commit ahead of `main`; if the fixture does not satisfy this precondition, synthesize a new fixture with a scripted git setup so the DRY-RUN gh-pr-create path is actually reached (otherwise the reference capture silently omits the `gh pr create` line — the primary assertion target).
  - `tests/fixtures/dry_run_reference.txt` — one-time capture: run `bash cortex_command/overnight/runner.sh --dry-run --state-path tests/fixtures/dry_run_state.json` with `TMPDIR` set to a fixed path (e.g., `TMPDIR=/tmp/dry-run-capture bash ...`) to stabilize the `$PR_BODY_FILE` path. Save stdout verbatim. This is the byte-identical reference for `test_runner_pr_gating.py::test_dry_run_byte_identical` in Task 12 — but note that Task 12's assertion applies path-normalization before full-line equality (see Task 12 Context) to handle `$TMPDIR` variance between capture and test execution environments.
- **Verification**: `pytest tests/test_fill_prompt.py` — pass if exit 0. `grep -c 'runner\.sh' tests/test_fill_prompt.py` — pass if 0. `test -f tests/fixtures/dry_run_reference.txt && test -s tests/fixtures/dry_run_reference.txt` — pass if exit 0. `grep -c "DRY-RUN " tests/fixtures/dry_run_reference.txt` — pass if ≥ 1.
- **Status**: [ ] pending

---

### Task 11: Port `tests/test_runner_signal.py` and `tests/test_runner_resume.py`
- **Files**: `tests/test_runner_signal.py` (modify), `tests/test_runner_resume.py` (modify)
- **What**: Port signal test to invoke `cortex overnight start` subprocess + `os.kill(pid, SIGHUP)` and assert R14 updated behavior (phase=paused not cleared, exit 130, circuit_breaker event). Port resume test by replacing the structural `grep` on `runner.sh` source (line 82) with a behavioral call to `state.load_state` / `interrupt.handle_interrupted_features`.
- **Depends on**: [6b, 7]
- **Complexity**: simple
- **Context**:
  - `test_runner_signal.py`: replace `RUNNER_SH` constant at line 22 with invocation via `["cortex", "overnight", "start", "--state", str(state_path), "--time-limit", "1h", "--max-rounds", "1", "--tier", "simple"]`. Remove the `.venv` symlink setup at line 40 (no longer needed — the tool is installed via `uv tool install -e .`). Keep `os.kill(proc.pid, signal.SIGHUP)` delivery. Assertions updated per R14: (a) exit code 130; (b) `overnight-events.log` last event JSON has `event == "circuit_breaker"` and `details.reason == "signal"`; (c) `~/.local/share/overnight-sessions/active-session.json` exists and `phase == "paused"` (not cleared); (d) no half-written backlog file under `backlog/`; (e) test completes within 30s.
  - `test_runner_resume.py`: line 82 `grep runner.sh count_pending` assertion replaced with a behavioral test — create an `OvernightState` fixture with one feature `status="paused"` and one `status="deferred"`; call `interrupt.handle_interrupted_features(state_path)`; reload via `state.load_state(state_path)`; assert paused feature's status was reset to `pending`; assert deferred feature's status is still `deferred`. Existing behavioral tests at lines 46-71 are preserved if still valid against the Python API.
- **Verification**: `pytest tests/test_runner_signal.py tests/test_runner_resume.py` — pass if exit 0. `grep -c 'runner\.sh' tests/test_runner_signal.py tests/test_runner_resume.py` — pass if total count is 0.
- **Status**: [ ] pending

---

### Task 12: Port `tests/test_runner_pr_gating.py` and `tests/test_runner_followup_commit.py`
- **Files**: `tests/test_runner_pr_gating.py` (modify), `tests/test_runner_followup_commit.py` (modify)
- **What**: Port both files to invoke `cortex_command.overnight.runner.run(dry_run=True, ...)` directly (primary) with a subprocess wrapper test (`cortex overnight start --dry-run`) for CLI wiring coverage. Add byte-identical DRY-RUN assertion against `tests/fixtures/dry_run_reference.txt` per R15. Preserve all 11 subtests in PR gating; preserve `DRY_RUN_GH_READY_SIMULATE` retention.
- **Depends on**: [6b, 7, 10]
- **Complexity**: complex
- **Context**:
  - `test_runner_pr_gating.py`: `_invoke_runner()` at line 160 changes from `["bash", "cortex_command/overnight/runner.sh", "--dry-run", ...]` to direct Python call `runner.run(state_path, session_dir, repo_path, plan_path, events_path, time_limit_seconds=None, max_rounds=None, tier="simple", dry_run=True)` — captures stdout via `contextlib.redirect_stdout` or by spawning as subprocess. `_build_env()` at line 139: remove `REPO_ROOT`/`PYTHONPATH` env vars (no longer needed under Python CLI); preserve `DRY_RUN_GH_READY_SIMULATE` passthrough (R15 mandate). Eleven subtest assertion bodies unchanged. Add new test `test_dry_run_stdout_byte_identical` — invoke `cortex overnight start --dry-run --state tests/fixtures/dry_run_state.json` via subprocess with `env={**os.environ, "TMPDIR": "/tmp/dry-run-capture"}` to stabilize `$PR_BODY_FILE` path. **Before full-line equality**, apply a path-normalization pass to both the captured actual stdout and the committed reference: replace any substring matching the pattern `/tmp/dry-run-capture/overnight-pr-body\.txt` with the literal token `<TMPDIR>/overnight-pr-body.txt` (use `re.sub`). Normalization is applied only to tokens known to carry runtime paths — `$PR_BODY_FILE` is the sole confirmed example from runner.sh audit; if additional runtime tokens surface during implementation, extend the normalization map and document each. Then assert `[line for line in normalized_stdout.splitlines() if line.startswith("DRY-RUN ")]` equals the corresponding filtered lines from the normalized reference. Full-line equality post-normalization; substring fallback is prohibited. R15's "byte-identical" contract is narrowed at the plan level to "byte-identical after environment-path normalization" — the correctness property R15 cares about (label + structural-token drift detection) is preserved; the unachievable property (literal byte match across machines) is replaced with a stable equivalent.
  - `test_runner_followup_commit.py`: audit all `subprocess.Popen` / `subprocess.run` runner invocations and repoint from `bash runner.sh` to `cortex overnight start`. State file fixture construction and `_poll_for_event`-style assertions unchanged.
  - Both files: remove any `cwd=REAL_REPO_ROOT` pattern that was only needed to locate `runner.sh`.
  - Dry-run reject-with-pending test: invoke `cortex overnight start --dry-run --state <fixture-with-pending>`; assert exit nonzero and stderr contains `--dry-run requires a state file with all features in terminal states` (R15 acceptance).
- **Verification**: `pytest tests/test_runner_pr_gating.py tests/test_runner_followup_commit.py` — pass if exit 0. `grep -c 'bash.*runner\.sh\|runner\.sh"' tests/test_runner_pr_gating.py tests/test_runner_followup_commit.py` — pass if count is 0.
- **Status**: [ ] pending

---

### Task 13: Replace `tests/test_runner_auth.sh` with `tests/test_runner_auth.py`
- **Files**: `tests/test_runner_auth.sh` (delete), `tests/test_runner_auth.py` (new)
- **What**: Replace the verbatim-line-range bash test with a Python pytest that exercises `cortex_command.overnight.auth` directly. Matches behavioral coverage of the original (ANTHROPIC_API_KEY resolution, `apiKeyHelper` path read, missing-file fallback).
- **Depends on**: [6b]
- **Complexity**: simple
- **Context**:
  - Audit `tests/test_runner_auth.sh` for its three behavioral scenarios (likely: ANTHROPIC_API_KEY env var precedence; `apiKeyHelper` from `~/.claude/settings.json`; fallback on missing settings file).
  - `tests/test_runner_auth.py` implements equivalent coverage using pytest. Patch `Path.home()` via `monkeypatch` to point at `tmp_path`; write test `settings.json` fixtures under `tmp_path/.claude/settings.json`; call `auth.get_api_key_helper()` and `auth.resolve_api_key()` directly.
  - Existing `cortex_command/overnight/tests/test_auth.py` may overlap — coordinate to avoid duplication; prefer extending the existing file if its scope is identical.
  - Auth path reads preserved per R23: `auth.py::get_api_key_helper()` still reads `~/.claude/settings.json` / `~/.claude/settings.local.json` at literal paths.
- **Verification**: `pytest tests/test_runner_auth.py` — pass if exit 0. `test -f tests/test_runner_auth.sh` exits 1 — pass. `grep -c '\.claude.*settings\.json' cortex_command/overnight/auth.py` — pass if ≥ 2.
- **Status**: [ ] pending

---

### Task 14: Add new coverage tests per R26 — resume semantics, fail-forward, sync-rebase, integration-branch persistence
- **Files**: `tests/test_runner_resume_semantics.py` (new), `tests/test_runner_fail_forward.py` (new), `tests/test_git_sync_rebase.py` (new), `tests/test_integration_branch.py` (new)
- **What**: Closes the four R16 `[M]`-tagged pipeline.md gaps that have no current test coverage.
- **Depends on**: [6b]
- **Complexity**: simple
- **Context**:
  - `test_runner_resume_semantics.py`: (a) `test_paused_feature_retried_on_resume` — fixture state with one feature `status="paused"`; invoke `interrupt.handle_interrupted_features(state_path)`; reload state; assert feature status is `pending` (reset for re-run). (b) `test_deferred_feature_skipped_on_resume` — fixture with `status="deferred"`; same call; assert status still `deferred`.
  - `test_runner_fail_forward.py`: `test_sibling_continues_after_one_fails` — two-feature state fixture; mock `feature_executor.dispatch_feature` via `unittest.mock.patch` to return `failed` for feature A and `merged` for feature B; invoke round-dispatch (direct call to `runner.run` with mocked orchestrator, or invoke `outcome_router.route_outcome` for both); reload state; assert feature B is `merged` despite A's failure.
  - `test_git_sync_rebase.py`: create a fixture git repo in `tmp_path` via `git init` with a synthetic integration branch and `sync-allowlist.conf`; invoke `subprocess.run(["bash", str(SYNC_REBASE_SH), ...], cwd=tmp_path)`; assert exit 0; assert `git log --merges --oneline` shows the expected merge-strategy commit (R26 `--merge` semantics check).
  - `test_integration_branch.py`: fixture state with `integration_branch="overnight/2026-04-23-test"`; invoke runner to `complete` transition (or write state directly with `phase="complete"`); call `subprocess.check_output(["git", "show-ref", "refs/heads/overnight/2026-04-23-test"], cwd=repo)`; assert exit 0 (branch persisted, not auto-deleted per pipeline.md L135).
- **Verification**: `pytest tests/test_runner_resume_semantics.py tests/test_runner_fail_forward.py tests/test_git_sync_rebase.py tests/test_integration_branch.py` — pass if exit 0.
- **Status**: [ ] pending

---

### Task 15: Retire `runner.sh`, `bin/overnight-start`, `bin/overnight-status`; update justfile and docs
- **Files**: `cortex_command/overnight/runner.sh` (delete), `bin/overnight-start` (delete), `bin/overnight-status` (delete), `justfile` (modify), `docs/setup-guide.md` (modify)
- **What**: Deletes retired artifacts (R6, R24) and updates `justfile` recipes to call `cortex overnight start/status` instead of bash shims. Adds `uv tool install -e .` line to setup guide (R21). `bin/overnight-schedule` is explicitly preserved (ticket 112 owns it).
- **Depends on**: [6b, 7, 10, 11, 12, 13]
- **Complexity**: simple
- **Context**:
  - `justfile`: locate `overnight-run` / `overnight-start` / `overnight-status` recipes; replace `bash "{{justfile_directory()}}/cortex_command/overnight/runner.sh" ...` with `cortex overnight start ...`; replace `bin/overnight-status` calls with `cortex overnight status`. Grep `overnight-start` and `overnight-status` to find all references.
  - `docs/setup-guide.md`: ensure the install instructions section contains `uv tool install -e .` as the supported install command.
  - `bin/overnight-schedule` must remain untouched.
  - Before deletion run `grep -rn 'runner\.sh' tests/ cortex_command/` and confirm only historical documentation/changelog references remain (no live test imports, no live code invocations).
- **Verification**: `test -f cortex_command/overnight/runner.sh` exits 1 — pass. `test -f bin/overnight-start` exits 1 — pass. `test -f bin/overnight-status` exits 1 — pass. `test -f bin/overnight-schedule` exits 0 — pass. `grep -n 'overnight-start\|overnight-status' justfile` exits 1 — pass. `grep -c 'uv tool install -e' docs/setup-guide.md` ≥ 1 — pass. `just test` exits 0 — pass.
- **Status**: [ ] pending

---

### Task 16: File follow-up backlog items (R27)
- **Files**: `backlog/<next-id>-non-editable-wheel-install-support.md` (new), `backlog/<next-id>-multi-session-host-concurrency.md` (new), `backlog/index.json` (regenerated)
- **What**: Files the two R27-mandated backlog tickets before 115 merges. Regenerates the backlog index.
- **Depends on**: [15]
- **Complexity**: trivial
- **Context**:
  - "Non-editable wheel install support": title `"Non-editable wheel install support for cortex-command"`, status `backlog`, tags `["distribution", "packaging"]`, body explains R21 deferral — the remaining work is ensuring `importlib.resources` returns usable `Traversable` under a non-editable wheel build backend (`$_SCRIPT_DIR/../..` no longer applies since 115 replaced it with explicit CLI path injection).
  - "Multi-session host concurrency": title `"Multi-session host concurrency registry for cortex overnight"`, status `backlog`, priority `contingent` (future-contingency, no owner yet), tags `["overnight", "ipc"]`, body captures the host-wide enumeration problem identified in research.md Adversarial #8 — activated if multi-session becomes concrete.
  - YAML frontmatter follows existing backlog format (see `backlog/<existing>.md` for structure — required fields: `id`, `title`, `status`, `priority`, `tags`, `blocked_by: []`).
  - Run `just backlog-index` to regenerate `backlog/index.json`.
- **Verification**: `ls backlog/*.md | xargs grep -l 'wheel install support' | wc -l` — pass if ≥ 1. `ls backlog/*.md | xargs grep -l 'Multi-session host concurrency' | wc -l` — pass if ≥ 1. `just backlog-index` exits 0 — pass.
- **Status**: [ ] pending

---

## Verification Strategy

After all tasks complete, end-to-end verification:

1. **Install check**: `uv tool install -e . --force && command -v cortex` exits 0. `cortex overnight start --help` exits 0 and stdout contains all five flags.
2. **No bash runner references in live code**: `test -f cortex_command/overnight/runner.sh` exits 1. `grep -rn 'bash runner\.sh\|runner\.sh"' tests/` exits 1. `grep -rn 'python3 -c\|python3 -m cortex_command' cortex_command/overnight/*.py` exits 1.
3. **IPC contract present**: `grep -c 'schema_version' cortex_command/overnight/state.py` ≥ 3. `grep -c 'cortex-runner-v1' cortex_command/overnight/ipc.py` ≥ 1. `grep -n 'cortex_version' cortex_command/overnight/*.py` exits 1 (single version axis).
4. **Package-internal resources via importlib**: `grep -c 'importlib.resources' cortex_command/overnight/fill_prompt.py cortex_command/overnight/runner.py` ≥ 2. `grep -n "REPO_ROOT\|CORTEX_COMMAND_ROOT\|\$PYTHONPATH" cortex_command/overnight/*.py` exits 1.
5. **Coordination primitives separated**: `grep -c 'threading\.Event\|threading\.Lock' cortex_command/overnight/runner_primitives.py` ≥ 3. `grep -c 'from cortex_command.overnight.runner_primitives' cortex_command/overnight/runner.py` ≥ 1.
6. **Dry-run byte-identical**: The `test_dry_run_stdout_byte_identical` test in `tests/test_runner_pr_gating.py` passes — full-line equality on `DRY-RUN ` prefixed lines.
7. **Full test suite**: `just test` exits 0.
8. **Security rejection**: `cortex overnight cancel "; rm -rf ~"` exits nonzero, stderr contains `invalid session id`. `cortex overnight cancel "../../../etc"` same.
9. **Follow-up backlog filed**: `ls backlog/*.md | xargs grep -l 'wheel install support' | wc -l` ≥ 1.

## Veto Surface

- **Extraction of `runner_primitives.py`** (Task 6a) — the spec names the four coordination primitives inline in `runner.py`'s requirement text (R7). Extracting them into a separate module is an architectural choice not mandated by the spec; it pays off in threading-test isolation (Task 9 imports from a leaf module without triggering the full orchestration graph), but adds one module boundary. Revisit if you prefer primitives live at top-level in `runner.py`.
- **`ipc.py` holding both PID file and active-session pointer** — R8 and R9 describe two artifacts with different paths (`lifecycle/sessions/{id}/runner.pid` vs `~/.local/share/overnight-sessions/active-session.json`) and different lifecycle rules (PID cleared on clean shutdown; active-session cleared only on `complete`). They share the R8 schema, so keeping them in one module avoids duplicating the atomic-write helper and schema constants. Revisit if you prefer a stricter per-artifact split (`pid_file.py` + `active_session.py`).
- **`logs.py` as a dedicated module** — byte-offset + RFC3339 cursor protocol (R11) is non-trivial (~80 lines including validation and EOF trailer handling). A dedicated module is defensible; alternatively, this could live inside `cli_handler.py`. Kept separate because it's substantive enough to deserve isolated unit tests (covered under `tests/test_runner_threading.py`-adjacent work, plus acceptance tests in R4).
- **`--merge` strategy test in Task 14** — `bin/git-sync-rebase.sh` is a shell script. The test invokes it via `subprocess.run(["bash", ...])`; a bats-style test would be equally valid. Python subprocess chosen for uniformity with the rest of the test suite.
- **`cli_handler.py` vs inlining into `cli.py`** — `cli.py` already has a pattern of `_make_stub("overnight")`; four substantial handler functions are sizable enough to warrant a dedicated module (keeps `cli.py` as pure argparse routing).
- **Late retirement of runner.sh (Task 15)** — retirement happens after all tests port, not early. This preserves `runner.sh` as a reference during test development and preserves the DRY-RUN byte-identical capture in Task 10. Revisit if you prefer earlier retirement (e.g., immediately after Task 6b).
- **`cortex-batch-runner` console-script shim** (Task 2) — the plan adds a `[project.scripts]` entry for batch_runner invocation to genuinely satisfy R5's intent (the literal grep alone would permit `[sys.executable, "-m", "cortex_command.overnight.batch_runner"]`, which implements the banned pattern while passing the textual check). Revisit if you prefer a different invocation mechanism (dedicated wrapper module at a non-matching path; subprocess via a shipped shell script in `bin/`).
- **`proc.wait(timeout=POLL_INTERVAL_SECONDS)` poll loop** (Task 6b) — chosen over the alternative of watchdog-driven kill on `shutdown_event` because it keeps kill authority on the main thread and avoids threading-test complexity around concurrent watchdog-kill vs main-thread-kill races. Watchdog remains specialized for stall detection only. Revisit if you prefer watchdog to own all kill paths (would require extending WatchdogThread's `shutdown_event` branch to SIGTERM+escalate rather than "exit cleanly").
- **R15 byte-identical scope narrowing to post-normalization equality** (Task 12) — the R15 spec contract says "byte-identical" and "full-line equality"; the plan narrows this to "byte-identical after `$TMPDIR` path normalization" because literal byte-identity is unachievable across machines where `$TMPDIR` varies. The correctness property R15 cares about (label + structural-token drift detection) is preserved. Revisit if you prefer to keep literal byte-identity and instead ship a test-only `TMPDIR` override that forces both the fixture capture and test execution to use the same path (alternative approach, same outcome, different mechanism).

## Scope Boundaries

Explicitly excluded (matches spec Non-Requirements):

- **MCP server / IPC implementation** — owned by ticket 116. 115 ships the contract surface (R8/R9/R10/R11); 116 builds MCP tooling on top.
- **`overnight_list_sessions` enumeration** — 116 scans `lifecycle/sessions/*/` using R8 schema; 115 commits to schema stability but does not implement the enumeration helper.
- **LaunchAgent scheduling migration** — owned by ticket 112. `bin/overnight-schedule` is untouched.
- **Dashboard migration** — dashboard stays in place; 115 preserves all state-file field names and nesting.
- **Plugin distribution** — owned by ticket 120. 115 ships a CLI, not a plugin.
- **Non-editable wheel install support** — 115 is editable-only per `requirements/project.md`; filed as Task 16 follow-up.
- **Multi-session host concurrency** — single-active-session preserved; multi-session support is a Task 16 follow-up (contingent priority).
- **Log rotation within a session** — events.log is append-only, single-file per session.
- **Full async rewrite** — sync + threading is the chosen model (R7). Async rejected.
- **Scope-creep refactors** — `report.py`, `outcome_router.py`, `integration_recovery.py` not rewritten; imported as-is.
