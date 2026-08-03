---
schema_version: "1"
uuid: 6581be4c-ed65-4f59-872b-2335d1488fd7
title: Remove the stale duplicate of ready.py left by the umbrella relocation
status: backlog
priority: low
type: chore
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
---
## Why

`cortex/backlog/ready.py` is a tracked, divergent, older copy of `cortex_command/backlog/ready.py`. Nothing dispatches to it: `pyproject.toml:63` binds `cortex-backlog-ready` to `cortex_command.backlog.ready:main`, and every skill callsite uses that console script. Its last real change was the `#202` umbrella relocation, which evidently copied rather than moved it. It carries its own `_ELIGIBLE_STATUSES` and its own docstring describing paths that no longer hold, so a reader grepping the status vocabulary finds a declaration that never executes.

## Role

Establishes whether the copy is dead and removes it if so, leaving one `ready.py`.

## Integration

Touches nothing at runtime if the deadness holds — the value is removing a second definition site that a vocabulary or readiness change would otherwise have to be kept consistent with.

## Edges

- Deletion needs positive evidence of deadness, not just an empty grep. Prior false negatives in this repo came from load-bearing files with zero code references, so check `cortex init`'s copy set and any consumer repo that may invoke the path directly before removing.
- The two copies have already diverged in behavior, not only in docstrings — compare before assuming the survivor is a superset.
- If it turns out something does invoke the path, the fix is to make it a thin re-export rather than to keep two implementations.

## Touch points

- `cortex/backlog/ready.py` — the suspected-dead copy, `_ELIGIBLE_STATUSES` at `:77`.
- `cortex_command/backlog/ready.py` — the live module bound by `pyproject.toml:63`.
- `c8110de5` — the `#202` relocation that appears to have left it behind.
