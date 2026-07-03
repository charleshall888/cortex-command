### 1b. Competing Plans (Critical Only)

> Extracted sibling of `plan.md` §1b, read only on the `critical` planning arm (via plan.md §1a). Contents: **a** prepare shared context · **b** dispatch plan agents (+ prompt template) · **c** collect results · **d** synthesizer dispatch · **e** envelope extraction · **f** route on verdict + confidence · **g** log v2 `plan_comparison` event.

When criticality is `critical`, dispatch 2-3 independent plan agents to produce competing plan variants. The orchestrator decides how many agents to dispatch (minimum 2, maximum 3) based on how many meaningfully distinct approaches it can identify from the spec and research.

**a. Prepare shared context**: Inject `{spec_path}` and `{research_path}` as absolute paths (derived from repo root) into the prompt template. Each plan agent reads the files itself rather than receiving inline contents. Do NOT share one agent's draft with another — each agent must work independently.

**b. Dispatch plan agents**: Launch each agent as a parallel Task tool sub-task. Use the plan agent prompt template below **verbatim** for each — substitute the variables (including `{spec_path}` and `{research_path}` as absolute paths) but do not omit, reorder, or paraphrase any instructions. Each agent reads the same spec and research files but is instructed to design an independent approach.
**Model**: resolve each plan agent's model at dispatch by running the verb — read it back rather than hardcoding a literal:

```bash
model=$(cortex-resolve-model --role competing-plan --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality)")
```

Dispatch each competing-plan agent with the captured `$model`. On nonzero exit from `cortex-resolve-model`, halt and escalate rather than guessing or substituting a model.

**Plan Agent Prompt Template:**

```
You are designing an implementation plan for the {feature} feature.

## Inputs

### Specification
Read the spec file at {spec_path}.

### Research
Read the research file at {research_path}.

## Read Both Inputs First

Before any planning work, Read both input files at the absolute paths above, then emit one `READ_OK: <path> <sha>` line per file (compute `<sha>` via `git hash-object <path>`) at the top of your output, before any plan content.

## Instructions

1. Design an independent implementation approach for this feature
2. Produce a complete plan following the format below — do not deviate from the structure
3. Design an architecturally distinct approach (not merely a different ordering or decomposition), and populate the Plan Format's `**Architectural Pattern**` field with exactly one category from this closed list — event-driven, pipeline, layered, shared-state, plug-in — plus a one-sentence statement of how this variant differs from the others in this `plan_comparison`.
4. Follow the code budget: plans are prose with structural context, not implementation code

### Allowed in Context and other fields:
File paths and directory structures; function signatures (name, parameters, return type); type definitions (field names and types only); pattern references ("follow the pattern in `src/hooks/useAuth.ts`"); config keys and values; interface contracts between tasks.

### Prohibited:
- Function bodies
- Import statements
- Error handling implementations
- Complete test code
- Any code that an implementer would copy-paste rather than write
- Verification fields that consist only of prose descriptions requiring human judgment to evaluate (e.g., "confirm the feature works correctly", "verify the change looks right")
- Verification steps that reference artifacts (files, log entries, status fields) the executing task creates solely for the purpose of satisfying verification — this is self-sealing and passes tautologically

Required fields per task: Files, What, Depends on, Complexity, Context, Verification, Status. Target 5-15 min per task, 1-5 files each. For critical tier, populate `**Architectural Pattern**` in the Overview per the closed enum `{event-driven, pipeline, layered, shared-state, plug-in}`.
```

**c. Collect results**: Wait for all agents to complete. If an agent fails (crash, timeout, garbage output), continue with results from successful agents. If only 1 agent succeeds, use its plan as the sole variant (skip §1b.d–f synthesizer flow and proceed to plan.md §3a). If all agents fail, fall back to the standard single-plan flow in plan.md §2–§3 in the main context.

**d. Synthesizer dispatch**: Dispatch one fresh Opus Task sub-agent (no worktree isolation needed; the synthesizer is read-only) to compare the variants and select one with structured rationale. The Task tool invocation:

- **Model**: resolve the synthesizer model by running `cortex-resolve-model --role synthesizer` (no `--criticality` flag and no lifecycle-state read) and dispatch with the captured name. On nonzero exit, halt and escalate (per §1b.b).
- **System prompt**: load the canonical synthesizer prompt fragment from `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources`. Do not paraphrase or inline the fragment elsewhere — load the canonical file.
- **User prompt**: inline the variant file paths (e.g. `cortex/lifecycle/{feature}/plan-variant-A.md`, `plan-variant-B.md`, optionally `plan-variant-C.md`) plus the swap-and-require-agreement instruction. The user prompt must direct the synthesizer to emit a JSON envelope per the schema in the system prompt fragment.

**e. Envelope extraction**: After the synthesizer Task sub-agent returns, parse its output using the LAST-occurrence anchor pattern from `plugins/cortex-core/skills/critical-review/references/verification-gates.md` (Phase 2 — Envelope extraction):

1. Locate the `<!--findings-json-->` delimiter using `re.findall(r'^<!--findings-json-->\s*$', output, re.MULTILINE)` and split at the last occurrence (tolerates prose that quotes the delimiter).
2. `json.loads` the post-delimiter tail. Validate the envelope schema: `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {"A","B","C"}` (string), `confidence ∈ {"high","medium","low"}` (string), `rationale` (string).
3. On any extraction or validation failure (no delimiter, JSON decode error, missing required field, invalid enum value), treat the synthesizer result as `confidence: "low"` for routing purposes in §1b.f.

**f. Route on verdict + confidence**:

- **`verdict ∈ {"A","B","C"}` AND `confidence ∈ {"high","medium"}`**: present the chosen variant to the operator with the synthesizer's `rationale`. The default operator action is **rubber-stamp** (Enter to accept the synthesizer's pick); to override, the operator types a different variant label (`A`, `B`, or `C`). On rubber-stamp, write the chosen variant's content to `cortex/lifecycle/{feature}/plan.md`. On override, write the operator-chosen variant's content to `cortex/lifecycle/{feature}/plan.md`. Verdict `"C"` (tie) at high/medium confidence: treat as malformed envelope and fall back to the legacy comparison table below.

- **`confidence: "low"` OR malformed envelope**: display the legacy comparison table for manual user-pick. The synthesizer's preliminary rationale is hidden from the comparison table so the operator judges independently. Render a table with columns **Plan A** / **Plan B** / **Plan C** (omit the Plan C column if only 2 agents were dispatched or only 2 succeeded) and rows **Approach** (1-2 sentence summary), **Task count**, **Risk profile** (key risks), and **Key trade-offs** (what each approach gains/sacrifices). Ask the operator to select a variant or reject all. On selection, write the selected variant's content to `cortex/lifecycle/{feature}/plan.md`. On rejection, fall back to the standard single-plan flow in plan.md §2–§3 in the main context.

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

After logging, proceed to plan.md §3a (Orchestrator Review) if a variant was selected, or to plan.md §2 (Design the Approach) if the operator rejected all variants on the fallback path.
