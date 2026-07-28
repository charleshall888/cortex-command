---
schema_version: "1"
uuid: c7139b02-b906-419f-90b0-bc9bc14a137a
title: Reconcile dashboard docs and observability requirements with reality
status: refined
priority: medium
type: chore
created: 2026-07-21
updated: 2026-07-28
discovery_source: cortex/research/dashboard-command-station/research.md
parent: "410"
tags: ['dashboard-command-station', 'dashboard']
areas: ['dashboard', 'docs']
complexity: complex
criticality: high
spec: cortex/lifecycle/reconcile-dashboard-docs-and-observability-requirements/spec.md
---
## Why

The observability requirements claim the dashboard binds all network interfaces by design while the shipped launch verb binds loopback only, and the app module's own docstring still shows a network-exposed launch line — an operator copy-pasting it would expose an unsanitized-markdown surface to the local network. The same doc's description, inputs, and panel list predate most of the panels the dashboard actually renders.

## Role

Makes the dashboard docs and the observability area requirements tell the truth the reader's no-sanitizer decision depends on, and gives the command-station panels their numbered documentation entries.

## Integration

One pass: the bind-address collapse, the docstring correction, the ownership declaration, and the requirements regather all land together. The bind-address correction is a correctness dependency of the sibling ticket reader's safety posture, so the whole change lands no later than that ticket; the regather replaces the stale description, inputs list, and panel enumeration in the same edit.

## Edges

- Single-pass by nature: the regather removes the panel enumeration rather than extending it, so it depends on no other command-station work.
- The dashboard doc has no declared owner in the policies ownership maps — name one or record the gap.
- Requirements edits follow the requirements-skill conventions rather than ad-hoc rewrites.

## Touch points

- `cortex/requirements/observability.md:29-30,107` — stale description, inputs, and bind claim
- `cortex/requirements/pipeline.md:156` — duplicate bind claim to replace with a delegation
- `cortex_command/dashboard/app.py:11` — stale docstring launch line
- `justfile:101` — the `dashboard_port` idiom the new host variable mirrors
- `docs/dashboard.md:9` — the already-correct bind statement to align with
- `docs/overnight-operations.md:603,607,623-629` — threat model and poller enumeration to relocate
- `docs/policies.md:39,43` — ownership maps lacking a dashboard entry
- `CLAUDE.md:32` — the `docs/policies.md` trigger that must route dashboard work