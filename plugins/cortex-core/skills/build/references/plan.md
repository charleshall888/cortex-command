# Plan Phase

Numbered tasks with file paths and verification steps. Give structure, not code.

## 1. Load context

Read `{roots.artifacts.path}/research.md` and `spec.md`, plus `cortex/lifecycle.config.md` if present. Use the criticality carried from SKILL.md; run `cortex-lifecycle-state --feature {feature} --field criticality` only if you lack it. **`critical`** → follow `${CLAUDE_SKILL_DIR}/references/competing-plans.md` first.

## 2. Write plan.md

```markdown
# Plan: {feature}

## Overview
[1-2 sentence approach + key architectural decisions]
**Architectural Pattern**: {category}
<!-- Only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise. -->

## Outline
<!-- H3 phase headings — H2 breaks the parser. ≥1 phase when complexity=simple, ≥2 when complex. -->

### Phase 1: {name} (tasks: 1, 2, ...)
**Goal**: {one-line objective}
**Checkpoint**: {observable end state}

## Tasks

### Task 1: {description}
- **Files**: {exact paths to create or modify}
- **What**: {what this accomplishes, 1-2 sentences}
- **Depends on**: none
- **Complexity**: simple|moderate|complex
- **Context**: {paths, signatures, type defs, pattern references}
- **Verification**: one of (a) command + expected output + pass/fail; (b) file/pattern check (e.g. `grep -c 'keyword' path` = 1); (c) `Interactive/session-dependent: [one-sentence rationale]`
- **Status**: [ ] pending

## Risks
[Design choices or scope calls the user might revisit. "None" if uncontroversial.]

## Acceptance
<!-- Only when complexity=complex. ~3 lines: the observable end state proving the feature works, distinct from per-task Verification. -->
```

Prose-only Verification fails review — use (a), (b), or (c).

### Authoring rules

- **Task sizing** — a unit an implementer with no prior context can finish from the task text and the files it names.
- **Complexity** sets overnight turn and budget limits. The parser accepts only `simple`/`moderate`/`complex`; other → `complex`, omitted → `moderate`, both reported as authoring errors. `simple` = 1–3 files, nothing to decide. `moderate` = reading across files, no design choice. `complex` = 4+ files, architectural change, new pattern, or multi-component integration.
- **Depends on** — `[N, M]` or `none`, between **What** and **Context**. Implement parallelizes on it; a missing or malformed field blocks that.
- **Write-serialization edges** — an edge that only orders same-file writes takes this parenthetical, which the parser strips: `**Depends on**: [12] (write-serialization: night_rig.gd)`. A trailing hyphen note is not stripped and fails the overnight plan check.
- **Graph shape** — prefer wide levels. Restructure when a one-task level sits between multi-task levels or depth nears half the task count — but never merge tasks to cut depth. Don't batch a `complex` task with lighter ones; give a heavy task its own batch.
- **Hub-file seam** — when two tasks would edit one coordinator file, have an early task add a registration point so later tasks add files instead of queuing on it. Where none fits, use an annotated write-serialization edge.
- **Sub-tasks** — `### Task 3a:` / `3b:` (one lowercase letter) are full tasks, ordered `3` < `3a` < `3b` < `4`. A bare `[3]` means task 3. `3ab`, `3A`, `3 a` are errors. Tasks in the same batch need separate `Files` or a serializing edge.
- **Files/Verification consistency** — every file a Verification touches is in Files; builders can't touch files outside their list.
- **Caller enumeration** — a task changing or removing a function, command, or interface lists ALL callers in **Files**.
- **Code budget** — paths, signatures, type field names, pattern references, config keys, contracts between tasks. No ready-to-paste code; no verification that passes by construction.

## 3. Orchestrator review

Follow `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md` for `plan`. Must pass before approval.

## 4. Approval (merged branch/dispatch surface)

One prompt covers both: picking a branch option also approves the plan. Present the plan summary plus **Produced** (one line) and **Trade-offs** (alternatives + rationale).

On `main`/`master`:

```bash
cortex-lifecycle-branch-decision --feature {feature}
```

- `state: prompt` → apply the guards as implement.md §1 does. A `dirty_tree` reason is expected (plan.md is uncommitted until §5) and does not block a worktree; another session's uncommitted changes are a reason *for* isolation.
- `state: resolved`, source `branch_mode` → config fixes the mode: offer it instead of the picker.
- `state: resolved`, source `dispatch_choice` → left over from an earlier run: show all options with it pre-selected; no auto-entry.

Off `main`/`master` the options are `[Approve & implement (current branch), Approve plan but wait to implement]`.

<!-- pause: plan-approval relayed-consent -->
**Options** (≤4): the branch modes plus **"Approve plan but wait to implement"**; the free-text **"Other"** covers Request-changes and Cancel.

| Operator selection | `--decision` | `--dispatch-choice` |
| --- | --- | --- |
| `Implement on current branch` | `branch-mode-approved` | `trunk` |
| `Implement on feature branch with worktree` | `branch-mode-approved` | `worktree-interactive` |
| `Create feature branch` | `branch-mode-approved` | `feature-branch` |
| `Approve plan but wait to implement` | `wait-approved` | (omit) |
| **"Other"**, cancel-intent | `cancelled` | (omit) |
| **"Other"**, any other text | `revise` | (omit) |

**Trunk cost**: no isolation, so same-file tasks run one after another. The plan must carry write-serialization edges — run `grep -c 'write-serialization' {roots.artifacts.path}/plan.md` and cite the count.

```bash
cortex-lifecycle-advance plan-decision --feature <name> --decision <decision> [--dispatch-choice <mode>]
```

Pass `advance_contract.expected_from_state` as `--from-state` when you have it (default `plan`). Route per SKILL.md § Advance-verb routing:

- `branch-mode-approved` → go straight to Implement, which uses `dispatch_choice` and skips its picker.
- `wait-approved` → approval recorded, feature stays at plan; **stop**. The next invocation goes to `implement` and its picker. If backlog-linked, warn that overnight may still execute the item.
- `cancelled` → stop. `revise` → nothing recorded; revise and re-present.

## 5. Transition

`plan-decision` owns the plan→implement transition; record nothing else here. On any approval:

```bash
cortex-lifecycle-stage-artifacts --phase plan --feature {feature} --commit-subject "Plan {feature}: tasks and approval"
```

`config_disabled` → show `message`. `nothing_staged` → nothing to do. `staged` → the verb committed the staged files: show `commit.sha`, or on `failed` show `commit.message` and stop. On "wait", this commit makes the approval last; then stop.
