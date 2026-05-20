# Research: Wire daytime dispatch through cortex CLI + MCP with process-detachment

Clarified intent: give daytime dispatch a CLI verb + MCP tool surface that lets a Claude session initiate dispatches without hitting `EPERM: mkdir ~/.claude/session-env/<child-uuid>/`, while preserving direct `cortex-daytime-pipeline` invocation from a fresh terminal as a regression guard.

Surface scope (per user): one CLI verb (`cortex daytime start`) + 4 MCP tools (`daytime_start_run`, `daytime_status`, `daytime_logs`, `daytime_cancel`). No `schedule`, no `list-sessions`.

## Codebase Analysis

### Overnight CLI verb structure (pattern to mirror)

- `pyproject.toml:22` — `cortex = "cortex_command.cli:main"` console script.
- `cortex_command/cli.py:769` — `main()` builds argparse tree and dispatches.
- `cortex_command/cli.py:378-456` — `overnight start` subparser with `--format {human,json}`, hidden `--launchd` flag. Default handler is `_dispatch_overnight_start` at `cli.py:48` which lazy-imports `cli_handler.handle_start`.
- `cortex_command/overnight/cli_handler.py:460-637` — `handle_start()` production logic.

Conventions to follow verbatim:
- JSON output prefixed with `"schema_version": "2.0"` via `_emit_json()` (`cli_handler.py:104-117`).
- Schema floor `_JSON_SCHEMA_VERSION = "2.0"` (`cli_handler.py:107`).
- Internal `--launchd` flag is `argparse.SUPPRESS`-hidden (`cli.py:450-455`); signals "you ARE the runner, skip the re-fork" (`cli_handler.py:603-611`).
- `--dry-run` and `--launchd` both short-circuit the async-spawn fork and call the inline runner — order matters: `--dry-run` is checked first to preserve stdout-streaming test contracts (`cli_handler.py:561-611`).

### Overnight MCP tool implementation pattern

- `plugins/cortex-overnight/server.py:2327-2419` — `_delegate_overnight_start_run`. Canonical model for `_delegate_daytime_start_run`.
- Pattern: `_gate_dispatch()` → build argv `["overnight", "start", "--format", "json"]` → wrap `_run_cortex(argv, timeout=_START_RUN_TOOL_TIMEOUT)` in `_retry_on_cli_missing` → branch on stdout content.
- `_run_cortex` (server.py:2225-2248): `subprocess.run(_resolve_cortex_argv() + argv_tail, capture_output=True, text=True, timeout=timeout)` — **no `check=True`** per Technical Constraints.
- Stdout branching: empty stdout + returncode 0 = "spawn confirmed, runner detached"; stdout JSON = structured refusal envelope.
- `_START_RUN_TOOL_TIMEOUT = 30.0` (server.py:2323) preserves headroom for slow-disk cases.
- Pydantic input/output models with `model_config = ConfigDict(extra="ignore")` for forward-compat (server.py:2059-2066).
- **Security gate (load-bearing)**: `confirm_dangerously_skip_permissions: Literal[True]` is the operational gate on `overnight_start_run` (`StartRunInput`, server.py:2049-2053). Pydantic Literal type means FastMCP cannot bypass it.

### What "Task 6 async-spawn refactor" actually is

The string at `server.py:2329` references `cli_handler._spawn_runner_async` (lines 317-457). That function does **plain process detachment via `setsid`-equivalent, NOT launchctl**:

```python
# cli_handler.py:377-384
child = subprocess.Popen(
    argv,
    stdin=subprocess.DEVNULL,
    stdout=stdout_fd,
    stderr=stderr_fd,
    start_new_session=True,
    close_fds=True,
)
```

Handshake polls `runner.pid` via `wait_for_pid_file` (`scheduler/spawn.py:50`).

`launchctl bootstrap` only enters the picture for `cortex overnight schedule` (future-scheduled launches). Even there, the actual runner detachment happens inside `scheduler/launcher.sh` via `setsid nohup`, not by launchctl itself — launchctl owns the wake-up timer (`cortex_command/overnight/scheduler/macos.py:248-336`, `scheduler/launcher.sh:144-158`).

### Daytime pipeline entry point (existing, do NOT refactor internals)

- `pyproject.toml:33` — `cortex-daytime-pipeline = "cortex_command.overnight.daytime_pipeline:_run"`.
- `cortex_command/overnight/daytime_pipeline.py:568-583` — argparse `--feature <slug>` required, no validator; `_run()` does `sys.exit(asyncio.run(run_daytime(args.feature)))`.
- `run_daytime()` (lines 308-565):
  - `_check_cwd()` (line 316) — must be in a cortex project root.
  - Reads `DAYTIME_DISPATCH_ID` env (line 320; `_check_dispatch_id` line 266); mints a fresh uuid4 hex with stderr warning if missing.
  - Writes `cortex/lifecycle/{feature}/daytime.pid` — **plain integer file**, no JSON, no schema, no magic, no pgid (lines 71, 107-113).
  - `_is_alive(pid)` uses bare `os.kill(pid, 0)`; treats `PermissionError` as alive (lines 86-104).
  - `session_id = os.environ.get("LIFECYCLE_SESSION_ID") or f"daytime-{feature}-{int(time.time())}"` (lines 395-397).
  - On completion writes `DaytimeResult` to `cortex/lifecycle/{feature}/daytime-result.json` (line 559) with `schema_version=1`.
