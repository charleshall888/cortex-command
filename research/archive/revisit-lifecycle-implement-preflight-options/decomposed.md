# Decomposition: revisit-lifecycle-implement-preflight-options

## Epic

- **Backlog ID**: 93
- **Title**: Modernize lifecycle implement-phase pre-flight options

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 94 | Fix daytime pipeline worktree atomicity and stderr logging | high | S | — |
| 95 | Replace daytime log-sentinel classification with structured result file | high | M | — |
| 96 | Add uncommitted-changes guard to lifecycle implement-phase pre-flight | high | S | — |
| 97 | Remove single-agent worktree dispatch and flip recommended default to current branch | medium | M | 96 |

## Key Design Decisions

### Consolidation

Research's original decomposition preview listed five tickets: ticket 4 ("Demote option 1 recommendation") and ticket 5 ("Flip default recommendation to option 3") were separate. During decomposition review (§3 same-file-overlap): both tickets modify the same `AskUserQuestion` block in `implement.md §1` and are two aspects of one prompt-text swap. Merged into a single ticket (now #097).

### User override on DR-1

Research's DR-1 recommended *demote* option 1 based on thin evidence (1 observed successful dispatch; retros are a negative-signal corpus). User overrode to *remove* during post-decomposition review, based on maintenance-cost judgment: preserving scaffolding for a feature with thin usage evidence carries ongoing cost (TC8 events.log divergence, AskUserQuestion sharp edge, `§1a` verbatim prompt, `.dispatching` marker, cleanup-hook coordination) without offsetting benefit. Mitigation for the "medium feature wants inline review" niche: option 4 (create feature branch) provides PR-based workflow without the inner-agent context ceiling.

Ticket #097 therefore scopes to *removal*, not demotion. It explicitly reverses epic #074's DR-2 ("co-exist").

## Dependency Graph

```
94 ─┐
95 ─┤     (independent; land in parallel)
96 ─┴─── 97 (blocked by 96)
```

## Suggested Implementation Order

1. **#094 + #095 in parallel**: daytime pipeline reliability (atomicity/logging) and output contract (structured result file). Independent of each other and of the pre-flight tickets. Ships measurable improvements for current option-2 users.
2. **#096**: uncommitted-changes guard. Prerequisite for #097. Standalone safety value.
3. **#097**: remove §1a + flip default. Final pre-flight reshape. Intermediate-state guarantee: at every step, the pre-flight has a safe default.

Intermediate-state analysis: no state between tickets is strictly worse than today. Before #097, option 1 is still the recommended default; users on main still get a worktree-based safe path. After #097 (with #096 landed), option 3 is recommended with the guard in place.

## Created Files

- `cortex/backlog/093-modernize-lifecycle-implement-phase-preflight-options.md` — epic
- `cortex/backlog/094-fix-daytime-pipeline-worktree-atomicity-and-stderr-logging.md`
- `cortex/backlog/095-replace-daytime-log-sentinel-classification-with-structured-result-file.md`
- `cortex/backlog/096-add-uncommitted-changes-guard-to-lifecycle-implement-phase-preflight.md`
- `cortex/backlog/097-remove-single-agent-worktree-dispatch-and-flip-recommended-default.md`
