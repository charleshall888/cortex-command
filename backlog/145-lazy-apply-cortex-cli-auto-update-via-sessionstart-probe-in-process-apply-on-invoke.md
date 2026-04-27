---
schema_version: "1"
uuid: 83bf0aaa-694e-456b-868b-2c993aaa40d2
title: "Lazy-apply cortex CLI auto-update via SessionStart probe + in-process apply-on-invoke"
status: wontfix
priority: medium
type: feature
created: 2026-04-24
updated: 2026-04-25
parent: "113"
tags: [distribution, upgrade, overnight-layer-distribution]
areas: [install]
complexity: complex
criticality: high
session_id: null
lifecycle_phase: closed
lifecycle_slug: lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke
spec: lifecycle/lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke/spec.md
complexity: complex
criticality: high
---

# Lazy-apply cortex CLI auto-update via SessionStart probe + in-process apply-on-invoke

## Closure note (2026-04-25)

**Closed as wontfix.** During plan-phase critical review and the subsequent architectural discussion, the spec's premise — "users frequently invoke `cortex` from a bare shell, so an inline gate at CLI invocation is the right hook point" — was rejected. The user's actual usage pattern is MCP-driven: Claude sessions invoke cortex via MCP tool calls, not via direct terminal invocation. The spec's `CLAUDECODE` skip predicate (req 4) and exit-and-rerun UX (req 8) together meant auto-update was structurally inactive on the primary user path.

Auto-update orchestration responsibility moved to **ticket 146** (Decouple MCP server from CLI Python imports via subprocess+JSON contract). Under that ticket's design, the MCP server checks for upstream updates on tool calls and runs `cortex upgrade` synchronously before delegating to the user's intended command. This composes cleanly with the user's actual usage pattern, avoids the TOCTOU race that motivated exit-and-rerun, and eliminates the in-flight MCP staleness wart entirely.

The CLI's existing explicit `cortex upgrade` verb (`cli.py:85-119`) remains available for bare-shell use; no inline gate is added.

Lifecycle artifacts (research.md, spec.md, plan.md) preserved in `lifecycle/lazy-apply-cortex-cli-auto-update-via-sessionstart-probe-in-process-apply-on-invoke/` as design history. They document the alternatives considered before the architectural pivot.

---

## Problem

Post-epic-113, cortex-command has three upgrade channels with three verbs: `cortex upgrade` (CLI), `/plugin update` (skills/hooks), `cortex init --update` (per-repo scaffolding). Claude Code owns plugin auto-update as an upstream gap (Q7 of the epic research). Per-repo scaffolding can stay manual — it's infrequent and repo-scoped. **The CLI upgrade verb is the one that will rot in practice**: users open Claude daily, forget to run `cortex upgrade`, and drift behind on fixes they want. The current manual-verb UX was adopted as the known-regression cost of the CLI+plugin split; this ticket closes that regression.

## Scope — Shape 3 (Hybrid lazy-apply)

The approach decouples *checking* (cheap, runs on SessionStart) from *applying* (expensive, runs inside `cortex` itself on next invocation). Rationale: the apply's 2–10s `uv tool install --force` cost is unsafe to run synchronously on every SessionStart but is acceptable when gated on user-initiated `cortex` invocation (the user is already synchronously waiting for that command). This avoids mid-session breakage, silent background failures, and multi-worktree concurrency hazards that a background-apply design would introduce.

### In scope

- **SessionStart hook** (`~/.claude/hooks/cortex-check-update.sh`) that:
  - Respects a daily throttle via `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/last-update-check`
  - Uses `flock -n` on the state-dir lock for parallel-session safety
  - Runs `timeout 5 git ls-remote` against `${CORTEX_REPO_URL:-https://github.com/charleshall888/cortex-command.git}` for the `main` ref
  - Writes `${XDG_STATE_HOME}/cortex-command/update-available` with the remote SHA if it differs from `git -C ${CORTEX_COMMAND_ROOT:-$HOME/.cortex} rev-parse HEAD`
  - Portable platform branching on `stat -f %m` (BSD) vs `stat -c %Y` (GNU)
- **`cortex` CLI wrapper** (`cortex_command/cli.py` `main()`) that:
  - On every invocation, checks the `update-available` flag
  - If set AND not in dev mode, runs `cortex upgrade` synchronously with a one-line user message (`Updating cortex (... → ...)`)
  - On successful upgrade, unlinks the flag
  - On failed upgrade, leaves the flag (retry on next invocation) and prints error but continues with the requested command
