# Decomposition: generative-ui-harness

## Epic
- **Backlog ID**: 033
- **Title**: Establish dashboard UI quality baseline

## Work Items
| ID | Title | Priority | Size | Depends On |
|----|-------|----------|------|------------|
| 034 | Fix inline style violations in session_panel and feature_cards | high | S | — |
| 035 | Define evaluation rubric, update lifecycle spec template, create dashboard/CONTEXT.md | high | S–M | — |
| 029 | Add Playwright + HTMX test patterns to dev toolchain | medium | S | 035 |
| 030 | Investigate and fix swim-lane inline styles and layout degradation | medium | M | 029 |
| 031 | Add hover states, loading feedback, and badge micro-interactions | medium | S–M | 034, 035 |
| 032 | Add accessibility foundations (aria-live, multi-modal severity) | medium | S | 035 |

## Wave Structure

**Wave 1** (truly parallel — disjoint file sets):
- 034: session_panel.html + feature_cards.html CSS violations
- 035: lifecycle spec template + claude/dashboard/CONTEXT.md

**Wave 2** (unlocks when both 034 and 035 complete):
- 029: Playwright MCP project config + HTMX settlement utility + fixture setup
- 031: Hover states + loading feedback + badge transitions (builds on violation-free baseline from 034, governed by rubric from 035)
- 032: aria-live regions + multi-modal severity (governed by rubric from 035)

**Wave 3** (unlocks after 029):
- 030: Swim-lane investigation + layout fix (needs Playwright DOM-structure baseline before touching fragile computed layout)

## Key Design Decisions

**Swim-lane excluded from Wave 1**: Swim-lane inline styles are likely data-driven computed values (widths/offsets from timestamps), not static violations. Investigation + refactoring is M effort and requires Playwright as a structural regression baseline before changes are made.

**028 is a merge**: Originally separate "define rubric" (029) and "create CONTEXT.md" (034) tickets. Merged because both are documentation artifacts produced by the same thought process, one feeds directly into the other, and 030 → 031 → 032 all depend on the merged output.

**No terminal evaluation ticket**: The user explicitly declined adding a ticket to apply the rubric against a completed feature. Rubric application happens as part of normal lifecycle review after these tickets land.

**Project-scoped Playwright MCP confirmed**: Research found `.mcp.json` in project root is supported via `claude mcp add --scope project`. No need to modify `~/.claude/settings.json`.

**Playwright cannot verify temporal ordering correctness**: The rubric criterion "swim-lane conveys temporal ordering correctly" requires human visual verification. Playwright covers DOM structure only (inline style absence, element presence, HTMX settlement). This is explicitly documented in ticket 030's safety net note.

## Suggested Implementation Order

Start 027 and 028 in Wave 1 immediately — both are high priority, no dependencies, and together they establish the baseline and quality framework that all downstream tickets need. 029, 031, and 032 can proceed in parallel once both Wave 1 tickets close. 030 (swim-lane) is the last ticket and the most technically complex.

## Created Files
- `backlog/033-dashboard-ui-quality-baseline-epic.md` — epic
- `backlog/034-fix-inline-style-violations-session-panel-feature-cards.md` — CSS violation cleanup
- `backlog/035-define-evaluation-rubric-spec-template-context-md.md` — rubric + spec template + CONTEXT.md
- `backlog/029-add-playwright-htmx-test-patterns-dev-toolchain.md` — Playwright toolchain
- `backlog/030-investigate-fix-swim-lane-inline-styles-layout.md` — swim-lane fix
- `backlog/031-add-hover-states-loading-feedback-badge-micro-interactions.md` — micro-interactions
- `backlog/032-add-accessibility-foundations-aria-live-severity.md` — accessibility foundations
