---
name: dev
description: Development entry point that analyzes requests and routes to the appropriate workflow. Use when user says "/cortex-core:dev", "what should I work on", "start working on", "dev hub", "where do I start", "next task", "what's next", or describes a feature without naming a specific skill.
inputs:
  - "request: string (optional) — development request or description; omit to trigger backlog triage of refined items"
outputs:
  - "Routing delegation (stdout) — one of: /cortex-core:lifecycle, /cortex-overnight:overnight, /cortex-core:discovery, or direct implementation"
  - "Backlog triage summary (stdout) — refined items with recommended workflows (when invoked with no request)"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory should exist (required for triage mode)"
---

# Dev

## Invocation

- `/cortex-core:dev` — open-ended; triggers backlog triage
- `/cortex-core:dev {{request}}` — analyze and route to the right workflow

## Step 1: Classify the Request

Classify the request into one of five routing branches, evaluated in order — first match wins.

**Skill name mentions**: naming a specific skill (e.g., "use skill-creator", "run discovery on X") is a strong signal, not an automatic pass-through — analyze independently, route with context if it agrees, or present the discrepancy and let the user decide if not.

### Branch 1: Backlog Triage

**Signals**: "what should I work on", "what's next", "where do I start", bare `/cortex-core:dev` with no arguments, or any request for prioritization guidance.

**Action**: Execute the backlog triage workflow (Step 3).

### Branch 2: Multi-Feature / Batch

**Signals**: lists of features, "these features", "all of these", "batch", or three or more distinct feature names in one request.

