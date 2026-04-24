---
schema_version: "1"
uuid: 092f85f8-4ffa-4af6-a32e-e466a6bfdd0f
title: "Multi-session host concurrency registry for cortex overnight"
status: backlog
priority: contingent
type: feature
tags: [overnight, ipc]
created: 2026-04-24
updated: 2026-04-24
blocks: []
blocked-by: []
---

# Multi-session host concurrency registry for cortex overnight

## Context

Filed per R27 follow-up from lifecycle 115. Captures the host-wide session-enumeration problem identified in `lifecycle/rebuild-overnight-runner-under-cortex-cli/research.md` Adversarial #8. This is a future-contingency ticket — no owner is assigned and no work should start until multi-session support becomes a concrete requirement.

## Current design (single-active-session)

Per R9, 115 ships with a single-active-session model: the pointer `~/.local/share/overnight-sessions/active-session.json` names the current session, and tooling (status, cancel, logs) resolves through it. The concurrency problem is avoided by design — at most one runner is expected to be active per host.

## Problem (activates if multi-session becomes concrete)

If cortex-command grows to support concurrent overnight sessions on the same host (e.g., one per repo, or one per lifecycle slug), the single pointer breaks down:

- Status / cancel / logs can no longer dereference a single file.
- Dashboard would need to enumerate live sessions rather than read one pointer.
- Process-group cleanup needs per-session tracking with no lock contention between sessions.

## Tentative scope (to be validated when activated)

- Replace the single `active-session.json` pointer with a registry directory (e.g., `~/.local/share/overnight-sessions/registry/<session-id>.json`) containing liveness metadata (PID, PGID, start time, state path).
- Add `cortex overnight list` to enumerate live and recently-exited sessions.
- Teach `cortex overnight status|cancel|logs` to accept an explicit `<session-id>` and to fall back to the single-live-session case when there is exactly one entry.
- Stale-entry garbage collection on registry reads.

## Out of scope

- All current single-active-session behavior shipped in 115 — this ticket activates only if the constraint is relaxed.

## References

- `lifecycle/rebuild-overnight-runner-under-cortex-cli/research.md` — Adversarial #8
- R9 (single-active-session requirement)
