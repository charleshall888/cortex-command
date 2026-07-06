# Triage Rendering

Consumed by `/cortex-core:dev` Step 3c: renders the Step-3b child map into two blocks. Build both before displaying either — Block 2's dedup depends on the full map.

#### Block 1: Epic Sections (one per epic in the Ready set)

Render in priority order (critical → high → medium → low). Per epic:

- **Heading**: epic title, marked non-workable (no workflow recommendation on the epic itself).
- **Child list**: show ALL children regardless of status — ID, title, status, and a refinement indicator: `[refined]` if `spec:` is present and non-null, else `[needs /cortex-core:refine]`. `in_progress`/`review` children keep their status label but are excluded from workflow recommendations (already being worked); `blocked` children get a `[blocked]` indicator.
- **No children** (childless, or all complete/abandoned): show the heading with "No active child tickets found — consider running `/cortex-core:discovery` to decompose this epic."
- **Per-epic recommendation**, evaluated over the non-blocked, non-in_progress, non-review active children only:
  - If any children are blocked, prepend "Note: [N] children are blocked — skip them until unblocked. Recommendations apply to the remaining [M] children."
  - All those children refined: "All children are refined. Run `/cortex-overnight:overnight` — it will auto-select them via its own readiness scan."
  - Any unrefined: "Run `/cortex-core:refine` on each unrefined child, one at a time (each needs interactive spec approval before the next): [unrefined IDs and titles]. Once all are `status: refined`, run `/cortex-overnight:overnight` to auto-select the group."

#### Block 2: Flat Ready List

After the epic sections, render remaining Ready items in priority order, excluding `type: epic` items (shown in Block 1) and any item whose ID is in the child map (it belongs to its epic group). Show priority/type badges, title, brief description, and workflow by type:

| Item Type | Default Recommendation |
|-----------|----------------------|
| `feature` | `/cortex-core:lifecycle` — structured phases for non-trivial features |
| `bug` | Direct implementation — bugs are typically well-scoped fixes |
| `chore` | Direct implementation — maintenance tasks follow known patterns |
| `spike` | `/cortex-core:discovery` — investigation before committing to build |
| `idea` | `/cortex-core:discovery` — needs research and decomposition first |
| `epic` | Grouped under Block 1 with per-group recommendations; never route to `/cortex-core:lifecycle`. |

After both blocks, ask the user which item to pick up, then route per its recommendation or the user's preferred alternative.
