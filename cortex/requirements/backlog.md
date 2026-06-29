# Requirements: backlog

> Last gathered: 2026-06-23

**Parent doc**: [requirements/project.md](project.md)

## Overview

The backlog becomes an **optional, backend-configurable** capability rather than a built-in. Today the backlog is a local-file system (`cortex/backlog/NNN-slug.md`) wired directly into `lifecycle`, `discovery`, `refine`, `dev`, `overnight`, and `morning-review`. This area makes two changes: (1) extract the interactive backlog surface into a new optional `cortex-backlog` plugin, mirroring how `cortex-overnight` is optional; and (2) let each repo declare, in the cortex init config, *which* ticketing backend cortex should use — the local cortex-backlog, an external tracker (GitHub Issues, Jira, …), or none.

The driving motivation is adoption: future users already run GitHub Issues / Jira and want cortex to work with their tracker **without cortex maintaining a code adapter per tool**. The key insight that makes "support any tracker" affordable is that the adapter is **user-authored prose in config, consumed by the LLM** — not cortex-maintained code. For an external backend, consumers fall back to the LLM's judgement: they read the configured backend plus a freeform `instructions` hint and drive the user's tracker best-effort (e.g. `gh issue create`). This trades per-tool fidelity for zero per-tool maintenance and aligns with the project's "prescribe What and Why, not How" principle.

The boundary is deliberate: this area delivers extraction + a declarative backend config + LLM-best-effort routing on interactive paths. It does **not** build concrete Jira/GitHub code adapters, and it does **not** physically remove the backlog engine from the wheel. This promotes the backlog from "documented inline (no area doc)" in `project.md` to its own area doc.

## Functional Requirements

### Optional `cortex-backlog` plugin packaging

- **Description**: The interactive backlog surface ships as a separately installable plugin so a repo can omit it. Only the skill surface moves; the engine stays shared.
- **Inputs**: The existing canonical skill `skills/backlog/` (only the interactive backlog surface moves; `skills/backlog-author/` stays in cortex-core).
- **Outputs**: A new `cortex-backlog` plugin containing the `backlog` skill, built and mirrored via the established dual-source pattern (registered in justfile `BUILD_OUTPUT_PLUGINS`, drift-checked at pre-commit, documented as optional in docs/setup.md).
- **Acceptance criteria**:
  - Only `skills/backlog` moves: it is packaged in the `cortex-backlog` plugin, not in `cortex-core`; `skills/backlog-author` remains in cortex-core.
  - The backlog Python engine (`cortex_command/backlog/*`) remains in the wheel and is unaffected by plugin install/uninstall.
  - The dual-source drift gate passes for the new plugin with canonical sources still top-level.
- **Priority**: must

### Configurable backend in the cortex init config

- **Description**: `cortex/lifecycle.config.md` (the doc `cortex init` scaffolds) gains a `backlog:` block declaring the active backend and optional prose instructions.
- **Inputs**: A `backlog:` mapping with `backend:` (one of `cortex-backlog` [default] | `github-issues` | `jira` | a freeform string | `none`) and an optional freeform `instructions:` string.
- **Outputs**: A resolved backend identity that every consumer reads before touching tickets.
- **Acceptance criteria**:
  - The scaffolded `lifecycle.config.md` documents the `backlog:` block with `cortex-backlog` as the default and commented alternatives.
  - An example external config (`backend: github-issues` + an `instructions` hint such as "Use the `gh` CLI; label cortex issues `cortex`; epics are milestones") is documented.
- **Priority**: must

### Backend resolution (config-authoritative)

- **Description**: "Which backend is active" is answered by the config field, defaulting to `cortex-backlog` — not by detecting whether the plugin is installed.
- **Inputs**: The `backlog.backend` value, or its absence.
- **Outputs**: The active backend; absent/unset resolves to `cortex-backlog`.
- **Acceptance criteria**:
  - With no `backlog:` block present, consumers behave exactly as they do today (local backlog).
  - Resolution never depends on introspecting installed Claude Code plugins.
