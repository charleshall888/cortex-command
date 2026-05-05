# Prompt 1 — Foundation

Run this first, in a fresh Claude Design project, after attaching the cortex-command repo URL.

---

I'm building an interactive landing page for cortex-command, an open-source AI workflow framework I built on top of Claude Code. I've attached three files from the repo as project context: `README.md` (project pitch, day/night thesis, install), `requirements/project.md` (vision, philosophy, audience), and `docs/agentic-layer.md` (lifecycle phase vocabulary, skills inventory, workflow diagrams). Read all three before generating. The rest of the repo (Python source, tests, backlog state, internal Claude Code docs) is intentionally not attached — it adds noise without adding signal. The page deploys to GitHub Pages and is the primary artifact. A static README hero will be screenshotted from the deployed page later — no separate extraction needed.

CORE CONCEPT. The page IS a spec document being filled in. As the viewer scrolls, sections of a spec lock in (Clarify, Research, Specify, Plan). Each lock activates an "agent online" indicator in a sidebar. Once the full spec is locked, a pipeline visualization activates below, showing autonomous agents executing against the spec the viewer just watched get earned.

The visible spec is for a fishing-minigame feature in a fictional pixel-art indie game called "NIGHTLINE" — a game about setting unattended fishing lines overnight and waking to your catch. The game's premise quietly mirrors cortex-command's thesis (set a tight spec, sleep, wake to PRs ready), making the demo content and the product argument the same argument. This is intentional — do not undermine it by treating the fishing spec as throwaway example content.

TAGLINE: A workflow framework where the spec is the work.
SUBCOPY: For Claude Code. Tight specs run interactively all day. When the spec earns it, you can hand off overnight too.
MANIFESTO (anchored below hero, two sentences): "Most AI tools optimize for speed. Cortex Command optimizes for the only thing that makes speed worth anything — a spec that knows what 'done' looks like."

AUDIENCE. Primary: Claude Code power users who'd actually install this. Secondary: engineering leaders and skeptical engineers triaging in 30-90 seconds. Tone: dry, lowercase microcopy, no marketing voice. Engineers should feel respected.

AESTHETIC: DIEGETIC DOCUMENT. References that matter most: Lucas Pope's Return of the Obra Dinn and Papers Please for diegetic UI / document-as-mechanic / ink-and-paper materiality. Bartosz Ciechanowski's essays (ciechanow.ski) for "the page IS the explanation." Val Town's homepage (val.town) for opinionated dev-tool voice. Are.na for editorial restraint. Avoid: Hades/Pyre, Stripe homepage (too SaaS), Linear (too sleek), generic-AI-startup.

VISUAL SYSTEM:
- Background: warm parchment off-white #f7f4ec primary, deep ink #0f1219 for night/overnight section
- Body type: high-contrast serif **Fraunces** (variable, freely available on Google Fonts) for headlines and spec body. **JetBrains Mono** for code/diffs/margin metadata. **Inter** for UI chrome only. All three must load from Google Fonts CDN — do not specify commercial fonts that won't resolve at deploy time.
- Schematic accent: blueprint blue #1e40af for diagram lines and locked-spec-section highlights
- Highlight: ochre #c2660a, used like a draftsman's highlighter, sparingly
- Texture: faint engineering-paper grid behind diagrams; subtle paper grain on warm sections
- Margin annotations: drafted-feeling pencil ticks, struck-through lines, dotted leader lines, small revision stamps ("R3", "as-built")

PAGE STRUCTURE.

1. Hero — fishing-minigame spec for "NIGHTLINE" open in viewport, mostly empty, page tagline overlaid in serif. Ambient ink cursor (small static vector glyph, no animation behaviors yet) idles in the spec margin.

2. Manifesto sentence — anchored below hero where eye lands.

2.5. Daytime use section — short, ~1/2 viewport. One sentence: "Most days you'll never run /overnight. The framework's daily value is interactive — /cortex-core:lifecycle, /cortex-core:refine, /cortex-core:critical-review." Plus a styled HTML/CSS terminal mockup (Claude Design renders this directly — NOT an external screenshot asset; no image file is supplied). The mockup shows ~6 lines of representative output from /cortex-core:lifecycle: the prompt, a phase header ("Phase: Specify"), one or two decision lines, and a "(awaiting input)" cursor. Use the JetBrains Mono palette and the warm parchment background; frame as a small terminal window with a subtle title bar reading "lifecycle · cortex-command". This section establishes that overnight is optional before the page commits to its overnight crescendo.

3. The diegetic spec — sections fill in as user scrolls: Clarify, Research, Specify, Plan. Content described below in SPEC CONTENT block.

4. Pipeline activation — once spec is locked, horizontal swimlane activates below. Framing copy: "If you've earned it, this is what handoff looks like." Discovery fans out, refine spawns rails per ticket, /overnight runs parallel rails, /morning-review converges. Mirrors the spec content's actual structure (NOT a generic 5-way fan-out).

