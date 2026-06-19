# Plan Phase

Produce a detailed implementation plan with numbered tasks, file paths, and verification steps. Plans are prose with implementation context, not code.

## Protocol

### 1. Load Context

Read prior artifacts:
- `cortex/lifecycle/{feature}/research.md` (always)
- `cortex/lifecycle/{feature}/spec.md` (required — produced in Specify phase)
- `cortex/lifecycle.config.md` at project root (if exists — project constraints)

### 1a. Check Criticality

Read criticality by running `cortex-lifecycle-state --feature {feature} --field criticality` (rules: criticality-matrix.md §Reading lifecycle state).

- **If criticality is `critical`**: proceed to §1b (Competing Plans).
- **Otherwise** (low, medium, high): proceed to §2 (Design the Approach) — the standard single-plan flow.

### 1b. Competing Plans (Critical Only)

When criticality is `critical`, dispatch 2-3 independent plan agents to produce competing plan variants. The orchestrator decides how many agents to dispatch (minimum 2, maximum 3) based on how many meaningfully distinct approaches it can identify from the spec and research.

**a. Prepare shared context**: Inject `{spec_path}` and `{research_path}` as absolute paths (derived from repo root) into the prompt template. Each plan agent reads the files itself rather than receiving inline contents. Do NOT share one agent's draft with another — each agent must work independently.

**b. Dispatch plan agents**: Launch each agent as a parallel Task tool sub-task. Use the plan agent prompt template below **verbatim** for each — substitute the variables (including `{spec_path}` and `{research_path}` as absolute paths) but do not omit, reorder, or paraphrase any instructions. Each agent reads the same spec and research files but is instructed to design an independent approach.
**Model**: `sonnet`

**Plan Agent Prompt Template:**

```
You are designing an implementation plan for the {feature} feature.

## Inputs

### Specification
Read the spec file at {spec_path}.

### Research
Read the research file at {research_path}.

## Read Both Inputs First

Before any planning work, Read both input files at the absolute paths above. After reading each, emit one `READ_OK` header line per file with the file's git blob SHA — one line per file, in this exact form: `READ_OK: <path> <sha>`. Example for the spec file: `READ_OK: {spec_path} <sha>` — and similarly for `{research_path}`. Compute `<sha>` via `git hash-object <path>`. Emit both `READ_OK` lines at the top of your output before any plan content.

## Instructions

1. Design an independent implementation approach for this feature
2. Produce a complete plan following the format below — do not deviate from the structure
3. Your approach must be architecturally distinct, not merely a different ordering or decomposition of the same strategy. Name your architectural category from this closed list — exactly one: event-driven, pipeline, layered, shared-state, plug-in.
4. Populate the Plan Format's `**Architectural Pattern**` field with the named category and a one-sentence statement of how this variant differs from the other variants in this `plan_comparison`.
5. Follow the code budget: plans are prose with structural context, not implementation code

### Allowed in Context and other fields:
- File paths and directory structures
- Function signatures (name, parameters, return type)
- Type definitions (field names and types only)
- Pattern references ("follow the pattern in `src/hooks/useAuth.ts`")
- Config keys and values
- Interface contracts between tasks

### Prohibited:
- Function bodies
- Import statements
- Error handling implementations
- Complete test code
- Any code that an implementer would copy-paste rather than write
- Verification fields that consist only of prose descriptions requiring human judgment to evaluate (e.g., "confirm the feature works correctly", "verify the change looks right")
- Verification steps that reference artifacts (files, log entries, status fields) the executing task creates solely for the purpose of satisfying verification — this is self-sealing and passes tautologically

Use the plan format defined in §3 Write Plan Artifact below. Required fields per task: Files, What, Depends on, Complexity, Context, Verification, Status. Target 5-15 min per task, 1-5 files each. For critical tier, populate `**Architectural Pattern**` in the Overview per the closed enum `{event-driven, pipeline, layered, shared-state, plug-in}`.
```

**c. Collect results**: Wait for all agents to complete. If an agent fails (crash, timeout, garbage output), continue with results from successful agents. If only 1 agent succeeds, use its plan as the sole variant (skip §1b.d–f synthesizer flow and proceed to §3a). If all agents fail, fall back to the standard single-plan flow (§2-§3) in the main context.