- `cortex_command/overnight/daytime_result_reader.py:163-167` — **hard equality check `schema_version == 1`**; any additive field changes need to land via Pydantic-style extra-ignore on read, not by bumping the version.

### Per-spawn sandbox tempfile pattern (and why it CANNOT fix EPERM alone)

- `cortex_command/overnight/sandbox_settings.py` is the canonical library. `build_sandbox_settings_dict(deny_paths, allow_paths, soft_fail)` (line 171) builds `{"sandbox": {"enabled": True, "failIfUnavailable": ..., "filesystem": {"denyWrite": ..., "allowWrite": ...}}}`. `write_settings_tempfile` writes 0o600 to `<session_dir>/sandbox-settings/cortex-sandbox-*.json` (line 222). Cleanup via `atexit.register` on clean shutdown + startup-scan in runner-init for crash paths.
- Caller usage: `cortex_command/pipeline/dispatch.py:562-635` — per-dispatch settings JSON with deny=[], allow=worktree + 6 `OUT_OF_WORKTREE_ALLOW_WRITERS`; passed via `ClaudeAgentOptions(settings=str(tempfile_path))`.
- **Critical**: `enableWeakerNestedSandbox: False` is set in `sandbox_settings.py:197`. This pattern configures the **child's** sandbox via `--settings`; it cannot **widen** the parent's grants. Parent's Seatbelt is the hard upper bound (kernel-enforced).

### Overnight `runner.pid` schema (recommended pattern for daytime.pid)

`cortex_command/overnight/ipc.py`:
- Schema: `{schema_version: 1, magic: "cortex-runner-v1", pid, pgid, start_time, session_id, session_dir, repo_path}` (lines 274-283).
- Constants: `_RUNNER_MAGIC = "cortex-runner-v1"`, `_SCHEMA_VERSION = 1`, `_START_TIME_TOLERANCE_SECONDS = 2.0` (lines 82-85).
- Mode 0o600 atomic O_EXCL claim (lines 250-251, 201).
- Verification: `verify_runner_pid` (lines 392-403) checks `psutil.Process(pid).create_time()` within ±2s.
- Takeover lock at `<session_dir>/.runner.pid.takeover.lock` (5s budget).
- `cortex overnight cancel` uses `os.killpg(pgid, SIGTERM)` (`cli_handler.py:1124`) — the stored `pgid` field is load-bearing for clean teardown of `claude -p` subprocesses.

### MCP plugin distribution & install

- `plugins/cortex-overnight/.mcp.json` registers `cortex-overnight` with `command: "uv", args: ["run", "${CLAUDE_PLUGIN_ROOT}/server.py"]`.
- `plugins/cortex-overnight/.claude-plugin/plugin.json` is metadata only — `{name, description, author}`. Tools discovered at runtime from `@server.tool` decorators.
- `plugins/cortex-overnight/server.py:106` — `CLI_PIN = ("v2.0.0", "2.0")`. `MCP_REQUIRED_CLI_VERSION = CLI_PIN[1]` is the schema floor (line 113).
- R1 invariant: server.py has zero `cortex_command.*` imports (line 13-15).

### `session_id` emission sites

1. `cortex_command/overnight/events.py:224` — `session_id = os.environ.get("LIFECYCLE_SESSION_ID", "manual")`.
2. `cortex_command/pipeline/dispatch.py:597` — same fallback.
3. `cortex_command/overnight/sandbox_settings.py:396` — same fallback.

Propagation: `cortex_command/overnight/runner.py:2012` sets `os.environ["LIFECYCLE_SESSION_ID"] = session_id` early so children pick it up. For detached daytime children, the wrapper should mint `daytime-<feature>-<epoch>` and set it as `LIFECYCLE_SESSION_ID` in the spawn env.

### `DAYTIME_DISPATCH_ID` contract (do not break)

`daytime_pipeline.py:267-287` — pipeline expects `DAYTIME_DISPATCH_ID` env preset by caller; mints a fresh uuid4 with stderr warning if missing. The lifecycle skill's `implement.md` §1a writes `cortex/lifecycle/{feature}/daytime-dispatch.json` BEFORE spawning, via `daytime_dispatch_writer.py`, so the dispatch_id is co-written and the freshness check at `daytime_result_reader.py:185-189` works. **The new wrapper MUST either (a) mint `DAYTIME_DISPATCH_ID` and write `daytime-dispatch.json` itself, or (b) document that the caller (MCP tool) is responsible.**

### MCP control plane contract

- `docs/internals/mcp-contract.md:1-36` — schema versioning: `version` (PEP 440 package) + `schema_version` (M.m envelope) on every payload. Current `schema_version = "2.0"`.
- Forever-public-API rule applies to `cortex --print-root`'s 5 fields, append-only. Adding new verbs is additive (no major bump required unless field shapes change).
- `docs/internals/mcp-contract.md:70-90` documents the structured concurrent-runner refusal envelope and the "successful starts produce no stdout JSON" contract — daytime should mirror this exactly.

### Files that will change

