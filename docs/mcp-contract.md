# MCP ↔ CLI Contract

This document defines the subprocess + JSON contract between the cortex MCP server (`plugins/cortex-overnight-integration/server.py`) and the cortex CLI (`cortex_command/cli.py`, `cortex_command/overnight/cli_handler.py`). The MCP plugin imports zero `cortex_command.*` modules; its sole interface to the CLI is `subprocess.run(["cortex", ...])` plus parsing the versioned JSON the CLI emits on stdout.

The contract exists so the plugin and the CLI can evolve and ship on independent cadences. The plugin is refreshed by Claude Code's `/plugin install`/refresh path; the CLI is refreshed by `cortex upgrade` (or the MCP-orchestrated auto-update flow when the sandbox probe permits it). Schema versioning (below) is what lets the two halves drift apart in version without silently producing wrong results.

## Schema versioning

Every JSON payload the CLI emits for MCP consumption carries a `"version"` string field of the form `"M.m"` — major-dot-minor. The shape follows Terraform's `format_version` precedent (e.g. `terraform show -json` emits `"format_version": "1.0"`): a versioned envelope on every payload, with two-axis evolution rules.

- **String, not number.** `"1.10"` parses correctly as a string; as a float it would equal `1.1`. Always parse as `str` then split on `.`.
- **Initial version: `"1.0"`.** Stamped on every payload from `cortex --print-root`, `cortex overnight start --format json`, `cortex overnight status --format json`, `cortex overnight logs --format json`, and `cortex overnight cancel --format json`. The CLI side of the constant lives at `cortex_command/overnight/cli_handler.py::_JSON_SCHEMA_VERSION`.
- **Major bump (M increments) = breaking change.** The MCP consumer hard-rejects payloads whose major component differs from its baked-in `MCP_REQUIRED_CLI_VERSION` constant. A major bump is reserved for renaming or retyping an existing field, removing a field, or changing its semantics.
- **Minor bump (m increments) = additive change.** The MCP consumer skips unknown fields and accepts payloads with a greater minor than its required floor. Minor bumps are how new fields land without breaking older MCP plugins paired with newer CLIs.
- **Single CLI major in scope.** The first implementation pins the MCP to one CLI major schema version. Multi-major compatibility is explicitly out of scope (see `lifecycle/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md` Non-Requirements).

### Forever-public API

