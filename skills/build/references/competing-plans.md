# Competing Plans (Critical Only)

Read only on the `critical` planning arm from plan.md §1. Dispatch 2–3 independent plan agents — as many as there are meaningfully distinct approaches the spec and research support.

**a. Dispatch** each as a parallel sub-task (model your call) with `{spec_path}` and `{research_path}` as absolute paths. Each agent reads the files itself and never sees another's draft. Each designs an **architecturally distinct** approach — not a re-ordering — setting the Overview's `**Architectural Pattern**` to exactly one of {event-driven, pipeline, layered, shared-state, plug-in} plus one sentence on how it differs. Output is a complete plan in plan.md's format under its sizing and code-budget rules.

**b. Collect** — wait for all, continuing past any crash, timeout, or garbage. Exactly 1 succeeds → sole variant, skip to plan.md §3. All fail → plan.md's single-plan flow.

**c. Synthesize** — one fresh read-only sub-agent compares the variants and picks one with structured rationale (the judgment step; weigh the model accordingly). System prompt: load `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources` — never paraphrase it. User prompt: the variant paths (`plan-variant-A.md`, `-B.md`, optionally `-C.md`) plus the swap-and-require-agreement instruction, directing a JSON envelope.

**d. Extract** — split on the LAST `<!--findings-json-->` delimiter, `json.loads` the tail, validate `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {A,B,C}`, `confidence ∈ {high,medium,low}`, `rationale` (string). Any failure → `confidence: "low"`.

**e. Route** — `verdict ∈ {A,B,C}` AND `confidence ∈ {high,medium}` → present the chosen variant with rationale; default rubber-stamp (Enter), override by label; write it to `plan.md` (verdict `C` at high/medium is impossible — treat as malformed). `confidence: low` or malformed → comparison table for a manual pick, **hiding the synthesizer rationale**: columns Plan A / B / C (drop C if absent), rows Approach, Task count, Risk profile, Key trade-offs. Selection → write it; reject-all → single-plan flow. The operator may **combine** variants (one base plus a grafted task or module) — record the graft in `selection_rationale`.

**f. Hand off** to plan.md §3 with a selected variant, or §2 on reject-all.