**d. Synthesizer dispatch**: Dispatch one fresh Opus Task sub-agent (no worktree isolation needed; the synthesizer is read-only) to compare the variants and select one with structured rationale. The Task tool invocation:

- **Model**: `opus`
- **System prompt**: load the canonical synthesizer prompt fragment from `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources`. Do not paraphrase or inline the fragment elsewhere — load the canonical file.
- **User prompt**: inline the variant file paths (e.g. `cortex/lifecycle/{feature}/plan-variant-A.md`, `plan-variant-B.md`, optionally `plan-variant-C.md`) plus the swap-and-require-agreement instruction directing the synthesizer to compare the variants twice with order swapped and require agreement before assigning `confidence: "high"` or `"medium"`. The user prompt must direct the synthesizer to emit a JSON envelope per the schema in the system prompt fragment.

**e. Envelope extraction**: After the synthesizer Task sub-agent returns, parse its output using the LAST-occurrence anchor pattern from `plugins/cortex-core/skills/critical-review/references/verification-gates.md` (Phase 2 — Envelope extraction):

1. Locate the `<!--findings-json-->` delimiter using `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)` and split at the last occurrence (tolerates prose that quotes the delimiter).
2. `json.loads` the post-delimiter tail. Validate the envelope schema: `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {"A","B","C"}` (string), `confidence ∈ {"high","medium","low"}` (string), `rationale` (string).
3. On any extraction or validation failure (no delimiter, JSON decode error, missing required field, invalid enum value), treat the synthesizer result as `confidence: "low"` for routing purposes in §1b.f.

**f. Route on verdict + confidence**:

- **`verdict ∈ {"A","B","C"}` AND `confidence ∈ {"high","medium"}`**: present the chosen variant to the operator with the synthesizer's `rationale`. The default operator action is **rubber-stamp** (Enter to accept the synthesizer's pick); to override, the operator types a different variant label (`A`, `B`, or `C`). On rubber-stamp, write the chosen variant's content to `cortex/lifecycle/{feature}/plan.md`. On override, write the operator-chosen variant's content to `cortex/lifecycle/{feature}/plan.md`. Verdict `"C"` (tie) at high/medium confidence: treat as malformed envelope and fall back to the legacy comparison table below.

- **`confidence: "low"` OR malformed envelope**: display the legacy comparison table for manual user-pick. The synthesizer's preliminary rationale is hidden from the comparison table so the operator judges independently. Render this table:

  | | Plan A | Plan B | Plan C |
  |---|---|---|---|
  | **Approach** | [1-2 sentence summary] | [1-2 sentence summary] | [1-2 sentence summary] |
  | **Task count** | [N] | [N] | [N] |
  | **Risk profile** | [key risks] | [key risks] | [key risks] |
  | **Key trade-offs** | [what this approach gains/sacrifices] | [what this approach gains/sacrifices] | [what this approach gains/sacrifices] |

  Omit the Plan C column if only 2 agents were dispatched or only 2 succeeded. Ask the operator to select a variant or reject all. On selection, write the selected variant's content to `cortex/lifecycle/{feature}/plan.md`. On rejection, fall back to the standard single-plan flow (§2-§3) in the main context.

  When presenting the comparison, surface to the operator that a `plan_comparison` may also be resolved by **combining variants** — selecting one variant as the base and grafting a named task or module from another variant into it (a cross-graft producing a combined plan). Record the graft in the §1b.g event log via `selection_rationale` (e.g. `"operator graft: Plan A base + Plan B Task 3"`) and write the combined plan content to `cortex/lifecycle/{feature}/plan.md`.

**g. Log v2 `plan_comparison` event**: Append a JSONL event to `cortex/lifecycle/{feature}/events.log` with `schema_version: 2` plus the five new fields:

```
{"ts": "<ISO 8601>", "event": "plan_comparison", "schema_version": 2, "feature": "<name>", "variants": [{"label": "Plan A", "approach": "<summary>", "task_count": <N>, "risk": "<risk summary>"}], "selected": "Plan A|none", "selection_rationale": "<synthesizer rationale or 'fallback: low-confidence user-pick' or 'fallback: malformed envelope user-pick'>", "selector_confidence": "high|medium|low", "position_swap_check_result": "agreed|disagreed", "disposition": "rubber_stamp|override|deferred|auto_select", "operator_choice": "Plan A|null"}
```

