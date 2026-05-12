---
name: dev
description: Development entry point that analyzes requests and routes to the appropriate workflow. Use when user says "/cortex-core:dev", "what should I work on", "start working on", "dev hub", "where do I start", "next task", "what's next", or describes a feature without naming a specific skill.
inputs:
  - "request: string (optional) — development request or description; omit to trigger backlog triage of refined items"
outputs:
  - "Routing delegation (stdout) — one of: /cortex-core:lifecycle, /pipeline, /cortex-core:discovery, or direct implementation"
  - "Backlog triage summary (stdout) — refined items with recommended workflows (when invoked with no request)"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory should exist (required for triage mode)"
---

# Dev

A conversational routing hub — the single entry point for all development workflows. Analyzes the user's request and delegates to the appropriate skill or workflow.

## Invocation

- `/cortex-core:dev` — open-ended; triggers backlog triage
- `/cortex-core:dev {{request}}` — analyze and route to the right workflow

## Step 1: Classify the Request

Read the user's input and classify it into one of five routing branches. Evaluate in this order — first match wins.

**Skill name mentions**: If the user names a specific skill (e.g., "use skill-creator", "run discovery on X"), treat it as a strong signal during classification — not an automatic pass-through. Dev always analyzes the request and provides its own assessment. If the analysis agrees with the user's stated preference, route there with context. If it disagrees, present the discrepancy and let the user decide. The user chose `/cortex-core:dev` over invoking the skill directly because they want the routing hub's analysis.

### Branch 1: Backlog Triage

The user asks what to work on, without naming a specific feature.

**Signals**: "what should I work on", "what's next", "next task", "where do I start", bare `/cortex-core:dev` with no arguments, or any request for prioritization guidance.

**Action**: Execute the backlog triage workflow (Step 3).

### Branch 2: Multi-Feature / Batch

The user describes multiple features or uses batch language.

**Signals**: Lists of features, "these features", "all of these", "batch", or three or more distinct feature names in one request.

**Action**: Assess each task's complexity before routing. Classify each as **trivial** (single file, obvious fix, one approach) or **non-trivial** (needs research, multiple files, architectural decisions).

- **All non-trivial**: State: "Invoke `/pipeline`" with the feature list.
- **All trivial**: Execute direct implementation (Step 4) for each sequentially in the current conversation.
- **Mixed**: Present a **hybrid plan** — `/pipeline` for non-trivial tasks, direct implementation for trivial ones. Execute trivial tasks first (or in parallel with the pipeline) to get quick wins shipped while structured work proceeds.

When presenting the hybrid plan, show a table classifying each task with its routing and brief justification, then ask the user to confirm or adjust before proceeding.

### Branch 3: Vague / Uncertain Topic

The user describes something broad or uncertain that needs decomposition before building.

**Signals**: "I'm not sure how to approach", "need to understand", "explore", "investigate", "what are the options for", or a topic description that lacks concrete implementation details.

**Action**: State: "Invoke `/cortex-core:discovery <topic>`" with the topic extracted from the request.

### Branch 4: Trivial Change

The user describes a change that is clearly trivial — single file, existing pattern, fully specified, one obvious approach.

**Signals**: "just change", "rename", "update the config", "bump the version", "fix this typo", or a request with an obvious single-file scope.

**Action**: Execute the direct implementation workflow (Step 4).

### Branch 5: Default (Single Concrete Feature)

The user describes a single non-trivial feature that does not match any earlier branch.

**Action**: Perform the criticality pre-assessment (Step 2), then state: "Invoke `/cortex-core:lifecycle <feature-name>`" along with the criticality context.

### Ambiguous Requests

When the request could reasonably match two branches (e.g., a topic that might be lifecycle or discovery), do not guess. Present both options with a one-sentence description of each path and ask the user to choose:

> This could go two ways:
> - **Lifecycle**: Build `<feature>` through structured phases (research → spec → plan → implement)
> - **Discovery**: Investigate `<topic>` deeply, then decompose into backlog tickets
>
> Which fits better?

Honor the user's choice immediately.

## Step 2: Criticality Pre-Assessment

Before routing to `/cortex-core:lifecycle`, analyze the feature description for heuristic signals that suggest elevated criticality.

### Heuristic Signals

Scan the feature description for these indicators:

| Signal | Suggests |
|--------|----------|
| Authentication, authorization, access control | high or critical |
| Security, encryption, secrets, tokens | high or critical |
| Payments, billing, financial data | critical |
| Shared library, core module, base class | high |
| CI/CD, deployment, infrastructure | high |
| Foundational tooling other capabilities are built on | high or critical |
| Database migration, schema change | high |
| Data deletion, destructive operations | high or critical |
| User-facing API change, public interface | medium or high |
| Configuration, settings, preferences | low or medium |
| Documentation, comments, formatting | low |

### Forming the Suggestion

Based on signals found (or absence of signals), suggest a criticality level:

- **low**: No elevated signals. Failure is easily reversed and has minimal impact.
- **medium**: Some signals present but scope is contained. Default when uncertain.
- **high**: Multiple signals or broad blast radius. Failure is hard to reverse.
- **critical**: Security, financial, or data-loss signals. Failure has severe consequences.

Present the suggestion conversationally:

