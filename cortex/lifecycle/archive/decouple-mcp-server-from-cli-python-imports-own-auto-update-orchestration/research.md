# Research: Decouple MCP server from CLI Python imports + own auto-update orchestration

Refactor the cortex MCP server into a thin protocol-translation layer with no shared Python imports against the CLI (versioned subprocess+JSON contract). Additionally, make the MCP server own auto-update orchestration so the MCP-primary user path stays current without an inline CLI gate.

Tier: complex. Criticality: high. Backlog: `146-decouple-mcp-server-from-cli-python-imports-via-subprocessjson-contract.md`.

Q#1 (sandbox-write probe from MCP-spawned subprocesses on macOS) is load-bearing: a negative result invalidates the entire MCP-orchestrated upgrade design and forces an alternative.

## Codebase Analysis

### Files that will change

**MCP server (decoupling target):**

- `cortex_command/mcp_server/tools.py` — replace in-process imports with subprocess+JSON. Currently imports:
  - `from cortex_command.overnight import cli_handler` (line 53) — used in `_resolve_repo_path()` and `_auto_discover_state()`.
  - `from cortex_command.overnight import ipc` (line 54) — used for `read_runner_pid`, `verify_runner_pid`, `clear_runner_pid`, `write_active_session`, `clear_active_session`.
  - `from cortex_command.overnight import logs` (line 55) — used for `LOG_FILES` mapping.
- `cortex_command/mcp_server/schema.py` — add `schema_version` field to every output Pydantic model.
- `cortex_command/mcp_server/server.py` — entry point unchanged in this refactor (will remain as the stdio MCP server module that the plugin invokes).

**CLI verb extensions (JSON output gaps):**

- `cortex_command/cli.py` — extend with new verbs and flags:
  - **New flag**: `cortex --print-root` (or `cortex root`) emitting `{"schema_version": 1, "root": "/abs/path", "remote_url": "...", "head_sha": "..."}`. Combines three round-trips into one.
  - **New JSON output**: `cortex overnight start --format json` for atomic-claim-collision response shape (today only exit-code and stderr text).
  - **New JSON output**: `cortex overnight logs --format json` (today plain-text streaming).
  - **Audit**: `cortex overnight cancel` for JSON support.
- `cortex_command/overnight/cli_handler.py` — `handle_start()` (line 106) calls `ipc.write_runner_pid()` which raises `ConcurrentRunnerError`; needs structured JSON exposure for the MCP atomic-claim pre-check path.

**Auto-update orchestration (new MCP-side logic):**

- New module (in plugin): update-check (`git ls-remote` vs local HEAD), skip-predicate evaluation (`CORTEX_DEV_MODE`, dirty tree, non-main branch), upgrade-orchestration (`cortex upgrade` + verification probe), `flock`-protected lock at `$cortex_root/.git/cortex-update.lock`, NDJSON error log at `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log`.

**Plugin distribution:**

- `plugins/cortex-overnight-integration/.mcp.json` (currently 9 lines pointing at `cortex mcp-server`) — repoint at plugin-bundled MCP via `uvx`.
- **New file** `plugins/cortex-overnight-integration/server.py` (PEP 723 single-file form recommended) OR `plugins/cortex-overnight-integration/server/` package. ~200–500 LOC.

**Tests:**

- `tests/test_mcp_subprocess_contract.py` (new) — unit tests mocking subprocess to verify each MCP tool invokes the right CLI verb and parses output correctly.
- `tests/test_mcp_auto_update_orchestration.py` (new) — update-check logic, skip predicates, flock concurrency.
- Concurrency tests follow the existing pattern in `cortex_command/init/tests/test_settings_merge.py:340-429` (threads/subprocesses contending for a flock).

**Documentation:**

- `docs/mcp-contract.md` (new) — the versioned JSON schema contract: every CLI verb the MCP consumes, schema, version, breaking-change rules.

### Existing patterns to reuse

- **Atomic write**: `cortex_command/common.py:366-407` `atomic_write(path, content)` — tempfile-in-same-dir + `durable_fsync()` + `os.replace()`. Reusable for NDJSON error log appends.
- **Sibling-lockfile + flock**: `cortex_command/init/settings_merge.py:69-85` `fcntl.flock(LOCK_EX)` on `~/.claude/.settings.local.json.lock`. Template for `$cortex_root/.git/cortex-update.lock`.
- **Subprocess for cortex orchestration**: `cortex_command/cli.py:85-119` `_dispatch_upgrade()` already uses `subprocess.run()` for git and uv commands. Pattern to reuse for MCP-side `cortex upgrade` invocation.
- **Subprocess for git path discovery**: `cortex_command/overnight/cli_handler.py:44-52` `subprocess.check_output()` for `git rev-parse`.
- **Schema versioning hard-equality**: `cortex_command/overnight/daytime_result_reader.py:163-165` `result_data.get("schema_version") != 1`.
- **Schema versioning range**: `cortex_command/overnight/ipc.py:52-54` magic + `1 <= schema_version <= MAX_KNOWN_RUNNER_PID_SCHEMA_VERSION`.
- **Existing MCP shell-out**: `cortex_command/mcp_server/tools.py:412-436` `_spawn_runner_subprocess` already shells out to `cortex overnight start` — the launcher path is partially aligned with the proposed pattern.
- **Structured tool errors**: `cortex_command/mcp_server/tools.py:714-721` raises `ToolError` with JSON body `{"error": "session_not_found", ...}`.

