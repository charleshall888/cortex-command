# Triage Rendering

Build both blocks before displaying either — Block 2's dedup depends on the full epic map.

## Block 1: Epic sections

One per epic in the ready set, in priority order. Per epic: the title marked non-workable (epics never get a workflow recommendation), then **all** children regardless of status — ID, title, status, and `[refined]` when `spec:` is present and non-null else `[needs /cortex-core:refine]`. `in_progress`/`review` children keep their label but are excluded from recommendations; `blocked` children get a `[blocked]` indicator.

No active children → "No active child tickets found — consider running `/cortex-core:discovery` to decompose this epic."

Otherwise recommend over the non-blocked, non-in_progress, non-review children:

- Any blocked → prepend "Note: [N] children are blocked — recommendations apply to the remaining [M]."
- All refined → "Run `/cortex-overnight:overnight` — it will auto-select them via its own readiness scan."
- Any unrefined → "Run `/cortex-core:refine` on each unrefined child, one at a time (each needs interactive spec approval before the next): [IDs and titles]."

## Block 2: Flat ready list

The remaining ready items in priority order, excluding epics (Block 1) and any item in the child map. Show priority/type badges, title, brief description, and the workflow: `feature` and `spike` → `/cortex-core:lifecycle`; `bug` and `chore` → direct implementation; `idea` → `/cortex-core:discovery`.
