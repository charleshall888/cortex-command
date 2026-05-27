# Decomposition: auto-init-and-update

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 267 | Auto-apply cortex init at /lifecycle entry via cortex init --ensure | medium | M | — |

## Consolidation Notes

The research-phase Architecture section enumerated six pieces by role (content-hash signal, `.cortex-init` marker field, `cortex init --ensure` flag, lifecycle SKILL.md wiring directive, `--print-root` envelope extension, CLAUDE.md flock primitive). At the R15 batch-review gate the user consolidated all six into a single ticket: four of the pieces (hash signal, marker field, --ensure flag, lifecycle wiring) ship together as one PR and cannot be sequenced independently; the CLAUDE.md flock fix was bundled as a co-traveler in the same ticket scope; the `--print-root` envelope publication was deferred and surfaced as a known follow-up inside the feature ticket's Edges section. The piece-by-role decomposition was structurally honest about the role boundaries, but the user's preference for fewer tickets reflected the practical reality that those roles all land in one implementation. The surviving ticket 267 carries Why/Role/Integration/Edges/Touch points covering all six original roles.

## Suggested Implementation Order

Single ticket — implement as one feature lifecycle. Within the lifecycle's plan phase, the natural sequence is: derive the `init_artifacts_hash` function in `scaffold.py`, extend the `.cortex-init` write_marker to persist the hash, add the `--ensure` argparse branch in `handler.py`, wire the lifecycle SKILL.md directive, add the CLAUDE.md sibling-lockfile flock to `ensure_claude_md_authorization`.

## Created Files

- `cortex/backlog/267-auto-apply-cortex-init-at-lifecycle-entry-via-cortex-init-ensure.md` — Auto-apply cortex init at /lifecycle entry via cortex init --ensure
