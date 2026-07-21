---
schema_version: "1"
uuid: 2801ee9a-7bbe-467f-b2fc-592e84335c52
title: Remove the four superseded lifecycle console verbs still shipping on PATH
status: backlog
priority: medium
type: chore
created: 2026-07-21
updated: 2026-07-21
tags: ['cli', 'cleanup']
areas: ['lifecycle']
---
## Why

Four `cortex-lifecycle-*` console entry points sit allowlisted as `deprecated-pending-removal` in the
parity exceptions file — `parse-args` and `dispatch-choice` since 2026-07-03, `branch-mode` and
`picker-decision` since 2026-07-20. Each was superseded by a composed façade verb that imports the
underlying function directly, so the CLI wrappers are dead weight shipping in every install.

The sharper reason is correctness, not tidiness. `cortex-lifecycle-picker-decision` is still on
`PATH` and still returns the guard-poor `{fire, reason}` payload whose poverty produced #358's wrong
"worktree unavailable" conclusion — it carries no `worktree_option_available` and no
`uncommitted_changes` field, so a caller cannot render the picker correctly from it. #404 replaced
the prose that called it, but a verb that still exists can still be called by a session working from
a stale protocol memory. Removing the entry point converts that fix from prose-only enforcement into
structural enforcement, which is the project's stated preference.

## Role

Retire the four superseded console entry points without touching the logic behind them.

1. Drop the four console-script entries and any CLI wrapper that exists solely to back them.
2. Keep every underlying function — the façade verbs import them directly and tests pin their
   behaviour.
3. Prune the four now-obsolete allowlist rows in the same change, so the orphan warning neither
   re-fires against live scripts nor points at deleted ones.
4. Decide the treatment of the two ADRs that name a removed verb.

## Integration

- Editing `bin/cortex-*` is lifecycle-gated by the project instructions, so this needs a lifecycle
  rather than an ad-hoc commit.
- Entry-point removal is a wheel/distribution surface change: it lands with the next release, and
  anyone invoking these verbs from muscle memory or a stale script gets command-not-found. They are
  internal lifecycle verbs with no documented consumer contract, so that is acceptable — but confirm
  no consumer repo invokes them before removing.
- The allowlist rows and the script removal must land together: pruning rows early re-fires the
  `W003` orphan warning, pruning late leaves rows pointing at nothing.

## Edges

- The underlying functions must survive: the picker-fire gate, the branch-mode read, the
  dispatch-choice read, and the invocation-grammar parser are all imported by the composed façade
  verbs and pinned by existing tests. Only the console wrappers go.
- Two accepted ADRs name a removed verb by its command name. ADRs are point-in-time records, so
  leaving them untouched is defensible — but the ADR citation audit should stay green either way.
- Historical lifecycle and research artifacts reference these verbs throughout. They are project
  history and must not be rewritten to match.
- Verify each script is genuinely unreferenced in the linter's scan surface before deleting; the
  allowlist currently suppresses the warning that would otherwise prove it.

## Touch points

- `pyproject.toml` — the four `[project.scripts]` entries.
- `bin/.parity-exceptions.md` — four `deprecated-pending-removal` rows to prune.
- `cortex_command/lifecycle_implement.py` (`should_fire_picker`),
  `cortex_command/lifecycle/branch_decision.py` (`read_branch_mode`, `read_dispatch_choice`),
  `cortex_command/lifecycle/parse_args.py` (`parse`) — keep the functions, drop wrapper entry points
  that exist only for the console scripts.
- `cortex/adr/0012-merged-plan-approval-and-dispatch-selection.md`,
  `cortex/adr/0018-structural-lifecycle-invocation-grammar.md` — mentions of removed verb names.
- Superseding verbs: `cortex-lifecycle-branch-decision`, `cortex-lifecycle-resolve`.
- Predecessor: #404 (removed the last prose call sites for `branch-mode` / `picker-decision`).
