---
status: proposed
---

# Configurable backlog backend and LLM-as-adapter

## Context

cortex's backlog is hard-wired to local files (`cortex/backlog/NNN-slug.md`) and the
management surface ships in cortex-core, blocking adoption by teams (multiple real users)
who already run their work on GitHub Issues or Jira. There is no switch to say "this repo
uses a different tracker" or "don't manage tickets here." The driving motivation is
adoption without cortex maintaining a code adapter per tracker.

## Decision

The active backend is declared in `cortex/lifecycle.config.md` (`backlog.backend`, default
`cortex-backlog`); consumers route on the resolved value at the skill layer. External
backends are driven by the LLM plus a freeform `instructions` hint — there is no per-tool
code adapter and the `cortex-*` backlog CLIs gain no backend awareness. The unattended
overnight runner structurally refuses any non-local backend, gated in-process at the prep
step (the only path to bootstrapping a session). The routing is designed to fail toward
today's local behavior so a normal `cortex-backlog` repo is never affected.

## Trade-off / rejected alternatives

- **Per-tool code adapters** — rejected for O(N) per-tracker maintenance. The core
  motivation is zero per-tool maintenance; a typed client per tracker reintroduces exactly
  the maintenance burden this decision exists to avoid.
- **Plugin-install introspection** (deciding the active backend by detecting whether the
  `cortex-backlog` plugin is installed) — rejected because the wheel cannot reliably
  introspect Claude Code plugins, and config must be the source of truth.

## Consequences

- Extensibility without per-tool code: new trackers are supported via user-authored prose,
  not cortex-maintained code.
- External backends are honest best-effort — GitHub Issues is well-supported (`gh` is
  near-universal); Jira and freeform backends are unverified and dependent on the user's
  CLI/auth.
- Consumers back-point to this ADR rather than restating its rationale.

(Three-criteria gate: **hard to reverse** — config schema plus per-consumer routing across
multiple call sites; **surprising without context** — a reader would not predict
LLM-as-adapter over typed clients; **real trade-off** — per-tool adapters were considered
and rejected.)
