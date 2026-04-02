# Research: Consolidate /devils-advocate and /critical-review skills

## Codebase Analysis

**Primary files:**
- `skills/devils-advocate/SKILL.md` — 121 lines, zero programmatic call sites, user-invocable only
- `skills/critical-review/SKILL.md` — 61 lines, 5 programmatic call sites

**CR call sites (all 5):**
- `skills/lifecycle/SKILL.md` — spec phase, complex tier gate
- `skills/lifecycle/references/specify.md` — same spec gate, in the phase reference
- `skills/lifecycle/references/plan.md` — plan phase, complex tier gate
- `skills/discovery/references/research.md` — after research, **no tier gate** (unconditional)
- `skills/skill-creator/SKILL.md` — call-graph constraint list (hardcodes "critical-review" by name)

**DA call sites:** None. Deleting DA requires zero reference file updates. Renaming CR requires updating all 5 files above.

**Execution model distinction:**
| Dimension | /devils-advocate | /critical-review |
|---|---|---|
| Execution | Inline, same-context agent | Fresh, unanchored dispatched agent |
| Output shape | 4-element narrative (fixed) | 3-4 derived angles → synthesis |
| Post-output action | Stops — user decides | Apply/Dismiss/Ask loop rewrites artifact |
| Lifecycle integration | None | Auto-triggers in specify + plan phases (complex tier) |
| Trigger domain | "challenge this", "poke holes", "devil's advocate" | "pressure test", "adversarial review", "pre-commit challenge" |

**Inter-skill coupling:** `clarify-critic.md:60` explicitly says "Mirror the critical-review skill's framework exactly" for the Apply/Dismiss/Ask logic. This is prose-level coupling, not code reuse — CR framework changes will silently drift clarify-critic.md.