### Integration points with adjacent tickets

- **Ticket 116 (`build-mcp-control-plane-server-with-versioned-runner-ipc-contract`)** — `status: complete` per backlog. Schemas (runner.pid, active-session pointer, cursor-based logs, schema versioning) are stable. 146 aligns with 116's contract; no architectural conflict. Verify schema-version semantics (hard-equality vs forward-compat) before publishing.
- **Ticket 113 (epic distribution model)** — frames CLI install via `uv tool install -e .` + plugin install via `/plugin install`; no PyPI publishing. 146's auto-update mechanism preserves this (uses `git pull` + `uv tool install --force`, not registry).
- **Ticket 145** (`lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke/`) — closed/wontfix 2026-04-25; auto-update absorbed into 146. Prior-art research (`research.md`, `spec.md`) preserved. Reusable conclusions: TOCTOU shim-rewrite race verified empirically on user's APFS volumes (motivated 145's exit-and-rerun); skip-predicate semantics (`CORTEX_DEV_MODE` / dirty / non-main); verification probe via `cortex --help` post-install (insufficient — see Adversarial 9). 146's separate-subprocess composition eliminates the TOCTOU race that motivated exit-and-rerun.

### Conventions to follow

- Subprocess invocation: `subprocess.run(..., capture_output=True, text=True)` — never `check=True`; catch and handle errors explicitly. Set `timeout` on long-running calls (`timeout=5` on `git ls-remote`). Inherit env vars; do not scrub.
- Path resolution: prefer `git rev-parse --show-toplevel`; fall back to `$CORTEX_COMMAND_ROOT`; final fallback `$HOME/.cortex`. All paths absolute and resolved.
- Tempfiles for atomic writes: same directory as target (not `$TMPDIR` — must be same filesystem for rename atomicity).
- Test structure: unit tests mock `subprocess.run` via `unittest.mock.patch`; integration tests spawn real `cortex` binary; concurrency tests follow `init/tests/test_settings_merge.py` pattern.

## Web Research

### Q#1 (LOAD-BEARING): Claude Code sandbox is bash-only

