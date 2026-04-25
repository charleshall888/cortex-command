# Research: MCP control-plane server with versioned runner IPC contract

Ticket: [116](../../backlog/116-mcp-control-plane-server-and-runner-ipc-contract.md). Tier: complex. Criticality: high.

## Epic Reference

This ticket is the DR-1 work item from epic [113 — overnight-layer distribution](../../research/overnight-layer-distribution/research.md) (see DR-1, lines 231–242; DR-6 is folded in). The epic covers CLI + plugin + MCP distribution strategy; this ticket scopes down to the MCP control-plane server and the versioned runner IPC contract that backs it. Epic-level decisions (plugin tiers, CLI packaging, bootstrap UX, roster design) are out of scope here and should not be re-litigated in spec or plan.

---

## Codebase Analysis

**Headline finding.** Most of the IPC contract this ticket calls for is **already implemented**. The ticket's principal new work is the MCP server layer on top of existing primitives, plus a small set of contract tightenings surfaced in adversarial review.

### Files that will change

- **New module**: `cortex_command/mcp_server/` — `__init__.py`, `server.py` (FastMCP scaffold, stdio transport), `tools.py` (five tool implementations), `schema.py` (Pydantic input/output models), and a `cursor.py` codec for opaque resume tokens.
- **CLI wiring**: `cortex_command/cli.py:262-267` — replace `_make_stub("mcp-server")` with a real `_dispatch_mcp_server` handler (pattern mirrors overnight handlers at `cli.py:116-257`).
- **Runner lock (MUST)**: `cortex_command/overnight/ipc.py` and `cortex_command/overnight/runner.py:464-481` — tighten `_check_concurrent_start` from read-then-write into an atomic `O_CREAT|O_EXCL` claim on a sibling `runner.lock`. See Adversarial §1.
- **Schema-version enforcement (MUST)**: `cortex_command/overnight/ipc.py:127-165` — `verify_runner_pid` currently accepts `schema_version >= 1`; tighten to refuse unknown future versions. See Adversarial §10.
- **Dependency**: `pyproject.toml` — add `mcp>=1.27.0` to runtime deps (Python>=3.10 is already required).
- **Tests**: `tests/test_mcp_*.py` — tool schemas, cursor codec, session enumeration, idempotent-start race, confirmation-arg gate, schema-version enforcement. Security tests at `tests/test_cortex_overnight_security.py` are the pattern.
- **Docs**: `docs/mcp-server.md` (new) — see Requirements §4 for the doc-ownership rationale.

### Relevant existing patterns (cite file:line)

**`schema_version` on overnight-state.json** — already present.
- `cortex_command/overnight/state.py:243-269` — `OvernightState` dataclass field `schema_version: int = 1`.
- `cortex_command/overnight/state.py:400` — load treats absence as 0 (legacy); next save upgrades to 1.
- Atomic write: `state.py:404-446` — `tempfile.mkstemp` → `durable_fsync` → `os.replace`.
- Existing state files on disk (e.g. `lifecycle/sessions/overnight-2026-04-21-1708/overnight-state.json`) lack the field; upgrade-on-save is already correct.
- Full 20-field schema enumerated: `session_id`, `plan_ref`, `plan_hash`, `current_round`, `phase`, `features`, `round_history`, `started_at`, `updated_at`, `paused_from`, `paused_reason`, `integration_branch`, `integration_branches`, `worktree_path`, `project_root`, `integration_worktrees`, `scheduled_start`, `integration_pr_flipped_once`, `integration_degraded`, `schema_version`.

**`runner.pid` IPC contract** — fully implemented, matches `requirements/pipeline.md`.
- Writer: `cortex_command/overnight/ipc.py:84-108` — `write_runner_pid(session_dir, pid, pgid, start_time, session_id, repo_path)`; schema `{schema_version: 1, magic: "cortex-runner-v1", pid, pgid, start_time (ISO 8601 string), session_id, session_dir, repo_path}`; mode 0o600; atomic via `_atomic_write_json` at `ipc.py:43-78`.
- Reader: `ipc.py:116-124`.
- Verifier: `ipc.py:127-165` — checks `magic == "cortex-runner-v1"`, `schema_version >= 1`, `psutil.Process(pid).create_time()` within ±2s of recorded `start_time`. Returns False on stale/dead/AccessDenied (never signals, never raises).
- Start: `runner.py:489-539` — captures `start_time` via `datetime.now(timezone.utc).isoformat()`, computes `pgid = os.getpgid(pid)` (fallback to pid on `ProcessLookupError`), writes under signal-deferral (`runner.py:523-532`).