- **Priority**: must

### Consumer backend routing (skill layer)

- **Description**: Backend branching lives in the consumer skills, not in the CLI tools. The `cortex-*` CLI tools remain the cortex-backlog-only local engine.
- **Inputs**: The resolved backend, read by each interactive consumer (`discovery`, `lifecycle`, `refine`, `dev`, `morning-review`).
- **Outputs**: One of three behaviors per consumer — local-engine call, LLM best-effort against an external tracker, or skip.
- **Acceptance criteria**:
  - `cortex-backlog` → consumer uses the existing CLI tools unchanged.
  - external → consumer performs the equivalent operation via LLM best-effort (below).
  - `none` → consumer skips (below).
  - No new per-tool code adapter is introduced; the branch is prose-driven.
- **Priority**: must

### External backend via LLM best-effort (create + round-trip)

- **Description**: For an external backend, consumers drive the user's tracker using the LLM plus the config `instructions`, with no typed client.
- **Inputs**: The composed ticket body (from `backlog-author`), the `instructions` prose, and the tracker's CLI/auth available in the repo.
- **Outputs**: Created/updated/closed tracker items; for write-back, the correct item re-located by search.
- **Acceptance criteria**:
  - Create (discovery): compose the body via `backlog-author`, then create the item in the configured tracker (e.g. `gh issue create`) honoring `instructions`.
  - Round-trip (lifecycle/morning-review): re-resolve the target item by searching the tracker for its title/slug (e.g. `gh issue list`) — the same fuzzy approach `cortex-resolve-backlog-item` uses locally — rather than relying on a persisted ID map.
- **Priority**: should

### Overnight requires `cortex-backlog`

- **Description**: The unattended overnight runner only supports the local backend.
- **Inputs**: The resolved backend at overnight start.
- **Outputs**: Normal operation when `cortex-backlog`; a clear refusal otherwise.
- **Acceptance criteria**:
  - With `backend: cortex-backlog`, overnight selection/scoring/batching is unchanged.
  - With any external backend or `none`, overnight refuses with a message naming the configured backend and stating that overnight requires `cortex-backlog`.
  - Overnight never performs external-tracker writes.
- **Priority**: must

### `none` backend behavior

- **Description**: A repo can opt out of all cortex ticket interaction, including LLM best-effort.
- **Inputs**: `backend: none`.
- **Outputs**: Incidental consumers skip; discovery surfaces its output instead of erroring.
- **Acceptance criteria**:
  - Incidental consumers (lifecycle write-back, refine seeding, morning-review close) skip with a one-line advisory.
  - Discovery surfaces the composed ticket bodies inline / in its research artifact rather than failing, so the work is not lost.
- **Priority**: should

## Non-Functional Requirements

- **Zero per-tool maintenance**: No code adapter per tracker — the core driver. New trackers are supported via user-authored prose, not cortex code.
- **Backward compatibility**: Existing local-backlog repos see no behavior change. The default backend is `cortex-backlog`, and an absent `backlog:` block resolves to it.
- **Safety**: External-tracker writes occur only on interactive (LLM-in-loop) paths where the user is present — never on the unattended overnight path with `--dangerously-skip-permissions`.
- **Honest support claims**: GitHub Issues is the well-supported case (`gh` is near-universal and the model drives it reliably). Jira and freeform backends are documented as best-effort, dependent on the user's CLI/auth, and unverified — not promised as parity. The `instructions` field is how a user closes that gap themselves.

## Architectural Constraints

