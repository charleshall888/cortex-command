# Ideation digest: training program research (2026-07-13)

> Condensed record of the multi-agent ideation and critique rounds behind the v1 deck. The v1 *decisions* live in `training-talk-messaging-brief.md` + `training-talk-deck-outline.md`; this file keeps the research that wave 2 and future audiences will need, so nothing load-bearing exists only in a chat transcript.

## The skill ladder (curriculum spine, all future material)

R0 **Chatbot user** (copy-paste courier) → R1 **Autocomplete user** (faster typist) → R2 **Pair programmer** (babysits every diff, one rotting chat) → R3 **Delegator** (tickets with done-criteria, reads plans, fixes the input not the output) → R4 **Context engineer** (fresh session per task, every correction encoded durably, agent self-verifies) → R5 **Systems builder** (parallel agents, structural gates, work runs unwatched).

Five unlocks (one per transition): **give it eyes → let go of the keyboard → write the ticket, not the wish → never say it twice → make it check itself.** Audiences differ in dwell time, not story: non-technical R0–R3, engineers R2–R5.

Load-bearing metaphor for less-technical audiences (unused in v1, gold for the law/science 1:1s): **the brilliant, amnesiac new hire** — infinitely capable, remembers nothing between sessions, knows only what's written down; CLAUDE.md/fresh-session discipline falls out of taking it seriously.

Per-tier misconceptions to break: non-technical — "it's a better Google," "one long chat that knows everything"; engineers — fixes the output instead of the input, "it should know," never reads the plan, session rot as long-term memory; advanced — expertise = prompt cleverness (it's environment design), automates before verifying, obeys review findings.

## Audience architecture (for reusing material across tiers)

One spine, three altitudes: same demo, tier-specific *debrief* depth — differentiate by commentary, not content. Big mixed rooms get the shared-altitude keynote (motivation + vocabulary, not skill transfer). Vocabulary runway even for engineers: the stateless-resend mechanic, compaction internals, fork-vs-subagent, rewind's existence. Non-technical framing that works: delegation/verification judgment, NOT prompt syntax (their real gap is evaluating output, not phrasing).

## Wave-2 format designs

- **The Cockpit** (engine seed: `docs/training/lib/filmstrip.js` + `terminal.js`): a simulated session the learner flies — pauses at branch points, pick a prompt (or type; fuzzy-match to nearest branch), watch the consequence unfold (vague prompt burns visible time/tokens), then **rewind and try the expert prompt** — felt consequence, safely repeatable. Scenarios as data packs on one engine. Variants that ride the same engine: **swarm cockpit** (big room votes branches by QR poll; deliberately let the room crash once, then redeem), **delegation-ladder diagnostic** (10–12 branch choices measuring trust calibration; ends with a *profile*, not a score — "you micromanage: 3 hours slower" — and routes to matching material).
- **Self-serve guide** (send-a-link register): separate scrollytelling page, freshly written narration over the same component library — narration is real writing, not promoted speaker notes. Scroll-triggered animations that settle to meaningful stills; never loop while reading.
- **Retention kit**: one-page delegation checklist (success criterion? context needed? how verified?) + copy-paste prompt patterns per tier; 7-day challenge ladder (day 1 "have it explain a file" → day 7 "delegate a small feature with tests"). Learning-design finding: the leave-behind carries ~a third of a workshop's value — revisit after the first real workshop.

## Prior-art stealables (with sources)

- Anthropic's docs embed an interactive **context-window scrubber** (code.claude.com/docs/en/context-window) — the genre is vendor-validated; open ground is every mechanic they haven't animated (loop, permissions, delegation, verification).
- Before/after prompt tables (code.claude.com/docs/en/best-practices) — clickable "play the bad run / good run" upgrade.
- Causally-linked draggable figures (ciechanow.ski) — drag context-fullness, watch output quality degrade.
- Nicky Case (blog.ncase.me/explorable-explanations): teach one mechanic in isolation before combining; **gating advanced content improves retention** vs. dumping everything; end explorables in a goal-free sandbox for expert audiences.
- Anthropic 4D fluency frame (Delegation / Description / Discernment / Diligence — aifluencyframework.org) — ready-made vocabulary, maps to all tiers.
- Champions cadence for org rollout (resources.github.com/enterprise/activating-internal-ai-champions): adoption jumped when champions ran live demos instead of pointing at docs — the self-serve link should be presentable BY a champion, not just readable.
- METR finding (experienced devs 19% slower on familiar code, while feeling faster): own it, explain the mechanism, never dodge — it's the credibility key for skeptical seniors.
- 50/30 grounding: direction is supported (lost-in-the-middle, RULER-class benchmarks, context-rot studies — effective < advertised context); the numbers are owned practitioner calibration, presented as such.

## Standing craft rules (apply to all future training artifacts)

- Concede-then-land on every contestable claim ("caching helps, AND…").
- Animate processes, never syntax/config/prose-quality; every animation settles to a still.
- One metaphor world max; no cameo metaphors.
- Mock-terminal content technically real (real prompt shapes, real diff hunks) even though staged — and disclose the staging as a strength.
- Tooling exposure budget: patterns unnamed, commands spoken once, brand only at the closer.
