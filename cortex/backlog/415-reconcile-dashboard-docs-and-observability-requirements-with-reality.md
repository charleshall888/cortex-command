---
schema_version: "1"
uuid: c7139b02-b906-419f-90b0-bc9bc14a137a
title: Reconcile dashboard docs and observability requirements with reality
status: backlog
priority: medium
type: chore
created: 2026-07-21
updated: 2026-07-21
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard', 'docs']
---
## Why

The observability requirements claim the dashboard binds all network interfaces by design while the shipped launch verb binds loopback only, and the app module's own docstring still shows a network-exposed launch line — an operator copy-pasting it would expose an unsanitized-markdown surface to the local network. The same doc's description, inputs, and panel list predate most of the panels the dashboard actually renders.

## Role

Makes the dashboard docs and the observability area requirements tell the truth the reader's no-sanitizer decision depends on, and gives the command-station panels their numbered documentation entries.

## Integration

The bind-address and docstring correction is a correctness dependency of the ticket reader's safety posture and lands no later than that ticket; the full requirements regather completes after the board and strip land, replacing the stale description, inputs list, and panel enumeration.

## Edges

- Two-stage by nature: bind-address truth early, panel regather after the panels exist.
- The dashboard doc has no declared owner in the policies ownership maps — name one or record the gap.
- Requirements edits follow the requirements-skill conventions rather than ad-hoc rewrites.

## Touch points

- `cortex/requirements/observability.md:29-30,107` — stale description, inputs, and bind claim
- `cortex_command/dashboard/app.py:11` — stale docstring launch line
- `docs/dashboard.md:9` — the already-correct bind statement to align with
- `docs/policies.md:39,43` — ownership maps lacking a dashboard entry