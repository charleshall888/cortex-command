# Competing Plans (Critical Only)

Read only when plan.md §1 sends you here at `critical`. Dispatch 2–3 independent plan agents, one per clearly different approach the spec and research support.

**a. Dispatch** each as a parallel sub-task (model your call) with `{spec_path}` and `{research_path}` as absolute paths. Each agent reads the files itself and never sees another's draft. Each designs a **different architecture**, not the same tasks in a new order. It sets the Overview's `**Architectural Pattern**` to exactly one of {event-driven, pipeline, layered, shared-state, plug-in} plus one sentence on how it differs. Output is a full plan in plan.md's format, under its sizing and code-budget rules.

**b. Collect** — wait for all; keep going past any crash, timeout, or unusable output. Exactly 1 succeeds → use it and skip to plan.md §3. All fail → plan.md's single-plan flow.

**c. Synthesize** — one new read-only sub-agent compares the variants, picks one, and gives its reasons. This is the judgment step; choose the model to match. System prompt: load `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources` — never paraphrase it. User prompt: the variant paths (`plan-variant-A.md`, `-B.md`, optionally `-C.md`) plus an instruction to compare again with the order swapped and require both runs to agree. Ask for JSON output.

**d. Extract** — split on the LAST `<!--findings-json-->` delimiter, `json.loads` the tail, validate `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {A,B,C}`, `confidence ∈ {high,medium,low}`, `rationale` (string). Any failure → `confidence: "low"`.

**e. Route** — `verdict ∈ {A,B,C}` AND `confidence ∈ {high,medium}` → show the chosen variant and its rationale. Enter accepts it; a label overrides it. Write the choice to `plan.md`. `C` is a tie, so `C` at high/medium is malformed. `confidence: low` or malformed → show a comparison table for a manual pick and **hide the synthesizer's rationale**: columns Plan A / B / C (drop C if absent), rows Approach, Task count, Risk profile, Key trade-offs. Selection → write it; reject-all → single-plan flow. The operator may **combine** variants (one base plus a task or module from another); record what was added in `selection_rationale`.

**f. Hand off** to plan.md §3 with a selected variant, or §2 on reject-all.