**Active-session pointer** — already wraps runner.pid schema with `phase`.
- `cortex_command/overnight/ipc.py:172-212` at `~/.local/share/overnight-sessions/active-session.json`.
- Retained on `paused`; cleared on `complete`.

**Log cursor infrastructure** — already implemented.
- `cortex_command/overnight/logs.py:31-35` — `LOG_FILES`: `events` → `overnight-events.log` (per-session), `agent-activity` → `agent-activity.jsonl` (per-session), `escalations` → `escalations.jsonl` (**repo-level, not per-session** — see Open Questions §1).
- `logs.py:87-145` — `read_log(log_path, since, tail, limit)` returns `(lines, next_byte_offset)`. Supports byte-offset cursor `@<int>` (seeks, idempotent) and RFC3339 timestamp cursor (filters). Past-EOF returns empty with `# cursor-beyond-eof` stderr trailer.
- `cli_handler.py:409-417` — `handle_logs` emits `next_cursor: @<int>` on stderr trailer.
- **No rotation logic** — logs are append-only JSONL per-session (or repo-level for escalations).

**Cancel path** — PGID signalling already implemented.
- `cli_handler.py:309-402` — resolves session (priority: `--session-dir` > positional id > active-session pointer); reads runner.pid; verifies via `ipc.verify_runner_pid()`; `os.killpg(pgid, SIGTERM)`; self-heals stale locks on `ProcessLookupError`.
- `runner.py:599, 654` — orchestrator and batch_runner subprocesses spawned with `subprocess.Popen(..., start_new_session=True)` — each child is in **its own PGID**. **Adversarial concern**: `os.killpg(runner_pgid, SIGTERM)` does NOT traverse into children's PGIDs; the runner's own SIGTERM handler must propagate to children (see Adversarial §2d).

**CLI shape** — MCP-server subparser stub already in place.
- `cli.py:262-267` — `subparsers.add_parser("mcp-server", ...)` currently set to `_make_stub("mcp-server")` (returns exit code 2). Ready to be replaced with `_dispatch_mcp_server()`.
- Overnight handlers (`cli.py:116-257`) are the pattern: lazy imports avoid slow `--help`, `set_defaults(func=...)` dispatch.

**Session enumeration** — glob-based.
- `cli_handler.py:55-99` — primary via `latest-overnight` symlink; fallback glob `lifecycle/sessions/*/overnight-state.json`, sorted by mtime; prefers `phase == "executing"`.
- Per-session marker files: `overnight-state.json`, `runner.pid`, `overnight-events.log`, `agent-activity.jsonl`, `morning-report.md`, `batch-{N}-results.json`, `session.json`.
- **No global index**; `overnight_list_sessions` must glob.

**Truncation / pagination patterns**.
- `cortex_command/pipeline/merge_recovery.py:166-176` and `pipeline/retry.py:103-113` truncate test/agent output with `"... (truncated)"` sentinel. Reusable shape for text tools, but **the MCP 25K cap demands cursor-based pagination, not truncation** (see Web §3).

### Integration points and dependencies

1. `cortex_command/overnight/ipc.py` — `write_runner_pid`, `read_runner_pid`, `verify_runner_pid`, `read_active_session`, `write_active_session`. Extend with `acquire_runner_lock(session_dir)`.
2. `cortex_command/overnight/state.py` — `load_state`, `save_state`; `OvernightState` dataclass.
3. `cortex_command/overnight/logs.py` — `read_log`; extend cursor codec for opacity (see Tradeoffs §D).
4. `cortex_command/overnight/session_validation.py` — `validate_session_id`, `resolve_session_dir` (R17/R18 regex + realpath containment — reuse verbatim in MCP tools).
5. `cortex_command/overnight/cli_handler.py` — tools wrap `handle_start`, `handle_status`, `handle_cancel`, `handle_logs` directly (the dylan-gluck "job registry" framing does not apply; see Adversarial §8).

### Conventions to follow

