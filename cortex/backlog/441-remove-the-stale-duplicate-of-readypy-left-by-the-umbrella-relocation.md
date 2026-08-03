---
schema_version: "1"
uuid: 6581be4c-ed65-4f59-872b-2335d1488fd7
title: Remove the stale duplicate of ready.py left by the umbrella relocation
status: complete
priority: low
type: chore
created: 2026-08-03
updated: 2026-08-03
parent: "434"
tags: ['staged-epic-gate-tickets']
complexity: simple
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

## Outcome

Deleted. Deadness held on six checks: `pyproject.toml:63` binds the console script to
`cortex_command.backlog.ready:main`; no `bin/` wrapper exists; the wheel packages only
`cortex_command/`, so the copy never shipped; `cortex init` scaffolds only
`cortex/backlog/README.md` into a consumer repo; and the live module is a behavioral
superset (identical `_ELIGIBLE_STATUSES`, same `--tag`, plus missing-index regeneration).

Two corrections to the Why:

- The culprit is `c065c73b` ("Promote cortex-backlog-ready to wheel-tier Python entry
  point", 2026-05-20), not the `#202` relocation `c8110de5`. The promotion created the
  `cortex_command/` copy from this one and left the original in place.
- **One consumer did exist**, contrary to the ticket's premise, and a grep found it only
  once the output was not truncated: `tests/test_backlog_ready_tag_filter.py` invoked the
  file directly as a script, so all six `--tag` behavior tests were pinning code that
  never runs. Repointed at `python -m cortex_command.backlog.ready` with `PYTHONPATH` set
  to the repo root rather than at the `cortex-backlog-ready` console script, which
  resolves to the installed wheel and would mask repo changes.
