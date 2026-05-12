# Decomposition: consolidate-artifacts-under-cortex-root

## Epic

- **Backlog ID**: 200
- **Title**: Consolidate cortex-command artifacts under a single cortex/ root

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 201 | Add upward-walking project-root detection in `_resolve_user_project_root()` | medium | S | — |
| 202 | Relocate cortex-command artifacts under `cortex/` root | medium | L | 201 |
| 203 | Add path-hardcoding parity gate to prevent cortex/ root drift | low | S | 202 |

## Suggested Implementation Order

1. **#201 first** — independent foundation. The upward-walking helper has standalone value (cortex CLIs work from subdirectories regardless of layout) and removes the DR-1/cwd-only contradiction surfaced in critical-review. Ships before the relocation to give #202 a clean base.
2. **#202 next** — the single atomic relocation commit per DR-7. Operational preconditions: `git add -A`, fresh sandbox preflight against pre-relocation HEAD, no overnight session active, post-commit `cortex init --update`. This is the load-bearing event.
3. **#203 last** — post-relocation drift prevention. Optional but recommended; small follow-up.

## Key Design Decisions

- **No consolidation merges performed**: the three work items each have standalone value and modify distinct file sets. #201 touches `cortex_command/common.py` plus a handful of callers; #202 is the cross-cutting relocation; #203 introduces a new parity gate script. No same-file overlap or no-standalone-value prerequisite triggered the consolidation review.
- **Audit of four unaudited `claude/hooks/`** was considered as a separate ticket but rolled into #202's lifecycle research phase as a pre-plan step — too small to warrant its own ticket.
- **`PREFLIGHT_PATH` data-driveness** and **state-file renaming** (`.cortex-init` → `init.json`, `lifecycle.config.md` → `config.md`) left as Open Questions in research.md rather than spawning tickets — both are cosmetic improvements without urgency.

## Created Files

- `backlog/200-consolidate-cortex-artifacts-under-cortex-root.md` — Epic
- `backlog/201-add-upward-walking-project-root-detection.md` — Foundation feature
- `backlog/202-relocate-cortex-command-artifacts-under-cortex-root.md` — The relocation
- `backlog/203-add-path-hardcoding-parity-gate-to-prevent-cortex-root-drift.md` — Drift-prevention follow-up
