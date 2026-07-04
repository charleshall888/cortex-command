# Plan Phase

Produce a detailed implementation plan with numbered tasks, file paths, and verification steps. Plans are prose with implementation context, not code.

## Protocol

### 1. Load Context

Read prior artifacts:
- `cortex/lifecycle/{feature}/research.md` (always)
- `cortex/lifecycle/{feature}/spec.md` (required — produced in Specify phase)
- `cortex/lifecycle.config.md` at project root (if exists — project constraints)

### 1a. Check Criticality

Read criticality by running `cortex-lifecycle-state --feature {feature} --field criticality` (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state).

- **If criticality is `critical`**: read and follow `${CLAUDE_SKILL_DIR}/references/competing-plans.md` before dispatching, then proceed per its guidance.
- **Otherwise** (low, medium, high): proceed to §2 (Design the Approach) — the standard single-plan flow.

### 1b. Competing Plans (Critical Only)

The competing-plans protocol (dispatch variants → synthesize → route → log the v2 comparison event) now lives in `${CLAUDE_SKILL_DIR}/references/competing-plans.md`; §1a's `critical` branch loads it before dispatching, and only the `critical` arm reaches it.

### 2. Design the Approach

Based on research and spec, determine the overall architecture and implementation strategy, the file creation/modification order, integration points with existing code, and the testing and verification approach.

### 3. Write Plan Artifact

Produce `cortex/lifecycle/{feature}/plan.md` with this structure:

```markdown
# Plan: {feature}

## Overview
[1-2 sentence summary of the implementation approach and key architectural decisions]
**Architectural Pattern**: {category}
<!-- Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise. -->

## Outline
<!-- Phase decomposition above the per-task list. Use H3 headings for phases (### Phase N: <name>) — H2 breaks the parser. Populate with ≥1 phase when `complexity=simple`; populate with ≥2 phases when `complexity=complex`. -->

### Phase 1: {phase name} (tasks: 1, 2, ...)
**Goal**: {one-line phase objective}
**Checkpoint**: {observable state at end of this phase — e.g., "tests green for module X", "fixture set in place"}

### Phase 2: {phase name} (tasks: 3, 4, ...)
**Goal**: {one-line phase objective}
**Checkpoint**: {observable state at end of this phase}

## Tasks

### Task 1: {description}
- **Files**: {exact paths to create or modify}
- **What**: {what this task accomplishes in 1-2 sentences}
- **Depends on**: none
- **Complexity**: trivial|simple|complex
- **Context**: {file paths, function signatures, type definitions, pattern references — structural context for the implementer}
- **Verification**: {(a) command + expected output + pass/fail (e.g., "run `just test` — pass if exit 0, all tests pass"), OR (b) specific file/pattern check (e.g., "`grep -c 'keyword' path/file` = 1 — pass if count = 1"), OR (c) "Interactive/session-dependent: [one-sentence rationale explaining why no command is possible]"}
- **Status**: [ ] pending

### Task 2: {description}
- **Files**: {exact paths}
- **What**: {what this accomplishes}
- **Depends on**: [1]
- **Complexity**: trivial|simple|complex
- **Context**: {structural context}
- **Verification**: {same (a)/(b)/(c) format as Task 1}
- **Status**: [ ] pending

...

## Risks
[Design choices, scope calls, or constraints the user might want to revisit before implementation begins. "None" if nothing is controversial.]

## Acceptance
<!-- Populate ONLY when `complexity=complex` (the Clarify §4-resolved tier dimension). Omit this section entirely on `complexity=simple` plans. -->
[~3 lines whole-feature acceptance criterion — the observable end-state that demonstrates the complete feature works as intended. Distinct from per-task Verification, which checks task-local effects.]
```

> Prose-only Verification fails the P4 checklist — use (a)/(b)/(c).

### Task Sizing

Target 5-15 minutes per task, 1-5 files each. A typical feature should decompose into 5-15 tasks. Split tasks that touch more than 5 files.

Each task must be self-contained — an implementer with no prior context should be able to complete it using only the task text and the files it references.

### Wiring Co-Location

