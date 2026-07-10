# Plan Phase

Produce an implementation plan of numbered tasks with file paths and verification steps. Plans are prose with structural context, not code.

## Protocol

### 1. Load Context

Read `cortex/lifecycle/{feature}/research.md` and `spec.md`, plus `cortex/lifecycle.config.md` at project root if it exists.

### 1a. Check Criticality

Read criticality (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state):

```bash
cortex-lifecycle-state --feature {feature} --field criticality
```

- **`critical`** → read and follow `${CLAUDE_SKILL_DIR}/references/competing-plans.md`, then proceed per its guidance.
- **Otherwise** (low/medium/high) → §3, the standard single-plan flow.

### 1b. Competing Plans (Critical Only)

The competing-plans protocol (dispatch variants → synthesize → route → log the v2 comparison event) lives in `${CLAUDE_SKILL_DIR}/references/competing-plans.md`; §1a's `critical` branch loads it, and only that arm reaches it.

### 3. Write Plan Artifact

Produce `cortex/lifecycle/{feature}/plan.md`:

```markdown
# Plan: {feature}

## Overview
[1-2 sentence approach + key architectural decisions]
**Architectural Pattern**: {category}
<!-- Only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise. -->

## Outline
<!-- Phase decomposition above the task list. H3 phase headings (### Phase N: <name>) — H2 breaks the parser. ≥1 phase when complexity=simple, ≥2 when complexity=complex. -->

### Phase 1: {name} (tasks: 1, 2, ...)
**Goal**: {one-line objective}
**Checkpoint**: {observable end state — e.g. "tests green for module X"}

## Tasks

### Task 1: {description}
- **Files**: {exact paths to create or modify}
- **What**: {what this accomplishes, 1-2 sentences}
- **Depends on**: none
- **Complexity**: trivial|simple|complex
- **Context**: {file paths, signatures, type defs, pattern references — structural context for the implementer}
- **Verification**: one of (a) command + expected output + pass/fail; (b) file/pattern check (e.g. `grep -c 'keyword' path` = 1); (c) `Interactive/session-dependent: [one-sentence rationale]`
- **Status**: [ ] pending

## Risks
[Design choices or scope calls the user might revisit before implementation. "None" if uncontroversial.]

## Acceptance
<!-- Only when complexity=complex; omit on simple. -->
[~3 lines whole-feature acceptance criterion — the observable end-state proving the feature works. Distinct from per-task Verification, which checks task-local effects.]
```

> Prose-only Verification fails the P4 checklist — use (a)/(b)/(c).

### Authoring rules

**Task sizing** — a coherent, self-contained unit an implementer with no prior context can complete from the task text and its referenced files alone. Split when a task spans unrelated concerns or grows too large for one focused pass.

**Complexity** — every task carries `**Complexity**`:

| Tier | When |
|------|------|
| `trivial` | single-file edit, no side effects, no commit |
| `simple` | 1–3 files, commit required, may run/validate commands |
| `complex` | 4+ files, architectural change, new pattern, or multi-component integration |

Tasks that create files, modify JSON settings, create symlinks, set permissions, or must commit are `simple` minimum — never `trivial` (its lower turn budget exhausts before the commit step). The field drives model and turn-limit selection in the overnight pipeline.

**Dependencies** — every task carries `**Depends on**` between **What** and **Context**: `[N, M]` or `none`. Implement dispatches independent tasks in parallel; a missing or malformed field blocks parallelism.

**Sub-task headings** — a task may split into `### Task 3a:`, `### Task 3b:` (single lowercase suffix), first-class dispatchable units ordered `3` < `3a` < `3b` < `4`. The integer part accepts `0`; a group need not start at `a`. Reference by full id (`[3a]`, `[13a, 13b]`) — a bare `[3]` means literal task `3`. Multi-letter (`3ab`), uppercase (`3A`), space-separated (`3 a`) fail loud. Same-batch siblings sharing a `Depends on` co-schedule into one worktree, so same-file writes race — give them disjoint `Files`, or serialize with an explicit edge (`3b` depends on `[3a]`).

**Files/Verification consistency** — every file Verification implies must be in Files; builders can't modify files outside their Files list.

**Caller enumeration** — when a task changes or removes a function/command/interface, search the codebase first and list ALL callers/dependents in **Files**.