- **Atomic writes** via `tempfile + durable_fsync + os.replace` (state.py:404-446, ipc.py:43-78).
- **Session-path resolution is a CLI-boundary concern** (R20): resolve paths at the CLI, pass typed args to lower layers. MCP tools are effectively another CLI boundary — do the same.
- **Signal deferral** during atomic state saves (`deferred_signals(coord)` context manager).
- **PGID isolation** via `start_new_session=True` on every subprocess spawn.
- **Byte-offset cursors** are exact/idempotent; RFC3339 cursors are filtered (less reliable with sub-second duplicates). Keep byte-offset as internal storage, encode opaquely for the wire.
- **Backwards compatibility** via `.get()` with dataclass defaults; new fields added to writers before readers enforce.
- **Error messages** standardized per R3/R18 (`"invalid session id"`, `"stale lock cleared"`, `"no active session"`).

---

## Web Research

### Python MCP SDK current shape (2026-04-24)

- **Package**: `mcp` on PyPI, latest `1.27.0` (2026-04-02). GitHub: `modelcontextprotocol/python-sdk`. Requires Python ≥ 3.10.
- **High-level scaffold**: `from mcp.server.fastmcp import FastMCP`. Decorator `@mcp.tool()` auto-derives JSON Schema from Pydantic models / type hints. `mcp.run(transport="stdio")` starts the server.
- **Low-level scaffold**: `mcp.server.lowlevel.Server` with `@server.list_tools()`/`@server.call_tool()` handlers and `mcp.server.stdio.stdio_server()` context manager. Use only if you need manual capability advertisement or structured-output validation control.
- **Tool schema from type hints**: Pydantic `BaseModel` with `Field(description=...)` produces the richest schemas. Untyped params produce **unstructured** output (schema omitted).
- **Stdio transport mandate**: **stderr only for logs**; stdout is the JSON-RPC stream. Clarified in 2025-11-25 spec — stdio servers may use stderr for *all* log levels, not just errors.
- **Structured errors**: FastMCP raises `fastmcp.exceptions.ToolError`. Per 2025-11-25 SEP-1303, input validation errors return as Tool Execution Errors (`isError: true`) so the model self-corrects — **not** as JSON-RPC protocol errors.

### dylan-gluck/mcp-background-job — pattern, not implementation

- Last code commit `abd2b4a`, **2025-08-06** — 8 months stale. License MIT. PyPI 0.1.2. Targets `fastmcp>=2.11.1` (PrefectHQ standalone, not the official `mcp` SDK).
- Tools: `list_jobs`, `get_job_status`, `get_job_output`, `tail_job_output(job_id, lines: int 1..1000)`, `execute_command(command: str) → {job_id}`, `interact_with_job`, `kill_job`.
- Job ID: `uuid.uuid4()`, receiver-generated, no user-supplied IDs, **no idempotency check**.
- **No resumable cursor** — `tail` takes line count, not offset. `collections.deque(maxlen=...)` ring buffers drop old output silently.
- **No process-group handling** on cancel — `subprocess.Popen` without `start_new_session=True`, so shell children aren't reaped.
- **No PID file / PGID on disk** — state is in-memory, lost on server restart.
- **Verdict**: architectural shape only (FastMCP + thin facade + state polling). Do **not** import dylan-gluck's job-registry model — cortex already has `lifecycle/sessions/{id}/` as the registry. Reject the dylan-gluck UUID framing (see Adversarial §8).

### MCP 25 K output cap (authoritative)

From Claude Code MCP docs (`code.claude.com/docs/en/mcp`):

> Default limit: the default maximum is 25,000 tokens. Output warning threshold: Claude Code displays a warning when any MCP tool output exceeds 10,000 tokens. Configurable via `MAX_MCP_OUTPUT_TOKENS`.

Overflow is a **HARD ERROR**: `Error: MCP tool "<name>" response (25013 tokens) exceeds maximum allowed tokens (25000)`. No truncation, no partial result.

Per-tool escape hatch: `_meta["anthropic/maxResultSizeChars"]` up to a hard ceiling of 500 000 characters, char-based not token-based, applies only to text content, persists large results to disk rather than inline.

**Decision signal**: Adversarial §4 recommends **decline** this escape hatch — the 500 K char ceiling can inject ~125 K tokens into context, 5× the 25 K cap. Force pagination at 25 K.

### Opaque cursor token requirement