**Created:**
- `cortex_command/overnight/daytime_cli_handler.py` (or extend `daytime_pipeline.py` with `handle_start`/`handle_status`/`handle_logs`/`handle_cancel` symmetric to overnight).
- `plugins/cortex-daytime/` (server.py, .mcp.json, .claude-plugin/plugin.json) **— recommended over embedding in `cortex-overnight`** (see Tradeoffs §1 and Adversarial §6).
- `tests/test_daytime_cli_detached_spawn.py` (ticket Acceptance) — must include a from-Claude-session test, not just fresh-terminal.
- `docs/daytime-operations.md` — explains the two entry points, the actual escape mechanism, and the explicit Seatbelt-dependency caveats.

**Modified:**
- `cortex_command/cli.py` — add `daytime` subparser mirroring `overnight` (cli.py:378-456 pattern).
- `cortex_command/overnight/daytime_pipeline.py` — promote `daytime.pid` schema to include `magic`, `pgid`, `start_time`; add feature-slug validator; close the TOCTOU window in `_recover_stale`. **The ticket's out-of-scope says no internals refactor — these are minimal, surgical PID-handling fixes, not internals work. Spec must explicitly call out which lines change.**
- `cortex_command/install_guard.py` — extend tripwire to consult daytime PID files (or have daytime register in `active-session.json`).
- `docs/internals/mcp-contract.md` — add daytime verbs to JSON payload reference.
- `docs/mcp-server.md` — add daytime tools to inventory.
- `docs/overnight-operations.md` — link to new daytime doc.

## Web Research

### macOS Seatbelt sandbox inheritance — what propagates, what breaks it

