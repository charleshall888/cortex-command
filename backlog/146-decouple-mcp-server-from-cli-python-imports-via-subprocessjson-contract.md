---
schema_version: "1"
uuid: 6baeb00e-799c-43e8-a354-3d54445e1a29
title: "Decouple MCP server from CLI Python imports + own auto-update orchestration"
status: complete
priority: medium
type: feature
created: 2026-04-25
updated: 2026-04-27
parent: "113"
tags: [distribution, mcp, architecture, upgrade, overnight-layer-distribution]
areas: [mcp-server,plugins]
complexity: complex
criticality: high
absorbed: ["145"]
session_id: null
lifecycle_phase: implement
lifecycle_slug: decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration
spec: lifecycle/archive/decouple-mcp-server-from-cli-python-imports-own-auto-update-orchestration/spec.md
---

# Decouple MCP server from CLI Python imports + own auto-update orchestration

## Problem

Two coupled architectural concerns, surfaced together during ticket 145's plan-phase critical review.

### Concern 1: MCP-CLI coupling

The cortex MCP server (`cortex_command/mcp_server/`) currently lives inside the CLI's Python package and imports cortex_command modules directly (atomic-claim helpers, session-discovery utilities, runner-pid coordination). This creates two coupling problems:

1. **MCP runtime = CLI install.** The plugin (`plugins/cortex-overnight-integration/.mcp.json`) is a 9-line registration shim pointing at `cortex mcp-server` — the CLI binary. So the MCP server runs whatever code is in the CLI install. Plugin auto-update (Claude Code's job per epic 113 Q7) cannot refresh MCP runtime behavior independently of the CLI install.
2. **In-flight MCP staleness.** A long-running `cortex mcp-server` subprocess holds `cortex_command` modules in memory. Even after the CLI is updated on disk, the running MCP serves the old code until Claude Code restarts.

The wider MCP ecosystem favors **thin MCP wrappers around CLIs**: the MCP server is a small process that spawns CLI subprocesses, parses JSON output, and returns structured results to Claude. Under that pattern, MCP and CLI update independently; in-flight staleness disappears (every tool call shells out fresh).

### Concern 2: CLI auto-update on the MCP-primary user path (absorbed from ticket 145)

The user's actual usage pattern is **MCP-primary, not bare-shell-primary**. Claude sessions invoke `cortex` via MCP tool calls; the user rarely (or never) types `cortex` from a terminal directly.

Ticket 145 originally proposed an inline auto-update gate inside `cortex_command/cli.py::main()` that fires on every bare-shell invocation. During plan-phase architectural discussion, two structural problems with that approach surfaced:

1. The spec's `CLAUDECODE` skip predicate (intentional, to avoid sandbox conflicts) made the gate inactive on the primary user path.
2. The spec's exit-and-rerun design (chosen to avoid TOCTOU race during `uv tool install --force` shim rewrite) meant that even if the gate fired from MCP-spawned cortex subprocesses, the user's intended command would NOT execute — the gate would update and exit 0 with no overnight session.

The right hook point for auto-update is the MCP server, not the CLI. The MCP can: (a) check for upstream updates before delegating to a CLI subprocess; (b) run `cortex upgrade` synchronously if needed; (c) then spawn the user's intended `cortex <subcommand>` against the freshly-installed CLI. Update and the user's intent compose cleanly because they happen in separate subprocesses — the TOCTOU concern that motivated exit-and-rerun in 145 doesn't apply at the MCP layer.

## Scope

Refactor the MCP server into a thin protocol-translation layer. **No shared Python imports** between MCP and CLI; the only contract is `subprocess.run(cortex_argv) + JSON output`.

### In scope

**Decoupling work:**

- **Strip `cortex_command` imports from `cortex_command/mcp_server/tools.py`.** Replace each in-process call (atomic-claim pre-check, session discovery, runner-pid lookup) with a subprocess invocation against the CLI plus JSON parsing.
- **Audit and extend CLI verbs to expose every operation the MCP needs.** Some MCP-internal helpers today have no CLI equivalent — they need to become CLI subcommands or new flags. Likely additions: a session-existence check, possibly a structured error-code path on `cortex overnight start` for atomic-claim collisions.
- **Add `--format json` to every CLI verb the MCP consumes.** Most already have it (`overnight status`, `overnight logs`); audit and fill gaps.
- **Define a versioned JSON contract.** Since the CLI's JSON output becomes a public API for the MCP, schemas need explicit versioning. Add a `schema_version` field to every JSON payload; document the contract in `docs/`.
- **Move MCP source into the plugin.** Either bundle the MCP package under `plugins/cortex-overnight-integration/server/` and invoke via `uvx --from ${CLAUDE_PLUGIN_ROOT}/server cortex-mcp`, or keep it as a PEP 723 single-file script with inline `# /// script` deps. Plugin auto-update then refreshes the MCP source.
- **Update `.mcp.json`** to point at the plugin-bundled invocation rather than `cortex mcp-server`.
- **Deprecate `cortex mcp-server` subcommand** (or keep it as a vestigial path that runs the plugin-bundled server for backward compat — TBD during refine).

**Auto-update orchestration (absorbed from 145):**

- **MCP-side update check.** Before delegating each tool call (or throttled — once per Claude Code session, or once per N minutes; throttle policy TBD during refine), the MCP server runs `git ls-remote` against the cortex repo and compares to local HEAD. Cheap (≤1s with `subprocess.run(timeout=1)`).
- **MCP-orchestrated apply.** When upstream advanced AND skip-predicates aren't tripped (`CORTEX_DEV_MODE=1`, dirty tree, non-main branch — same predicates as the rejected 145 spec, but evaluated MCP-side), the MCP spawns `cortex upgrade` as a subprocess, waits for it to complete, verifies success via `cortex --help` probe.
- **Then-delegate composition.** After successful upgrade, the MCP spawns the user's originally-intended `cortex <subcommand>` against the freshly-installed CLI. From Claude's perspective: one tool call, slightly slower if upgrade was needed, intended action completes. No exit-and-rerun protocol exposed to the user.
- **Concurrent-safe.** Apply path uses blocking `flock` at `$cortex_root/.git/cortex-update.lock` so two concurrent MCP servers (multiple Claude Code sessions) don't both try to upgrade simultaneously. First wins; second waits up to N seconds; if still held after the budget, second logs and continues without upgrading.
- **Failure surface.** Errors at any stage (`ls_remote`, `apply`, `verification`) log structured NDJSON to `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-error.log` AND surface a one-line stderr message via the MCP's logging path. The user's intended tool call still executes against the on-disk CLI version (degraded but not broken).
- **Tests for update orchestration.** Unit tests for the update-check path (mock `git ls-remote`); integration tests verifying upgrade-then-delegate composes correctly; concurrency tests for the flock semantics.

**General:**

- **Tests**: unit tests for the new subprocess+JSON glue; integration tests verifying the MCP correctly invokes CLI subcommands and parses output; tests for schema-version negotiation.

### Out of scope

- **Inline auto-update gate inside `cortex_command/cli.py::main()`.** This was ticket 145's design and was rejected during architectural discussion. The CLI keeps its existing explicit `cortex upgrade` verb (`cli.py:85-119`); no inline gate.
- **Removing the CLI's overnight orchestration logic.** The CLI keeps owning all the heavyweight code; the MCP just delegates.
- **Remote MCP transport (SSE/HTTP).** Stdio remains the only transport.
- **Python deps bundling for the plugin.** Either use uvx (network-fetch on first run) or PEP 723 inline (uvx still does the resolution); not vendoring deps inside the plugin.
- **Multi-version compatibility between MCP and CLI.** First implementation pins MCP to a single CLI schema version; cross-version compatibility is a future concern.
- **Auto-update for bare-shell `cortex` invocations.** Out of scope; bare-shell users explicitly run `cortex upgrade` when they want to update. (If discoverability matters later, a one-line "update available" notice on `cortex` invocation is a small follow-up — not load-bearing.)

## Why now

- The architectural insight came up during ticket 145's plan-phase critical review: the MCP-CLI coupling makes auto-update reasoning unnecessarily entangled.
- Decoupling supports the broader epic 113 distribution model (MCP via plugin auto-update, CLI via `cortex upgrade`), which currently doesn't fully cohere because plugin auto-update can't refresh MCP runtime under the coupled design.
- The change is well-scoped now: cortex's MCP surface is small (5-7 tools), the CLI already exposes most needed verbs with JSON output, and the refactor doesn't require external API changes.

## Value

- **Independent update cadences.** Plugin auto-update refreshes MCP source; the MCP itself orchestrates CLI updates by spawning `cortex upgrade` when needed. Two layers, two mechanisms, neither fights the other.
- **No CLI staleness on the MCP path.** Each MCP tool call shells out to the on-disk CLI fresh; if `cortex upgrade` ran (manually or MCP-orchestrated) since the MCP server started, the next tool-call delegation sees the new code. No Claude Code restart needed for CLI updates to take effect.
- **MCP-protocol staleness still applies.** The MCP server's own protocol-translation glue is loaded in memory at session start; bug fixes to the glue itself require Claude Code restart (or plugin reload). This is unchanged by the refactor — it's a property of any long-running stdio server.
- **Aligns with ecosystem norms.** The thin-MCP-around-CLI pattern matches how `gh`, `aws`, and similar tools' MCP wrappers work. Easier to reason about for anyone reading the codebase.
- **Smaller MCP surface.** ~200-500 lines instead of ~1500. The MCP becomes maintainable as a discrete component instead of an octopus reaching into cortex_command internals.

## Costs / risks

- **Subprocess-call overhead** (~50-100ms per fork/exec). Negligible for Claude's tool-call rate (<10/min) but shows up in benchmarks.
- **JSON contract becomes load-bearing.** Breaking changes to `--format json` output schemas break the MCP. Schema-version field mitigates but doesn't eliminate.
- **CLI surface widens slightly.** Every operation the MCP needs becomes a CLI verb. Most are already there; some new ones may be needed.
- **Refactor scope is non-trivial.** Estimated 10-15 tasks now that auto-update orchestration is absorbed; involves changes across `cortex_command/mcp_server/`, the plugin directory, `cortex_command/cli.py` for new verbs/flags, and `tests/` for both the JSON-contract glue and the upgrade-orchestration concurrency tests.

## Refine-phase open questions

These need answers in research/spec before planning. Listed in priority order.

1. **(LOAD-BEARING) Sandbox reality check: do MCP-spawned subprocesses have write access to `$cortex_root/.git/` and `~/.local/share/uv/tools/cortex-command/`?** Claude Code spawns the MCP server as a stdio subprocess. On macOS, the MCP server may inherit Claude Code's Seatbelt sandbox, which constrains writes to `allowWrite` paths. The 145 spec called out exactly this concern as the rationale for the `CLAUDECODE` skip predicate ("Sandbox writes to `$cortex_root/.git/` would fail anyway"). If the same sandbox applies to MCP-spawned `cortex upgrade`, the entire auto-update orchestration approach in this ticket is structurally broken on macOS. **First research task**: empirically verify whether `cortex upgrade` spawned from an MCP server context can complete, by either (a) reading Claude Code's actual sandbox behavior for MCP subprocesses, or (b) running a probe (`subprocess.run(["touch", "/path/in/.git/test"])` from inside an MCP tool handler) and observing the result. If it fails: the design needs `cortex init`-time `allowWrite` registration of `$cortex_root/.git/` and uv-tools paths, OR a different update-application mechanism entirely.

2. **Throttle policy for the update check.** Three options: (a) every tool call (~165ms ls-remote per call); (b) once per MCP server lifetime (per-process cache, no persistent state needed); (c) once per N minutes (file-based timestamp in `${XDG_STATE_HOME}/cortex-command/last-update-check`, persists across MCP restarts). Decision affects design — (b) is simplest, (c) gives best UX across short-lived sessions, (a) is wasteful. Default proposal during research: option (b), instance-cache; revisit if multi-session UX suffers.

3. **MCP source distribution: PEP 723 single-file vs subdirectory package?** Two options for shipping the MCP source in the plugin: (a) `plugins/cortex-overnight-integration/server.py` with inline `# /// script` deps, invoked via `uvx server.py`; (b) `plugins/cortex-overnight-integration/server/` as a small package with `pyproject.toml`, invoked via `uvx --from ${CLAUDE_PLUGIN_ROOT}/server cortex-mcp`. (a) is simpler if the MCP fits in one file; (b) gives test isolation and editor support. Decision affects plugin layout and CI.

4. **`cortex_root` discovery from the decoupled MCP.** Today the MCP imports `cortex_command` to discover the install root. After decoupling, options: (a) ask the CLI via `cortex --print-root` (new flag); (b) inherit `CORTEX_COMMAND_ROOT` env var convention; (c) hardcoded fallback `$HOME/.cortex` (current convention). Likely (b) + (c) as fallback chain, but should be specified.

5. **JSON contract enumeration.** Audit which CLI verbs need `--format json` (some have it: `overnight status`, `overnight logs`; others may not: `overnight start` exit-on-error, atomic-claim-collision response shape). Enumerate every payload the MCP consumes and define `schema_version` field placement. This is research/spec scope; needs to land before plan.

6. **Skip-predicate semantics for the dogfooding case.** The user is the cortex-command developer; their install is typically a feature branch with a dirty tree. Under the proposed `CORTEX_DEV_MODE` / dirty-tree / non-main-branch skip predicates, the MCP-orchestrated update is structurally inactive for the user's own dogfooding sessions (which is fine — they don't want auto-updates while developing). But this means the user themselves doesn't benefit from this ticket's auto-update; only end-users on clean installs do. Worth confirming this matches user intent before building.