5. Day → night transition mid-pipeline — page desaturates (CSS filter saturate 1→0.4, brightness 1→0.85 over 2-3s), deep blue overnight rail ignites, faint starfield fades in.

6. Dawn / morning-review — single gold rail converges. Page re-saturates over 2s. ACHIEVEMENT TOAST: "ACHIEVEMENT — First Light · Overnight run completed before you woke up."

7. Install — 3 commands in big monospace.

8. Footer — links to docs, GitHub, license, plus a one-line author note linking to author's pixel-art game work (this signal should be plain, not subtextual).

SPEC CONTENT (load-bearing — this is what the viewer actually reads).

Title shown in spec frontmatter: "Spec: Nightline · Fishing minigame · v0.3"

Each section abridged to ~60 words max. The viewer reads at their own scroll pace; the lock fires as a transition event, not as a reading deadline.

- CLARIFY (locks first, ~50 words):
  > "What does it feel like to set a nightline well? Player loop: choose tackle → cast at dusk → set depth → leave the line → return at dawn. Fish simulated overnight. Catch determined by depth, bait, weather, patience. Scope-in: a satisfying choice + a felt morning."

- RESEARCH (locks second, four bullets, ~45 words total — render as actual bullet list, not inline numbering):
  > - "Stardew Valley: tight skill window, instant feedback."
  > - "Sea of Thieves: fishing as social ritual."
  > - "Dredge: dread, reward, depth as risk axis."
  > - "Real-world nightline: hooks set at dusk, retrieved at dawn — a sleep-while-you-fish craft."

- SPECIFY (locks third, ~58 words):
  > "Tackle: 3 rod tiers, 6 lure types, 4 bait types. Depth: 1-5 fathoms. Weather modifies catch table per fathom. Overnight simulation: discrete tick at midnight resolves bites against a Markov model parameterized by depth/bait/weather. Morning UI: animated reveal of the line being pulled. Edge cases: empty, snagged, legendary."

- PLAN (locks fourth, ~58 words):
  > "Implementation: (a) tackle data model + UI, (b) cast/set screen, (c) overnight resolver, (d) dawn reveal animation, (e) catch encyclopedia. Acceptance: a player who sets a line and sleeps wakes to a result that feels earned. Risk: the resolver is the soul of the feature; mock it badly and the loop collapses."

JARGON GLOSSING. The page never explains cortex-command's vocabulary directly. Instead, when a cortex-specific term first appears in the diegetic spec or sidebar (Clarify, Research, Specify, Plan, /critical-review, /refine, /overnight), display a small margin gloss styled as a draftsman's footnote — italic JetBrains Mono, ochre underline, ~6 words max. Glosses are diegetic (they read as part of the document, not as marketing tooltips). Examples:
- next to "Clarify": "* the lifecycle's first phase: pin the unknowns"
- next to "/critical-review": "* an adversarial review by a fresh agent"
- next to "/overnight": "* the autonomous parallel-execution mode"

INK CURSOR (v1 SCOPE). Static placement only — small vector ink-cursor glyph idle in the spec's left margin. Behavioral choreography (phrase underlining, pencil ticks, self-correction) deferred to session 2 once spec content is locked.

SCAN-LAYER SIDEBAR. Persistent top-right panel, ~280px wide on desktop, collapses to a small badge on mobile. Contains in this order, no decoration:
1. Product line: "Cortex Command — workflow framework for Claude Code"
2. One-line value prop: "Tighter specs. Faster ships. Optional autonomy."
3. Tiny status row (monospace, dim): "v0.4 · MIT · github.com/charleshall888/cortex-command"
4. Single CTA: "Install (3 commands) ↓" — anchors to install section.

Background: parchment matching page. Thin blueprint-blue rule-line on its left edge so it reads as marginal annotation, not marketing chrome. Sticky; absorbs into the diegetic conceit as the document's running header.

ACHIEVEMENT TOAST (one in v1, second added in session 2).
- v1 toast: "ACHIEVEMENT — Spec Earned" — slides in when the diegetic spec finishes locking, before any pipeline activates. Style: Steam-achievement structure, blueprint palette, lowercase subtitle.

Build a first version of the full page now. Don't polish — just get the structure, the diegetic spec content, the scan-layer sidebar, and the section-lock state machine rendering. We'll deep-dive on the pipeline activation, day/night transition, and second toast in session 2.

ACCEPTANCE CHECK FOR v1. Before running Prompt 2, verify both:
1. Spec sections visibly transition between unlocked and locked states as the user scrolls — observable from the spec body itself, not just the sidebar.
2. Sidebar agent indicators activate paired to specific spec sections (not random, not all-at-once).

If either fails, you've spent a session learning the diegetic concept doesn't render reliably in Claude Design. Accept the session loss. Do not iterate session 1 a third time hoping the third try lands. Decide outside the tool: retry next week with a simplified concept (e.g., a non-state-machine version where sections fade in on scroll without sidebar coupling), or pause the project and reassess. There is no pre-built fallback prompt — this is the trade you accepted by going with the ambitious version of the design.