- Seatbelt sandbox state is inherited by `fork()` and survives `execve()`. From Chromium sandbox docs (https://chromium.googlesource.com/chromium/src/+/HEAD/sandbox/mac/README.md) and macOS sandboxing reference: "Once applied, sandbox profiles inherit to every child process and **cannot be removed from inside**." A sandboxed process that nests `sandbox_init`/`sandbox-exec` traps — "the macOS sandbox doesn't nest." Violations return `EPERM` at the syscall (matches the spec failure mode).
- **Microsoft Security Blog on CVE-2022-26706** (https://www.microsoft.com/en-us/security/blog/2022/07/13/uncovering-a-macos-app-sandbox-escape-vulnerability-a-deep-dive-into-cve-2022-26706/): "Processes launched via the LaunchService.framework **don't inherit** the sandbox restriction."
- **jhftss "A New Era of macOS Sandbox Escapes"** (https://jhftss.github.io/A-New-Era-of-macOS-Sandbox-Escapes/): "LaunchAgents created by launchd won't inherit sandbox rules enforced onto a parent application."
- HackTricks macOS sandbox page: "The `open` command doesn't create child processes on its own; instead it performs IPC with macOS Launch Services, whose logic is implemented in the context of the launchd process, which then launches the app and is not restricted by the caller's sandbox."

### What does NOT break inheritance

- `os.setsid()` / `start_new_session=True` / classic double-fork: session-ID/TTY detachment only. Python `subprocess` docs (https://docs.python.org/3/library/subprocess.html), Linux setsid(2) man page (https://man7.org/linux/man-pages/man2/setsid.2.html), and Apple Developer Forums "fork is no-no but why?" (https://developer.apple.com/forums/thread/747499) all describe these as session-leadership/TTY-detachment, not security context. **None of these touch the Seatbelt label the kernel attaches to the process.**
- `nohup`: pure TTY/SIGHUP detachment.
- `subprocess.Popen` with any flags: still a direct fork+exec from the sandboxed parent; the kernel-attached profile rides along.

### Claude Code official sandbox documentation

- https://code.claude.com/docs/en/sandboxing: "These OS-level restrictions ensure that **all child processes spawned by Claude Code's commands inherit the same security boundaries**." Official confirmation that fork-exec inheritance is by design.
- https://code.claude.com/docs/en/settings: `sandbox.filesystem.{allowWrite,denyWrite,allowRead,denyRead}` arrays merge across scopes (user/project/local/managed) — they concatenate and dedupe, not override.
- `--dangerously-skip-permissions`: turns off the permission *prompt*; does NOT lift Seatbelt. The flag is no-op when Claude detects it's already inside a recognized sandbox. **You cannot make an inner Claude session unsandboxed via this flag.**
- `dangerouslyDisableSandbox` (per-Bash-tool parameter, distinct from the CLI flag): the in-session escape hatch for individual Bash commands. User can disable via `"allowUnsandboxedCommands": false`. Affects the Bash invocation, not a child Claude session.
- `~/.claude/session-env/<uuid>/` directory pattern is undocumented in public docs. Only visible references: env vars `CLAUDE_SESSION_ID`, `CLAUDECODE=1`, and `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1` (https://www.turboai.dev/blog/claude-code-env-vars-v2-1-83). Treat as observed behavior, do not depend on stability across releases.

### MCP server stdio conventions

- MCP Python SDK + FastMCP (https://github.com/modelcontextprotocol/python-sdk, https://gofastmcp.com/deployment/running-server): stdio servers are subprocess-spawned by Claude Code; line-delimited JSON-RPC 2.0; stderr reserved for logs.
- **Tool naming budget**: Claude Code prefixes plugin-wrapped MCP tools as `mcp__plugin_<plugin>_<server>__<tool>`. **64-character API limit applies** to the full name (claude-code issues #20830, #21846). Compounded plugin+server+tool names can exceed it.
- Background-job MCP server convention (https://github.com/dylan-gluck/mcp-background-job, https://www.arsturn.com/blog/no-more-timeouts-how-to-build-long-running-mcp-tools-that-actually-finish-the-job): the established quartet for async work is `start_*`, `status`/`wait_*`, `output`/`logs`/`tail`, `cancel`/`kill`. **The user's chosen 4-tool surface (start/status/logs/cancel) is canonical and aligned with prior art.**

### CLI verb design for "start a detached job, return JSON envelope"

- Closest prior art: `docker run -d` (returns container ID), `systemd-run --user --scope` (returns unit name), `kubectl create -o json`, `gh run watch --json`. None standardize on a single JSON shape; the ticket's `{started, pid, feature, started_at}` is well-aligned.
- Anti-pattern: returning child's stdout/stderr inline. Convention is to write logs to a file the `logs`/`tail` tool reads later — exactly what the spec implies.

### launchctl best practices

Sources: launchd.info, https://www.alansiu.net/2023/11/15/launchctl-new-subcommand-basics-for-macos/, ss64 launchctl, Apple Developer Forums.

- Modern syntax (`load`/`unload` deprecated):
  - Load: `launchctl bootstrap gui/$UID ~/Library/LaunchAgents/<label>.plist`
  - Unload: `launchctl bootout gui/$UID/<label>`
  - Force-restart loaded: `launchctl kickstart -k gui/$UID/<label>`
- For a one-shot fire-and-forget invocation: minimum plist is `Label` + `ProgramArguments`; include `RunAtLoad=true` and program self-exits.
- **Gotchas**:
  - If you `bootout` a disabled service, you must re-`enable` it before re-`bootstrap`.
  - Error 5 / "Bootstrap failed" common cause: plist still claimed by previous session (need `bootout` first).
  - Same label re-`bootstrap` without `bootout` fails — rotate label per invocation (uuid-suffixed) or `bootout` defensively.
- Cleanup pattern: have the program itself `launchctl bootout gui/$UID/<own-label>` + `rm` of plist in its final cleanup hook (Jamf community pattern: https://community.jamf.com/t5/jamf-pro/launch-script-once-via-launchd-library-launchagent-and-remove/m-p/89027).
- `SMAppService` is the Apple-blessed future replacement for sandboxed apps, but CLI from a user shell using `launchctl bootstrap` is current best practice.

## Requirements & Constraints

### "Daytime" is not documented as a named subsystem

- `cortex/requirements/project.md:11`: "Day/night split: Daytime is iterative collaboration; overnight is handoff; morning is strategic review, not debugging." — posture statement only.
- `cortex/requirements/project.md:17`: "Daytime work: Research before asking; don't fill unknowns with assumptions." — posture statement only.
- **No "daytime dispatch" subsystem is documented in `cortex/requirements/*`.** `daytime_pipeline` and `daytime_result_reader` modules appear once in `cortex/requirements/observability.md:144` as install-mutation audit classification only.
- `cortex/requirements/glossary.md` does not exist (directory contains only `multi-agent.md`, `observability.md`, `pipeline.md`, `project.md`, `remote-access.md`).
- **Natural docking point**: `pipeline.md` (owns the CLI verb structure and runner/MCP server contract). Cross-link from `multi-agent.md` if daytime reuses dispatch-spawn mechanics.

### CLI verb structure constraint (does not constrain daytime)

`pipeline.md:28` defines `cortex overnight {start|status|cancel|logs|schedule|list-sessions}`. This is scoped to overnight — **does not mandate parity with daytime, does not prescribe a daytime verb surface, does not prohibit a smaller daytime surface**. The user's chosen omission of `schedule`/`list-sessions` is internally consistent: daytime is per-feature and short-running; no scheduled multi-session backlog.

### MCP-tool surface and CLI_PIN coupling

`project.md:32`: "Schema-floor majors are forever-public-API per `docs/internals/mcp-contract.md`: **repurposing an existing field requires a major bump**." **Adding new MCP tools is not a major-bump trigger** under this rule.

`pipeline.md:153`: "`cortex mcp-server` exposes five stdio tools ... wrapping `cli_handler` boundaries. The server is stateless; tools accept `session_id` and read filesystem-grounded state. `confirm_dangerously_skip_permissions: Literal[True]` is the operational gate on `overnight_start_run`."

The architectural pattern (stateless server, filesystem-grounded state, `cli_handler` wrappers, `Literal[True]` gate) is binding for new tools. The `Literal[True]` gate is scoped to `overnight_start_run` in the doc — but spec must mirror it for `daytime_start_run` as a security gate (see Adversarial §11).

### Per-spawn sandbox tempfile pattern (constraints if reused)

`pipeline.md:158`: tempfiles must be 0o600 + atomic-write; cleanup must cover both clean-shutdown (`atexit`) and crash paths (startup-scan); schema is documented Claude Code `sandbox.filesystem.{denyWrite,allowWrite}` shape; path layout `cortex/lifecycle/sessions/{session_id}/sandbox-settings/` is tied to a `session_id` namespace. **Reusing this pattern for daytime is allowed but does not solve the EPERM problem** (see Tradeoffs §C and Adversarial §1).

### Pre-install in-flight guard

`pipeline.md:154`: guard aborts when an active overnight session is detected (phase != `complete` AND `verify_runner_pid` succeeds). Carve-outs: pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, cancel-force. **No daytime marker today** — see Adversarial §5 for the gap.

### Hardcoded `.vscode`/`.idea` sandbox denies

`pipeline.md:167`: Claude Code's binary permanently blocks writes to these directories even when in `sandbox.filesystem.allowWrite`. Relevant if daytime reuses the per-spawn sandbox tempfile mechanism — Claude-binary-level constraint applies regardless of settings JSON.

### File-based state & atomic writes

- `project.md:27`: "Lifecycle, backlog, pipeline, sessions in plain files (markdown/JSON/YAML). No database." Daytime state must live in files.
- `pipeline.md:21,126`: "All state writes are atomic (tempfile + `os.replace()`)." Applies to any new daytime state files.
- `project.md:28`: `cortex init` is the only write cortex-command makes in `~/.claude/`; `fcntl.flock`-serialized. Daytime mechanisms writing elsewhere under `~/.claude/` would violate this.

### CLAUDE.md policy constraints

- **Solution horizon**: surface durable-vs-stop-gap tradeoff explicitly. Spec must call out whether the chosen mechanism is permanent or a bridge until upstream Claude Code changes.
- **Design principle: prescribe What and Why, not How**: spec describes the daytime dispatch behavior (escape parent Seatbelt state, surface diagnostics, expose CLI/MCP surface) — not procedural detachment steps, unless the mechanism is load-bearing (here it IS, see Adversarial §1).
- **MUST-escalation policy**: default to soft positive-routing in new authoring.

## Tradeoffs & Alternatives

### A. Architectural parity with overnight (actual launchctl)

Build a `cortex daytime start` CLI verb that, when invoked from a sandboxed context, writes a one-shot plist into `~/Library/LaunchAgents/` and calls `launchctl bootstrap gui/$UID <plist>` to spawn the pipeline as a launchd grandchild. Use uuid-suffixed labels to avoid bootout-before-rebootstrap. Self-clean via `launchctl bootout` + plist rm in the pipeline's final cleanup hook.

- **Pros**: Only documented kernel-layer Seatbelt escape (per web research §1 and archived research at `cortex/research/archive/overnight-runner-sandbox-launch/research.md:16`). Matches the ticket's "launchd detachment" framing literally. Provides a guarantee that does not depend on `dangerouslyDisableSandbox: true` being available.
- **Cons**: Plist write/cleanup machinery is new surface (~150 LOC); the `bootout` lifecycle has gotchas; macOS-only (would need a fallback or explicit "macOS-only" gate matching `cortex overnight schedule`'s pattern at `pipeline.md:28`). The Bash-tool path still EPERMs without `dangerouslyDisableSandbox: true` because the wrapper itself runs in the parent sandbox before reaching launchctl.

### B. Mirror overnight's actual run-now mechanism (Popen + start_new_session)

Use `subprocess.Popen(start_new_session=True)` from a daytime CLI verb, matching what `cli_handler._spawn_runner_async` does today. Document explicitly that:
- From a fresh terminal: works.
- From a Claude session via Bash tool: requires `dangerouslyDisableSandbox: true` (mirrors overnight's `skills/overnight/SKILL.md:77` invocation pattern).
- From a Claude session via MCP tool: works because the MCP server runs unsandboxed at hook trust level (`docs/overnight-operations.md:599`).

- **Pros**: Identical to overnight's production mechanism; least new surface (~30 LOC for the detachment, ~80 LOC for the MCP tool delegates); proven by overnight's daily use.
- **Cons**: Does NOT actually escape Seatbelt — relies on two unrelated harness behaviors. If Anthropic restricts `dangerouslyDisableSandbox` or makes MCP servers sandboxed in a future release, regresses to EPERM. Ticket's "launchd detachment" framing is misleading for this option.

### C. Per-spawn sandbox-settings adjustment

**Rejected**. Per `sandbox_settings.py:197` (`enableWeakerNestedSandbox: False`) and `docs/internals/sdk.md:199` (kernel-level Seatbelt enforcement), the child's allowWrite cannot widen the parent's grants. The child's UUID is also unknown at parent settings-write time. The pattern doesn't solve this problem.

### D. `--bare` mode / API-key auth migration

**Rejected**. Speculative: `--bare` doesn't appear in the cortex codebase; auth is forwarded today via `ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` (`dispatch.py:545-548`). The blocker is the Bash tool's unconditional `mkdir ~/.claude/session-env/<child-uuid>`, which is a property of the Claude binary, not auth mode.

### E. Document-only fix

**Rejected** (user choice + UX). Forces operators to break out of Claude Code into a fresh terminal for every dispatch; undermines the daytime UX promise. Silent failure mode for callers who don't read the docs.

### F. CLI verb only, no MCP tools

**Rejected** (user choice — see Clarify Q1). Creates an asymmetry where overnight has MCP tools but daytime does not. MCP-tool boilerplate is largely Pydantic models + thin delegate functions.

### Recommended approach: **A (real launchctl) — with a caveat**

The adversarial review and prior archived research at `cortex/research/archive/overnight-runner-sandbox-launch/research.md` agree that **launchctl-bootstrap is the only kernel-layer Seatbelt escape**. Alternative B works in practice today only because of two independent harness behaviors (`dangerouslyDisableSandbox: true` on Bash + MCP-being-unsandboxed) — neither of which the cortex project controls.

**Caveat**: a 3-line empirical test should run BEFORE locking in A. Run `cortex-daytime-pipeline --feature smoke` from a Claude session's Bash tool, once with `dangerouslyDisableSandbox: false` and once without. If the latter actually escapes via just `start_new_session=True`, Alternative B is viable — but prior research strongly predicts EPERM in both cases. The test belongs in the spec's acceptance criteria, not deferred to implementation review (see Adversarial §17 and §23).

If A is chosen: spec must (a) name the plist label scheme (uuid-suffixed), (b) document the bootout/cleanup pattern, (c) gate the verb to macOS with the same "scheduling requires macOS" error template overnight `schedule` uses, (d) explicitly write a non-macOS fallback path (graceful Popen for Linux/CI without claiming sandbox escape).

If B is chosen: spec must (a) rename the ticket's "launchd detachment" framing throughout, (b) explicitly document the two harness dependencies (`dangerouslyDisableSandbox: true` + MCP-unsandboxed-at-hook-trust-level), (c) call out the brittleness if either changes upstream.

## Adversarial Review

### Critical: the ticket's central premise is wrong

The ticket says: "Overnight's launchd detachment lets a Claude session call `overnight_start_run` via MCP and have the runner spawn in a fresh process tree — escaping the calling session's Seatbelt sandbox state."

**This is incorrect.** Overnight's run-now path uses `subprocess.Popen(start_new_session=True)`, NOT launchctl. `launchctl bootstrap` is only used for `cortex overnight schedule` (future-scheduled launches), and even there the actual detachment happens via `setsid nohup` inside `launcher.sh` (`scheduler/launcher.sh:144-158`).

The actual reason overnight works from inside a Claude session today is one of:
- **Bash-tool path** (`/overnight`, `/overnight resume`): the skill invokes Bash with `dangerouslyDisableSandbox: true` (`skills/overnight/SKILL.md:77`). The Bash invocation is unsandboxed, and the spawned `cortex overnight start` and its tree inherit "no sandbox," not "narrowed sandbox."
- **MCP path** (`overnight_start_run`): MCP servers run unsandboxed at hook trust level (`docs/overnight-operations.md:599`, https://code.claude.com/docs/en/plugins-reference). The MCP server's `subprocess.run` starts an unsandboxed child.

Direct evidence: archived research at `cortex/research/archive/overnight-runner-sandbox-launch/research.md:12,16` (macOS Seatbelt inheritance is one-way; `launchctl bootstrap`-spawned jobs do not inherit caller's seatbelt). Archived spec at `cortex/lifecycle/archive/migrate-overnight-schedule-to-a-launchagent-based-scheduler/spec.md:7` admits the implementation does not match its own rationale: the run-now path is bare Popen + `setsid`, only scheduled is real launchctl.

### Failure modes and edge cases

1. **Path traversal via `--feature`**: `daytime_pipeline.py:574` argparse `--feature` has no validator; `_write_pid` calls `pid_path.parent.mkdir(parents=True, exist_ok=True)`. A caller passing `--feature ../../etc/passwd-clone` creates the parent directory. **Wrapper CLI verb and MCP tool input model MUST apply `^[a-zA-Z0-9._-]{1,128}$` regex validation** (reuse `session_validation.py:15`-pattern) BEFORE argv construction. Pydantic `Field(pattern=...)` on the MCP model.

2. **TOCTOU concurrency**: `daytime_pipeline.py:377-393` reads-then-writes PID without a lock. Two concurrent dispatches both observe PID file absent → both enter recover-stale → both call `git worktree remove --force --force` on the same path. Mitigation: O_EXCL atomic claim like `ipc.py:201` (`_exclusive_create_runner_pid`).

3. **PID-recycling false positives**: `_is_alive(pid)` is bare `os.kill(pid, 0)` and treats PermissionError as alive (`daytime_pipeline.py:99`). Recycled PIDs (`vim`, `node`, `claude`) cause `concurrent_dispatch` refusals against unrelated processes. Mitigation: schema upgrade to include `magic="cortex-daytime-v1"` + `start_time` for ±2s psutil-`create_time` verification.

4. **`pgid` capture absent → cancel can't `killpg`**: Plain-integer PID file cannot support `os.killpg(pgid, SIGTERM)`. The pipeline spawns `claude -p` subprocesses (SDK); SIGTERM to the wrapper PID alone leaves SDK children orphaned to `init`. The `_orphan_guard` at `daytime_pipeline.py:244-263` only fires when `os.getppid() == 1` — there's a window where SDK children are still running and the user cannot kill them. **`daytime_cancel` MCP tool will leak SDK children** without `pgid`-based killpg.

5. **`install_guard` is blind to daytime**: `install_guard.py:71-73,288-294` only consults `~/.local/share/overnight-sessions/active-session.json`. Daytime never writes there (zero references in `daytime_pipeline.py`). A user running `cortex upgrade` during a live daytime dispatch is unguarded — upgrade can clobber the running pipeline. **Mitigation**: either (a) extend `check_in_flight_install_core` to scan `cortex/lifecycle/*/daytime.pid` for liveness, OR (b) have `daytime_pipeline.run_daytime` write/clear `active-session.json` like overnight does (`runner.py:865`).

6. **MCP tool name length budget**: With `mcp__plugin_cortex-overnight_cortex-overnight__` (44 chars) the safe budget for unprefixed tool name is 20 chars. `daytime_start_run` (17) = 64 chars total, AT the limit. `daytime_list_sessions` (21) would exceed it (68). With `mcp__plugin_cortex-daytime_cortex-daytime__` (40) the budget is 24 chars. **Use a separate `cortex-daytime` plugin**, not embedding in `cortex-overnight`. Secondary reason: the overnight plugin's `_gate_dispatch()` orchestrates schema-floor upgrade and `CLI_PIN` semantics scoped to overnight; bolting daytime on conflates release cadences.

7. **`DAYTIME_DISPATCH_ID` env contract**: `daytime_pipeline.py:267-287` expects the caller to set this and write `daytime-dispatch.json` BEFORE spawning. If the new wrapper spawns blindly without env propagation and dispatch-file priming, the freshness check at `daytime_result_reader.py:185-189` fails → result reader falls to Tier 2/3 "unknown" forever. **Spec MUST specify**: (a) whether the wrapper mints the dispatch_id and writes the dispatch JSON, or (b) leaves both to the MCP-tool caller, with explicit documentation of the contract either way.

8. **`daytime-result.json` schema_version is hard-equality `== 1`** (`daytime_result_reader.py:163-167`). The new wrapper's stdout JSON envelope `{started, pid, feature, started_at}` MUST be a separate envelope, not written into `daytime-result.json` — and any additive fields for forward-compat must use Pydantic `extra="ignore"`-style reading, not version bumps.

9. **Spawn-handshake omission silent break under disk pressure**: Overnight's `_SPAWN_HANDSHAKE_TIMEOUT_SECONDS = 5` with `wait_for_pid_file` doing both existence + liveness check. If daytime cuts the wait to 1 second (per Alternative B's "lighter" framing), disk-pressure machines (Time Machine, Spotlight) can return `started: false` while the pipeline actually launches 1.2s later → Claude session retries → two concurrent dispatches race on the worktree. **Use 5s like overnight**, not 1s.

10. **The ticket's "session_id: manual" empirical comparison conflates two factors**: ticket §Empirical evidence cites "fresh-terminal session_id=manual succeeded; from-Claude-session session_id=parent-uuid failed." But `session_id` is just `LIFECYCLE_SESSION_ID` env or default "manual" — zero causal relationship to whether the spawn escaped Seatbelt. The "manual" success could equally be because the fresh terminal wasn't sandboxed in the first place. Evidence does not distinguish "Popen escaped" from "parent shell wasn't sandboxed."

### Security concerns

11. **Prompt-injection sandbox-escape gate**: Today, MCP `overnight_start_run` is gated by `confirm_dangerously_skip_permissions: Literal[True]` (server.py:2049-2053). This Pydantic Literal type means FastMCP cannot bypass it. **`daytime_start_run` MUST mirror this exact `Literal[True]` gate**. Anything weaker — e.g., a plain `confirm: bool` field — accepts injected `True` from prompt injection. Ticket §2 mentions "feature slug + confirmation" but doesn't spell out the `Literal[True]` shape.

12. **Path traversal × no-sandbox-spawn** (compound of #1 and #11): Without server-side regex validation BEFORE argv construction, a prompt-injection-routed `daytime_start_run feature="../../../tmp/exfil"` creates `/tmp/exfil/` and operates on it as a "feature directory." Mitigation: validation at the Pydantic input model level, defense-in-depth at the CLI argparse level, and `assert_path_contained` at the wrapper level.

13. **`_recover_stale` destructive under attacker-controlled feature names**: `daytime_pipeline.py:142-168` calls `git worktree remove --force --force <worktree_path>` and `git worktree prune` on stale-PID detection. Cross-feature collision in `_worktree_path()` resolution destroys the wrong worktree. Input validation per #1 mitigates.

### Assumptions that may not hold

14. **"MCP server is unsandboxed forever"**: Per `sandbox-overnight-child-agents/research.md:27` citing GitHub issue #29048. Anthropic could change this in any release. If MCP servers gain Seatbelt enforcement, every cortex MCP tool that spawns subprocesses regresses to EPERM. Spec MUST document this dependency explicitly so a future Claude Code release that closes the gap surfaces a known break, not a silent regression.

15. **"`dangerouslyDisableSandbox: true` will always be available"**: Same risk. Overnight's CLI-Bash path (`skills/overnight/SKILL.md:77`) is brittle to changes here. Daytime CLI-Bash path inherits the same brittleness.

### Recommended mitigations (must be in spec)

- **Empirical Seatbelt test in acceptance criteria**: Run `python3 -m cortex_command.overnight.daytime_pipeline --feature smoke-test` from a Bash tool WITHOUT `dangerouslyDisableSandbox: true`. Confirm EPERM. Then run the same via the proposed wrapper — predict still-EPERM unless mechanism is real launchctl. This test belongs IN the acceptance criteria.
- **From-Claude-session MCP test**: Run `daytime_start_run` from a Claude session via MCP. Confirm `events.log` shows no `EPERM` events AND the pipeline reaches at least `feature_dispatched`. If either fails, the implementation does not solve the user's problem regardless of test-suite pass.
- **Mirror `Literal[True]` security gate** on `daytime_start_run` input model.
- **Feature-slug validator regex** at MCP input model + CLI argparse + wrapper layer.
- **Upgrade `daytime.pid` schema** to include `magic`, `pgid`, `start_time` matching overnight `ipc.py`.
- **Extend install_guard** to track daytime PID files OR have daytime register in `active-session.json`.
- **Separate `cortex-daytime` plugin** (not embedding in `cortex-overnight`).
- **5s spawn handshake**, not 1s.
- **Document `DAYTIME_DISPATCH_ID` ownership**: spec specifies whether wrapper or MCP-tool caller is responsible for minting + writing `daytime-dispatch.json`.

## Empirical Smoke Tests (run during research)

Both tests ran from this Claude session's Bash tool against `~/.claude/session-env/<test-uuid>/`:

| Test | Mechanism | Outcome |
|------|-----------|---------|
| 1 | `mkdir ~/.claude/session-env/test-direct...` directly via Bash | **EPERM** (`Operation not permitted`, rc=1) |
| 2 | `subprocess.Popen(..., start_new_session=True)` then mkdir from child | **EPERM** (`Operation not permitted`, errno 1, rc=1) |
| 3 | `launchctl asuser $UID python3 ...` (launchd re-exec) | Not run (user denied Bash permission for the launchctl invocation; no further empirical signal from this session) |

**Confirmed**: `Popen + start_new_session=True` does NOT escape Seatbelt inheritance. The web agent and archived research at `cortex/research/archive/overnight-runner-sandbox-launch/research.md` (RQ2, RQ4) were correct; the codebase agent and tradeoffs agent's claim that PGID detachment provides the escape was wrong.

**Implication for mechanism choice**: Alternative B ("mirror overnight's actual production mechanism") works in practice today ONLY because of harness behaviors orthogonal to `Popen + start_new_session`:
- `dangerouslyDisableSandbox: true` on the Bash invocation in the calling skill, OR
- MCP server running unsandboxed at hook trust level.

Without one of those harness behaviors, the daytime CLI verb's `Popen` spawn — like overnight's `Popen` spawn — emits a child that still hits EPERM on its first Bash-tool invocation. The spec MUST document both harness dependencies explicitly.

## Open Questions

1. **Mechanism choice — RESOLVED**: User selected Alternative B (mirror overnight's actual production mechanism: `subprocess.Popen(start_new_session=True)` + documented harness dependencies). The empirical smoke test confirms B's dependencies are load-bearing — the `Popen` detachment alone does NOT escape Seatbelt. Spec must document the two harness behaviors B relies on (`dangerouslyDisableSandbox: true` on Bash invocations; MCP-unsandboxed-at-hook-trust-level) and call out the brittleness if either changes upstream. The ticket's "launchd detachment" framing must be reworded throughout — the spec describes process-group detachment, not launchctl. Alternative A (real launchctl) and A+B hybrid remain durably-correct fallbacks if Anthropic restricts either harness behavior in a future release; spec should record A as the named upgrade path in a forward-compat note.

2. **Empirical pre-spec smoke test — RESOLVED**: Tests 1 and 2 ran (see table above). Test 3 (launchctl asuser) was permission-denied by the user; not retried, since the archived research at `overnight-runner-sandbox-launch/research.md:16` already states launchctl-bootstrap-spawned jobs do not inherit caller's seatbelt — independent confirmation isn't needed for this lifecycle. A from-Claude-session integration smoke test still belongs in the spec's acceptance criteria (per Adversarial §17, §23).

3. **`DAYTIME_DISPATCH_ID` ownership**: Does the new `cortex daytime start` wrapper mint the dispatch_id and write `daytime-dispatch.json`, or does the MCP-tool caller (or the lifecycle skill) own this? Deferred: needs spec-phase decision. The current lifecycle skill writes `daytime-dispatch.json` in `implement.md §1a` via `daytime_dispatch_writer.py`; if the wrapper does it too, ordering and dedupe must be specified.

4. **`active-session.json` participation**: Does daytime register in `~/.local/share/overnight-sessions/active-session.json`? The pointer is overnight-scoped by name; alternatives are (a) a sibling `daytime-sessions/active-session.json`, (b) reusing the overnight pointer with `phase: "daytime"`, or (c) leaving daytime out of the global pointer and adding daytime-aware logic to `install_guard`. Deferred: needs spec-phase decision.

5. **`cortex-daytime` plugin vs `cortex-overnight` extension** (recommended new plugin per Adversarial §6, but confirms with user): the name-length budget and conceptual separation argue for a new plugin; the install-step overhead argues for extending. Deferred: spec needs an explicit decision.

6. **PID schema upgrade scope**: The ticket out-of-scope says "no internals refactor of `daytime_pipeline.py`." Promoting `daytime.pid` from plain-integer to JSON+magic+pgid+start_time is technically internals work. Either (a) treat as in-scope (the PID-file write is ~5 lines and the read sites are limited), OR (b) write a parallel `daytime.pid.v2` file from the wrapper and have the wrapper's `cancel` consume that, leaving the existing pipeline's plain-integer write intact. Deferred: spec needs a call.

7. **What `session_id` does a detached daytime dispatch emit?** The codebase generates `daytime-<feature>-<epoch>` when `LIFECYCLE_SESSION_ID` is unset (`daytime_pipeline.py:395-397`). The ticket's acceptance criterion uses placeholder `<manual-style>`. Spec should pin the literal value the wrapper sets via env propagation.

8. **macOS-only gate**: `cortex overnight schedule` is macOS-only (`pipeline.md:28`). If the daytime verb uses launchctl, it inherits the same constraint. If it uses Popen, it's portable but provides weaker guarantees. The spec must explicitly state the OS gate and the fallback behavior on non-darwin.