Field semantics:
- `schema_version` (int, always `2`).
- `selection_rationale` (string): the synthesizer's `rationale` on the high/medium-confidence path; a short fallback string on the user-pick path.
- `selector_confidence` (`"high"`|`"medium"`|`"low"`): the synthesizer's `confidence`; `"low"` when the path was the legacy comparison-table fallback.
- `position_swap_check_result` (`"agreed"`|`"disagreed"`): derived from the synthesizer's `confidence` (`"high"`/`"medium"` → `"agreed"`; `"low"` → `"disagreed"`); on malformed envelope, set to `"disagreed"`.
- `disposition` (`"rubber_stamp"`|`"override"`|`"deferred"`|`"auto_select"`): operator action — `"rubber_stamp"` when the operator pressed Enter on the synthesizer's pick, `"override"` when the operator typed a different variant label, `"deferred"` when the operator rejected all variants on the fallback path, `"auto_select"` reserved for the overnight surface (not emitted from interactive §1b).
- `operator_choice` (string|null): the variant label the operator chose (`"Plan A"`, `"Plan B"`, etc.); `null` when no operator was present (overnight) or the operator rejected all variants.

After logging, proceed to §3a (Orchestrator Review) if a variant was selected, or to §2 (Design the Approach) if the operator rejected all variants on the fallback path.

### 2. Design the Approach

Based on research and spec, determine:
- Overall architecture and implementation strategy
- File creation/modification order
- Integration points with existing code
- Testing and verification approach

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

| Tier | When to use | Examples |
|------|-------------|---------|
| `trivial` | Single-file edit, no side effects, no commit needed | Update a comment, bump a version string, fix a typo |
| `simple` | 1–3 file changes, commit required, may run shell commands or validate output | Create a hook script, edit settings.json, create a symlink, run chmod, wire a new entry into a config array |
| `complex` | 4+ files, architectural change, new pattern, or multi-component integration | Add a new subsystem, refactor a module's public API, integrate two previously independent components |

**Critical rule**: Tasks that create files, modify JSON settings, create symlinks, set file permissions, or must commit are `simple` minimum — **never `trivial`**. The `trivial` tier has a lower turn budget; assigning it to multi-step tasks causes turn exhaustion before the commit step.

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

**Allowed in Context and other fields:**
- File paths and directory structures
- Function signatures (name, parameters, return type)
- Type definitions (field names and types only)
- Pattern references ("follow the pattern in `src/hooks/useAuth.ts`")
- Config keys and values
- Interface contracts between tasks

**Prohibited:**
- Function bodies
- Import statements
- Error handling implementations
- Complete test code
- Any code that an implementer would copy-paste rather than write
- Verification fields that consist only of prose descriptions requiring human judgment (e.g., "confirm the feature works correctly")
- Verification steps that reference artifacts (files, log entries, status fields) the executing task creates solely for the purpose of satisfying verification — this is self-sealing and passes tautologically

After writing `plan.md`, register the `"plan"` artifact in `cortex/lifecycle/{feature}/index.md` per the canonical artifact-registration recipe in backlog-writeback.md (loaded at lifecycle Step 2).

### 3a. Orchestrator Review

Before presenting the artifact to the user, read and follow the orchestrator-review protocol (use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest: the **orchestrator-review** target) for the `plan` phase. The orchestrator review must pass before proceeding to user approval.

### 3b. Critical Review

After orchestrator review passes, read the active tier and criticality (rules: criticality-matrix.md §Reading lifecycle state — use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest):

- `cortex-lifecycle-state --feature {feature} --field tier`
- `cortex-lifecycle-state --feature {feature} --field criticality`

