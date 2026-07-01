# Triage Rendering

Consumed by `/cortex-core:dev` Step 3c (Branch 1 backlog triage). Read this before producing any triage output; it renders the child map from Step 3b into two blocks.

Output is rendered in two blocks. Build both before displaying either — the child map from Step 3b is required for correct deduplication.

#### Block 1: Epic Sections (one per epic in the Ready set)

Render each epic in priority order (critical → high → medium → low). For each epic:

**Epic heading** — render the epic title as a heading marked as non-workable. Do not assign a workflow recommendation to the epic itself (epics are not directly implementable).

**Child list** — under the heading, render ALL children from the child map for that epic (regardless of status — include in_progress, review, blocked, and non-refined children to give a complete picture). For each child, show:

- **ID** — the child's numeric ID
- **Title** — the child's title
- **Status** — the child's current status
- **Refinement indicator**:
  - `[refined]` if the child's `spec:` frontmatter field is present with a non-null value
  - `[needs /cortex-core:refine]` if the `spec:` field is absent or null

**Status-based display variations**:
- Children with `status: in_progress` or `status: review`: show in the list with their status label. Note them as already being worked on; exclude from workflow recommendations.
- Children with `status: blocked`: show in the list with a `[blocked]` indicator. Before the group-level recommendation, note how many children are blocked.

**No-children case** — if the epic has no children in the child map (childless or all children are complete/abandoned): display the heading and a note: "No active child tickets found — consider running `/cortex-core:discovery` to decompose this epic."

**Per-epic workflow recommendation** — after rendering the child list (or no-children note), append a recommendation based on the children's state:

- **No active children** (childless epic or all children complete/abandoned): "No active child tickets found. Consider running `/cortex-core:discovery` to decompose this epic into child tickets."

- **Blocked children note** — if any children have `status: blocked`, prepend the following to the recommendation: "Note: [N] children are blocked — skip them until unblocked. Recommendations apply to the remaining [M] children." (where N is the count of blocked children and M is the count of non-blocked active children).

- **All children refined** (all active, non-in_progress, non-review, non-blocked children have `spec:` present): "All children are refined. Run `/cortex-overnight:overnight` — it will auto-select them via its own readiness scan."

- **Any children unrefined** (any active child that is not in_progress/review/blocked lacks `spec:`): "Run `/cortex-core:refine` on each unrefined child one at a time (each requires interactive spec approval before moving to the next): [list unrefined child IDs and titles]. Once all are refined and have `status: refined`, run `/cortex-overnight:overnight` — it will auto-select the full group."

For the blocked-children note: evaluate the all-refined vs any-unrefined branch using only the non-blocked, non-in_progress, non-review active children. The blocked note is prepended to whichever branch applies.

#### Block 2: Flat Ready List

After all epic sections, render the remaining Ready items in priority order (critical → high → medium → low). Apply the following filters before rendering:

- **Suppress epics**: items detected as `type: epic` are shown in Block 1 — do not repeat them here.
- **Suppress children** (deduplication rule): if an item's numeric ID appears in any entry of the child map built in Step 3b, skip it in the flat list. This applies regardless of whether the child's own status is refined — the child belongs to its epic group, not the flat list.

For each remaining item, render with:
- Priority and type badges
- Title and brief description
- Recommended workflow based on type:

| Item Type | Default Recommendation |
|-----------|----------------------|
| `feature` | `/cortex-core:lifecycle` — structured phases for non-trivial features |
| `bug` | Direct implementation — bugs are typically well-scoped fixes |
| `chore` | Direct implementation — maintenance tasks follow known patterns |
| `spike` | `/cortex-core:discovery` — investigation before committing to build |
| `idea` | `/cortex-core:discovery` — needs research and decomposition first |
| `epic` | See epic grouping section above — children are shown grouped under their epic with per-group workflow recommendations. Do not route epics to `/cortex-core:lifecycle`. |

After presenting both blocks, ask the user which item to pick up. Once chosen, route according to the recommended workflow (or the user's preferred alternative).
