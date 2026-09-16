# Plan Phase

Numbered tasks with file paths and verification steps — structural context, not code.

## 1. Load context

Read `{roots.artifacts.path}/research.md` and `spec.md`, plus `cortex/lifecycle.config.md` if present. Use the criticality carried from SKILL.md (`cortex-lifecycle-state --feature {feature} --field criticality` only if it never reached this context). **`critical`** → follow `${CLAUDE_SKILL_DIR}/references/competing-plans.md` first.

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

- **Task sizing** — a self-contained unit an implementer with no prior context can complete from the task text and its referenced files.
- **Complexity** drives overnight turn and budget ceilings; the parser takes `simple`/`moderate`/`complex` only (other → `complex`, omitted → `moderate`, both reported as mis-authoring). `simple` = 1–3 files, nothing to decide; `moderate` = orientation across files, no design fork; `complex` = 4+ files, architectural change, new pattern, or multi-component integration.
- **Depends on** — `[N, M]` or `none`, between **What** and **Context**. Implement parallelizes on it; a missing or malformed field blocks parallelism.
- **Write-serialization edges** — an edge that only orders same-file writes takes the parenthetical the parser strips: `**Depends on**: [12] (write-serialization: night_rig.gd)`. A trailing hyphen note is not stripped and fails overnight conformance.
- **Graph shape** — prefer wide levels; a single-task level between multi-task levels, or depth near half the task count, is a restructure signal — never merge tasks to shrink depth. Don't co-batch a `complex` task with lighter siblings; give a heavy straggler its own wave.
- **Hub-file seam** — when two tasks would edit one coordinator file, add a registration seam in an early task so later tasks add files instead of serializing; where no seam applies, use an annotated write-serialization edge.
- **Sub-tasks** — `### Task 3a:` / `3b:` (single lowercase suffix) are first-class units ordered `3` < `3a` < `3b` < `4`; a bare `[3]` means task 3; `3ab`, `3A`, `3 a` fail loud. Same-batch siblings need disjoint `Files` or a serializing edge.
- **Files/Verification consistency** — every file a Verification implies is in Files; builders can't touch files outside their list.
- **Caller enumeration** — a task changing or removing a function, command, or interface lists ALL callers in **Files**.
- **Code budget** — paths, signatures, type field names, pattern references, config keys, inter-task contracts. No copy-paste-ready code, no self-sealing verification.

## 3. Orchestrator review

Follow `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md` for `plan`. Must pass before approval.

## 4. Approval (merged branch/dispatch surface)

Branch selection folds into approval — each branch option implies approval. Present the plan summary plus **Produced** (one line) and **Trade-offs** (alternatives + rationale).

On `main`/`master`:

```bash
cortex-lifecycle-branch-decision --feature {feature}
```

`state: prompt` → render guards as implement.md §1 does. A `dirty_tree` reason is expected (plan.md is uncommitted until §5) and is not a worktree blocker; dirt from another session argues *for* isolation. `state: resolved` → `branch_mode` is config-pinned: fold the fixed mode in rather than opening the picker; `dispatch_choice` is a stale carryover — render the full surface with it pre-selected only, no auto-entry.

Off `main`/`master` the surface is `[Approve & implement (current branch), Approve plan but wait to implement]`.

<!-- pause: plan-approval relayed-consent -->
**Options** (≤4): the branch modes plus **"Approve plan but wait to implement"**; the **"Other"** free-text escape carries Request-changes and Cancel.

| Operator selection | `--decision` | `--dispatch-choice` |
| --- | --- | --- |
| `Implement on current branch` | `branch-mode-approved` | `trunk` |
| `Implement on feature branch with worktree` | `branch-mode-approved` | `worktree-interactive` |
| `Create feature branch` | `branch-mode-approved` | `feature-branch` |
| `Approve plan but wait to implement` | `wait-approved` | (omit) |
| **"Other"**, cancel-intent | `cancelled` | (omit) |
| **"Other"**, any other text | `revise` | (omit) |

**Trunk cost**: no isolation, so same-file tasks serialize — the plan must carry write-serialization edges (`grep -c 'write-serialization' {roots.artifacts.path}/plan.md`; cite the count).

```bash
cortex-lifecycle-advance plan-decision --feature <name> --decision <decision> [--dispatch-choice <mode>]
```

Thread `advance_contract.expected_from_state` via `--from-state` when you have it (default `plan`). Route per SKILL.md § Advance-verb routing:

- `branch-mode-approved` → auto-advance to Implement, which consumes `dispatch_choice` and skips its picker.
- `wait-approved` → approval recorded, feature holds at plan; **halt**. Re-invocation routes to `implement` and its fallback picker. If backlog-linked, warn that overnight may still execute the item.
- `cancelled` → stop. `revise` → nothing recorded; revise and re-present.

## 5. Transition

The plan→implement transition rides the plan-decision arm. On any approval:

```bash
cortex-lifecycle-stage-artifacts --phase plan --feature {feature} --commit-subject "Plan {feature}: tasks and approval"
```

`config_disabled` → relay `message`; `nothing_staged` → nothing; `staged` → the verb committed the staged set — relay `commit.sha`, or `commit.message` on `failed` and halt. On "wait" the commit makes approval durable, then the lifecycle halts.
