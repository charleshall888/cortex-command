# Plan Phase

Produce a detailed implementation plan with numbered tasks, file paths, and verification steps. Plans are prose with implementation context, not code.

## Contents

1. [Protocol](#protocol)
2. [Hard Gate](#hard-gate)

## Protocol

### 1. Load Context

Read prior artifacts:
- `lifecycle/{feature}/research.md` (always)
- `lifecycle/{feature}/spec.md` (required — produced in Specify phase)
- `lifecycle.config.md` at project root (if exists — project constraints)

### 1a. Check Criticality

Read `lifecycle/{feature}/events.log` and find the most recent event containing a `criticality` field (`lifecycle_start` or `criticality_override`). Extract the criticality value. If no criticality field is found, default to `medium`.

- **If criticality is `critical`**: proceed to §1b (Competing Plans).
- **Otherwise** (low, medium, high): proceed to §2 (Design the Approach) — the standard single-plan flow.

### 1b. Competing Plans (Critical Only)

When criticality is `critical`, dispatch 2-3 independent plan agents to produce competing plan variants. The orchestrator decides how many agents to dispatch (minimum 2, maximum 3) based on how many meaningfully distinct approaches it can identify from the spec and research.

**a. Prepare shared context**: Read `lifecycle/{feature}/spec.md` and `lifecycle/{feature}/research.md` in the main context. These will be provided to each plan agent. Do NOT share one agent's draft with another — each agent must work independently.

**b. Dispatch plan agents**: Launch each agent as a parallel Task tool sub-task. Use the plan agent prompt template below **verbatim** for each — substitute the variables but do not omit, reorder, or paraphrase any instructions. Each agent receives the same spec and research content but is instructed to design an independent approach. The dispatched agents emit plans in the §3 Write Plan Artifact format below; for critical tier only, they also populate the `**Architectural Pattern**` field in the Overview per the closed enum `{event-driven, pipeline, layered, shared-state, plug-in}`.
**Model**: `sonnet` (competing plan agents always use sonnet)

**Plan Agent Prompt Template:**

```
You are designing an implementation plan for the {feature} feature.

## Inputs

### Specification
{full contents of lifecycle/{feature}/spec.md}

### Research
{full contents of lifecycle/{feature}/research.md}

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
- **System prompt**: load the canonical synthesizer prompt fragment from `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources.files()` (e.g. `importlib.resources.files("cortex_command.overnight.prompts").joinpath("plan-synthesizer.md").read_text()`). Do not paraphrase or inline the fragment elsewhere — load the canonical file so both interactive and overnight surfaces stay in lockstep.
- **User prompt**: inline the variant file paths (e.g. `lifecycle/{feature}/plan-variant-A.md`, `plan-variant-B.md`, optionally `plan-variant-C.md`) plus the swap-and-require-agreement instruction directing the synthesizer to compare the variants twice with order swapped and require agreement before assigning `confidence: "high"` or `"medium"`. The user prompt must direct the synthesizer to emit a JSON envelope per the schema in the system prompt fragment.

The synthesizer is dispatched as a fresh Task sub-agent — it shares no context with the plan-gen sub-agents from §1b.b — so its judgment is fresh by construction.

**e. Envelope extraction**: After the synthesizer Task sub-agent returns, parse its output using the LAST-occurrence anchor pattern from `plugins/cortex-core/skills/critical-review/SKILL.md:176-182`:

1. Locate the `<!--findings-json-->` delimiter using `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)` and split at the last occurrence (tolerates prose that quotes the delimiter).
2. `json.loads` the post-delimiter tail. Validate the envelope schema: `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {"A","B","C"}` (string), `confidence ∈ {"high","medium","low"}` (string), `rationale` (string).
3. On any extraction or validation failure (no delimiter, JSON decode error, missing required field, invalid enum value), treat the synthesizer result as `confidence: "low"` for routing purposes in §1b.f.

**f. Route on verdict + confidence**:

- **`verdict ∈ {"A","B","C"}` AND `confidence ∈ {"high","medium"}`**: present the chosen variant to the operator with the synthesizer's `rationale`. The default operator action is **rubber-stamp** (Enter to accept the synthesizer's pick); to override, the operator types a different variant label (`A`, `B`, or `C`). On rubber-stamp, write the chosen variant's content to `lifecycle/{feature}/plan.md`. On override, write the operator-chosen variant's content to `lifecycle/{feature}/plan.md`. Verdict `"C"` (tie) at high/medium confidence is a logically impossible state per the synthesizer prompt fragment's instruction to pair `"C"` with `confidence: "low"`; if it occurs, treat as malformed envelope and fall back to the legacy comparison table below.

- **`confidence: "low"` OR malformed envelope**: display the legacy comparison table for manual user-pick. The synthesizer's preliminary rationale is hidden from the comparison table to preserve fresh-judgment freshness — the operator must form an independent verdict from the variant content rather than anchoring on a low-confidence synthesizer recommendation. Render this table:

  | | Plan A | Plan B | Plan C |
  |---|---|---|---|
  | **Approach** | [1-2 sentence summary] | [1-2 sentence summary] | [1-2 sentence summary] |
  | **Task count** | [N] | [N] | [N] |
  | **Risk profile** | [key risks] | [key risks] | [key risks] |
  | **Key trade-offs** | [what this approach gains/sacrifices] | [what this approach gains/sacrifices] | [what this approach gains/sacrifices] |

  Omit the Plan C column if only 2 agents were dispatched or only 2 succeeded. Ask the operator to select a variant or reject all. On selection, write the selected variant's content to `lifecycle/{feature}/plan.md`. On rejection, fall back to the standard single-plan flow (§2-§3) in the main context.

  When presenting the comparison, surface to the operator that a `plan_comparison` may also be resolved by **combining variants** — selecting one variant as the base and grafting a named task or module from another variant into it (a cross-graft producing a combined plan). Record the graft in the §1b.g event log via `selection_rationale` (e.g. `"operator graft: Plan A base + Plan B Task 3"`) and write the combined plan content to `lifecycle/{feature}/plan.md`.

**g. Log v2 `plan_comparison` event**: Append a JSONL event to `lifecycle/{feature}/events.log` with `schema_version: 2` plus the five new fields:

```
{"ts": "<ISO 8601>", "event": "plan_comparison", "schema_version": 2, "feature": "<name>", "variants": [{"label": "Plan A", "approach": "<summary>", "task_count": <N>, "risk": "<risk summary>"}], "selected": "Plan A|none", "selection_rationale": "<synthesizer rationale or 'fallback: low-confidence user-pick' or 'fallback: malformed envelope user-pick'>", "selector_confidence": "high|medium|low", "position_swap_check_result": "agreed|disagreed", "disposition": "rubber_stamp|override|deferred|auto_select", "operator_choice": "Plan A|null"}
```

Field semantics:
- `schema_version` (int, always `2`): anchors the v2 sweep. Existing v1 readers tolerate this field-additively.
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

Produce `lifecycle/{feature}/plan.md` with this structure:

```markdown
# Plan: {feature}

## Overview
[1-2 sentence summary of the implementation approach and key architectural decisions]
**Architectural Pattern**: {category}
<!-- Include only when the implementation commits to one of: event-driven, pipeline, layered, shared-state, plug-in. Omit otherwise. -->

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
- **Verification**: {(a) command + expected output + pass/fail (e.g., "run `just test` — pass if exit 0, all tests pass"), OR (b) specific file/pattern check (e.g., "`grep -c 'keyword' path/file` = 1 — pass if count = 1"), OR (c) "Interactive/session-dependent: [one-sentence rationale explaining why no command is possible]"}
- **Status**: [ ] pending

...

## Verification Strategy
[How to verify the complete feature works end-to-end after all tasks are done]

## Veto Surface
[Design choices, scope calls, or constraints the user might want to revisit before implementation begins. "None" if nothing is controversial.]

## Scope Boundaries
[What is explicitly excluded from this feature. Maps to the spec's Non-Requirements section.]
```

> Verification fields that consist only of prose descriptions (e.g., "confirm the feature works correctly") do not pass the P4 checklist. Use format (a), (b), or (c) from the task template above.

### Task Sizing

Target 5-15 minutes per task, 1-5 files each. A typical feature should decompose into 5-15 tasks. Split tasks that touch more than 5 files.

Each task must be self-contained — an implementer with no prior context should be able to complete it using only the task text and the files it references.

### Wiring Co-Location

When a task deploys a new `bin/cortex-*` script, the SAME task must include the consumer wiring — typically a SKILL.md mention, hook reference, or doc reference that names the script as inline code or a path-qualified token. The pre-commit parity check (`bin/cortex-check-parity`) emits W003 ("orphan: deployed but not referenced") and rejects intermediate commits where a script exists in `bin/` but no in-scope file references it. Splitting deployment from wiring across tasks forces `--no-verify`, which is discouraged.

If wiring is too large to combine with deployment in one task, reorder so wiring lands first — a SKILL.md mention is fine even before the script exists, since the parity check flags `deployed-but-unreferenced` (W003), not `referenced-but-undeployed`.

### Task Complexity Classification

Every task requires a `**Complexity**` field. Choose from `trivial`, `simple`, or `complex`:

| Tier | When to use | Examples |
|------|-------------|---------|
| `trivial` | Single-file edit, no side effects, no commit needed | Update a comment, bump a version string, fix a typo |
| `simple` | 1–3 file changes, commit required, may run shell commands or validate output | Create a hook script, edit settings.json, create a symlink, run chmod, wire a new entry into a config array |
| `complex` | 4+ files, architectural change, new pattern, or multi-component integration | Add a new subsystem, refactor a module's public API, integrate two previously independent components |

**Critical rule**: Tasks that create files, modify JSON settings, create symlinks, set file permissions, or must commit are `simple` minimum — **never `trivial`**. The `trivial` tier has a lower turn budget; assigning it to multi-step tasks causes turn exhaustion before the commit step.

The `**Complexity**` field drives model and turn-limit selection in the overnight pipeline. If absent, the parser defaults to `simple` — which is the safer default.

### Dependency Annotations

Every task requires a `**Depends on**` field between **What** and **Context**. Use `[N, M]` (bracketed task numbers) for tasks with dependencies, or `none` for independent tasks. The implement phase uses these annotations to dispatch independent tasks in parallel — omitting or misformatting the field blocks parallel execution.

### Files/Verification Consistency

Every file that Verification implies must be listed in Files. If Verification says "write a test," the test file must appear in Files. Builders are instructed not to modify files outside their Files list — contradicting this with Verification creates an impossible constraint.

### Caller Enumeration

When a task modifies or removes a function, command, or interface — enumerate ALL files that call, reference, or depend on it in the task's **Files** field. A task that renames a command without updating every caller leaves broken references. A task that changes a function signature without updating its callers causes runtime errors. "Only the file I'm editing" is insufficient when the change propagates to call sites.

Before writing the Files list for any modification task, search the codebase for all references to the symbol being changed and list every affected file.

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
- Verification steps that reference artifacts (files, log entries, status fields) the executing task creates solely for the purpose of satisfying verification — this is self-sealing and passes tautologically

After writing `plan.md`, update `lifecycle/{feature}/index.md`:
- If `"plan"` is already in the `artifacts` array, skip entirely (no-op)
- Otherwise: append `"plan"` to the artifacts inline array
- Add wikilink: `- Plan: [[{lifecycle-slug}/plan|plan.md]]`
  (where `{lifecycle-slug}` is the feature directory name, e.g. `add-lifecycle-feature-indexmd-for-obsidian-navigation`)
- Update the `updated` field to today's date
- Rewrite the full `index.md` atomically

### 3a. Orchestrator Review

Before presenting the artifact to the user, read and follow `references/orchestrator-review.md` for the `plan` phase. The orchestrator review must pass before proceeding to user approval.

### 3b. Critical Review

After orchestrator review passes, check `lifecycle/{feature}/events.log` for the most recent `lifecycle_start` or `criticality_override` event. Extract `tier`.

**Run** when `tier = complex`: invoke the `critical-review` skill with the plan artifact. Present the synthesis to the user before plan approval.

**Skip** when `tier = simple`. Proceed directly to user approval.

### 4. User Approval

Present the plan summary (overview + task list). In addition to the overview and task list, include these approval surface fields:

- **Produced** (one-line summary of the artifact)
- **Trade-offs** (alternatives considered and rationale for chosen approach)

The user must approve before implementation begins. If the user requests changes, revise and re-present.

### 5. Transition

Append a `phase_transition` event to `lifecycle/{feature}/events.log`:

```
{"ts": "<ISO 8601>", "event": "phase_transition", "feature": "<name>", "from": "plan", "to": "implement"}
```

If `commit-artifacts` is enabled in project config (default), stage `lifecycle/{feature}/` and commit using `/cortex-core:commit`.

After approval, proceed to Implement.

## Hard Gate

Do NOT write implementation code in the plan. Plans describe WHAT each task does and provide structural context, not HOW to write the code.

| Thought | Reality |
|---------|---------|
| "This plan is so detailed I might as well write the code" | If you are writing function bodies, you have violated the code budget. Plans provide structure, not implementation. |
| "The backlog item said to do it this way" | Backlog items suggest approaches — they don't prescribe them. Unless the backlog item has linked research/spec artifacts that already validated the approach, evaluate it critically and weigh alternatives. |
| "The agent can verify by checking the file it just wrote" | Verification that checks an artifact the same task creates solely for verification is self-sealing — it passes tautologically. Use test commands, pre-existing state, or prior-task outputs instead. |
