# Model Selection Guide

Centralized reference for model routing across lifecycle and pipeline agent dispatches. Each dispatch point in the lifecycle references embeds its own inline guidance — this file is the canonical source for those values.

## Principle

- **Sonnet** as the workhorse — 97-99% of Opus coding capability, faster, less over-engineering
- **Haiku** for speed and exploration — read-only traversal, trivial edits, parallel volume
- **Opus** for critical quality — deep reasoning, complex high-stakes implementations, final reviews

## Lifecycle Matrix (Task tool — criticality drives model)

| Task Type | low | medium | high | critical |
|---|---|---|---|---|
| Codebase exploration | haiku | haiku | sonnet | sonnet |
| Parallel research agents | — | — | — | sonnet |
| Competing plan agents | — | — | — | sonnet |
| Builder sub-task | sonnet | sonnet | opus | opus |
| Review sub-task | sonnet | sonnet | opus | opus |
| Orchestrator fix dispatch | sonnet | sonnet | sonnet | opus |

## Pipeline Matrix (Agent SDK — complexity x criticality)

| Complexity \ Criticality | low | medium | high | critical |
|---|---|---|---|---|
| trivial | haiku | haiku | sonnet | sonnet |
| simple | sonnet | sonnet | sonnet | sonnet |
| complex | sonnet | sonnet | opus | opus |

Pipeline review dispatch follows the lifecycle review row (sonnet for low/medium, opus for high/critical).

## Model Profiles

### Haiku ($1/$5 per MTok, fastest)

- Codebase exploration, read-only discovery
- Claude Code's built-in Explore agent uses Haiku
- Trivial implementation tasks (single-file, config tweaks)
- SWE-bench: 73.3% (90% of Sonnet 4.5's capability)

### Sonnet ($3/$15 per MTok, fast)

- Implementation, planning, reviews at standard criticality
- Delivers 97-99% of Opus coding capability (SWE-bench: 79.6% vs 80.8%)
- Better instruction following, less over-engineering than Opus
- Preferred for parallel agent dispatch (breadth over per-agent depth)

### Opus ($5/$25 per MTok, moderate)

- Critical implementations where quality failures have severe consequences
- High-stakes reviews catching subtle bugs (async, memory leaks, logic errors)
- Complex multi-file engineering at high/critical criticality
- Deep reasoning tasks (GPQA: 91.3% vs Sonnet's ~74%)
- 128K max output tokens

## Design Rationale

- **Parallel agents always sonnet**: Parallel research and competing plans (critical-only) benefit from breadth across multiple agents, not maximum depth per agent. The orchestrator synthesizes outputs, so individual quality need not be maximal.
- **Exploration always haiku (unless high/critical)**: Read-only pattern discovery is Haiku's sweet spot. At high/critical, upgrade to sonnet for more nuanced analysis since findings feed all downstream phases.
- **Complex + low/medium → sonnet (not opus)**: Sonnet 4.6 benchmarks show the gap with Opus is < 2% on coding tasks. Sonnet's faster latency and lower over-engineering tendency make it the better default. Reserve opus for when criticality demands maximum quality.
- **Reviews follow criticality, not complexity**: Review quality depends on how much the bugs matter, not how many files were changed. High/critical features warrant opus review regardless of implementation complexity.
