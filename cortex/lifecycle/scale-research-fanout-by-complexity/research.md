# Research: Scale research fan-out by tier/criticality

**Clarified intent:** Make the parallel research fan-out (number of researcher agents) scale up — roughly doubling for complex and/or critical work, peaking at the complex+critical corner — across all three research entry points the user named: `/cortex-core:research` (which `/refine` and `/lifecycle` delegate to) and `/cortex-core:discovery` (which has its own separate research path).

**Tier/criticality:** complex / high.

## Codebase Analysis

The agent count is **prose-only, model-applied** — no Python or shell computes it. Single source of truth:

- `skills/research/SKILL.md:47-57` — the count model:
  ```
  tier_count:        simple→3, complex→4
  criticality_count: low→3, medium→4, high→5, critical→5
  agent_count = max(tier_count, criticality_count)
  ```
  Realizable matrix: simple→{3,4,5,5}, complex→{4,4,5,5}. **The corner is flattened**: complex+critical = `max(4,5)` = 5 — the same as simple+critical and complex+high.
- Agent roster `skills/research/SKILL.md:75-191`: Agent 1 Codebase, Agent 2 Web, Agent 3 Requirements & Constraints (baseline 3); Agent 4 Tradeoffs (added at ≥4); Agent 5 Adversarial (added at ≥5, dispatched in a second wave after 1–4 summarized).
- Output conditional sections `skills/research/SKILL.md:230-237` (omit Tradeoffs if <4, Adversarial if <5).
- `skills/refine/SKILL.md:108-114` — `/refine` delegates to `/cortex-core:research` passing `tier`/`criticality`; **no independent count logic**. `/lifecycle` wraps `/refine`.
- `skills/discovery/references/research.md` — discovery has its **own** research protocol: a sequential, single-orchestrator deep dive across §2–§5, **not** a parallel agent fan-out, and `skills/discovery/SKILL.md` frontmatter exposes only `topic`/`phase` — **no tier/criticality input**. So discovery is a genuinely separate code path; changing the `/research` matrix does not touch it.

**Stale "single vs parallel" binary framing** (predates the current graduated formula — already wrong today, independent of this change):
- `skills/lifecycle/references/criticality-matrix.md:17-20` ("Single research" for low/med/high; "Parallel research" for critical)
- `docs/agentic-layer.md:116-119` (same binary table)
- `skills/lifecycle/assets/model-selection.md:16,58` (implies only critical gets parallel research)

**"3–5" range claims** that move if the ceiling changes: `skills/research/SKILL.md:6` (frontmatter), `docs/skills-reference.md:47`.

**Test coverage:** none. Grep of `tests/` for `agent_count`/`tier_count`/`criticality_count`/`researcher`/`research_dispatch` returns no count-matrix assertion. The only related edge check is `tests/test_skill_callgraph.py:32` (asserts refine contains the delegate-to-research string).

**Conventions:** edit `skills/` only — `plugins/cortex-core/` is an auto-regenerated mirror (drift test `tests/test_dual_source_reference_parity.py`; pre-commit hook regenerates). SKILL.md 500-line cap (`tests/test_skill_size_budget.py`); `skills/research/SKILL.md` is at 259 — a table + one subdivision rule fits easily; fully-specified new agent role-blocks (~15-20 lines each) would not.

## Web Research

- **Anthropic's own multi-agent research system**: 3–5 subagents by default; explicitly names **"10+ subagents" for complex research**; ~15× chat token cost; token usage explains ~80% of performance variance. This is the closest prior art and endorses scaling above 5 for hard work. [anthropic.com/engineering/multi-agent-research-system]
- **Width > depth** for information-seeking; multiple papers (WideSeek-R1, "More Agents Is All You Need") show harder tasks benefit proportionally more from more agents — **but only if the agents are genuinely diverse**.
- **Redundant same-angle agents plateau hard** (~8–15 samples) and can *degrade* past ~10–15 in untrained base models (noise accumulation) [arxiv 2511.00751; WideSeek-R1].
- **Centralized synthesis is the safety layer**: flat independent parallel amplifies errors ~17×; a centralized orchestrator pass cuts that to ~4× — the synthesis step (already present here) is what justifies fan-out.
- **Bottom line:** 5→10 helps *only if* the extra agents cover orthogonal ground; redundant clones buy ~1–2% for ~2× cost. For a single-codebase feature, ~5–7 truly distinct angles exist — so beyond that, value comes from **subdividing an angle by scope** (e.g., two codebase agents on different subsystems, two adversarial agents on opposing stances), which is parallelized breadth, *not* redundancy.

## Requirements & Constraints

