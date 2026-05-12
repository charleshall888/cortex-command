---
schema_version: "1"
uuid: 7f9dd538-380e-49cf-8492-3bd6fb561fb2
title: "Add path-hardcoding parity gate to prevent cortex/ root drift"
status: ready
priority: low
type: feature
created: 2026-05-11
updated: 2026-05-11
tags: [drift-prevention, parity, consolidate-artifacts-under-cortex-root]
complexity: simple
criticality: low
areas: [parity, hooks]
session_id: null
parent: 200
blocked-by: [202]
discovery_source: research/consolidate-artifacts-under-cortex-root/research.md
---

# Add path-hardcoding parity gate to prevent cortex/ root drift

## Problem

After #202 relocates artifacts under `cortex/`, no automated check prevents new code from re-introducing pre-relocation path literals. The existing parity linter at `bin/cortex-check-parity` enforces SKILL.md ↔ bin parity and SKILL.md ↔ source-skill prose parity but does not scan for hardcoded `Path("lifecycle/...")` or `Path("backlog/...")` literals in Python sources. Existing code at `cortex_command/overnight/state.py:321` and similar sites currently uses such literals — a natural pattern future code is likely to copy.

## Value

A parity gate that flags new `Path("lifecycle/...")` / `Path("backlog/...")` / `Path("research/...")` / `Path("requirements/...")` literals (with an allowlist for legitimate cases like the parameterized `lifecycle_base` defaults) prevents silent regression to the pre-relocation layout in any new code added to `cortex_command/`. Without it, drift is gradual and only visible when a path-dependent feature breaks in production.

## Research Context

Listed as Open Question in `research/consolidate-artifacts-under-cortex-root/research.md` — flagged as "follow-up ticket, not a blocker for the relocation itself." Scope:

- New parity check (e.g., `bin/cortex-check-path-hardcoding`) wired into the pre-commit chain alongside `bin/cortex-check-parity`.
- Allowlist support for legitimate parameter defaults (e.g., `lifecycle_base=Path("cortex/lifecycle")` in function signatures).
- Optional: encourage callers to use the upward-walking helper from #201 rather than hardcoding any path prefix.