MCP spec (2025-11-25 Tasks utility): "Requestors MUST treat cursors as opaque tokens and not attempt to parse or modify them." Use base64-encoded JSON so the encoding can evolve (add inode/size later) without breaking consumers.

### SEP-1686 "Tasks" status

- **Shipped 2025-11-25 as experimental**. Spec warns "design and behavior may evolve."
- Claude Code **client support is not documented** in the public MCP docs page as of 2026-04 — treat as not-yet-usable in Claude Code.
- 2026 MCP roadmap (2026-03-05) flags open gaps: retry semantics on transient failure, expiry policies.
- **Ticket's "out of scope" decision holds**: keep tools synchronous-return-immediately, model polls via `overnight_status`.

### Token-cost estimates (cl100k_base tiktoken; ±10% Anthropic-tokenizer drift)

Dense structured JSON averages ~3 chars/token.

| Payload | Tokens | Notes |
|---|---|---|
| Typical 150-char log line | 50 | 3 chars/token structural overhead |
| 100 log lines | 5 000 | 50% of the 10 K warning |
| 150 log lines | 7 500 | safe default page |
| **200 log lines** | **10 000** | **hits 10 K warn** |
| 500 log lines | 25 000 | at cap — single more line errors |
| 20-feature overnight-state object (22 fields) | ~270 | trivial |
| Session summary × 50 | ~4 000 | fine with headroom |

**Recommended defaults**: `overnight_logs` limit **100** (server-cap 200), `overnight_status` inline, `overnight_list_sessions` default 10 recent + all active with cursor.

### MCP server registration (for `cortex mcp-server`)

- CLI: `claude mcp add cortex-overnight --scope user --transport stdio -- cortex mcp-server`
- Scopes: `local` (default, per-project in `~/.claude.json`), `user` (global in `~/.claude.json`), `project` (committed `./.mcp.json`).
- Plugin distribution: ship inside the `cortex-overnight-integration` plugin's `.mcp.json` per epic DR-10 roster — auto-registers on `/plugin install`. Same server binary; only registration UX differs.

### Process-model reminders

- Stdio MCP server is per-Claude-Code-session; killed at session end. Runner is out-of-process (`start_new_session=True`), addressed via PID file — runner survives Claude Code exit. Reparent to PID 1 (launchd) on macOS is expected behavior.
- Known footguns: stdout pollution of JSON-RPC stream (always log to stderr); signal-handler races calling `asyncio.create_task` from sync handlers (prefer `loop.add_signal_handler`); no "single instance" enforcement across multiple Claude Code sessions (the runner-layer lock is the fix).

---

## Requirements & Constraints

### `runner.pid` contract (requirements/pipeline.md:151, verbatim)

> `lifecycle/sessions/{session_id}/runner.pid` — per-session IPC contract (JSON `{schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path}`, mode 0o600, atomic write). Cleared on clean shutdown; cancel verifies magic + start_time (±2s via psutil) before signalling to close the PID-reuse race. Stable contract for ticket 116 MCP control plane.

### `active-session.json` contract (requirements/pipeline.md:152, verbatim)

> `~/.local/share/overnight-sessions/active-session.json` — host-global active-session pointer sharing the `runner.pid` schema plus a `phase: "planning|executing|paused|complete"` field. Retained on `paused` transition (preserves dashboard/statusline visibility); cleared on `complete`.

### Architectural constraints (requirements/project.md)

- **File-based state**: markdown/JSON/YAML only; no database or server. MCP server is a reader/facade — it must not introduce mutable in-process state.
- **Atomicity**: all state writes `tempfile + os.replace()`; no partial-write corruption.
- **Permission model**: runner uses `--dangerously-skip-permissions`; sandbox configuration is the critical security surface. → Surfacing `overnight_start_run` via MCP extends this surface — see Adversarial §9 for operational-safety mitigations.
- **Defense-in-depth**: for sandbox-excluded commands (git, gh, WebFetch), allow/deny list is the sole enforcement layer. The MCP server itself runs with Claude Code's permissions — not the runner's elevated ones.

### Doc-ownership rule (CLAUDE.md, verbatim)

> Overnight docs source of truth: `docs/overnight-operations.md` owns the round loop and orchestrator behavior, `docs/pipeline.md` owns pipeline-module internals, and `docs/sdk.md` owns SDK model-selection mechanics. When editing overnight-related docs, update the owning doc and link from the others rather than duplicating content.