The shape of `cortex --print-root` is forever-public-API: append-only after publication; existing fields never change semantics or types without a major bump. Concretely, the four fields named in the [JSON payload reference](#json-payload-reference) below — `version`, `root`, `remote_url`, `head_sha` — are stable forever in their current types and meanings. New fields may be added under a minor bump; existing fields may not be renamed, retyped, or repurposed without a major bump.

This stability commitment exists because `cortex --print-root` is the bootstrap call: it is what the MCP uses to discover where the CLI lives, what remote it tracks, and what HEAD it is at. The MCP cannot version-negotiate before reading this payload, so the payload itself must not move underneath it.

The same append-only rule applies to the four overnight verbs documented below (`overnight start`, `overnight status`, `overnight logs`, `overnight cancel`), but those verbs are co-versioned with the CLI: a major bump on any of them is allowed in lock-step with a major bump of `cortex --print-root`'s `version` field. `cortex --print-root` itself is the anchor.

## JSON payload reference

The CLI verbs the MCP currently consumes, with the exact fields each emits.

### `cortex --print-root`

Top-level flag (not a subcommand). Emits one line of JSON to stdout, exit 0.

Source: `cortex_command/cli.py::_dispatch_print_root` (around lines 128–165).

```json
{
  "version": "1.0",
  "root": "/abs/path/to/cortex/checkout",
  "remote_url": "git@github.com:user/cortex-command.git",
  "head_sha": "<40-hex-char git sha>"
}
```

Field semantics:

- `version` — schema-floor stamp; see [Schema versioning](#schema-versioning).
- `root` — absolute path to the Cortex checkout that this `cortex` shim resolves to. Resolution chain (in order): `CORTEX_COMMAND_ROOT` env override → editable-install discovery via `cortex_command.__file__` → `~/.cortex` fallback → hard-fail on stderr.
- `remote_url` — output of `git -C $root remote get-url origin`, stripped. Empty string if the git command fails (e.g. `.git` is missing). Never `null`.
- `head_sha` — output of `git -C $root rev-parse HEAD`, stripped. Empty string if the git command fails. Never `null`.

This payload is the MCP's canonical source of truth for the upstream URL and local HEAD that R8 and R13 compare against.

### `cortex overnight start --format json`

Source: `cortex_command/overnight/cli_handler.py::handle_start` (around lines 126–208).

The JSON contract is intentionally narrow: it only covers the structured refusal path that the MCP needs to discriminate. Successful starts hand off to `runner_module.run` and produce no stdout JSON envelope.

**Concurrent-runner refusal (exit 1):**

```json
{
  "version": "1.0",
  "error": "concurrent_runner",
  "session_id": "<existing session id>",
  "existing_pid": 12345
}
```

`existing_pid` is included only when the recorded value is an integer. `session_id` is always present and is the empty string when the existing PID record lacks one.

Other failure paths in `handle_start` (missing state file, no auto-discoverable session) print to stderr and exit non-zero without emitting a JSON envelope. The MCP treats absence of stdout JSON as "non-structured failure; surface stderr verbatim."

### `cortex overnight status --format json`

Source: `cortex_command/overnight/cli_handler.py::handle_status` (around lines 231–301). This verb existed before this feature; the shape has been stable since.

**No active session (exit 0):**

```json
{"active": false}
```

Note: this payload pre-dates the schema-versioning convention and does **not** carry a `"version"` field. The MCP treats an absent `"version"` on a `{"active": false}` payload as the legacy unversioned no-active-session signal and accepts it. Future major bumps may version-stamp this branch.

**Active session (exit 0):**

```json
{
  "session_id": "<id>",
  "phase": "<phase>",
  "current_round": 4,
  "features": {"<feature-name>": {...}}
}
```

Field semantics:

- `session_id` — string; empty string when missing from the underlying state file.
- `phase` — string; one of the runner phase tokens (e.g. `executing`, `complete`); empty string when missing.
- `current_round` — integer; defaults to `0` when missing.
- `features` — object; the `features` map from `overnight-state.json` passed through verbatim. May be empty.

Note: this payload is also unversioned in the current shape, mirroring the `{"active": false}` legacy. The MCP's schema-floor check (R13) reads `version` from `cortex --print-root`, not from `overnight status`, so the absence here does not block the schema-floor gate.

### `cortex overnight logs --format json`

Source: `cortex_command/overnight/cli_handler.py::handle_logs` (around lines 500–583).

**Success (exit 0):**

```json
{
  "version": "1.0",
  "lines": ["...", "..."],
  "next_cursor": "@<byte-offset>",
  "files": "events"
}
```

Field semantics:

- `version` — schema-floor stamp.
- `lines` — array of strings, one per log line, in file order.
- `next_cursor` — opaque cursor of the form `"@<int>"` (byte offset). Pass back unchanged as `--since`.
- `files` — echo of the `--files` argument: `"events"`, `"agent-activity"`, or `"escalations"`.

**Error (exit 1):**

```json
{
  "version": "1.0",
  "error": "invalid_session_id" | "no_active_session" | "invalid_cursor",
  "message": "<human string>"
}
```

### `cortex overnight cancel --format json`

Source: `cortex_command/overnight/cli_handler.py::handle_cancel` (around lines 378–479).

**Success (exit 0):**

```json
{
  "version": "1.0",
  "cancelled": true,
  "session_id": "<id>",
  "pgid": 12345
}
```

`session_id` is the empty string when the recorded PID file lacks one. `pgid` is always an integer (validated before signalling).

**Error (exit 1):**

```json
{
  "version": "1.0",
  "error": "invalid_session_id" | "no_active_session" | "stale_lock_cleared" | "cancel_failed",
  "message": "<human string>"
}
```

`stale_lock_cleared` indicates self-heal: the recorded PID was not actually alive, so the runner-pid and active-session pointers were cleared. Surfaces as "stale lock cleared — session was not running" in the message.

### `cortex overnight list-sessions`

Not currently a CLI verb. The `overnight_list_sessions` MCP tool reads the sessions directory directly from the plugin (no `cortex_command` imports). When `overnight list-sessions --format json` is added to the CLI, its payload shape will be documented here under the same schema-versioning rules as the other verbs.

## Threat model

MCP-orchestrated auto-update is auto-RCE. If the upstream cortex repository on GitHub is compromised — account takeover, malicious PR merged, dependency poisoning of the install script — the next MCP-triggered `cortex upgrade` runs attacker-controlled code with the user's privileges. That includes filesystem write access to `~/.local/share/uv/tools/cortex-command/`, `~/.local/bin/cortex`, and any path the cortex CLI subsequently reaches during normal operation.

This trade-off is accepted deliberately. Per `requirements/project.md`, cortex-command is personal tooling — "Published packages or reusable modules for others — out of scope." The user is responsible for the trustworthiness of their own upstream repository (their own GitHub account). The threat surface is one-self.

Mitigations that exist:

- **Skip predicates (R9).** `CORTEX_DEV_MODE=1`, dirty working tree, or non-`main` branch all suppress the auto-update path. The dogfooding case has a per-machine kill switch via the env var.
- **Bare-shell users opt out by default.** No MCP-orchestrated upgrade fires for invocations that aren't running through the MCP server. `cortex upgrade` from a terminal stays explicit and user-driven.
- **Schema-floor refusal (R13).** A compromised CLI that emits malformed `version` payloads will be rejected by the MCP's schema-floor check rather than silently consumed.

Mitigations that are explicitly out of scope for this ticket:

- **`CORTEX_REPO_PIN_SHA` tamper window.** A pin-to-SHA env var would let a stability-conscious user freeze updates to a known-good commit. Not required to ship; trivially adds later if a user emerges who wants it. Tracked as a future follow-up, not a near-term gap.

The full requirement is R22 in this feature's spec.

## Cross-tool serialization carve-out

The MCP holds a single flock at `$cortex_root/.git/cortex-update.lock` while it runs `cortex upgrade`. This serializes concurrent **MCP-driven** upgrades — multiple Claude Code sessions racing to apply the same upstream advance. Only one MCP wins the lock; the others observe the post-acquire HEAD re-verification (R11) and skip the redundant invocation.

There is intentionally **no second flock** at `~/.local/share/uv/tools/cortex-command/.cortex-update.lock` (or any equivalent location) for cross-tool serialization. An external `uv tool upgrade cortex-command` invoked from a separate shell — concurrent with an MCP-orchestrated upgrade — may produce indeterminate results: partial installs, conflicting module rewrites, or shim-layer mismatches.

This is accepted for two reasons:

1. **External `uv tool upgrade` is a hostile concurrency partner.** It does not know about the MCP's flock, will not honor it, and the MCP cannot block it. A second flock at the uv tool path would only serialize cooperating processes; an actually-concurrent `uv` invocation would either bypass or deadlock on it.
2. **The user is the cross-tool serialization mechanism.** A user who runs `uv tool upgrade cortex-command` from a shell while a Claude Code session is mid-tool-call has chosen to race the two paths. The MCP's threat model already trusts the user with auto-RCE on every tool call (see [Threat model](#threat-model)); requiring them to not race their own upgrade tools is a strictly weaker ask.

Recovery after an indeterminate result: run `cortex upgrade` (or `uv tool install -e <path> --force`) once from a bare shell after the MCP and any external invocations have settled. The verification probe (R12) on the next MCP tool call will catch any partial-install corruption and surface it through the NDJSON error log (R14).

This carve-out is documented under "Non-Requirements" in this feature's spec; it is not a future TODO.