**Action**: classify each task as **trivial** (Branch 4's criteria) or **non-trivial** (needs research, multiple files, architectural decisions):

- **All non-trivial**: run `/cortex-overnight:overnight` with the feature list.
- **All trivial**: direct implementation (Step 4) for each, sequentially, in the current conversation.
- **Mixed**: present a hybrid plan — overnight for non-trivial tasks, direct implementation for trivial ones (run first or in parallel). Show a table classifying each task with its routing and justification, and confirm before proceeding.

### Branch 3: Vague / Uncertain Topic

**Signals**: "I'm not sure how to approach", "need to understand", "explore", "investigate", or a topic description that lacks concrete implementation details.

**Action**: State: "Invoke `/cortex-core:discovery <topic>`" with the topic extracted from the request.

### Branch 4: Trivial Change

The request is clearly trivial: single file, existing pattern, fully specified, one obvious approach.

**Signals**: "just change", "rename", "bump the version", "fix this typo", or a request with an obvious single-file scope.

**Action**: Execute the direct implementation workflow (Step 4).

### Branch 5: Default (Single Concrete Feature)

**Action**: Perform the criticality pre-assessment (Step 2), then state: "Invoke `/cortex-core:lifecycle <feature-name>`" along with the criticality context.

### Ambiguous Requests

When a request could reasonably match two branches (e.g., lifecycle vs. discovery), don't guess — present both paths and ask the user to choose:

> This could go two ways:
> - **Lifecycle**: build `<feature>` through structured phases
> - **Discovery**: investigate `<topic>`, then decompose into backlog tickets
>
> Which fits better?

## Step 2: Criticality Pre-Assessment

Before routing to `/cortex-core:lifecycle`, analyze the feature description for signals suggesting elevated criticality.

### Resumed Lifecycle

If `cortex/lifecycle/<feature>/` exists, read its criticality via `cortex-lifecycle-state --feature <feature> --field criticality` (JSON; default `medium`) and ask: "A lifecycle for `<feature>` exists at `<phase>`. Resume it?" Confirmed: state "Invoke `/cortex-core:lifecycle <feature>`", skipping the suggestion below. Fresh start: confirm discarding existing artifacts first.

Read `${CLAUDE_SKILL_DIR}/references/criticality-heuristics.md` and apply its heuristic-signals table before forming a criticality suggestion.

## Step 3: Backlog Triage

### Backend gate (resolve before any index read)

Triage reads the local `cortex/backlog/index.{md,json}` and calls `cortex-build-epic-map` / `cortex-generate-backlog-index`, both assuming a `cortex-backlog` (local) repo — resolve the active backend first, before any step below, with `cortex-read-backlog-backend`:

- **`cortex-backlog`** (the default): proceed with Steps 3a–3c below.
- **anything else** (`none` or an external tracker): the local index isn't authoritative. Skip triage: advise the user to consult that backend directly and route through `/cortex-core:lifecycle` or `/cortex-core:discovery` instead — do not run `cortex-generate-backlog-index`, read `index.{md,json}`, or call `cortex-build-epic-map`.

### 3a. Regenerate the Index

Run the global shell command `cortex-generate-backlog-index` directly (do NOT use a project-local script). If it fails:
- Warn the user: "Index generation failed. Falling back to the existing index."
- Attempt to read `cortex/backlog/index.md` directly; if that's also missing, report: "No backlog index found. Use `/cortex-backlog:backlog add` to create items, then re-run `/cortex-core:dev`."

### 3b. Read the Ready Set

There's no section literally named "Ready" — the **ready set** is `## Refined` (`status: refined`, overnight-eligible) ∪ `## Backlog` (`status: backlog`, not yet refined). The generator already excludes blocked/`deferred`/non-actionable items, so presence in either is the readiness signal.

Read both sections from `cortex/backlog/index.md`. The master table at top is the full ledger (also has blocked/`proposed`/`deferred` items), not a candidate list — items in neither ready section are non-actionable; surface at most as a "parked / blocked" footnote, never as candidates.

If both `## Refined` and `## Backlog` are empty:
- Report: "No ready items in the backlog."
- Suggest: check the master table for blocked items with stale dependencies, or create new items with `/cortex-backlog:backlog new`.

**Epic detection and child map** (complete before rendering output): invoke `cortex-build-epic-map`, which reads `index.json`, auto-detects `type: epic` items, groups non-epic items under their normalized parent, and prints the map as JSON to stdout.

**Output schema**: `{"schema_version": "1", "epics": {epic_id: {"children": [{"id": <num>, "title": <str>, "status": <str>, "spec": <str|null>}]}}}` — non-null `spec` marks refined. Emits ALL detected epics; pass only those intersecting the ready set to Step 3c.

**Exit codes**:
- 1 (missing or malformed `index.json`): warn, then fall back to reading `index.md`'s table columns.
- 2 (`schema_version` mismatch): report it and halt triage — don't silently fall back and mask the schema-bump signal against a newer envelope.

### 3c. Present Ready Items with Workflow Recommendations

Read `${CLAUDE_SKILL_DIR}/references/triage-rendering.md` and render Blocks 1–2 per its protocol before producing any triage output.

### Empty or Missing Backlog

If `cortex/backlog/` contains no item files (or does not exist):
- Report: "No backlog found."
- Suggest: "Use `/cortex-backlog:backlog new` to create items, or describe what you want to build and I'll route you directly."

## Step 4: Direct Implementation Confirmation

When a request appears trivial (Branch 4), confirm before skipping lifecycle:

> This looks like a trivial change — implement directly without lifecycle?
>
> - **Yes**: Proceed with the change immediately
> - **No**: Route through `/cortex-core:lifecycle` for structured phases

If the user confirms direct implementation:
- Implement the change in the current conversation
- Commit the result

If the user declines:
- Perform the criticality pre-assessment (Step 2)
- Route to lifecycle: "Invoke `/cortex-core:lifecycle <feature-name>`" with criticality context

## Constraint: No Built-In Plan Mode

Never use Claude Code's built-in `EnterPlanMode` as a substitute for `/cortex-core:lifecycle` — its structured phases replace built-in plan mode entirely.

## Step 5: User Override

At any point during routing, if the user disagrees with the suggested route:
- Honor their choice immediately
- Do not re-analyze or argue for the original suggestion
- If they name a specific skill, route to that skill
- If they change the scope (e.g., "actually this is bigger than I thought"), re-classify from Step 1