**Per official Claude Code docs (https://code.claude.com/docs/en/sandboxing) — verbatim:**

> "**Sandboxing** provides OS-level enforcement that restricts what Bash commands can access at the filesystem and network level. **It applies only to Bash commands and their child processes.**"

> "Built-in file tools: Read, Edit, and Write use the permission system directly rather than running through the sandbox."

**Corroborating signals:**

- `anthropic-experimental/sandbox-runtime` README documents the *recommended* way to sandbox an MCP server: explicitly wrap its launch command with `srt`. This is implicit confirmation that MCP servers are NOT in the bash sandbox by default — the opt-in `srt` wrap would be redundant otherwise.
- GitHub issue #26616 (open feature request "Sandbox should isolate all tool execution, not just Bash") explicitly confirms scope: *"Claude Code's sandbox enforces filesystem and network restrictions only on the Bash tool and its child processes."*
- Issue #29688's process-tree dump confirms MCP servers are direct children of `claude-code/cli.js`, not of the sandboxed Bash process tree.

**Implication**: Writes from MCP-spawned `cortex upgrade` to `$cortex_root/.git/` and `~/.local/share/uv/tools/cortex-command/` should succeed *without* `cortex init` allowWrite registration. **However, the Adversarial Review (item 1) flags this as a positive-scope statement that does not preclude future MCP-sandboxing — and the cortex codebase itself has prior empirical observations that other Claude-Code-spawned processes hit Seatbelt-adjacent surfaces.** An empirical probe on the user's machine is still required before commit.

### Thin-MCP-around-CLI is the 2026 industry direction

- **alexei-led/aws-mcp-server** is the closest reference to the proposed pattern: two MCP tools (`aws_cli_help`, `aws_cli_pipeline`) that pure-shell-out to `aws`. Configurable subprocess behavior via env vars. No shared Python imports. Relies on `aws --output json` (no schema_version envelope).
- **Anti-pattern reference**: `containers/kubernetes-mcp-server` is a fat Go-native MCP that talks to the K8s API directly, NOT via `kubectl`. Worth citing in spec for contrast.
- 2026 community sentiment ("CLI is the new MCP" articles on oneuptime, dev.to, manveerc.substack) argues thin CLI-wrapping MCPs beat fat MCPs because (a) the model already knows CLI ergonomics from training, (b) `--help` and CLI-native JSON output is cheaper context than dumping a large tools schema. Matches cortex's proposal.
- **Schema versioning is more rigorous than industry default.** Most CLI-wrapping MCPs do not add a `schema_version` envelope; cortex's plan is more rigorous — keep it.

### uvx as Python MCP distribution

- Official MCP Python SDK recommends `uv` + `pyproject.toml`-style packaging.
- PEP 723 single-file is widely used in community MCPs (`#!/usr/bin/env -S uv run --script` + inline `# /// script` block). Good for one-file distribution; weaker for multi-module testing.
- **uvx caching wart**: per docs.astral.sh/uv/concepts/cache, uvx caches per-script-hash; first-run network resolution; LRU eviction can re-resolve.
- **Critical pin discipline**: AWS MCP issue #2533 hit fastmcp 3.x cold-cache breakage from bare `dependencies = ["fastmcp"]`. **Cortex must pin majors**: `dependencies = ["mcp>=1.27,<2", "pydantic>=2.5,<3"]`. See Adversarial item 4.
- FastMCP 3.0 (2026-01-19) is the de-facto framework but adds breaking changes — pin or test against pinned majors.

### `uv tool install --force` semantics

- Installs into isolated venv under `$UV_TOOL_DIR` (default `~/.local/share/uv/tools`); executables symlinked into `$UV_TOOL_BIN_DIR` (default `~/.local/bin`).
- `--force` overwrites prior installs; uv applies a file-based lock during install but the lock location is undocumented and uv-version-dependent.
- **Known races**: issue #9492 (`--force` fails to update local-path installs), issue #15335 (Linux concurrent `uv pip install -e` race at uv 0.8.5+). Implies uv's locking is best-effort, not bulletproof.
- **Cortex implication**: `flock` belt-and-braces is correct. The proposed cortex flock at `$cortex_root/.git/cortex-update.lock` does NOT serialize against non-cortex `uv` invocations (different namespace) — see Adversarial item 2.

### Schema-versioning JSON contracts: Terraform `format_version` is the reference

- Per https://developer.hashicorp.com/terraform/internals/json-format:
  - Minor bump (e.g., `"1.1"`): backward-compatible additions. Consumer skips unknown fields.
  - Major bump (e.g., `"2.0"`): breaking. Consumer rejects unsupported major.
- Use a **string** version (`"1.0"`) so `"1.10"` parses correctly, not a number.
- Echo version in every CLI JSON response.
- **Anti-pattern**: do not round-trip unknown fields back into the CLI; treat as forward-compat-only.

### Auto-update orchestration patterns

- **rustup**: three-mode auto-self-update (`enable` / `disable` / `check-only`). PR #2763 added the configurable mode. `--no-self-update` flag suppresses on a single invocation. `CI=1` disables. **Closest analog for cortex**.
- **gh**: explicit-only; tells users to use their package manager. Conservative end of the spectrum.
- **uv, nvm**: explicit-only.
- **Subprocess update wrapped in process-orchestration layer is unusual but not unprecedented**: rustup itself is exactly this — a thin wrapper that orchestrates `rustup-init`/toolchain subprocesses. Closest analog is rustup's `auto-self-update = check-only`: probe at startup, surface "new version available", require explicit user signal to apply.

### Stdio MCP server concurrency

- **Claude Code spawns one stdio MCP child per session.** Process tree: each `claude-code/cli.js` session forks its own MCP server. Per issue #29688: 4 sessions × 6 MCP servers = 24 processes (not 6). Issue #28860 is the open feature request for shared MCP across sessions; not implemented as of 2026.
- **Implication for cortex flock**: concurrency is real and concrete. If a user opens 3 Claude Code windows on cortex repos, three independent MCP processes start in parallel and three independent SessionStart probes race. The flock approach is correct; design must include post-lock-acquire HEAD re-verification (Adversarial item 8).

## Requirements & Constraints

### Distribution & installation model (`requirements/project.md` + `docs/setup.md`)

- Cortex ships as `uv tool install -e .` (CLI) plus plugins via `/plugin install`.
- **No PyPI publishing** ("Published packages or reusable modules for others — out of scope").
- Per-repo sandbox registration via `cortex init` writes to `~/.claude/settings.local.json`'s `sandbox.filesystem.allowWrite` array, serialized via `fcntl.flock` on a sibling lockfile.

### MCP server & runner IPC contract (`requirements/pipeline.md` + `docs/mcp-server.md`)

- **Load-bearing**: `lifecycle/sessions/{session_id}/runner.pid` JSON schema `{schema_version, magic, pid, pgid, start_time, session_id, session_dir, repo_path}`, mode `0o600`, atomic write. **Stable contract for ticket 116 MCP control plane.**
- `~/.local/share/overnight-sessions/active-session.json` — host-global active-session pointer with `phase` field.
- `cortex mcp-server` exposes 5 stdio tools (`overnight_start_run`, `overnight_status`, `overnight_logs`, `overnight_cancel`, `overnight_list_sessions`) wrapping `cli_handler` boundaries; the server is stateless.
- **Pre-install in-flight guard**: `cortex` aborts when an active overnight session is detected; bypassable via `CORTEX_ALLOW_INSTALL_DURING_RUN=1` (do NOT export). Carve-outs: pytest, `CORTEX_RUNNER_CHILD=1`, dashboard, cancel-force.
- `lifecycle/sessions/{session_id}/runner-bootstrap.log` — captures runner stdout/stderr on the MCP-spawned start path so pre-`events.log`-init failures are diagnosable.

### Sandbox & defense-in-depth (`requirements/project.md`)

- "The overnight runner bypasses permissions entirely (`--dangerously-skip-permissions`), making sandbox configuration the critical security surface for autonomous execution."
- "For sandbox-excluded commands (git, gh, WebFetch), the permission allow/deny list is the sole enforcement layer; keep global allows read-only and let write operations fall through to prompt."
- All session state writes are atomic (tempfile + `os.replace()`).

### CLI ownership & versioning (ticket 115 + 146)

- `cortex overnight {start,status,cancel,logs}` are the canonical CLI surface.
- `cortex overnight cancel` validates session-ids against `^[a-zA-Z0-9._-]{1,128}$` + realpath containment + runner.pid magic + psutil `create_time` ±2s.
- Notifications fall back to stderr with `NOTIFY:` prefix when `~/.claude/notify.sh` is absent (stdout reserved as orchestrator agent's input channel).

### File-based-state posture intact

- All lifecycle artifacts, backlog items, pipeline state use plain files. No database, no server. The 146 refactor preserves this — no in-memory long-lived state introduced beyond the per-MCP-process instance cache.

### Scope boundaries explicitly carried into 146

**In scope:**
- Strip `cortex_command` imports from MCP.
- Audit/extend CLI verbs for JSON output.
- Move MCP source into plugin (PEP 723 or package).
- Auto-update orchestration (update check, apply, then-delegate, concurrency-safe, failure surface).
- Tests for subprocess+JSON glue and update orchestration concurrency.

**Out of scope (do not re-litigate):**
- Inline auto-update gate inside `cortex_command/cli.py::main()` (rejected ticket 145).
- Removing CLI's overnight orchestration logic (CLI keeps owning the heavy lifting).
- Remote MCP transport (stdio only).
- Python deps bundling in plugin (uvx or PEP 723; not vendored).
- Multi-version compatibility between MCP and CLI (single schema version).
- Auto-update for bare-shell `cortex` invocations.
- PyPI publishing.

## Tradeoffs & Alternatives

### Recommended approach: **Alternative A — MCP-orchestrated `cortex upgrade`**

The proposed approach. MCP server checks `git ls-remote vs HEAD` before delegating each tool call (throttled), spawns `cortex upgrade` synchronously when upstream advances, verifies via probe, then spawns the user's intended subcommand. Lock at `$cortex_root/.git/cortex-update.lock`. Fail-soft (NDJSON to last-error.log + stderr; intended call still executes).

**Why A wins:**
- Hits the *actual* primary user path (MCP-driven), unlike rejected ticket 145 (CLI gate inactive on `CLAUDECODE` path).
- Update + intended call compose in *separate subprocesses* — TOCTOU shim-rewrite race that killed 145 is eliminated by construction.
- Single failure surface (MCP logs); other approaches split visibility.
- Aligns with existing `_spawn_runner_subprocess` pattern (`tools.py:412-436`) and ecosystem norm (alexei-led/aws-mcp-server, rustup `check-only`).
- Concurrency story is clean (blocking flock with budget).

**Sensitive to**: Q#1 sandbox check. If MCP-spawned subprocesses cannot write `$cortex_root/.git/` or `~/.local/share/uv/tools/`, A degrades to D (notice-only). Web research strongly suggests A is unaffected (sandbox is bash-only) but empirical probe still required.

### Alternatives considered and rejected

**B — SessionStart hook runs `cortex upgrade`.** Structurally broken: SessionStart fires before MCP servers connect, so the hook does NOT reliably gate MCP tool calls; SessionStart cannot block MCP tools per the hooks reference. Inherits 145's sandbox concern in worse form (hook runs inside Claude Code's process tree). Split failure surface — MCP can't tell if upgrade ran. **Rejected.**

**C — Daemon-based applier (launchd/systemd-user).** Mid-session breakage hazard (rewriting `cortex` shim while subprocess is mid-import → ImportError, same concern that killed 145 Shape 1). Misalignment with file-based-state posture. Pre-empts ticket 112 LaunchAgent ownership. macOS-only without parallel work. Failure visibility worst-of-class. **Rejected.**

**D — Explicit-only with discoverability nudge.** Solves the wrong half of the problem — discoverability nudge doesn't help users who see and ignore it. Dogfooding user already knows about `cortex upgrade`. **Viable fallback if A's sandbox check fails**, but not the primary recommendation.

**E — SessionStart-probe-in-process-apply-on-invoke (rejected ticket 145).** Both rejection reasons still apply: `CLAUDECODE` skip predicate deactivates the gate; exit-and-rerun discards user intent. **Reaffirmed rejected.**

### Sub-decision: MCP source distribution → **PEP 723 single-file** (default; revisit if grows past ~600 LOC)

`plugins/cortex-overnight-integration/server.py` invoked via `uvx server.py`.

- Simplicity: ~200–500 LOC fits one file.
- Plugin-update ergonomics: smallest diff for `/plugin update`.
- uvx caching: identical participation as `pyproject.toml`.
- pytest can import a `# /// script`-prefixed module — no special CI handling.
- Editor support is minor regression (recent VS Code Python extension supports PEP 723; older editors don't see deps).
- Move to subdirectory package only if file grows past ~600 LOC or sub-modules emerge.

**Pin discipline (load-bearing per Adversarial item 4)**: PEP 723 deps must use major bounds, e.g.:
```python
# /// script
# requires-python = ">=3.12"
# dependencies = ["mcp>=1.27,<2", "pydantic>=2.5,<3"]
# ///
```
Bare names risk fastmcp 3.x-style cold-cache regressions (AWS MCP issue #2533).

### Sub-decision: Throttle policy — **CONTRADICTION between Tradeoffs (b) and Adversarial (c)**

Tradeoffs agent recommends **(b) per-MCP-server-lifetime instance cache**: simplest correct, no XDG state file, no clock-skew, naturally bounded across multiple sessions.

Adversarial agent recommends **(c) per-N-minutes file-based timestamp** at `${XDG_STATE_HOME}/cortex-command/last-update-check`: handles the offline-morning and flaky-network blip cases that (b) materially worsens (a 30-second `git ls-remote` 503 from GitHub — observed monthly — leaves the MCP stale for the rest of its lifetime; (c) retries on next call after the throttle window).

**This is an open contradiction → spec phase resolves.** Default proposal carried into spec: option (c) per-N-minutes file-based with a 5-minute window AND a separate transient-error flag that resets on network errors so the next call retries immediately. This is a strict superset of (b)'s simplicity benefits in exchange for one persisted timestamp file — the 145 lifecycle already established the `${XDG_STATE_HOME}` pattern.

### Sub-decision: `cortex_root` discovery — **chain `CORTEX_COMMAND_ROOT` → `cortex --print-root` → editable-install `.pth` → `$HOME/.cortex`** with hard-fail on full miss

1. `CORTEX_COMMAND_ROOT` env var if set (matches existing `cli.py:90` convention).
2. `cortex --print-root` (new flag) emitting `{schema_version, root, remote_url, head_sha}` — combines three round-trips.
3. **Adversarial extension (item 5)**: read `~/.local/share/uv/tools/cortex-command/lib/python*/site-packages/_editable_impl_cortex_command.pth` to resolve the editable-install source dir before falling back to `$HOME/.cortex`. Without this, dogfooding install at `~/Workspaces/cortex-command` (not `$HOME/.cortex`) breaks the chain silently.
4. `$HOME/.cortex` final fallback.
5. **Hard-fail on full miss** — do NOT silently proceed against a phantom directory.

`cortex --print-root` JSON shape becomes a forever-public-API (it precedes schema-version negotiation). See Adversarial item 7: append-only fields after publication.

## Adversarial Review

### Failure modes & edge cases

**1. Q#1 sandbox claim is structurally fragile and needs an empirical probe, not a docs read.**
The web agent's "Seatbelt does not apply to MCP-spawned subprocesses" inference is based on a *positive-scope* docs statement, not a *negative-scope* one. Anthropic could add MCP-sandboxing in a 2.x.y minor without breaking the doc's literal claim, and issue #26616 is exactly that proposal. Cortex codebase has prior empirical observations of other Claude-Code-spawned processes hitting Seatbelt-adjacent surfaces (`lifecycle/migrate-overnight-schedule-to-a-launchagent-based-scheduler/research.md:354`; `lifecycle/permissions-audit-round-2-cfa-android-learnings/spec.md:107` — "User flagged during spec that MCP servers may or may not inherit the Seatbelt sandbox.").
**Required mitigation**: empirical probe on user's actual machine. PEP 723 script invoked as a real MCP from a real Claude Code session; attempt `pathlib.Path("$cortex_root/.git/.cortex-write-probe").touch()` and `subprocess.run(["uv", "tool", "install", "-e", str($cortex_root), "--force"])`; observe exit codes. Document result in spec.

**2. Cross-tool uv invocation race.**
Proposed flock at `$cortex_root/.git/cortex-update.lock` does NOT serialize against non-cortex uv invocations targeting the same `~/.local/share/uv/tools/cortex-command/` directory. uv's internal lock location is undocumented and version-dependent.
**Mitigation**: add a second flock at `~/.local/share/uv/tools/cortex-command/.cortex-update.lock` to serialize against external uv invocations, OR explicitly carve out "external uv invocations against this tool dir are out of scope" in spec.

**3. Plugin-update timing is uninvestigated.**
Open questions:
- Does Claude Code restart MCP servers on plugin refresh, or only on session restart? If only on session restart, the user is on the *old* MCP source until they restart Claude Code — defeating Value bullet 2 ("no Claude Code restart needed").
- If Claude Code restarts MCPs mid-session, in-flight `overnight_start_run` could be cancelled mid-spawn — race the design doesn't address.
- Plugin auto-update *itself* may run while a tool call is in flight, leaving `.mcp.json` pointing at a path the plugin update has deleted.
**Mitigation**: empirical investigation in spec; do not assume favorable behavior.

**4. PEP 723 dependency pin discipline (covered above)**: ship pins, never bare names.

**5. Discovery chain falls silently to `$HOME/.cortex` if `cortex` is off PATH (covered above)**: extend chain with editable-install `.pth` resolution; hard-fail on full miss.

**6. Schema-version one-axis vs two-axis (Terraform pattern).**
Codebase's daytime-result-reader uses hard equality (`!= 1`); ipc.py uses range (`1 <= schema_version <= MAX_KNOWN`). Both correct for their use cases (writer-newer-than-reader: fail closed; same-process: range tolerant).

For MCP-CLI contract, *both directions* of drift can occur during the auto-update window:
- Plugin updates first → MCP newer than CLI.
- CLI updates first → MCP older than CLI.

Hard-equality forces lockstep updates (which the design explicitly does NOT enforce). Skip-unknown-on-minor-bump (Terraform) is correct *if* minor-bumps are additive.
**Mitigation**: split `schema_version` into `(major, minor)` or replace with semver `"1.0"` string. Major: hard-equality, MCP refuses to serve. Minor: skip-unknown, forward-compat. Document in `docs/mcp-contract.md`.

**7. `cortex --print-root` is forever-public-API.**
The flag is invoked *before* the MCP knows the CLI's schema_version — it's how the MCP discovers the CLI in the first place. **You cannot version-negotiate the version-negotiation flag.** Future changes to the JSON shape are breaking changes.
**Mitigation**: freeze the shape forever or use a single `version` field with publicly-documented compatibility floor; the rest of the payload becomes append-only.

**8. Concurrent MCP racing: post-flock-acquire re-verification missing from spec.**
`backlog/146.md:68` says "First wins; second waits up to N seconds; if still held after the budget, second logs and continues without upgrading." Says nothing about post-acquire re-verification. As specified, waiter 2 acquires the lock and runs `cortex upgrade` redundantly on an already-fresh tree — `git pull --ff-only` is fast but `uv tool install --force` is 2–10s of redundant shim-rewrite (re-introducing the TOCTOU race 145 established empirically).
**Mitigation**: post-flock-acquire, waiter must `git -C $cortex_root rev-parse HEAD` and compare to captured-pre-flock remote_sha. Skip apply if matches.

**9. Verification probe `cortex --help` is too weak.**
145 used `cortex --help` post-install; both 145 and 146 inherit this weakness. `--help` exercises argparse only, not module imports — and 145 research identified `from cortex_command.overnight import cli_handler` as a lazy-import failure mode during partial install. Post-install `cortex --help` succeeds even if `cli_handler.py` is mid-rewrite-corrupted.
**Mitigation**: verification probe is `cortex --print-root && cortex overnight status --format json` against an empty path — forces module import. Anything weaker leaves a corrupt-install-undetected window.

**10. Plugin-update + CLI-update bidirectional staleness window.**
Plugin updates first → MCP source new → MCP runs update check → triggers `cortex upgrade` → during the 10-second gap, every tool call sees a contract mismatch (new MCP expects `schema_version=2`, CLI still on `schema_version=1`). Fail-soft executes the user's call against the old CLI → JSON output the new MCP can't parse → tool error.
**Mitigation**: new MCP must declare its *minimum acceptable CLI schema_version*. On detecting too-old CLI, run `cortex upgrade` *synchronously before* delegating any tool call (lifecycle gate, not throttle). This is a separate concern from the throttle policy.

**11. Cache-attempts-vs-success: instance cache (sub-decision b) has worse failure mode.**
Network-up-but-503 from GitHub (real, observed monthly) → attempt cached "failed" → MCP runs 8 hours stale even after network recovers 30 seconds later. Per-N-minutes file-based throttle (option c) handles this strictly better.
**Mitigation feeding into spec**: option (c) with separate transient-error flag.

**12. Multi-fork + multi-clone cache key.**
Cache key not specified. Path-keyed: two cortex installs work fine. Remote-URL-keyed: forks collide.
**Mitigation**: cache key = `(cortex_root absolute path, remote URL HEAD ref)`.

### Security concerns / anti-patterns

**13. Auto-RCE persists from 145 and gets *worse* in 146.**
145 adversarial review flagged "auto-update is auto-RCE" (no signature check, no ref pinning). In 145, trigger was "user opens Claude session." In 146, trigger is "every MCP tool call after stale-window expires" — much more frequent. Threat-model blast radius increases.
**Mitigation**: explicitly cite in spec; either accept (document trade-off in `requirements/project.md`) or add `CORTEX_REPO_PIN_SHA=<sha>` for users wanting a tamper window.

**14. `${CLAUDE_PLUGIN_ROOT}` confused-deputy.**
New MCP source invoked via `uvx ${CLAUDE_PLUGIN_ROOT}/server.py`. Attacker who can override env var (untrusted plugin marketplaces, malicious `.envrc`) directs uvx to run arbitrary Python. PEP 723 inline `# /// script` deps fetched without verification.
**Mitigation**: refuse to run if `${CLAUDE_PLUGIN_ROOT}/server.py` is not where the plugin's own manifest expects it (path-equality check against `.mcp.json` author-declared location).

**15. Stale-flag-from-145 in 146 form.**
If user uninstalls plugin then reinstalls a forked plugin pointing at a different repo, MCP cache may carry over remote URL or HEAD SHA from the old plugin.
**Mitigation**: cache entries include fingerprint of resolving plugin's `.mcp.json`; on plugin update, fingerprint mismatch invalidates cache.

### Assumptions that may not hold

**16. "Subprocess overhead negligible at <10 tool calls/min".**
Backlog 146:101 cites this estimate. Overnight `overnight_status` polling at 30s + dashboard `overnight_logs` cursor-pagination produce much higher rates. Each call adds: discovery (cached) + update-check (cached) + JSON-spawn + JSON parse + Pydantic re-validation. Cold-Python-startup overhead may be 5× higher in practice.
**Mitigation**: measure before committing. Add a benchmark to spec acceptance criteria.

**17. MCP-protocol staleness reframing.**
Value bullet 3 says "MCP-protocol staleness still applies. This is unchanged by the refactor." More precisely: refactor *moves* staleness from "CLI staleness on MCP path" to "MCP-source staleness on plugin path." Latter is fixed by Claude Code restart (assumed common); former was fixed by Claude Code restart + explicit `cortex upgrade`. Trade-off is real.
**Mitigation**: document in spec as known limitation. Users running Claude Code as a persistent service (screen/tmux) are affected.

**18. "One MCP per session" architecture assumption.**
If Claude Code adds shared MCP across sessions (issue #28860), per-instance-cache breaks: 1 MCP serves N sessions with potentially different cortex repos via different CWDs.
**Mitigation**: design cache invalidation around "first-tool-call-from-this-session-id" pattern, not MCP server lifetime. Defensive against future Claude Code architecture changes.

## Open Questions

These need resolution in the Spec phase. Q-numbering aligned with backlog ticket where applicable. Q#1 is load-bearing.

1. **Q#1 (LOAD-BEARING) Sandbox empirical probe.** Web docs say MCP-spawned subprocesses are not in Claude Code's bash sandbox (Seatbelt does not apply). Adversarial review says docs read alone is insufficient given prior cortex empirical observations of MCP-spawned processes hitting Seatbelt-adjacent surfaces. **Deferred: spec phase must execute the empirical probe — invoke a PEP 723 MCP from a real Claude Code session on user's macOS, attempt `touch $cortex_root/.git/.cortex-write-probe` AND `uv tool install -e $cortex_root --force`, document result.** If probe passes, proceed with Alternative A. If probe fails, degrade to Alternative D (notice-only) and file follow-up to register `$cortex_root/.git/` and `~/.local/share/uv/tools/cortex-command/` in `cortex init` allowWrite.

2. **Q#2 Throttle policy CONTRADICTION.** Tradeoffs agent recommends per-MCP-server-lifetime instance cache (option b); adversarial agent recommends per-N-minutes file-based timestamp (option c) because (b) materially worsens flaky-network and offline-morning UX. **Deferred to spec for user resolution.** Default proposal: option (c) — `${XDG_STATE_HOME}/cortex-command/last-update-check` with 5-minute window plus separate transient-error flag.

3. **Q#3 MCP source distribution: PEP 723 single-file vs subdirectory package.** Resolved per Tradeoffs recommendation: PEP 723 single-file. Pin major bounds in `# /// script` block to avoid AWS MCP issue #2533-style cold-cache breakage.

4. **Q#4 `cortex_root` discovery chain.** Resolved: `CORTEX_COMMAND_ROOT` → `cortex --print-root` → editable-install `.pth` resolution → `$HOME/.cortex` → hard-fail. `cortex --print-root` JSON shape becomes forever-public-API; append-only after publication.

5. **Q#5 JSON contract enumeration & schema versioning policy.** Add `--format json` to `overnight start`, `overnight logs`, `overnight cancel`. Add new `cortex --print-root` flag. **Deferred to spec: schema versioning policy** — single integer (current codebase pattern) vs `(major, minor)` (Terraform pattern). Adversarial review argues Terraform two-axis is required given the bidirectional staleness window during plugin-update + CLI-update interaction. Default proposal: `"version": "1.0"` string with major-hard-equality + minor-skip-unknown, documented in new `docs/mcp-contract.md`.

6. **Q#6 Skip-predicates for dogfooding.** **Resolved**: user accepts the skip per clarify-phase answer. Predicates: `CORTEX_DEV_MODE=1` env var OR dirty tree (`git status --porcelain` non-empty) OR non-main branch (`git rev-parse --abbrev-ref HEAD != main`). Log skip reason to stderr so user is aware.

7. **Q#7 Verification probe scope.** Adversarial review says `cortex --help` is too weak — argparse-only, doesn't force module import. **Deferred to spec: should the verification probe be `cortex --print-root && cortex overnight status --format json` (forces module import)?** Default proposal: yes; adopts Adversarial item 9.

8. **Q#8 uvx offline first-run.** **Deferred to spec**: ticket scope already accepts the degradation; spec must document the failure-mode UX for offline-fresh-laptop case (MCP server fails to start; Claude Code shows server-unavailable error). No mitigation required; documentation only.

9. **Q#9 Plugin migration for existing installs.** **Deferred to spec**: empirical investigation of Claude Code's plugin-refresh + MCP-restart semantics. Does Claude Code restart MCPs on plugin update, only on session restart, or asynchronously? Affects whether Value bullet 2 ("no Claude Code restart needed for CLI updates to take effect") holds.

10. **Q#10 Ticket 116 alignment.** **Resolved**: 116 is `status: complete`. Verify schema-version semantics in spec — confirm whether 116's existing schemas use hard-equality, range, or two-axis, and align 146's contract with the precedent.

11. **(NEW from Adversarial item 2) Cross-tool uv lock.** **Deferred to spec**: add second flock at `~/.local/share/uv/tools/cortex-command/.cortex-update.lock` to serialize against external uv invocations, OR explicitly carve out as out-of-scope?

12. **(NEW from Adversarial item 8) Post-flock re-verification.** **Resolved**: spec must specify post-acquire `git rev-parse HEAD` re-comparison; skip apply if already at remote_sha.

13. **(NEW from Adversarial item 10) Synchronous schema-floor gate.** **Deferred to spec**: when MCP detects a CLI older than its required schema_version, force synchronous `cortex upgrade` before delegating any tool call. This is a separate gate from the throttle policy.

14. **(NEW from Adversarial item 12) Cache key.** **Resolved**: `(cortex_root absolute path, remote URL HEAD ref)` to handle multi-fork/multi-clone cases.

15. **(NEW from Adversarial item 13) Auto-RCE threat model documentation.** **Deferred to spec**: explicitly document trade-off in spec; consider adding `CORTEX_REPO_PIN_SHA=<sha>` for users wanting a tamper window. Update `requirements/project.md` if accepted.

16. **(NEW from Adversarial item 14) Confused-deputy on `${CLAUDE_PLUGIN_ROOT}`.** **Deferred to spec**: path-equality check against plugin manifest's author-declared MCP source path before invoking.

17. **(NEW from Adversarial item 16) Subprocess-overhead measurement.** **Deferred to spec**: add benchmark as acceptance criterion; measure cold-Python-startup overhead for a representative tool-call rate (overnight polling, dashboard cursor pagination).