**Code budget** — prose with structural context only: paths, directory structures, function signatures, type field names/types, pattern references, config keys/values, inter-task contracts. No copy-paste-ready code, and no self-sealing verification (steps referencing artifacts the same task creates solely to satisfy the check).

After writing `plan.md`, register the artifact: `cortex-lifecycle-register-artifact --feature {feature} --artifact plan`.

### 3a. Orchestrator Review

Before user presentation, read and follow `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md` (shared protocol) plus its Post-Plan checklist `${CLAUDE_SKILL_DIR}/references/orchestrator-checklist-plan.md` for the `plan` phase. It must pass before approval.

### 3b. Critical Review

After orchestrator review passes, read tier and criticality (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state):

```bash
cortex-lifecycle-state --feature {feature} --field tier
cortex-lifecycle-state --feature {feature} --field criticality
```

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`: invoke the `critical-review` skill with the plan artifact; present its synthesis before approval. Otherwise read and follow `${CLAUDE_SKILL_DIR}/references/critical-review-gate.md` for the `plan` phase.

### 4. User Approval (merged branch/dispatch surface)

This surface folds the Implement branch/dispatch selection into plan approval — each branch option implies plan approval. Present the plan summary (overview + task list) plus **Produced** (one-line artifact summary) and **Trade-offs** (alternatives considered + rationale).

**Assemble the option set.** On `main`/`master`, assemble the adaptive branch options with Implement §1's branch-mode preflight — it owns the picker guards (uncommitted-changes demotion; the `cortex-lifecycle-prepare-worktree` runtime-probe degrade that hides the worktree option when absent), and [worktree-entry.md](${CLAUDE_SKILL_DIR}/references/worktree-entry.md) owns the suppressed-picker routing:

```bash
cortex-lifecycle-branch-mode .
cortex-lifecycle-picker-decision . {feature} {branch_mode}
```

Off `main`/`master`, the sub-choices collapse to `trunk` (the current branch), so the surface offers only `[Approve & implement (current branch), Approve plan but wait to implement]`.

<!-- pause: plan-approval relayed-consent -->
**Compose `AskUserQuestion` `options`** (≤4): the branch modes plus **"Approve plan but wait to implement"**. The platform's **"Other"** free-text escape (appended outside the 4-cap) carries Request-changes and Cancel. Route on the selection:

- **A branch mode** (`Implement on current branch`→`trunk`; `Implement on feature branch with worktree`→`worktree-interactive`; `Create feature branch`→`feature-branch`) — implies approval. Append `plan_approved` with the `dispatch_choice`, then §5's `phase_transition`, then auto-advance to Implement (it consumes `dispatch_choice` and skips its own picker). `cortex-lifecycle-event plan-approved --feature <name> --dispatch-choice <trunk|worktree-interactive|feature-branch>`
- **Approve plan but wait to implement** — append `plan_approved` with `dispatch_choice: "wait"`, then `feature_paused`, then **halt** (no auto-advance, no dispatch). Re-invocation routes to `implement` (the plan IS approved); Implement §1 fires its fallback picker since `wait` is not a branch mode. If the feature is backlog-linked, warn now that the overnight runner may still execute the item unless paused (overnight eligibility does not yet honor `feature_paused`).
  ```bash
  cortex-lifecycle-event plan-approved --feature <name> --dispatch-choice wait
  cortex-lifecycle-event feature-paused --feature <name>
  ```
- **"Other" free-text** — cancel-intent → append `lifecycle_cancelled` and halt. Any other text → **Request changes**: revise the plan and re-present this surface. Do not emit `plan_approved` on revision rounds — only a terminal branch-mode or "wait" selection emits it.

### 5. Transition

On a branch-mode selection (not "wait"), append `phase_transition` (the §4 `plan_approved` must precede it): `cortex-lifecycle-event phase-transition --feature <name> --from plan --to implement`

On any approval (branch-mode or "wait"), run `cortex-read-commit-artifacts`. `true` (default) → stage `cortex/lifecycle/{feature}/` and commit via `/cortex-core:commit`; `false` → skip silently. On the "wait" path the commit makes approval durable, then the lifecycle halts.

## Hard Gate

Backlog items suggest approaches — they don't prescribe them. Unless the item has linked research/spec artifacts that already validated the approach, evaluate it critically and weigh alternatives.
