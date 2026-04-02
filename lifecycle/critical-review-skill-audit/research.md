# Research: critical-review-skill-audit

## Codebase Analysis

### Current skill structure
`skills/critical-review/SKILL.md` (61 lines) dispatches exactly one general-purpose agent. No worktree isolation. The reviewer receives the artifact content and a fixed adversarial prompt instructing it to derive 3–4 challenge angles from the artifact content, work through each, synthesize, and end with "These are the strongest objections. Proceed as you see fit." The orchestrator handles Apply/Dismiss/Ask classification after the agent returns.

### Multi-agent dispatch patterns in this repo

Several existing skills use parallel/sequential agent dispatch:

- **`skills/lifecycle/references/research.md` §1a** (parallel research, critical-only): orchestrator derives 2–3 angles, dispatches them as parallel Task sub-tasks, each returns structured findings, orchestrator synthesizes. Each agent gets: feature description, assigned angle, output format template. No agent sees another's output.
- **`skills/research/SKILL.md`**: 3–5 agents by tier/criticality matrix. Roles: Codebase, Web, Requirements & Constraints, Tradeoffs & Alternatives, Adversarial. First four run in parallel; Agent 5 (Adversarial) runs after, receiving summarized prior findings.
- **`skills/lifecycle/references/plan.md` §1b** (competing plans, critical-only): 2–3 independent plan agents each produce a distinct approach, orchestrator presents comparison table, user selects.
- **`skills/pr-review/references/protocol.md`**: Haiku triage → four parallel Sonnet reviewers (CLAUDE.md compliance, correctness/security, test coverage, architecture/design) → Opus synthesis. Most complex pipeline in the repo.
- **`skills/lifecycle/references/clarify-critic.md`**: single fresh agent mirroring critical-review's exact framework. Explicitly says "Mirror the critical-review skill's framework exactly."

**Pattern**: parallel agents work best when roles are orthogonal (each covers a distinct dimension with no overlap), when each receives the same artifact but is assigned a specific lens, and when synthesis is done by the orchestrator (not by having agents read each other's work).

### Callsites where critical-review is actually executed

| Callsite | Artifact | Gate condition |
|----------|----------|---------------|
| `skills/lifecycle/references/specify.md:144` | `lifecycle/{feature}/spec.md` | Complex tier |
| `skills/lifecycle/references/plan.md:232` | `lifecycle/{feature}/plan.md` | Complex tier |
| `skills/discovery/references/research.md:127` | `research/{topic}/research.md` | Unconditional |

The `lifecycle/SKILL.md:250` reference is a description of the same gate as `specify.md:144`, not a separate callsite.

### Context-awareness in the current codebase

**None exists in behavior.** `lifecycle.config.md` has a `type` field (`web-app | cli-tool | library | game | other`) that is commented out by default. No skill reads this field to adapt behavior. Requirements files (`requirements/project.md`, area docs) are loaded as content injection at several points in lifecycle and research flows, but this is static context — it does not change the skill's protocol or which agents are dispatched.

### Reviewer prompt analysis

The current prompt tells the reviewer: "Derive 3–4 distinct challenge angles from its content. Pick the angles most likely to reveal real problems **for this specific artifact**." The example list is: architectural risk, unexamined alternatives, fragile assumptions, integration risk, scope creep, real-world failure modes.

The angles are stated as examples, not a fixed menu. The derivation is artifact-driven — the reviewer reads the artifact and infers angles from the text's salient terms. For a skill orchestration spec that uses terms like "agent isolation," "event log integrity," and "prompt injection," those concepts become salient and the reviewer will produce sharp, on-point objections. For a mobile game touch input spec, the same mechanism will fire on whatever terms dominate the artifact's text — but if the artifact doesn't mention "60fps main thread constraint" or "Android haptic latency," the reviewer can't surface what's not there.

**The limitation**: The prompt gives the reviewer no domain scaffolding. It has no mechanism to recognize project type (game, mobile, process repo) and no instruction to apply domain-specific knowledge or weight certain failure modes accordingly. For familiar domains (agentic workflow tooling), the artifact content is rich enough that angle derivation works well. For unfamiliar or specialized domains, the reviewer defaults to generic software engineering angles that may miss the most important failure modes.

### Artifact self-describing quality

- **spec.md**: Reasonably self-describing via Problem Statement and Technical Constraints. But spec content reflects what questions were asked during the interview — domain-specific gaps in the spec won't be visible to the reviewer.
- **plan.md**: Partial. File paths and task descriptions carry domain signal, but the overview is only 1–2 sentences.
- **discovery/research.md**: Most self-describing — includes Codebase Analysis, Web Research, Domain & Prior Art Analysis, Feasibility Assessment. Significant domain signal available.

No artifact carries machine-readable project type metadata. `lifecycle.config.md` `type` field exists but is not passed to the reviewer.

## Open Questions

- Should critical-review add multiple specialized reviewer agents (each assigned a domain-specific lens) or improve the single-agent prompt with domain scaffolding (inject project type, domain constraints, suggest domain-specific angle classes)?
- What is the right mechanism for domain detection — read `lifecycle.config.md` `type` field, read `requirements/project.md`, or rely on content inference?
- For discovery research (unconditional gate), does the richer artifact content make multi-agent overkill, or is it actually the case that needs it most?
- The `type` field in `lifecycle.config.md` is defined but unused by any skill. Should critical-review be the first skill to consume it, or should project type detection go in a different layer?