When a task deploys a new `bin/cortex-*` script, the SAME task must include the consumer wiring — typically a SKILL.md mention, hook reference, or doc reference that names the script as inline code or a path-qualified token. `cortex-check-parity` emits W003 ("orphan: deployed but not referenced") at the deployed-but-unreferenced boundary.

If wiring is too large to combine with deployment in one task, reorder so wiring lands first — a SKILL.md mention is fine even before the script exists, since W003 flags `deployed-but-unreferenced`, not `referenced-but-undeployed`.

### Task Complexity Classification

Every task requires a `**Complexity**` field. Choose from `trivial`, `simple`, or `complex`:

| Tier | When to use |
|------|-------------|
| `trivial` | Single-file edit, no side effects, no commit needed |
| `simple` | 1–3 file changes, commit required, may run shell commands or validate output |
| `complex` | 4+ files, architectural change, new pattern, or multi-component integration |

**Critical rule**: Tasks that create files, modify JSON settings, create symlinks, set file permissions, or must commit are `simple` minimum — **never `trivial`**, whose lower turn budget causes turn exhaustion before the commit step on multi-step tasks.

The `**Complexity**` field drives model and turn-limit selection in the overnight pipeline.

### Dependency Annotations

Every task requires a `**Depends on**` field between **What** and **Context**. Use `[N, M]` (bracketed task numbers) for tasks with dependencies, or `none` for independent tasks. The implement phase uses these annotations to dispatch independent tasks in parallel — omitting or misformatting the field blocks parallel execution.

### Sub-task headings (`### Task Na`)

A task may be decomposed into ordered sub-units with a single lowercase letter suffix on the heading: `### Task 3a:`, `### Task 3b:`. These parse as first-class, independently-dispatchable units with a distinct identity (`3` < `3a` < `3b` < `4`); the integer part accepts `0` and a sub-task group need not start at `a` (an orphan `8b` is valid). Reference a sub-task in `Depends on` by its full id (`[3a]`, `[13a, 13b]`) — a bare `[3]` means the literal task `3` only and is **not** auto-expanded to the group, so enumerate sub-task dependencies explicitly. Only a single lowercase letter is supported; multi-letter (`3ab`), uppercase (`3A`), and space-separated (`3 a`) suffixes fail loud.

**Same-batch sub-tasks must declare disjoint `Files`.** Sibling sub-tasks that share a `Depends on` (e.g. `13a`/`13b`/`13c` all depending on `[10]`) co-schedule in one batch. In the overnight runner a batch dispatches into one shared worktree, so same-batch tasks writing the same file race (last-writer-wins). Give same-batch sub-tasks disjoint `Files` lists, or serialize them with an explicit `Depends on` edge (`3b` depends on `[3a]`).

### Files/Verification Consistency

Every file that Verification implies must be listed in Files. If Verification says "write a test," the test file must appear in Files. Builders are instructed not to modify files outside their Files list — contradicting this with Verification creates an impossible constraint.

### Caller Enumeration

When a task modifies or removes a function, command, or interface — enumerate ALL files that call, reference, or depend on it in the task's **Files** field. Before writing the Files list, search the codebase for all references to the symbol being changed.

### Code Budget

Plans are prose with structural context. The line between design and implementation:

**Allowed in Context and other fields:** file paths and directory structures; function signatures (name, parameters, return type); type definitions (field names and types only); pattern references ("follow the pattern in `src/hooks/useAuth.ts`"); config keys and values; interface contracts between tasks.

**Prohibited:**
- Function bodies
- Import statements
- Error handling implementations
- Complete test code
- Any code that an implementer would copy-paste rather than write
- Verification steps that reference artifacts (files, log entries, status fields) the executing task creates solely for the purpose of satisfying verification — this is self-sealing and passes tautologically

After writing `plan.md`, register the `"plan"` artifact in `cortex/lifecycle/{feature}/index.md` per the canonical artifact-registration recipe in backlog-writeback.md (loaded at lifecycle Step 2).

### 3a. Orchestrator Review

Before presenting the artifact to the user, read and follow `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md` for the `plan` phase. The orchestrator review must pass before proceeding to user approval.

### 3b. Critical Review

After orchestrator review passes, read the active tier and criticality (rules: `${CLAUDE_SKILL_DIR}/references/criticality-matrix.md` §Reading lifecycle state):

