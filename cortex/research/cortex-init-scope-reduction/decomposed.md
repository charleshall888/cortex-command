# Decomposition: cortex-init-scope-reduction

## Work Items

| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 273 | Rescope cortex init --ensure to never write ~/.claude/ | high | S | — |

## Single-piece rationale

The discovery surfaced a small, coherent change: drop three calls from `_run_ensure` in `handler.py`, add a marker-absent stderr message, wire the lifecycle skill to surface the exit-2 case, and align README + landing-page docs. The work pieces are not independently shippable in a useful way — the handler change without the skill wire-up leaves the lifecycle skill broken on bootstrap-from-session; the skill wire-up without the docs fix leaves the modal first-contact path still pointing users to a broken flow; the docs without the code change advertise a feature that doesn't exist yet. One ticket lands the full slice; the plan phase can split into commits if useful.

## Suggested Implementation Order

Single ticket. Suggested commit sequence inside the implementation:

1. handler.py `_run_ensure` refactor + test update.
2. lifecycle SKILL.md Step 2 wire-up.
3. README + docs/index.html alignment.
4. Inline spec.md:5 amendment (or separate follow-on lifecycle if implementation lands in a new release cycle — Open Question #3 of the research).

## Created Files

- `cortex/backlog/273-rescope-cortex-init-ensure-to-never-write-claude.md` — Rescope cortex init --ensure to never write ~/.claude/

## Notes

The discovery went through two synthesis rounds before reaching this recommendation. Round 1 pre-declared an approach before evidence supported one; round 2 over-corrected to theatrical symmetric framing. The final recommendation is grounded in three follow-up gap artifacts (plugin install feasibility, EP/EF/CO load-bearing decomposition, first-contact path frequency) and the user's stated principle that an AI helper shouldn't touch the user's Claude Code settings automatically. The two prior synthesis revisions are preserved in the artifact's §Decision Records as a learning record.
