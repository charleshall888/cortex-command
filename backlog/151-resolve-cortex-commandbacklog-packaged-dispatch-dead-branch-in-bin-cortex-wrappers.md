---
schema_version: "1"
uuid: 35d35337-7372-4f11-b135-3d5b3756ce88
title: "Resolve cortex_command.backlog packaged-dispatch dead branch in bin/cortex-* wrappers"
status: complete
priority: medium
type: bug
blocked-by: []
tags: [scripts, backlog, plugins]
created: 2026-04-29
updated: 2026-04-29
complexity: complex
criticality: high
spec: lifecycle/archive/resolve-cortex-commandbacklog-packaged-dispatch-dead-branch-in-bin-cortex-wrappers/spec.md
areas: [scripts]
lifecycle_phase: implement
session_id: null
---

# Resolve cortex_command.backlog packaged-dispatch dead branch in bin/cortex-* wrappers

## Problem

Four bash wrappers in `plugins/cortex-interactive/bin/` open with a "Branch (a): packaged form" that probes `python3 -c "import cortex_command.backlog.<module>"` and, on success, executes `python3 -m cortex_command.backlog.<module>`. The `cortex_command.backlog` namespace does not exist in this repository — the backlog scripts live at top-level `<repo>/backlog/<module>.py`, not as submodules of the `cortex_command` package. Branch (a) is therefore unreachable in every wrapper: every invocation falls through to Branch (b) (`CORTEX_COMMAND_ROOT`-based dispatch) or Branch (c) (the not-found error).

The dead branch misleads readers about the actual dispatch order, presents a false sense of "packaged" support that doesn't exist, and bloats every wrapper with a probe that is guaranteed to fail.

## Affected wrappers

- `plugins/cortex-interactive/bin/cortex-update-item:5-8`
- `plugins/cortex-interactive/bin/cortex-create-backlog-item`
- `plugins/cortex-interactive/bin/cortex-generate-backlog-index`
- `plugins/cortex-interactive/bin/cortex-build-epic-map`

Each contains the same three-branch shape — Branch (a) is the dead one in every case.

## Out of scope

- `cortex-resolve-backlog-item` has a different, unrelated bug (a Python script that computes the backlog directory as `Path(__file__).parent.parent / "backlog"` under a stale "bin/ → repo root" assumption). It will be tracked in a separate ticket.

## Open questions for refinement

- Is the right fix (a) to delete Branch (a) from each wrapper, (b) to actually move the backlog scripts into a `cortex_command.backlog` package so the branch becomes live, or (c) something else? Research should weigh these options against the broader packaging direction the project is heading in.
- Are there other `bin/cortex-*` wrappers (beyond the four named) that contain the same dead branch and were missed?
