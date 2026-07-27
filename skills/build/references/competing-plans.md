# Competing Plans (Critical Only)

Read only on the `critical` planning arm, via plan.md §1. Dispatch 2–3 independent plan agents — as many as there are meaningfully distinct approaches the spec and research support.

**a. Shared context** — inject `{spec_path}` and `{research_path}` as absolute paths. Each agent reads the files itself; never share one agent's draft with another.

**b. Dispatch** each as a parallel sub-task with the template below **verbatim**, choosing each agent's model yourself.

Each agent reads the spec and research itself and designs an **architecturally distinct** approach — not merely a different ordering — populating the Overview's `**Architectural Pattern**` with exactly one of {event-driven, pipeline, layered, shared-state, plug-in} plus a one-sentence statement of how this variant differs from the others. Output is a complete plan in plan.md's standard format, targeting 5–15 min and 1–5 files per task, under the same code budget (structural context only, no function bodies or copy-paste code, no prose-only or self-sealing Verification).


**c. Collect** — wait for all agents, continuing past any crash, timeout, or garbage output. Exactly 1 succeeds → use it as the sole variant, skip to plan.md §3. All fail → fall back to plan.md's single-plan flow.

**d. Synthesize** — one fresh read-only sub-agent compares the variants and picks one with structured rationale. This is the judgment step; weigh the model accordingly. System prompt: load `cortex_command/overnight/prompts/plan-synthesizer.md` via `importlib.resources` — don't paraphrase or inline it. User prompt: the variant paths (`plan-variant-A.md`, `-B.md`, optionally `-C.md`) plus the swap-and-require-agreement instruction, directing a JSON envelope.

**e. Extract** — split on the LAST `<!--findings-json-->` delimiter, `json.loads` the tail, and validate `schema_version: 2` (int), `per_criterion` (object), `verdict ∈ {A,B,C}` (string), `confidence ∈ {high,medium,low}` (string), `rationale` (string). Any failure → treat as `confidence: "low"`.

**f. Route:**

- **`verdict ∈ {A,B,C}` AND `confidence ∈ {high,medium}`** — present the chosen variant with its rationale; default rubber-stamp (Enter), override by typing a different label. Write it to `plan.md`. Verdict `C` (tie) at high/medium is logically impossible — treat as malformed and fall through.
- **`confidence: low` OR malformed** — show the comparison table for a manual pick, **hiding the synthesizer rationale** so the operator judges independently: columns Plan A / Plan B / Plan C (drop C if not dispatched), rows Approach, Task count, Risk profile, Key trade-offs. On selection write that variant to `plan.md`; on reject-all fall back to the single-plan flow. The operator may also **combine** variants (one base plus a grafted task or module) — record the graft in `selection_rationale`.

**g. Hand off** to plan.md §3 if a variant was selected, or plan.md §2 if the operator rejected all.
