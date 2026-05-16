# Cortex Command landing page · Claude Design prompts

Prompts for building the cortex-command marketing landing page in [Anthropic's Claude Design](https://claude.ai/design). Two prompts, run sequentially in a single Claude Design project.

## What this delivers

A single interactive landing page deployed to GitHub Pages. The page is the primary artifact — all other materials (README hero image, future slide decks if needed) are screenshotted or extracted from the deployed page later.

## Stable context (does not duplicate prompt content)

The prompts are the source of truth for tagline, manifesto, copy, fallback rules, toast names, and visual system. This README captures only the editorial decisions that don't change as you iterate.

- **Concept**: diegetic spec document. The page IS a spec being filled in as the viewer scrolls.
- **Visible spec content**: a fishing-minigame feature spec for a fictional pixel-art game called **Nightline** — a game about setting unattended fishing lines overnight and waking to your catch. The game's premise quietly mirrors cortex-command's thesis.
- **Aesthetic frame**: technical-blueprint substrate (Stripe / Linear / Increment) layered with diegetic-document craft (Lucas Pope's Obra Dinn / Papers Please).
- **Acceptance check**: defined in `prompt-1-foundation.md` (search "ACCEPTANCE CHECK FOR v1"). There is no pre-built fallback prompt — if v1 fails the check, accept the session loss and reassess outside the tool.

## How to run

1. Open Claude Design (claude.ai/design) and create a new project.
2. Upload three files from this repo as project context: `README.md` (top-level), `cortex/requirements/project.md`, and `docs/agentic-layer.md`. Do **not** attach the full repo — Python source, plugin internals, backlog state, and internal Claude Code docs add noise without adding signal, and risk Claude Design treating implementation detail as design intent.
3. Upload `prompt-1-foundation.md` as the opening prompt. Refine v1 via inline comments, sliders, and direct text edits — *not* chat reprompts. (Inline comments batch into one model turn; chat reprompts reprocess full context and burn budget fast.)
4. **Run the acceptance check in `prompt-1-foundation.md`** before proceeding. If either criterion fails, stop — do not run Prompt 2.
5. Manual save before the next step: tell Claude *"Save what we have."* That's the only checkpoint primitive available.
6. Upload `prompt-2-pipeline.md` as the next chat reprompt in the same project. Continue refining via cheap channels.
7. **Export as standalone HTML.** Claude Design produces a bundle (HTML + CSS + JS + asset references); confirm it's a deployable directory, not a single file. Inspect the export for:
   - Asset path style: prefer site-relative (`./assets/...`) over root-absolute (`/assets/...`) — root-absolute breaks under GitHub Pages' `repo-name/` subpath unless a custom domain is configured.
   - Font loading: Fraunces, JetBrains Mono, and Inter must resolve from `fonts.googleapis.com`. If the export references commercial fonts (Editorial New, Tiempos), the prompt needs another inline-comment fix before continuing.
8. **Deploy to GitHub Pages.** Recommended config: drop the export into a `docs/` folder on `main`, then set Pages source to "Deploy from a branch · main · /docs" in repo settings. (Alternatives: gh-pages branch via Action; root deploy. Pick what fits your workflow.) The deployed URL will be `https://charleshall888.github.io/cortex-command/` unless you configure a custom domain.
9. **Smoke-test the deployed page** before screenshotting:
   - Fonts render correctly (no system-font fallback for Fraunces).
   - Spec sections lock as the viewer scrolls.
   - Sidebar agent indicators activate paired to specific spec sections.
   - Pipeline animation runs at production scroll speeds (test on both trackpad and mouse-wheel).
   - The Konami easter egg either works or has the documented `?mode=redlined` fallback URL.
   - Mobile rendering: scan-layer sidebar collapses to badge; sticky pipeline section is scrollable.
10. Screenshot the most striking moment of the deployed page → save as `assets/hero.png` for the repo's main README.

## Budget guidance

This project is configured for **Max 200 tier**, which has roughly 40× Pro's Claude Design quota — both prompts plus extensive inline iteration fit comfortably in a single session day. Pro-tier budget anxiety (the well-publicized "80% of weekly allowance in 25 minutes" data points) does not apply at Max 200 scale.

The risk concentration shifts from *budget* to *time*: a clean v1 + v2 run with active iteration is roughly a 2-3 hour focused session. If v1 fails the acceptance check, restart in a fresh project the next day with a simplified concept — quota is not the constraint, your attention is.

If you ever hit the meter unexpectedly, the documented escape is *Handoff to Claude Code* — Claude Design bundles components/tokens/assets/markup so you can continue locally with your existing Claude Code budget.

Refinement channel hierarchy (cheapest → most expensive):

1. **Sliders** Claude generates on the fly — free, client-side, no model turn
2. **Direct text edits** (click-and-type into the canvas) — free
3. **Inline comments** — batch many into ONE model turn before sending
4. **Chat reprompts** — full context reprocess, expensive, structural changes only

## Post-export workflow (v9 hybrid, current state)

The v9 export is committed at `landing-page/_imports/Cortex Command v9.html` (~270KB, 6,304 lines) and treated as the **read-only canonical** artifact from Claude Design. The deployed `docs/index.html` is a stripped + edited copy of v9, hand-modified for ship-readiness:

- edit-mode scaffold removed (`.tweaks-panel` CSS + markup + the `__edit_mode_*` postMessage protocol)
- `data-stain="carbon"` set on `<html>` so the carbon default survives the JS-shim removal
- SEO/social meta tags, favicon.svg, robots.txt, sitemap.xml, og-image.png added
- mobile (<600px) + a11y + reduced-motion fixes
- copy rewrites in §02 / §03 / §06
- progressive scroll-scrub reveal on the hood gatefold (Fig 9)
- R3 sidebar stamp doubles as the redline-mode toggle

This was landed across five atomic commits (`a0d137bc` → `87b41b14` on `main`), each tagged Phase 1 through 5 in the subject.

### Future v10 imports — interim workflow

Until the proper multi-file build pipeline lands (see backlog ticket `cortex/backlog/226-landing-multi-file-rebuild.md`), the path for a new Claude Design export is:

1. Export the new draft from Claude Design as a single HTML file.
2. Save to `landing-page/_imports/Cortex Command v<N>.html`.
3. Diff against the current `docs/index.html` to surface what changed.
4. Manually replay the post-export edits listed above on the new export.
5. Replace `docs/index.html` with the new stripped+edited version.

This is fragile — the goal of ticket 226 is to make it reliable.