**Placement decision**: **new `docs/mcp-server.md`** as a control-plane sibling to `overnight-operations.md` / `pipeline.md` / `sdk.md`. MCP is a separate interface plane — not round-loop, not pipeline internals, not SDK model-selection. Cross-link from `overnight-operations.md` and the plugin `README.md`.

### DR-1 prerequisites (research/overnight-layer-distribution/research.md:236-242, verbatim)

> IPC contract the runner must expose (prerequisite for the MCP control plane):
> - Versioned state-file schema in `lifecycle/overnight-state.json` — `schema_version` field; external consumers can detect compat breaks
> - Explicit subcommands: `cortex overnight start`, `cortex overnight status <id>`, `cortex overnight cancel <id>`, `cortex overnight logs <id> [--tail]`
> - PID + PGID record at `lifecycle/sessions/{id}/runner.pid` written atomically on start, removed on clean exit; `cancel` sends signal to PGID
> - `events.log` / `agent-activity.jsonl` gain a cursor protocol (byte offset or line number) so `logs --since <cursor>` is idempotent and cheap

All four prerequisites are implemented in the codebase today.

### Conflicts with other requirements

- **None direct**. Cloudflare/remote-MCP is explicitly deferred per DR-3 and `requirements/project.md`; ticket is local-MCP + CLI, aligned.
- **Observability consumers** (requirements/observability.md): dashboard + statusline read `~/.local/share/overnight-sessions/active-session.json` and per-session `overnight-state.json`. Cursor-based log reads are additive; must not break existing readers (they don't use cursors today).
- **Remote-access** (requirements/remote-access.md): terminal persistence via tmux/mosh/Tailscale — no MCP overlap.

### Test conventions

- Python pytest under `tests/`; shell-script regressions for hooks/skills; slow tests gated via `@pytest.mark.slow` (`--run-slow` opt-in).
- Fixture pattern: `tmp_path / "lifecycle" / "sessions" / "{session_id}"` with minimal `overnight-state.json` + `runner.pid` + `overnight-events.log` samples.
- Existing patterns to reuse: `tests/test_cortex_overnight_security.py` (R17/R18 session-id regex, realpath containment, PID verification, E2E cancel), `tests/test_lifecycle_state.py` (parametrized fixture-based phase detection).
- Gating per pipeline.md: **complex tier at any criticality → review**. This ticket will go through orchestrator review at phase boundaries and post-merge spec-compliance review.

---

## Tradeoffs & Alternatives

| Alt | Verdict | One-line reason |
|---|---|---|
| A — In-process runner hosted by MCP server | **Reject** | Runner must outlive Claude Code sessions; DR-1 settled. Document once so rejection is durable. |
| B — Push notifications vs. pull polling | **Reject (park)** | Claude Code's stdio client doesn't render progress notifications visibly today (anthropics/claude-code#4157); long-lived tool calls eat context. Revisit when SEP-1686 ships stable + Claude Code renders notifications. |
| C — Unix socket vs. state-file polling | **Reject** | State files survive runner death and answer historical queries; sockets add runtime coupling and macOS path-length limits. |
| D — Cursor encoding: byte offset / line / opaque | **Opaque encoding `{offset, file_size_at_emit}` base64-JSON** | Meets MCP spec mandate for opacity; `file_size_at_emit` enables truncate-detection (Adversarial §3); offset wins on read cost. Inode is unreliable (APFS reuse). |
| E — Versioning policy | **Integer monotonic `schema_version`** | Matches existing convention (`state.py:269`); Terraform-style; verifier refuses unknown future versions (Adversarial §10). |
| F — `list_sessions` shape | **`{active: [...], recent: [last 10], total_count}`** with optional `status` / `since` / `limit` filters | Bounded by default, fits well under 25 K; filters enable drilldown. |
| G — Single server vs. multiple | **Single `cortex mcp-server`** with tool-name grouping (`overnight_*`) | 5-tool schema is ~2–3 K tokens/turn; conditional registration via `CORTEX_MCP_DISABLE` env as future escape hatch. |

**Recommended approach overall**: implement the ticket as written, with the refinements above, plus the MUST-fix mitigations from Adversarial Review. Net scope grows by: (i) runner-layer `O_CREAT|O_EXCL` lock, (ii) `verify_runner_pid` unknown-future-version check, (iii) `confirm_dangerously_skip_permissions: Literal[True]` arg on `overnight_start_run`, (iv) server-side max-bytes-read on every file-touching tool, (v) `stdin=stdout=stderr=DEVNULL` on MCP-spawned runner. Everything else (cursor codec, integer versioning, 25 K pagination, single-server design) follows the codebase's existing conventions.

---

## Adversarial Review

### MUST fix before merge

- **(A1) Concurrent-start race.** `runner.py:464-481` `_check_concurrent_start` is read-then-write (read runner.pid → verify → write). Two concurrent `overnight_start_run` calls (two MCP servers on the same repo, or two tool calls in one turn) both read `None`, both spawn, both write `runner.pid` (last wins). Result: two orchestrators editing the same `lifecycle/sessions/{id}/` artifacts, corrupted session, two parallel sets of Opus tokens, first runner orphaned from cancel. Race window ~tens to hundreds of ms during `_start_session`. **Fix**: atomic `O_CREAT|O_EXCL` on `session_dir/runner.lock` as the claim, *before* any runner-start work. On `FileExistsError`, read the lock, run `verify_runner_pid` semantics, fail fast or self-heal-then-retry-once. Lives in the **runner layer** — MCP and CLI both inherit.
- **(A2d) Cancel does not traverse into orchestrator/batch_runner PGIDs.** `start_new_session=True` at `runner.py:599,654` puts each child in its own PGID; `os.killpg(runner_pgid, SIGTERM)` signals only the runner. The runner's SIGTERM handler must explicitly propagate to its children, or cancel leaves orphan `claude -p` orchestrators burning tokens. **Fix**: verify the runner's signal handler propagates; add a test that starts the runner, sends SIGTERM to its PGID, and asserts no `claude` processes remain.
- **(A4) Decline `_meta["anthropic/maxResultSizeChars"]`.** Setting this on `overnight_logs` lets a single call inject ~125 K tokens into Claude's context — 60% of a 200 K window. The model is the wrong adjudicator. Pagination at the 25 K cap via opaque cursors is the primary path; for one-shot postmortem dumps, users can run `cortex overnight logs` in a terminal.
- **(A6a) Server-side max-bytes-read on every file-touching tool.** An MCP server that blocks reading a gigabyte log file hangs the tool call until Claude Code's timeout (~60s). **Fix**: every file read in a tool honors a server-side max-bytes budget and an asyncio cancel token.
- **(A7-G3) Spawn runner with `stdin=stdout=stderr=DEVNULL`.** If the MCP server spawns the runner without DEVNULL-ing stdio, the runner inherits the server's pipes (connected to Claude Code's JSON-RPC stream) and can pollute it. **Fix**: explicit `subprocess.Popen(..., stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)`.
- **(A9) `overnight_start_run` operational-safety gate.** The runner uses `--dangerously-skip-permissions`; today users consent by typing the CLI command. With MCP, an assistant could innocently invoke `overnight_start_run` on a vague user question and burn hours of Opus tokens unattended. **Fix**: required parameter `confirm_dangerously_skip_permissions: Literal[True]` whose parameter name encodes the warning back at the model; tool description leads with: *"This tool spawns a multi-hour autonomous agent that bypasses permission prompts and consumes Opus tokens. Only call when the user has explicitly asked to start an overnight run."* This is the **most important safety concern in the review**.
- **(A10) `verify_runner_pid` must refuse unknown future schema versions.** Currently `ipc.py:127-165` checks `schema_version >= 1`. A future v2 with breaking changes would pass this check and cancel would use v1 logic against a v2 runner. **Fix**: `1 <= schema_version <= MAX_KNOWN_VERSION`.

### SHOULD document or fix soon

- **(A2a) Clock-step false-negative cancel.** ±2s tolerance against `psutil.Process.create_time()` is correct as defense against PID wrap, but a manual `sntp -sS` step > 2 s will make legitimate cancel self-heal (clear the lock) while the runner keeps running silently. **Mitigation**: add a boot-time anchor (`psutil.boot_time()`) to the runner.pid so `create_time - boot_time` stays stable under wall-clock steps; or widen to 60s with an explicit monotonic-clock cross-check. Document the residual risk either way.
- **(A3) Truncation-then-regrow silent corruption.** Byte-offset cursors cannot detect "file shrunk, then grew past old offset" — seek lands in the middle of an unrelated record. **Fix**: cursor encodes `file_size_at_emit`; reader declares `cursor_invalid` when current size < cursor size, forcing the client to re-baseline.
- **(A5) Tool schema registration cost.** 5 tools × full Pydantic input+output ≈ 1.5–3 K tokens per turn even when overnight isn't in use. **Mitigations**: skip output schemas (FastMCP supports input-only), compact input schemas (plain types, validation in tool body), ship `CORTEX_MCP_DISABLE=overnight` env opt-out. Do not collapse to `dict[str, Any]` — loses model self-correction on field names.
- **(A7-G2) App Nap on headless runner.** An MCP-spawned runner with no controlling tty can be put to sleep when the laptop lid closes. **Mitigation**: the runner self-spawns `caffeinate -i $$` on macOS when it detects no tty, or fails loudly.
- **(A8) Reject dylan-gluck framing in spec.** No UUID `job_id`; tools accept `session_id` and auto-discover from `active-session.json`. Tools are thin wrappers over `cli_handler.py` functions; MCP server is stateless.
- **(A10-escalations) Resolve `escalations.jsonl` per-session vs repo-level.** Ticket implies per-session; codebase has repo-level (`logs.py:31-35`). Pick explicitly in spec: (a) MCP reads repo-level and filters by session_id (requires escalation records to embed `session_id` — verify), (b) change runner to write per-session, or (c) exclude escalations from `overnight_logs` until per-session lands.

### MAY defer

- (A2b/2c) PID-wrap and PID-reuse-within-2s false-positive — document.
- (A3-corruption) Mid-file NUL corruption on power loss — current skip-malformed-line behavior is acceptable.
- (A6b) `kill -9` on MCP server requires Claude Code session restart — document.
- (A9-audit) Audit log of `overnight_start_run` invocations to `~/.local/share/overnight-sessions/audit.log` for postmortem.

### Assumptions that may not hold

- "Runner is a singleton per repo" — true only if enforced; user discipline is insufficient when MCP makes start a one-line tool call.
- "PGID-aware cancel reaches all children" — **false**; `start_new_session=True` on each child defeats this. Signal propagation relies on the runner's handler.
- "Consumers re-baseline cursors on file changes" — no mechanism to *detect* change; truncate-regrow silently corrupts.
- "Stdio MCP server killed with session = no leftover state" — true for MCP server, false for runner; cleanup for orphaned runners is out-of-band (consider `cortex overnight cancel --all-stale` periodic).
- "`schema_version` protects forward compat" — currently decorative; only `verify_runner_pid` reads it, and only with `>= 1`. Enforcement is in scope.

---

## Open Questions

1. **escalations.jsonl — per-session vs. repo-level**. Codebase (`logs.py:31-35`) has `escalations.jsonl` at repo-level; ticket body implies per-session. Do escalation records embed `session_id` today? If yes, option (a) — MCP reads repo-level and filters. If no, option (b) or (c). *Deferred: will be resolved in Spec by asking the user or inspecting the current escalations.jsonl format.*
2. **macOS launchd/loginwindow detached-runner survival at user logout**. `start_new_session=True` detaches from the POSIX session but not the macOS audit session. `nohup` processes empirically survive logout on macOS but it is not spec-guaranteed. *Deferred: will be resolved in Spec by a single manual test (spawn detached process, logout+re-login, check survival).*
3. **Claude Code MCP Tasks client capability**. SEP-1686 shipped experimental server-side in MCP 2025-11-25; Claude Code's public MCP docs do not document client-side Task support as of 2026-04. This affects only the "out of scope" posture — not the critical path. *Deferred: ticket 116's "SEP-1686 out of scope" decision stands regardless.*
4. **Plugin distribution UX vs. CLI distribution UX for `cortex mcp-server`**. Ship via the `cortex-overnight-integration` plugin's `.mcp.json` (auto-registers on `/plugin install`) or require users to `claude mcp add`. Same server binary either way; only registration UX differs. *Deferred: spec-phase decision, orthogonal to the MCP server's implementation.*
5. **Unit test strategy for MCP tool-layer invocation**. Existing tests hit `cli_handler.py` directly. MCP tools wrap the same functions, so the test surface is mostly covered; need to decide whether to also unit-test via `FastMCP.test_client` (adds a dependency on a testing harness). *Deferred: will be resolved in Plan.*