- `cortex-lifecycle-state --feature {feature} --field tier`
- `cortex-lifecycle-state --feature {feature} --field criticality`

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`: invoke the `critical-review` skill with the plan artifact. Present the synthesis to the user before plan approval. Otherwise, read and follow `${CLAUDE_SKILL_DIR}/references/critical-review-gate.md` for the `plan` phase.

### 4. User Approval (merged branch/dispatch surface)

This surface folds the Implement-phase branch/dispatch selection into plan approval — **each branch option implies plan approval**, so the operator answers one question, not two. Present the plan summary (overview + task list) plus the approval-surface fields:

- **Produced** (one-line summary of the artifact)
- **Trade-offs** (alternatives considered and rationale for chosen approach)

**Assemble the merged option set.** When the current branch is `main`/`master`, assemble the adaptive branch options using the **same branch-mode preflight Implement §1 runs** (see Implement §1 "Branch-mode dispatch preflight" for the authoritative routing rules):

```bash
cortex-lifecycle-branch-mode .
cortex-lifecycle-picker-decision . {feature} {branch_mode}
```

Apply the same rules Implement §1 documents: the suppressed-routing (a configured `branch-mode` fixes a single choice and skips the menu), the uncommitted-changes-guard demotion, and the `command -v cortex-worktree-create` runtime-probe degrade (which hides the worktree option when the console-script is absent). When **not** on `main`/`master`, the branch sub-choices collapse: implementation will proceed on the current branch (`trunk`), so the surface offers only `[Approve & implement (current branch), Approve plan but wait to implement]`.

**Compose the `AskUserQuestion` `options`** (≤4): the assembled branch modes, plus a final **"Approve plan but wait to implement"** option. The auto-provided **"Other"** free-text escape is appended by the platform *outside* the 4-option `options` cap and carries Request-changes and Cancel. Route on the selection:

- **A branch mode** (`Implement on current branch` → `trunk`; `Implement on feature branch with worktree` → `worktree-interactive`; `Create feature branch` → `feature-branch`) — implies plan approval. Append `plan_approved` carrying the chosen `dispatch_choice`, then the `phase_transition` from §5, then auto-advance to Implement (which consumes `dispatch_choice` and skips its own picker). Proceed automatically.
  ```bash
  cortex-lifecycle-event log --event plan_approved --feature <name> --set dispatch_choice=<trunk|worktree-interactive|feature-branch>
  ```
- **Approve plan but wait to implement** — append `plan_approved` with `dispatch_choice: "wait"`, then append `feature_paused`, then **halt** (do not auto-advance, do not dispatch). Re-invocation routes to `implement` (the plan IS approved); Implement §1 fires its fallback picker since `wait` is not a branch mode. The feature surfaces as `implement-paused`. **When the feature is backlog-linked (Context A), warn now** that the overnight runner may still execute the item unless it is paused (overnight eligibility does not yet honor `feature_paused` — see the overnight-honors-pause backlog item).
  ```bash
  cortex-lifecycle-event log --event plan_approved --feature <name> --set dispatch_choice=wait
  cortex-lifecycle-event log --event feature_paused --feature <name>
  ```
- **"Other" free-text** — interpret the text. A cancel-intent → append `lifecycle_cancelled` and halt. Any other text → treat as **Request changes**: collect the change, revise the plan, and **re-assemble and re-present** this merged surface (re-running the branch-picker assembly). Do not emit `plan_approved` on revision rounds — only a terminal branch-mode or "wait" selection emits it.

### 5. Transition

On a branch-mode selection (not "wait"), append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log` (the `plan_approved` event from §4 must precede this one in the log):

```bash
cortex-lifecycle-event log --event phase_transition --feature <name> --set from=plan --set to=implement
```

On any approval (a branch-mode selection OR "wait" — both emit `plan_approved`), run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag. If stdout is `true` (the default), stage `cortex/lifecycle/{feature}/` and commit using `/cortex-core:commit`. If stdout is `false`, skip the commit silently. On the "wait" path the commit makes the approval durable, then the lifecycle halts.

## Hard Gate

Backlog items suggest approaches — they don't prescribe them. Unless the backlog item has linked cortex/research/spec artifacts that already validated the approach, evaluate it critically and weigh alternatives.
