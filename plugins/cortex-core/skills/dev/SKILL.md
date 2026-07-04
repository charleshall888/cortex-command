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

A conversational routing hub — the single entry point for all development workflows. Analyzes the user's request and delegates to the appropriate skill or workflow.

## Invocation

- `/cortex-core:dev` — open-ended; triggers backlog triage
- `/cortex-core:dev {{request}}` — analyze and route to the right workflow

## Step 1: Classify the Request

Read the user's input and classify it into one of five routing branches. Evaluate in this order — first match wins.

**Skill name mentions**: If the user names a specific skill (e.g., "use skill-creator", "run discovery on X"), treat it as a strong signal during classification — not an automatic pass-through. Dev always analyzes the request and provides its own assessment. If the analysis agrees with the user's stated preference, route there with context. If it disagrees, present the discrepancy and let the user decide.

### Branch 1: Backlog Triage

The user asks what to work on, without naming a specific feature.

**Signals**: "what should I work on", "what's next", "next task", "where do I start", bare `/cortex-core:dev` with no arguments, or any request for prioritization guidance.

**Action**: Execute the backlog triage workflow (Step 3).

### Branch 2: Multi-Feature / Batch

The user describes multiple features or uses batch language.

**Signals**: Lists of features, "these features", "all of these", "batch", or three or more distinct feature names in one request.

**Action**: Assess each task's complexity before routing. Classify each as **trivial** (single file, obvious fix, one approach) or **non-trivial** (needs research, multiple files, architectural decisions).

- **All non-trivial**: Tell the user to run `/cortex-overnight:overnight` with the feature list.
- **All trivial**: Execute direct implementation (Step 4) for each sequentially in the current conversation.
- **Mixed**: Present a **hybrid plan** — `/cortex-overnight:overnight` for non-trivial tasks, direct implementation for trivial ones. Execute trivial tasks first, or in parallel with the overnight pipeline.

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

### Resumed Lifecycle

Before performing this criticality assessment, check whether `cortex/lifecycle/<feature>/` already exists. If it does:

1. Read criticality by running `cortex-lifecycle-state --feature <feature> --field criticality` (emits JSON; defaults to `medium` when the key is absent).
2. Inform the user: "A lifecycle for `<feature>` already exists at `<phase>`. Resume it?"
3. If the user confirms, state: "Invoke `/cortex-core:lifecycle <feature>`" to resume. Skip the criticality suggestion — the existing lifecycle already has one.
4. If the user wants to start fresh, confirm they want to discard existing artifacts before proceeding.

Read `${CLAUDE_SKILL_DIR}/references/criticality-heuristics.md` and apply its heuristic-signals table before forming a criticality suggestion.

## Step 3: Backlog Triage

When routing to backlog triage:

### Backend gate (resolve before any index read)

Triage reads the local `cortex/backlog/index.{md,json}` and calls `cortex-build-epic-map` / `cortex-generate-backlog-index`, all of which only describe a `cortex-backlog` (local) repo. So resolve the active backend first — before reaching any of the steps below — with `` `cortex-read-backlog-backend` ``:

- **`cortex-backlog`** (the default arm) — proceed with triage exactly as today (Steps 3a–3c below).
- **any other value** (`none` or an external tracker) — the local index does not represent the active backlog, so skip triage with a one-line advisory: this repo's backlog lives in a non-`cortex-backlog` backend, so consult it directly and route work through `/cortex-core:lifecycle` (a single concrete feature) or `/cortex-core:discovery` (a topic to decompose). Do not run `cortex-generate-backlog-index`, read `cortex/backlog/index.{md,json}`, or call `cortex-build-epic-map`.

The steps below run only on the `cortex-backlog` arm.

### 3a. Regenerate the Index

Run the global shell command `cortex-generate-backlog-index` directly (do NOT use a project-local script). If it fails, warn that `index.json` may not be produced.

If it fails:
- Warn the user: "Index generation failed. Falling back to the existing index."
- Attempt to read `cortex/backlog/index.md` directly. If that file also does not exist, report: "No backlog index found. Use `/cortex-backlog:backlog add` to create items, then re-run `/cortex-core:dev`."

### 3b. Read the Ready Set

The index has no single section literally named "Ready". The actionable buckets are `## Refined` (`status: refined` — spec-approved, overnight-eligible) and `## Backlog` (`status: backlog` — not yet refined). The **ready set** is the union of these two sections. The generator already excludes blocked, `deferred`, and non-actionable items, so an item's presence in `## Refined`/`## Backlog` is the readiness signal.

Read both sections from `cortex/backlog/index.md`. The master table at the top is the **full non-terminal ledger**, not a candidate list — it intentionally also contains blocked, `proposed`, and `deferred` items. Items that appear in the master table but in **neither** `## Refined` nor `## Backlog` are non-actionable. Do NOT present master-table-only items as work candidates; at most surface them as a brief "parked / blocked" footnote so the user can act on stale ones.

If both `## Refined` and `## Backlog` are empty:
- Report: "No ready items in the backlog."
- Suggest: check the master table for blocked items with stale dependencies, or create new items with `/cortex-backlog:backlog new`.

**Epic detection and child map construction** (must complete before any output is rendered):

Invoke `cortex-build-epic-map` to produce the deterministic epic→children map. The script reads `cortex/backlog/index.json`, auto-detects `type: epic` items, and groups non-epic items under their normalized parent epic. Capture stdout as JSON.

**Output schema**: an envelope `{"schema_version": "1", "epics": {...}}` where each `epics[epic_id]` has a `children` array; each child has `id` (numeric), `title` (string), `status` (string), and `spec` (string or null). A non-null `spec` marks a refined child.

**Ready intersection**: the script emits ALL detected epics; pass only those whose keys intersect the ready set (`## Refined` ∪ `## Backlog`) to Step 3c.

**Exit-code handling**:
- Exit 1 — missing or malformed `index.json`: warn, then fall back to reading `index.md`'s table columns.
- Exit 2 — `schema_version` mismatch: report it and halt triage. Do not silently fall back — that would mask the schema-bump signal and run stale parsing against a newer envelope.

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

**The user must explicitly confirm.** Do not auto-skip lifecycle.

If the user confirms direct implementation:
- Implement the change in the current conversation
- Commit the result

If the user declines:
- Perform the criticality pre-assessment (Step 2)
- Route to lifecycle: "Invoke `/cortex-core:lifecycle <feature-name>`" with criticality context

## Constraint: No Built-In Plan Mode

Never use Claude Code's built-in `EnterPlanMode` as a substitute for `/cortex-core:lifecycle`. When a feature requires planning, route through `/cortex-core:lifecycle` — its structured phases (research → specify → plan → implement → review → complete) replace the built-in plan mode entirely.

## Step 5: User Override

At any point during routing, if the user disagrees with the suggested route:
- Honor their choice immediately
- Do not re-analyze or argue for the original suggestion
- If they name a specific skill, route to that skill
- If they change the scope (e.g., "actually this is bigger than I thought"), re-classify from Step 1
