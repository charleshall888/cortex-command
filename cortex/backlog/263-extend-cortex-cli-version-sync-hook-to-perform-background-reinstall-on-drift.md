---
schema_version: "1"
uuid: 1b9ed218-01d7-4ad1-a699-26e2d8097d79
title: "Extend cortex-cli-version-sync hook to perform background reinstall on drift"
status: refined
priority: high
type: feature
created: 2026-05-25
updated: 2026-05-25
lifecycle_slug: extend-cortex-cli-version-sync-hook
lifecycle_phase: research
complexity: complex
criticality: high
spec: cortex/lifecycle/extend-cortex-cli-version-sync-hook/spec.md
areas: ['overnight-runner', 'hooks']
---
## Problem

The cortex-cli-version-sync SessionStart hook (#235) is visibility-only — it detects CLI_PIN drift and emits `additionalContext` but does not reinstall. The reinstall path remains MCP-tool-call-gated via `_ensure_cortex_installed` in `plugins/cortex-overnight/server.py:775`. Users who never invoke an overnight MCP tool (daytime-only workflows: skill prose, Bash `cortex …`, hooks under `claude/hooks/`, plugin-mirrored bin scripts) stay on a stale CLI indefinitely. Manual remediation (`uv tool install --reinstall --refresh-package cortex-command git+…@<tag>`) is the only recovery path.

The original ticket #235 proposed reinstall-on-drift but was reduced to visibility-only at the Spec phase. The rationale (recorded in `cortex/lifecycle/trigger-cortex-cli-reinstall-at-sessionstart/research.md:205-282`) was:

1. No streaming UI at SessionStart → blocking install freezes launcher
2. `from server import CLI_PIN` broken at import
3. Probe cost ~10× optimistic without throttle
4. `_ensure_cortex_installed` already covers execution gap on next MCP call

Findings 2 and 3 were resolved by the visibility hook's actual implementation (`cli_pin.py` sibling extraction + 30-minute throttle sentinel). Finding 1 is moot if the install runs in the background (no UI required). Finding 4 was the load-bearing assumption — it presumed every user eventually triggers an MCP call, which fails for daytime-only users.

## Proposed direction

Extend the existing visibility hook to also fire a background reinstall when drift is detected. The hook returns immediately (no freeze); the install completes in 5–30s in the background. The existing `additionalContext` warning is still emitted so Claude routes intelligently during the race window.

The install runs via `nohup` + `&` + `disown` so the SessionStart hook does not block. `uv tool install --reinstall` rewrites the binary in place; already-exec'd processes hold the old inode and new `cortex` invocations re-exec from PATH after install completes.

## Design constraints

- **Background install must acquire the existing flock** to avoid racing the MCP-call-gated `_ensure_cortex_installed` path or concurrent SessionStart hooks.
- **Consult `check_in_flight_install_core`** before reinstalling — abort if an overnight session is active (matches existing semantics).
- **Use `--refresh-package cortex-command`** in the install argv (matches the canonical form at `server.py:631`) so force-pushed release tags invalidate uv's git cache.
- **Honor existing skip predicates** (`CORTEX_DEV_MODE=1`, dirty tree, non-`main` branch) — same as the visibility hook.
- **Log to `~/.local/state/cortex-command/last-install.log`** for failure diagnosability — the user has no other surface to see background install failures.
- **Handle first-install case** — probe says \"not installed\" → trigger fresh install instead of reinstall.
- **Schema-floor mismatch during install window** — `_schema_floor_violated` should detect an in-progress background install (via flock or marker file) and emit \"install in progress, retry in 30s\" instead of the generic remediation.

## Open questions

- **Factor vs vendor the install logic.** `_ensure_cortex_installed` is ~200 lines tangled with MCP-specific concerns (NDJSON staging, MCP return shapes). Two paths:
  - Factor into a shared stdlib-only module that both server.py and the hook import. Cleanest but requires real refactor.
  - Vendor a byte-identical mirror at `plugins/cortex-overnight/install_core.py` the same way `install_guard.py` is mirrored, with pre-commit parity enforcement. Faster; adds a third file to the mirror set.
- **NDJSON audit records** — should the background install emit `session_start_reinstall` records to the existing audit log? Adds an allowlist entry to `_NDJSON_ERROR_STAGES`.
- **Throttle behavior on reinstall** — reuse the existing 30-min visibility-hook sentinel, or use a separate sentinel for reinstall attempts? (E.g. avoid retrying a failed install for 30 minutes.)

## References

- `cortex/backlog/235-trigger-cortex-cli-reinstall-at-sessionstart-on-cli-pin-drift.md` — original ticket, now `status: complete` (visibility-only as shipped).
- `cortex/lifecycle/trigger-cortex-cli-reinstall-at-sessionstart/research.md` — Alternatives A–F analysis; Q1 in Open Questions was the central scope decision.
- `docs/internals/auto-update.md` — two-layer architecture; this ticket would change the Bash-tool carve-out section.
- `plugins/cortex-overnight/server.py:580-772` — `_run_install_and_verify` (the install argv + verify probe to reuse).
- `plugins/cortex-overnight/server.py:775` — `_ensure_cortex_installed` (the orchestrator to factor or vendor).
- `plugins/cortex-overnight/hooks/cortex-cli-version-sync.sh` — visibility hook to extend.
- `cortex_command/install_guard.py` + `plugins/cortex-overnight/install_guard.py` — existing byte-identical mirror pattern.

## Conversation context

2026-05-25 session: user investigated whether CLI auto-update was working, observed local CLI at 2.9.0 vs CLI_PIN at v2.10.0 (just released that day), and traced the gap. Original objection: \"It is absolutely not an option to make users manually update this or wait for the MCP to do it. Some users may not even use the MCP overnight mode, and just use daytime.\"