> **Criticality suggestion: `<level>`** — `<one-sentence justification>`.

If no heuristic signals are detected, suggest **medium** (the lifecycle default) and note that no elevated signals were found.

### Resumed Lifecycle

Before performing this assessment, check whether `cortex/lifecycle/<feature>/` already exists. If it does:

1. Read criticality by running `cortex-lifecycle-state --feature <feature> --field criticality` (emits JSON; defaults to `medium` when the key is absent).
2. Inform the user: "A lifecycle for `<feature>` already exists at `<phase>`. Resume it?"
3. If the user confirms, state: "Invoke `/cortex-core:lifecycle <feature>`" to resume. Skip the criticality suggestion — the existing lifecycle already has one.
4. If the user wants to start fresh, confirm they want to discard existing artifacts before proceeding.

## Step 3: Backlog Triage

When routing to backlog triage:

### 3a. Regenerate the Index

Run the global shell command `cortex-generate-backlog-index` directly (do NOT use a project-local script). If it fails, warn that `index.json` may not be produced.

If it fails:
- Warn the user: "Index generation failed. Falling back to the existing index."
- Attempt to read `cortex/backlog/index.md` directly. If that file also does not exist, report: "No backlog index found. Use `/cortex-core:backlog add` to create items, then re-run `/cortex-core:dev`."

### 3b. Read the Ready Section

Read `cortex/backlog/index.md` and extract the **Ready** section — items with no unresolved blockers.

If no items are in the Ready section:
- Report: "No ready items in the backlog."
- Suggest: check blocked items for stale dependencies, or create new items with `/cortex-core:backlog add`.

**Epic detection and child map construction** (must complete before any output is rendered):

Invoke `cortex-build-epic-map` to produce the deterministic epic→children map. The script reads `cortex/backlog/index.json`, auto-detects `type: epic` items, and groups non-epic items under their normalized parent epic (handling quote-stripping, UUID-format parent references, and integer comparison internally). Capture stdout as JSON.

**Schema note**: The Refined section contains `status: refined` items (spec-approved, overnight-eligible). The Backlog section contains `status: backlog` items (not yet refined).

**Output schema**: The script emits an envelope `{"schema_version": "1", "epics": {...}}` where each `epics[epic_id]` contains a `children` array. Each child entry has four fields: `id` (numeric), `title` (string), `status` (string), and `spec` (string or null). A non-null `spec` indicates a refined child; Step 3c reads this field directly to render the `[refined]` indicator.

**Ready intersection**: The script emits ALL detected epics from `index.json`. Step 3b filters by intersecting the script's emitted `epics` keys with the IDs already extracted from the Ready section above. Only Ready set epics are passed to Step 3c for rendering.

**Fallback for missing index**: If `index.json` is missing after Step 3a ran, warn and fall back to reading `index.md` using the existing table columns. The script signals this case via exit 1.

**Exit-code handling**:
- Exit 1 — missing or malformed `index.json`: warn the user, then fall back to reading `index.md` table columns as in the missing-index case above.
- Exit 2 — `schema_version` mismatch: report the mismatch and halt triage. Do not silently fall back, because that would mask the schema-bump signal and let stale parsing logic run against a newer envelope.

### 3c. Present Ready Items with Workflow Recommendations

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

- **All children refined** (all active, non-in_progress, non-review, non-blocked children have `spec:` present): "All children are refined. Run `/overnight` — it will auto-select them via its own readiness scan."

- **Any children unrefined** (any active child that is not in_progress/review/blocked lacks `spec:`): "Run `/cortex-core:refine` on each unrefined child one at a time (each requires interactive spec approval before moving to the next): [list unrefined child IDs and titles]. Once all are refined and have `status: refined`, run `/overnight` — it will auto-select the full group."

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

### Empty or Missing Backlog

If `cortex/backlog/` contains no item files (or does not exist):
- Report: "No backlog found."
- Suggest: "Use `/cortex-core:backlog add <description>` to create items, or describe what you want to build and I'll route you directly."

## Step 4: Direct Implementation Confirmation

When a request appears trivial (Branch 5), confirm before skipping lifecycle:

> This looks like a trivial change — implement directly without lifecycle?
>
> - **Yes**: Proceed with the change immediately
> - **No**: Route through `/cortex-core:lifecycle` for structured phases

**The user must explicitly confirm.** Do not auto-skip lifecycle.

If the user confirms direct implementation:
- Implement the change in the current conversation
- Commit the result

If the user declines:
- Perform the criticality pre-assessment (Step 2)
- Route to lifecycle: "Invoke `/cortex-core:lifecycle <feature-name>`" with criticality context

## Constraint: No Built-In Plan Mode

Never use Claude Code's built-in `EnterPlanMode` as a substitute for `/cortex-core:lifecycle`. When a feature requires planning, route through `/cortex-core:lifecycle` — its structured phases (research → specify → plan → implement → review → complete) replace the built-in plan mode entirely. The `/cortex-core:dev` skill exists to route to the right workflow skill, not to perform planning itself.

## Step 5: User Override

At any point during routing, if the user disagrees with the suggested route:
- Honor their choice immediately
- Do not re-analyze or argue for the original suggestion
- If they name a specific skill, route to that skill
- If they change the scope (e.g., "actually this is bigger than I thought"), re-classify from Step 1
