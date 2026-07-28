# Plan Phase

Numbered tasks with file paths and verification steps. Prose with structural context, not code.

## 1. Load context

Read `cortex/lifecycle/{feature}/research.md` and `spec.md`, plus `cortex/lifecycle.config.md` if present.

### 1a. Check criticality

Use the criticality SKILL.md Step 2 carried forward; read it with `cortex-lifecycle-state --feature {feature} --field criticality` only if it never reached this context.

### 1b. Competing Plans (Critical Only)

**`critical`** → read and follow `${CLAUDE_SKILL_DIR}/references/competing-plans.md`, then proceed per its guidance. **Otherwise** → §2.

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
- **Complexity**: trivial|simple|complex
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

**Task sizing** — a self-contained unit an implementer with no prior context can complete from the task text and its referenced files alone.

**Complexity** drives model and turn-limit selection in the overnight pipeline: `trivial` = single-file edit, no side effects, no commit; `simple` = 1–3 files, commit required; `complex` = 4+ files, architectural change, new pattern, or multi-component integration. Anything creating files, modifying JSON settings, creating symlinks, setting permissions, or committing is `simple` **minimum** — a trivial turn budget exhausts before the commit step.

**Dependencies** — `**Depends on**` sits between **What** and **Context**: `[N, M]` or `none`. Implement parallelizes on it, so a missing or malformed field blocks parallelism.

**Write-serialization edges** — an edge that only orders same-file writes takes the parenthetical dialect the parser strips: `**Depends on**: [12] (write-serialization: night_rig.gd)`. A trailing single-hyphen note is *not* stripped and fails overnight conformance. Ordering-only semantics: an executor with per-task isolation may relax it to not-before; none deletes it.

**Graph shape** — prefer wide levels. A single-task level between multi-task levels, or a level count approaching half the task count, is a restructure signal; never merge tasks to shrink depth. Every edge counts at face value; write-serialization-annotated segments are dissolve-first candidates, not a depth discount. Don't co-batch a `complex` task with `trivial`/`simple` siblings at one level — give a heavy straggler its own wave.

**Hub-file seam** — when two tasks would edit one coordinator file, add a registration seam in an early task so later tasks add files instead of serializing edits. Where a seam can't apply (structural rework, deletions, re-pointing), the honest remedy is an annotated write-serialization edge.

**Sub-task headings** — `### Task 3a:`, `### Task 3b:` (single lowercase suffix) are first-class dispatchable units ordered `3` < `3a` < `3b` < `4`. Reference by full id; a bare `[3]` means literal task 3. `3ab`, `3A`, `3 a` fail loud. Same-batch siblings sharing a `Depends on` co-schedule into one worktree, so give them disjoint `Files` or an explicit serializing edge.

**Files/Verification consistency** — every file a Verification implies must be in Files; builders can't touch files outside their list.

**Caller enumeration** — when a task changes or removes a function, command, or interface, search first and list ALL callers in **Files**.

**Code budget** — structural context only: paths, signatures, type field names, pattern references, config keys, inter-task contracts. No copy-paste-ready code. No self-sealing verification. A task building a capture or evidence rig must produce and validate a discarded sample of the exact committed-evidence shape end to end.

Then: `cortex-lifecycle-register-artifact --feature {feature} --artifact plan`.

## 3. Orchestrator review

Follow `${CLAUDE_SKILL_DIR}/references/orchestrator-review.md` for the `plan` phase. Must pass before approval.

## 4. Approval (merged branch/dispatch surface)

Folds Implement's branch selection into plan approval — each branch option implies approval. Present the plan summary plus **Produced** (one-line artifact summary) and **Trade-offs** (alternatives considered + rationale).

On `main`/`master`, resolve the option set with the verb Implement §1 calls; §4 renders the guards from its payload itself:

```bash
cortex-lifecycle-branch-decision --feature {feature}
```

`state: prompt` → render guards as Implement §1 does. A `dirty_tree` reason is expected: plan.md is uncommitted until §5, so §4 dirties its own tree. That alone is not a worktree blocker, and dirt from another session is the strongest case *for* isolation, not against it.

`state: resolved` → **`branch_mode`** is config-pinned; fold the fixed mode in rather than opening the picker. **`dispatch_choice`** is a stale carryover from a prior approval pass; render the full surface with the carried mode as a pre-selected default only — it authorizes no worktree auto-entry.

Off `main`/`master` the sub-choices collapse, so the surface offers only `[Approve & implement (current branch), Approve plan but wait to implement]`.

<!-- pause: plan-approval relayed-consent -->
**Compose `AskUserQuestion` options** (≤4): the branch modes plus **"Approve plan but wait to implement"**. The platform's **"Other"** free-text escape carries Request-changes and Cancel.

| Operator selection | `--decision` | `--dispatch-choice` |
| --- | --- | --- |
| `Implement on current branch` | `branch-mode-approved` | `trunk` |
| `Implement on feature branch with worktree` | `branch-mode-approved` | `worktree-interactive` |
| `Create feature branch` | `branch-mode-approved` | `feature-branch` |
| `Approve plan but wait to implement` | `wait-approved` | (omit) |
| **"Other"**, cancel-intent | `cancelled` | (omit) |
| **"Other"**, any other text | `revise` | (omit) |

**Trunk cost**: no isolation, so same-file tasks serialize — the plan must carry write-serialization edges. When this plan already has some (`grep -c 'write-serialization' cortex/lifecycle/{feature}/plan.md`), cite the count.

```bash
cortex-lifecycle-advance plan-decision --feature <name> --decision <decision> [--dispatch-choice <mode>]
```

Thread the envelope's `advance_contract.expected_from_state` via `--from-state` when you have it (default: `plan`). Route on the returned `state` per SKILL.md § Advance-verb routing:

- **`branch-mode-approved`** → auto-advance to Implement, which consumes `dispatch_choice` and skips its own picker.
- **`wait-approved`** → approval recorded, feature holds at plan; **halt**. Re-invocation routes to `implement` and Implement fires its fallback picker. If backlog-linked, warn that overnight may still execute the item — its eligibility does not yet honor a paused feature.
- **`cancelled`** → stop here. **`revise`** → nothing recorded; revise and re-present.

## 5. Transition

The plan→implement transition rides the plan-decision arm — no separate step. On any approval:

```bash
cortex-lifecycle-stage-artifacts --phase plan --feature {feature}
```

The verb reads `commit-artifacts` itself. Act on `signal`: `config_disabled` → relay its `message` and skip the commit; `nothing_staged` → skip silently; `staged` → commit via `/cortex-core:commit`. A non-zero exit is a staging failure — halt rather than commit a partial set. On "wait" the commit makes approval durable, then the lifecycle halts.

**Hard gate**: backlog items suggest approaches, they don't prescribe them. Unless the item has linked research/spec artifacts that already validated the approach, evaluate it critically and weigh alternatives.