7. **Verification probe + rollback.** What if `cortex upgrade` succeeds at git-pull but `uv tool install --force` fails halfway? Same half-applied concern from the rejected 145 spec. The spec resolved this with a verification probe (`cortex --help` after upgrade); same approach should work here. But there's still no rollback — if verification fails, the install is broken and the MCP can't fix it. The user has to manually `cortex upgrade` from a bare shell. Should be acknowledged as a known limitation.

8. **uvx offline behavior.** First-run uvx invocation does network resolution (~5-10s); subsequent runs are cached. What happens if the user is offline AND the cache is missing (e.g., fresh laptop, first Claude Code session)? The MCP server fails to start. Worth specifying degraded-mode behavior or a bundled-deps fallback.

9. **Migration path for existing plugin installs.** Today's `.mcp.json` points at `cortex mcp-server`. After this ticket, it points at `uvx ${CLAUDE_PLUGIN_ROOT}/...`. Users with the existing plugin get auto-updated to the new config when Claude Code refreshes the plugin. Should be tested or at least specified.

10. **Coordination with ticket 116 (MCP control-plane).** Ticket 116's MCP control-plane work is in flight (per recent commits). The decoupling work in 146 should coordinate with 116's contract to avoid breaking in-flight changes. Refine-phase research should read 116's current state and identify integration points.

## References

- Ticket 145 plan-phase critical review (this conversation): surfaced the coupling concern during the open-questions discussion about gate scope.
- `cortex_command/mcp_server/tools.py:412-436` — current `_spawn_runner_subprocess` already shells out to `cortex overnight start`; the launcher path is already aligned with the proposed pattern.
- `plugins/cortex-overnight-integration/.mcp.json` — current 9-line registration shim; would change to point at plugin-bundled MCP.
- Claude Code plugin docs: `${CLAUDE_PLUGIN_ROOT}` variable for bundled plugin files; `uvx` is the canonical Python MCP distribution mechanism.
- 38% of MCP servers in the public ecosystem are Python uvx-distributed (per MCP server surveys, 2025-2026).