- **Dev-mode detection** (skip auto-apply when):
  - `CORTEX_DEV_MODE=1` env var set
  - `git -C ${CORTEX_COMMAND_ROOT} status --porcelain` non-empty (dirty tree; `cortex upgrade` would refuse anyway per 118 R6)
  - `git -C ${CORTEX_COMMAND_ROOT} rev-parse --abbrev-ref HEAD` not `main` (active branch work)
- **`cortex init` allowlist registration**: extend the existing `settings_merge.py` flow to register `${XDG_STATE_HOME}/cortex-command/` in `sandbox.filesystem.allowWrite`
- **Hook wiring**: add the new hook to `~/.claude/settings.json`'s `SessionStart` array alongside the existing `cortex-sync-permissions.py` and `cortex-scan-lifecycle.sh` hooks
- **Tests**: unit coverage for the dev-mode predicates, subprocess-mocked integration test for the apply path, happy-path + failure-path + flag-sticky-on-failure scenarios
- **Documentation**: `docs/setup.md` note explaining the auto-update behavior and how to disable it (`CORTEX_DEV_MODE=1` or deleting the hook)

### Out of scope

- **Background fire-and-forget apply** (Shape 1). Rejected per design review — introduces mid-session breakage (concurrent `cortex` invocations racing with `uv tool install --force` regenerating entry points), requires active-session detection that doesn't map cleanly to cortex's architecture, and requires separate failure-visibility surface.
- **LaunchAgent daemon** (Shape 2 / ticket 112). That's a clean architecture but ticket 112 is currently parked pending CLI shape; Shape 3 delivers the same user-facing UX without the daemon.
- **Auto-applying plugin updates**. Claude Code's job per Q7 research.
- **Auto-applying `cortex init --update`** for project scaffolding. Orthogonal; infrequent; user-triggered is fine.
- **Statusline indicator for pending updates**. Redundant with the in-process apply message. Skip unless user research shows the apply-on-first-invoke message is too subtle.
- **Cross-platform daemon install** (systemd / launchd). Not needed for Shape 3 — the hook + in-process check is pure portable shell + Python.
- **`--version` flag on `cortex` CLI**. Separate concern; useful for brew `test do` but not for this ticket.

## Measured baselines (from feasibility analysis, 2026-04-24)

- `git ls-remote https://github.com/charleshall888/cortex-command.git main`: **150–180ms** consistently across 5 runs on developer machine
- Existing SessionStart chain: `cortex-sync-permissions.py` **71ms** + `cortex-scan-lifecycle.sh` **1.3s** = **~1.4s baseline**
- Auto-update hook daily-check cost: **~165ms** (ls-remote) + ~5ms (rev-parse HEAD) + filesystem ops = **~200ms**, capped at 5s via `timeout`
- Auto-update hook fast-path cost: **<1ms** (timestamp stat + throttle check)
- Apply cost (when triggered on user's next `cortex` invocation): **2–10s** for `git pull --ff-only && uv tool install -e --force`

## References

- Feasibility analysis: session transcript 2026-04-24 (cortex-command lifecycle `homebrew-tap-as-thin-wrapper-around-the-curl-installer`)
- Epic research Q7: `research/overnight-layer-distribution/research.md` (CLI verb chosen; plugin auto-update gap acknowledged)
- Ticket 118 bootstrap installer (idempotency guarantee R10; dirty-tree refusal R6): `backlog/118-bootstrap-installer-curl-sh-pipeline.md`
- `cortex init` allowlist mechanism: `cortex_command/init/settings_merge.py`
- Existing SessionStart hooks: `~/.claude/hooks/cortex-{sync-permissions.py,scan-lifecycle.sh}`

## Related decisions

- **Ticket 125 (Homebrew tap) closed as `wontfix`** — the wrapper-Formula approach was found architecturally unsupported (Pattern B 0/N in survey) and the brew tap's discoverability value did not justify the mismatch; see `lifecycle/homebrew-tap-as-thin-wrapper-around-the-curl-installer/` for the full research and closure rationale. Auto-update (this ticket) was surfaced during 125's design review as a genuinely separate UX improvement and was confirmed feasible via measured timings.
- **Epic 113 DR-4** recommended a brew tap for discoverability; dropping 125 leaves DR-4 partially unaddressed (the discoverability surface). This ticket (145) does NOT substitute for that surface — it addresses a different concern (upgrade UX). If discoverability matters, a follow-up discovery is warranted on Option 2 (from-source Formula via `uv tool install --from git+url@tag`) or equivalent.