**Skills can invoke each other** via the Skill tool. `disable-model-invocation: true` must NOT be set on any skill invoked by another skill (enforced in skill-creator's call-graph constraint).

## Web Research

**Anchoring bias is the key structural differentiator.** LLM research confirms inline critique (same agent, same context) exhibits significant anchoring bias that chain-of-thought and reflection do not adequately mitigate. A fresh unanchored agent is the architecturally correct solution. This is CR's primary value proposition over DA.

**However, the "unanchored" benefit is partial.** CR Step 4 (Apply/Dismiss/Ask) runs in the orchestrator's main context — the same anchored context where the artifact was produced. The fresh agent reduces anchoring bias for critique generation only; the disposition pass reintroduces it. Additionally, passing the artifact verbatim to the fresh agent can prime it toward the artifact's own framing — content anchoring is distinct from context anchoring.

**Overlapping skill descriptions cause wrong tool selection.** This is documented as the #1 agent failure mode in MCP tool design research. DA and CR share near-synonymous trigger phrases ("stress test" vs. "pressure test") which creates routing ambiguity.

**Tool proliferation anti-pattern vs. Golden Hammer.** Having too many overlapping tools degrades routing accuracy. But over-consolidating into one heavy tool means lightweight critique tasks (DA use cases) get routed to the heavier CR machinery unnecessarily.

**Skill delegation pattern is recognized.** One skill invoking another is a documented agentic pattern (Microsoft Copilot Studio, Google ADK). This is mechanically viable in this codebase via the Skill tool.

**Multi-agent critique without tight output constraints amplifies errors 17x** (Google DeepMind research, 2025). CR's "derive 3-4 angles → synthesize → Apply/Dismiss/Ask" structure provides tight enough constraints to avoid this.

## Requirements & Constraints

**Source: `requirements/project.md`**

- **"Complexity must earn its place"** — complexity built for hypothetical future needs will be cut. The simpler solution is correct when in doubt.
- **"Maintainability through simplicity"** — complexity is managed by iteratively trimming skills and workflows. The system should remain navigable by Claude as it grows.
- **"The system exists to make shipping faster, not to be a project in itself"** — over-engineering skill distinctions is itself out of scope.
- No explicit constraints on skill composition (one skill invoking another) — neither mandated nor prohibited.
- Critique skills are implicit daytime-phase tools (surfacing gaps before overnight handoff), though no explicit constraint limits them to daytime.

## Tradeoffs & Alternatives

**A. Keep both as-is**
- Pros: No disruption; each skill has a distinct identity
- Cons: Doubles maintenance cost when critique philosophy evolves; description overlap causes routing confusion; CR's description explicitly calls itself "more thorough than /devils-advocate" which implies ranking rather than distinction

**B. Trim /devils-advocate (restructure, not just compress)**
- Target: ~70 lines from 121 by replacing verbose error-handling prose with a compact failure table and collapsing the two output examples to one tight inline example
- DA's structural problem: ~60 lines (50%) are error handling; ~40 lines (33%) are the actual critique instructions. Error handling outweighs the core value
- Pros: Sharpens DA's identity as lightweight inline critique; reduces token load; preserves the 4-element framework
- Cons: Substantive error handling is genuinely useful — careless trimming degrades agent behavior; the output examples serve as calibration for "specific enough"
- Note: Restructure (promote 4-element format to section headers, compact error table) rather than prose compression

**C. CR's dispatch prompt adopts DA's 4-element format**
- Pros: Structural consistency across both skills; Apply/Dismiss/Ask loop handles more predictable output shape
- Cons: Defeats the fresh agent's core value — it should derive its own angles; narrows CR to DA's fixed categories, losing "integration risk", "scope creep" etc.

**D. Consolidate into one skill**
- DA absorbed into CR: loses the lightweight inline use case
- CR absorbed into DA: Apply/Dismiss/Ask logic (~25 lines of policy) conflicts with DA's "stop after making the case" design; cramming it in bloats DA and conflates two different mental models
- Verdict: The inline vs. dispatch distinction is real and worth preserving

**E. CR invokes DA as a step in its process**
- Breaks CR's core design invariant: the whole point is a fresh unanchored agent. DA is inline, same-context. This eliminates the primary benefit of CR.
- Verdict: Not viable

**Recommended: B (restructure DA) + targeted trigger domain fix**
Restructure DA to ~70 lines (compact error table, one example, 4 elements as section headers). Separately assign non-overlapping trigger domains to resolve routing ambiguity. This is two independent changes with no coupling — do not bundle them with CR's dispatch format.

## Adversarial Review

**DA's 4-element format may not be reliably enforced.** The skill instructs the agent to write "a flowing narrative covering these four things" — but there is no structural enforcement. Claude models do not reliably self-enforce output schemas specified in prose, especially in long-context conversations. Promoting the 4 elements to section headers (structural enforcement) rather than a narrative suggestion would address this.

**CR's angles already map 1:1 to DA's four elements.** CR's example angles: "unexamined alternatives" = DA's alternatives; "fragile assumptions" = DA's fragile assumption; "real-world failure modes" = DA's strongest failure mode. The distinction is not in *what* gets surfaced — it's in how free the fresh agent is to *choose* which to include. This distinction is more cosmetic than structural.

**Discovery's CR call is unconditional — asymmetry with lifecycle calls.** Lifecycle gates CR on `tier = complex`. Discovery does not gate it at all. Every discovery run dispatches a fresh CR agent regardless of topic complexity. This asymmetry is unexplained and likely inadvertent — it creates overhead for simple discovery topics.

**clarify-critic.md's "mirror CR's framework" instruction is silent drift risk.** The Apply/Dismiss/Ask framework is 8 lines of policy. Delegating by reference means any CR framework update silently drifts clarify-critic.md. The framework should be inlined with a "based on critical-review" comment.

**Trigger phrase collision is the most immediately actionable problem.** DA lists "stress test this" as a trigger; CR lists "pressure test this." These are near-synonyms. The agent resolves ambiguity using the description field — but both descriptions also use "challenge," "adversarial," and "poke holes" (implied). Assigning non-overlapping domains is a standalone fix with zero risk.

## Open Questions

- **Should DA's 4-element format be promoted to section headers for structural enforcement?** Deferred to spec — this is a design decision about whether to make DA's output more rigidly structured. Upside: more reliable output; downside: loses the "flowing narrative" quality that distinguishes DA from a bulleted checklist.
- **Is the discovery CR call intentionally unconditional?** Deferred — checking `skills/discovery/references/research.md` confirms there is no tier gate. Whether to add one is a scope decision for a separate ticket (not this one, which is focused on DA/CR relationship).
