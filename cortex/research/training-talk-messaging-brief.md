# Messaging brief: team talk on working well with AI coding agents

> Interviewed: 2026-07-13 · Feeds the v1 workshop deck (`cortex/requirements/training.md`)

## Occasion

- First delivery: the user's engineering team — mostly Cursor users today, team shift toward Claude Code anticipated. The talk quietly doubles as onboarding for that shift.
- One-hour screen-share slot: ~35–40 min of material, interruptions welcome, discussion absorbs the rest.
- Screen-share design consequence: bold shapes, generous text sizes — video compression eats fine detail.
- Future audiences (semi-technical 1:1s: law/science) are noted, not designed for; keep examples non-gamer-legible where free.

## Spine

**"Models get the headlines; attention is the game."** Every practice is a way to keep your agent at Tuesday-9AM instead of Friday-4PM — the recurring refrain. Cold open: the same request handled crisply by a fresh agent and botched by one six hours into a session; reveal: same model, same harness.

Explicitly NOT a harness pitch. Practices first; the user's tooling appears only as "here's how I solved this" existence proofs; one quiet closing slide links the cortex-command landing page ("want to see how deep this goes?"). No demo, no feature tour, no adoption ask.

Rhetorical pattern throughout: **concede the steelman, then land the narrower hard claim** — "caching helps, AND…", "models matter, AND…", "compaction works, AND…".

## Content decisions

### In

- **Context management.** The stateless-resend mechanic (every turn reprocesses the whole session; caching discounts but doesn't erase, and dies on prefix changes). The 50/30 rule **owned as his numbers**: "mine, from a year of daily use — under 30% is goldilocks, at 50% plan your exit. Your numbers may differ; that you *have* numbers is the point."
- **Compaction is an airbag, not the brakes.** Lossy, no guarantee it keeps what you cared about; if it fires you should have split the work or persisted state. Vendor steelman conceded first (newer models genuinely handle it better), then: "handles it better" ≠ "best output per token."
- **Decomposition** taught as generic verbs — extract (first miles of the journey) → explore → decompose → execute, with each ticket carrying the epic badge (parent context). Slash-command names (/requirements, /discovery, /lifecycle) appear once, spoken, as "my shop runs this as three commands." Deliberate session break: refine to ~40%, quit, fresh agent implements the spec.
- **Subagent fan-out** for creative problems — "kick off a few agents from creative angles"; fresh minds beat one polluted mind. Real example: this very talk was designed by fanning out ideation agents (editor, narrator, visual designer, fact-checker, audience critic) — self-demonstrating.
- **Fork + rewind.** Rewind is the designated "cheapest win" — zero setup, immediate payoff. Don't converse forward from a polluted state; scrub back, carry the lesson not the tokens.
- **Adversarial review, including its failure modes.** A review agent never says "looks good" — it was asked for findings, so it manufactures findings. The skill is the synthesis step allowed to say "three of these five are noise." Honest beat kept verbatim: "sometimes I notice it put me down the wrong path, but more often than not it makes things better."
- **Models vs harnesses**, framed for the transition: "the harness is a variable you're currently ignoring." Ceiling vs yield (model sets the ceiling; harness determines how much you get). Behaviors shown, never ranked — split-screen mock: same ambiguous prompt, one harness asks a clarifying question, one infers and barrels forward. "Run the twenty-minute A/B yourself."
- **Skills discipline.** Never let the agent own authorship of skills/agent files — open-ended + unverifiable is the worst task shape for an LLM, and models ratchet instruction length. War story (real, first person): building his harness with Claude required massive trimming; "if I could go back, I'd hand-craft the simple skills and have Claude build the CLI around them." Team hygiene: incubate locally, generic skills go in a plugin repo not the project, project-specific beats generic, progressive disclosure in one line. Pocock name-check for tiny skill files.
- **Structure beats prose.** When you need an agent to reliably do X, a hook/gate/lint that forces it beats begging in instructions.
- **Verification shapes delegation.** LLMs excel at closed-ended verifiable problems; the expert move is engineering tasks into that shape (agent-verifiable acceptance criteria). This is also the prepared answer to "didn't you build your harness with Claude?" — yes, by making skill-writing verifiable (size budgets, ratchets, lint gates).
- **The by-hand list** (negative space): reviewing work, knowing what a good design/UX is, writing skills.

### Out

- Overnight autonomy (discussion-bait only if asked).
- Model-selection economics (audience already understands).
- All beginner lessons (what-is-a-subagent banned).
- Pricing/window numbers on slides — spoken only, volatile. No ">200k premium" claim for Claude (inverted since Opus 4.7; Gemini still tiers). Durable line: "pricing shuffles quarterly; the constant is you resend the whole session every turn."
- Progressive disclosure beyond one line (vendor-documented ground).
- Brand-verdict framing ("X is better") — personalities, not rankings.

## Example system

All staged demos live in **Nightline** (the overnight fishing game from the cortex-command landing page), riding its existing canon (catch table, dusk-to-dawn resolver, rods/lures/fathoms). **Screen fictional, scars real**: staged visuals in Nightline, true first-person stories narrated over them. The confirmed real scars: the harness-trimming retrospective; the adversarial-review honest beat; rewind spoken generically if no specific story surfaces.

- **Running epic — the Catch Log**: "every fish you catch gets an entry you can flip through at dawn." Tickets: record events / entry format / flip-through UI / empty state. Epic badge: *the log is a keepsake, not analytics* — the schema ticket is only correct knowing that. Vague-prompt beat: "make the log better" → agent bolts on filters and stat charts, violating the keepsake intent (the drift reteaches the badge). Fan-out beat: "three creative angles on the log page" → scrapbook / stats table / story journal; synthesis picks scrapbook *because of the epic intent*.
- **Adversarial-review vignette — throw small fish back**: auto-release under the size limit. Edge cases: exactly-at-limit; rare-but-small (epic intent: never punish a rare catch). One rigorous-sounding finding (frame-accurate input-latency compensation) binned by the synthesizer — cozy single-player doesn't need it.
- **Rewind vignette — overnight activation**: fishing should activate at night. First direction: server-driven time so players can't cheat — exploration sprawls into accounts, sync, infra. The turn: "this is a single-player fishing game; if people want to cheat, let them." Rewind to the fork; device-clock branch. Bonus lesson: know who you're defending against (echoes the review-overcorrection beat without repeating it).

## Stage lines bank

- "Past 50% context, your agent is you at 4PM on a Friday after a day of putting out fires."
- "Compaction is an airbag, not the brakes."
- "The first few miles decide where you land." (extraction)
- "The model sets the ceiling; the harness determines how much of it you get."
- "Never let the agent write its own job description."
- "A bad idea isn't history, it's contamination — rewind."
- "You asked it for findings, so it manufactures findings. Synthesize; don't obey."
- "If I could go back: hand-craft the simple skills, let Claude build the CLI around them."
- "This is a single-player fishing game. If people want to cheat, let them."
- Closer: "Everyone rents the same models. The habits are what you own. Send your agents home before Friday afternoon."