- **Philosophy of Work** (`cortex/requirements/project.md`): "Complexity must earn its place… when in doubt simpler wins." The `max()`→matrix change is justified (max() structurally can't peak the corner), but the *minimum* form that achieves it is preferred over a redesign.
- **Prescribe What/Why not How** + **MUST-escalation** (CLAUDE.md): the matrix should state cell values + intent, not narrate an algorithm; new dispatch phrasing stays soft-routed (no new MUST without an evidence artifact).
- **No interactive budget circuit-breaker**: research sub-agents run on the parent session, *not* governed by the overnight pipeline's 1–3 concurrency limit and with **no per-dispatch cost cap**. Doubling agents doubles spend with no automatic guard — the count cap *is* the cost guard, so it must be chosen deliberately.
- **Precedent**: a 2D tier×criticality matrix already exists for post-merge review gating — a literal table is an accepted shape in this repo.
- **Size budget**: the MVP (table + one subdivision sentence ≈ 15 lines) needs no extraction; a specialist-roster redesign (~75–100 lines) would approach the 500-line cap.

## Tradeoffs & Alternatives

**Count model** — three options: (A) raise the `max()` numbers, (B) additive `base+tier_bonus+criticality_bonus`, (C) explicit 2D lookup table. (A) is rejected: raising one axis to reach ~8–10 distorts single-axis cases and *still* can't peak the corner. (B) and (C) both express stacking; the adversarial review's decisive point is that an additive formula whose constants are hand-tuned to hit the corner is "a lookup table wearing a formula's clothes" — **(C) the explicit 8-cell table is more legible and honest** and each cell is independently tunable. **Recommend C.**

**What agents beyond the 5 angles do** — breadth (new orthogonal angles) is exhausted by ~7; topic-conditional "specialist" routing is a brittle new heuristic that must classify every topic correctly (rejected as over-engineering); redundant clones are wasteful. **Recommend scope-subdivision**: agents 6+ subdivide the **codebase** angle by subsystem and the **adversarial** angle by stance — one rule, no new role-blocks, no topic-classifier.

**Discovery** — leaving it unchanged contradicts the user's explicit ask; importing tier/criticality is misaligned (discovery has no such input by design). **Recommend scaling discovery on the breadth signal it already has** ("broad or complex topics") — raise its own research-question/investigation count for broad/complex topics, without tier/criticality.

**Cap** — the user chose 10 *after* seeing the queueing tradeoff. The synthesis's "concurrency ceiling 4–6" argument is weak (sourced from third-party API-tier blog posts, not Claude Code `Agent`-tool in-session behavior) and largely irrelevant for the overnight path (latency-insensitive; cost is the only real constraint). So the honest framing is not "8 is technically right" but: **beyond ~7 angles, agents 8–10 are scope-subdivisions, not new kinds of investigation** — keep 10 with that understanding, or drop to ~8. This is a user decision, surfaced at spec approval.

## Adversarial Review

- The evidence-based synthesis **silently overrode two explicit user decisions** (cap 10→8; scale discovery→leave unchanged). Both must be re-surfaced, not downgraded.
- The cap-8 justification rests on a **concurrency-ceiling claim from third-party blogs**, conflating API-session limits with in-session `Agent` fan-out. For overnight (the dominant path) wall-clock is nearly irrelevant; only token cost matters.
- The additive formula + topic-conditional specialist roster + three-wave dispatch is a **redesign answering a bigger question than asked** — fails "complexity earns its place." The minimum-viable change (table + subdivision rule) satisfies the literal ask, stays legible, and avoids the size cliff.
- Genuinely correct regardless of preference: past the count of distinct angles, more agents is wasteful — so a literal cap-10 *will* force scope-subdivision at the corner. That's fine if named explicitly.
- Don't-miss items: the stale docs are **already wrong today**; there is **no regression test**; doubling agents has **no cost circuit-breaker**.

## Open Questions

1. **Cap at the complex+critical corner: 10 (your stated choice) vs ~8?** → **Deferred: surfaced to you at Spec approval (§4 value gate).** Honoring 10 means agents 8–10 are scope-subdivisions of the codebase/adversarial angles (only ~5–7 distinct angles exist); 8 stops near the natural angle ceiling. Default carried into the spec: **honor 10** with subdivision, since you chose it knowing the queueing tradeoff.
2. **Exact per-cell counts of the 2D table.** → **Resolved (proposal, finalized at Spec §4):** corner = the chosen cap; simple+low stays 3; both axes monotonically increase toward the corner so complex+critical is strictly the peak. Concrete grid drafted in Spec.
3. **What agents 6+ do.** → **Resolved:** scope-subdivision (codebase by subsystem, adversarial by stance) — not specialist routing, not redundant clones.
4. **Discovery scaling mechanism.** → **Resolved:** scale on discovery's existing breadth signal; do not import tier/criticality.
5. **Stale-doc reconciliation (criticality-matrix.md, agentic-layer.md, model-selection.md) + "3–5" range strings.** → **Resolved: in scope** — they are already inaccurate; this change fixes them so the docs stop lying.
6. **Regression test for the count table.** → **Resolved: add one** (none exists today).
