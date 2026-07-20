### 1b. Competing Plans (Critical Only)

> Extracted sibling of `plan.md` §1b, read only on the `critical` planning arm (via plan.md §1a).

When criticality is `critical`, dispatch 2-3 independent plan agents — as many as there are meaningfully distinct approaches the spec and research support.

**a. Prepare shared context** — inject `{spec_path}` and `{research_path}` as absolute paths into the template. Each agent reads the files itself; never share one agent's draft with another.

**b. Dispatch plan agents** — launch each as a parallel Task sub-task with the template below **verbatim** (substitute variables, don't paraphrase). Resolve each agent's model, never hardcoding:

```bash
model=$(cortex-resolve-model --role competing-plan --criticality "$(cortex-lifecycle-state --feature {feature} --field criticality --raw)")
```

Dispatch with the captured `$model`; on nonzero exit, halt and escalate.

**Plan Agent Prompt Template:**

```
You are designing an implementation plan for the {feature} feature.

## Inputs
Read the spec at {spec_path} and the research at {research_path}. Before any planning, emit one `READ_OK: <path> <sha>` line per file (`<sha>` from `git hash-object <path>`) at the top of your output.

## Instructions
1. Design an independent, architecturally distinct approach (not merely a different ordering); populate the Overview's `**Architectural Pattern**` with exactly one of {event-driven, pipeline, layered, shared-state, plug-in}, plus a one-sentence statement of how this variant differs from the others.
2. Produce a complete plan in the standard format — Overview + Tasks, each with Files, What, Depends on, Complexity, Context, Verification, Status. Target 5-15 min and 1-5 files per task.
3. Code budget: prose with structural context only — no function bodies, imports, error handling, test code, or copy-paste-ready code. No prose-only or self-sealing Verification.
```

**c. Collect results** — wait for all agents, continuing past any crash/timeout/garbage output. Only 1 succeeds → use it as the sole variant (skip d-f, go to plan.md §3a). All fail → fall back to the single-plan flow in plan.md §3.

**d. Synthesizer dispatch** — one fresh read-only Opus Task sub-agent compares the variants and picks one with structured rationale:
- **Model**: `cortex-resolve-model --role synthesizer` (no `--criticality` flag and no lifecycle-state read); dispatch with the captured name, halt and escalate on nonzero exit.
- **System prompt**: load the canonical fragment from `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources` — don't paraphrase or inline it.
- **User prompt**: inline the variant paths (`plan-variant-A.md`, `-B.md`, optionally `-C.md`) plus the swap-and-require-agreement instruction, directing a JSON envelope per the schema.

**e. Envelope extraction** — parse with the LAST-occurrence delimiter anchor, the same pattern the critical-review gate uses: split on the last `<!--findings-json-->` delimiter, `json.loads` the tail, and validate `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {A,B,C}` (string), `confidence ∈ {high,medium,low}` (string), `rationale` (string). Any extraction/validation failure → treat as `confidence: "low"`.

**f. Route on verdict + confidence:**
- **`verdict ∈ {A,B,C}` AND `confidence ∈ {high,medium}`** — present the chosen variant with the synthesizer's `rationale`; default rubber-stamp (Enter), override by typing a different label. Write it to `cortex/lifecycle/{feature}/plan.md`. Verdict `C` (tie) at high/medium is logically impossible — treat as malformed and fall to the table below.
- **`confidence: low` OR malformed envelope** — show the legacy comparison table for a manual pick, hiding the synthesizer rationale so the operator judges independently: columns **Plan A** / **Plan B** / **Plan C** (drop C if not dispatched), rows **Approach**, **Task count**, **Risk profile**, **Key trade-offs**. On selection, write that variant to `plan.md`; on reject-all, fall back to the single-plan flow. The operator may also **combine** variants (base + a grafted task/module from another) — record the graft in `selection_rationale` below.

**g. Hand off** — go to plan.md §3a if a variant was selected, or plan.md §3 if the operator rejected all on the fallback path.
