---
schema_version: "1"
uuid: e697d252-3c14-4d08-a7aa-5e1390186f9f
title: "Trigger cortex CLI reinstall at SessionStart on CLI_PIN drift"
status: complete
priority: medium
type: feature
created: 2026-05-18
updated: 2026-05-20
complexity: complex
criticality: high
spec: cortex/lifecycle/trigger-cortex-cli-reinstall-at-sessionstart/spec.md
areas: [overnight-runner,hooks]
session_id: null
---

## Problem

The current CLI auto-update flow (see `docs/internals/auto-update.md`) is MCP-tool-call-gated: `_ensure_cortex_installed` only fires when a call routes through the `cortex-overnight` MCP server. Anything else — interactive skill prose that shells out to `cortex …` via Bash, hooks in `claude/hooks/`, plugin-mirrored `bin/cortex-*` Python helpers that import from `cortex_command.*`, schema-bumped envelopes parsed outside MCP — bypasses the version check entirely. The `implement.md §1a` preflight surfaces this gap loudly but only fires in the overnight loop; interactive sessions get no analogous protection.

When the plugin updates via marketplace (Layer 1) and the user starts a new session, the new `CLI_PIN[0]` is loaded but no mechanism syncs the installed CLI until they happen to invoke an MCP tool. Failure modes when this gap bites: `No such command 'X'` on a Bash-routed `cortex` invocation, `ImportError` from a mirrored bin script importing a not-yet-installed module, silent JSON-parsing breakage on schema-bumped envelopes.

## Proposed direction

Add a SessionStart hook that runs the same version probe + reinstall logic `_ensure_cortex_installed` uses, factored out so both the MCP entrypoint and the SessionStart hook share one source of truth (or vendored byte-identical the way `check_in_flight_install_core` already is between CLI and plugin).

Confirmed via claude-code-guide: there is no `PluginUpdated` event in Claude Code's hook system. SessionStart is the only practical hook point. Plugin hooks load at SessionStart, and the marketplace fast-forward completes before SessionStart fires, so the hook sees the post-update `CLI_PIN`.

## Design constraints

- **Probe must be cheap in the no-op case** (~50ms): silent parse of `cortex --print-root --format json`, compare against embedded `CLI_PIN[0]`. Only block on actual mismatch.
- **Honor dev-mode skip predicates** identically to `_ensure_cortex_installed`: `CORTEX_DEV_MODE=1`, dirty working tree, non-`main` branch. Dogfooders must not fight their own clones.
- **Defensive on its own failures**: probe error (network, uv missing, transient) must `exit 0` — a hook that bricks Claude Code launch is worse than the gap it's closing. Log the failure to a known path so the next interactive Bash failure can correlate.
- **Reuse `check_in_flight_install_core`**: byte-identical vendoring already exists between `cortex_command/install_guard.py` and `plugins/cortex-overnight/install_guard.py`; add a third mirror or factor differently as part of this work.
- **Clear user-facing status on the mismatch path**: print a single line like `cortex CLI 2.0.0 → 2.1.0, reinstalling…` so a 30s pause is comprehensible rather than mysterious.
- **Schema-floor check parity**: the existing `_schema_floor_violated` stderr remediation message logic should fire from this hook too when the schema major differs.

## Open questions

- Block startup until reinstall completes (safer, closes the gap) vs surface a warning and let the first Bash failure carry the diagnostic (faster startup, doesn't fully close the gap)? Recommendation: block, since the no-op path is cheap and the slow path is the rare correct-behavior case.
- Where does the shared probe/install module live? Likely a third byte-identical mirror or a refactor of the plugin-imports-zero-cortex-modules contract.
- How does the SessionStart hook discover `CLI_PIN[0]`? Today only the cortex-overnight plugin carries it. If the hook ships in a different plugin (or in cortex-core), CLI_PIN needs to be readable from there too, or the hook needs to read the cortex-overnight plugin's source file.

## References

- `docs/internals/auto-update.md` — two-layer architecture, component map, Bash-tool carve-out (currently documented as wontfix per `#145`).
- `plugins/cortex-overnight/server.py:775` — `_ensure_cortex_installed` is the canonical Layer-2 implementation to factor or vendor.
- `cortex_command/install_guard.py` + `plugins/cortex-overnight/install_guard.py` — existing byte-identical mirror pattern (`.githooks/pre-commit` enforces parity, `tests/test_install_guard_parity.py` asserts identical decisions).
- `skills/lifecycle/references/implement.md` §1a — existing preflight diagnostic that surfaces the gap in the overnight flow.
- Conversation context (2026-05-18 session): user-initiated investigation of plugin versioning, established the Bash-tool gap as a structural risk for interactive sessions.
