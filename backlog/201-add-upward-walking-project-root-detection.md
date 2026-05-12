---
schema_version: "1"
uuid: 391e2823-ea89-4b72-8b35-54660eb983a3
title: "Add upward-walking project-root detection in _resolve_user_project_root()"
status: ready
priority: medium
type: feature
created: 2026-05-11
updated: 2026-05-11
tags: [cli-ergonomics, consolidate-artifacts-under-cortex-root]
complexity: simple
criticality: low
areas: [cli, init]
session_id: null
parent: 200
discovery_source: research/consolidate-artifacts-under-cortex-root/research.md
---

# Add upward-walking project-root detection in _resolve_user_project_root()

## Problem

`cortex_command/common.py:79-80` detects the cortex project root via a cwd-only check (`(cwd / "lifecycle").is_dir() or (cwd / "backlog").is_dir()`) — no upward walk. Running any cortex CLI (`cortex backlog list`, `cortex backlog show`, etc.) from a subdirectory raises `CortexProjectRootError`. Every comparable tool (git, npm, cargo, terraform, kubectl) walks upward to find the project root.

## Value

After the `cortex/` relocation (epic #200), users will routinely `cd` into `cortex/lifecycle/<feature>/` to read artifacts (the visibility rationale in research DR-1 explicitly anticipates this — "content you'll spend time in"). Cwd-only resolution then misfires from inside their own project, making every cortex CLI invocation fail until they `cd` back to repo root. Upward-walking removes that papercut and brings cortex in line with conventional CLI behavior.

## Research Context

See research §DR-10 for the decision and reviewer-3's critical-review challenge that surfaced the DR-1/cwd-only contradiction. Scope per the DR:

- Implement a small helper (e.g., `_resolve_user_project_root_with_walk()`) that walks upward from `cwd` until it finds `cortex/` (or `lifecycle/`/`backlog/` during the transition) OR hits a `.git/` boundary.
- Update callsites at `cortex_command/common.py:79-80`, `cortex_command/overnight/daytime_pipeline.py:59`, `cortex_command/backlog/{generate_index,update_item,create_item}.py`, and `cortex_command/discovery.py`.
- Emit the resolved root in CLI invocation logging (one line) so failure modes are self-diagnosing.

## Out of scope

- The full `cortex/` relocation (epic #200, ticket #202) — this ticket ships independently and applies to today's flat layout.
- Refactoring callsites that already accept a `lifecycle_base` parameter — those are already parameterizable and need no resolver change.