**Run** when `tier = complex` AND `criticality ∈ {medium, high, critical}`: invoke the `critical-review` skill with the plan artifact. Present the synthesis to the user before plan approval. Otherwise, read and follow the critical-review gate protocol (use the body-resolved absolute path from lifecycle SKILL.md's Reference-path propagation manifest: the **critical-review-gate** target) for the `plan` phase.

### 4. User Approval (merged branch/dispatch surface)

This surface folds the Implement-phase branch/dispatch selection into plan approval — **each branch option implies plan approval**, so the operator answers one question, not two. Present the plan summary (overview + task list) plus the approval-surface fields:

- **Produced** (one-line summary of the artifact)
- **Trade-offs** (alternatives considered and rationale for chosen approach)

**Assemble the merged option set.** When the current branch is `main`/`master`, read the branch-mode and picker decision (two Bash calls, exactly as Implement §1 does), then follow the shared decision logic in **branch-picker.md** (body-resolved absolute path — SKILL.md Reference-path propagation manifest) to assemble the adaptive branch options:

```bash
cortex-lifecycle-branch-mode .
cortex-lifecycle-picker-decision . {feature} {branch_mode}
```

branch-picker.md defines the suppressed-routing (a configured mode fixes a single choice), the uncommitted-changes-guard demotion, and the runtime-probe degrade. When **not** on `main`/`master`, the branch sub-choices collapse: implementation will proceed on the current branch (`trunk`), so the surface offers only `[Approve & implement (current branch), Approve plan but wait to implement]`.

**Compose the `AskUserQuestion` `options`** (≤4): the assembled branch modes, plus a final **"Approve plan but wait to implement"** option. The auto-provided **"Other"** free-text escape is appended by the platform *outside* the 4-option `options` cap and carries Request-changes and Cancel. Route on the selection:

- **A branch mode** (`Implement on current branch` → `trunk`; `Implement on feature branch with worktree` → `worktree-interactive`; `Create feature branch` → `feature-branch`) — implies plan approval. Append `plan_approved` carrying the chosen `dispatch_choice`, then the `phase_transition` from §5, then auto-advance to Implement (which consumes `dispatch_choice` and skips its own picker). Proceed automatically.
  ```
  {"ts": "<ISO 8601>", "event": "plan_approved", "feature": "<name>", "dispatch_choice": "<trunk|worktree-interactive|feature-branch>"}
  ```
- **Approve plan but wait to implement** — append `plan_approved` with `dispatch_choice: "wait"`, then append `feature_paused`, then **halt** (do not auto-advance, do not dispatch). Re-invocation routes to `implement` (the plan IS approved); Implement §1 fires its fallback picker since `wait` is not a branch mode. The feature surfaces as `implement-paused`. **When the feature is backlog-linked (Context A), warn now** that the overnight runner may still execute the item unless it is paused (overnight eligibility does not yet honor `feature_paused` — see the overnight-honors-pause backlog item).
  ```
  {"ts": "<ISO 8601>", "event": "plan_approved", "feature": "<name>", "dispatch_choice": "wait"}
  {"ts": "<ISO 8601>", "event": "feature_paused", "feature": "<name>"}
  ```
- **"Other" free-text** — interpret the text. A cancel-intent → append `lifecycle_cancelled` and halt. Any other text → treat as **Request changes**: collect the change, revise the plan, and **re-assemble and re-present** this merged surface (re-running the branch-picker assembly). Do not emit `plan_approved` on revision rounds — only a terminal branch-mode or "wait" selection emits it.

### 5. Transition

On a branch-mode selection (not "wait"), append a `phase_transition` event to `cortex/lifecycle/{feature}/events.log` (the `plan_approved` event from §4 must precede this one in the log):

```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "plan", "to": "implement"}
```

On any approval (a branch-mode selection OR "wait" — both emit `plan_approved`), run `cortex-read-commit-artifacts` to read the `commit-artifacts` flag. If stdout is `true` (the default), stage `cortex/lifecycle/{feature}/` and commit using `/cortex-core:commit`. If stdout is `false`, skip the commit silently. On the "wait" path the commit makes the approval durable, then the lifecycle halts.

## Hard Gate

Do NOT write implementation code in the plan. Plans describe WHAT each task does and provide structural context, not HOW to write the code.

Backlog items suggest approaches — they don't prescribe them. Unless the backlog item has linked cortex/research/spec artifacts that already validated the approach, evaluate it critically and weigh alternatives.