- Backend routing lives at the skill/consumer layer; the `cortex-*` CLI tools remain cortex-backlog-only (they *are* the local engine).
- The backlog engine (`cortex_command/backlog/*`) stays in the wheel as a shared library; only the skill surface moves to the plugin. Physically removing the package from the wheel (gating every import site in lifecycle/overnight) is explicitly out of scope.
- The `backlog-author` skill remains in cortex-core (it is **not** moved to cortex-backlog): discovery and morning-review compose ticket bodies through it on the external-tracker create path even when the local backlog plugin is absent, so it must ship with the always-installed core plugin.
- The config field is the source of truth for the active backend, not plugin-install detection — the wheel cannot reliably introspect installed Claude Code plugins, and lifecycle/overnight import the backlog module from the wheel.
- Follow the established optional-plugin pattern: register `cortex-backlog` in justfile `BUILD_OUTPUT_PLUGINS`, enforce the dual-source mirror at pre-commit, and document the plugin as optional in `docs/setup.md`.
- Terminology: the local backend is named `cortex-backlog` consistently in config values and prose (not `local`).
- This is a load-bearing decision recorded in [ADR-0016](../adr/0016-configurable-backlog-backend-and-llm-as-adapter.md) (configurable backlog backend + LLM-as-adapter rationale); consumer skills should back-point to it rather than restating rationale.
- The backend-blind rule above applies to the backlog-*engine* `cortex-*` CLIs (the local engine: `cortex-create-backlog-item`, `cortex-update-item`, etc.). A skill-helper verb (`cortex-refine`) may carry a caller-passed `--backend` flag purely as a structural guard — coercing a stale local slug away on a non-local backend — without resolving the backend itself, per [ADR-0019](../adr/0019-skill-helper-verb-backend-structural-guard.md).

## Dependencies

- **Internal consumers**: `lifecycle` (resolve / status-check / write-back), `discovery` (decompose → create), `refine` (tier/criticality seeding), `dev` (pick), `morning-review` (auto-close) — all interactive and backend-aware; `overnight` — cortex-backlog-only.
- **Local engine**: the wheel's `cortex_command.backlog` package and its `cortex-*` console scripts (`cortex-create-backlog-item`, `cortex-update-item`, `cortex-backlog-ready`, `cortex-resolve-backlog-item`, `cortex-generate-backlog-index`, …).
- **External tooling** (non-local backends): the `gh` CLI for GitHub Issues; whatever CLI/auth the user references in `instructions` for Jira and others.
- **Config plumbing**: `cortex init` and the `cortex/lifecycle.config.md` scaffold (`cortex_command/init/handler.py` + templates).
- **Build/distribution**: justfile `BUILD_OUTPUT_PLUGINS` + `build-plugin`, the pre-commit dual-source drift gate, the `docs/setup.md` plugin table, and the CLAUDE.md architecture description.

## Edge Cases

- **External backend configured but overnight is run**: overnight refuses with a clear message naming the configured backend and requiring `cortex-backlog`.
- **Round-trip ambiguity (multiple tracker items match a title/slug)**: the LLM disambiguates or asks the user rather than guessing.
- **Existing `lifecycle.config.md` with no `backlog:` block**: resolves to `cortex-backlog`; zero behavior change (migration is implicit).
- **Empty `instructions` for an external backend**: the LLM falls back to general knowledge of the named tool, best-effort.
- **Backend names a tool the LLM can't drive (no CLI / no auth)**: best-effort fails gracefully and surfaces the error to the user rather than silently dropping work.
- **`none` + discovery**: composed tickets are surfaced inline / in the research artifact, not treated as an error.

## Open Questions

- The Jira best-effort path is unverified — which CLI/auth assumption to document, and whether to ship a starter `instructions` snippet. Deferred until a real Jira user drives it.
- Whether to persist the external ticket ref in the lifecycle artifact for more robust round-tripping, versus relying on title/slug re-resolution. Recommendation: re-resolution for v1; revisit if it proves flaky.
- Whether `cortex init` should interactively prompt for a backend, versus scaffolding the `cortex-backlog` default with commented alternatives. Recommendation: scaffold-with-default + comments, no interactive prompt in v1.
- Whether building any concrete external adapter (beyond LLM best-effort) is ever warranted. Explicitly deferred to a future area decision driven by real demand.
