# Research: generative-ui-harness

## Research Questions

1. What UI does this project currently have, and what are its quality gaps — aesthetics, functionality, or both?
   → **FastAPI + Jinja2 + HTMX + Tailwind v4 dashboard at `claude/dashboard/`. ~3,000 Python LOC + ~900 HTML LOC. Seven live panels (session status, feature cards, agent fleet, alerts, round history, swim-lane, pipeline) served via HTMX polling partials. Quality gaps: CSS mixing (inline styles violate DESIGN.md rules), no hover states or loading feedback, swim-lane layout degrades when events cluster, session history page has no filters/sorting. Accessibility: no ARIA labels, color contrast unverified on swim-lane phase backgrounds. Structural quality (data layer, design tokens) is solid; presentation layer is rough at the edges.**

2. Which of the three agent roles (planner, generator, evaluator) are missing or conflated in how UI work is currently done?
   → **All three are conflated. UI features go through the standard lifecycle (research → spec → plan → implement), using Claude as both planner and generator. There is no dedicated evaluator role. Post-implementation evaluation is: unit tests checking string presence in rendered HTML, plus human review. The unit tests verify data-layer correctness, not visual quality, layout integrity, or behavioral usability. The evaluator role is entirely absent.**

3. What would the four-criteria rubric look like adapted to this project's specific UI context?
   → **Adapted rubric: (1) Information clarity (≈design quality): operational state readable at a glance — status hierarchy visually distinct, feature status scannable without reading every label; (2) Consistency (≈craft): design tokens used throughout, no inline styles, no Tailwind/component class mixing, forbidden patterns absent; (3) Operational usefulness (≈functionality): alerts prominent, swim-lane conveys temporal ordering correctly, HTMX refresh produces no visible flicker, session history usable for morning review; (4) Purposefulness (≈originality): feels like a purpose-built monitoring tool, not a generic admin panel — relevant for large design changes, low relevance for small functional improvements. Weighting for this project: information clarity > consistency > operational usefulness >> purposefulness.**

4. Does this project have the tooling for live evaluation (Playwright MCP or equivalent)? If not, what would it take?
   → **No. No Playwright, no Selenium, no headless browser dependency installed. No MCP configuration for Playwright in the project or globally. What exists that makes Playwright feasible: `just dashboard` starts the server at `localhost:8080`; `just dashboard-seed` generates fixture data; `.ui-config.json` captures the dev server URL. What it would take: add `@playwright/mcp` to MCP server config, add `playwright` as a dev dependency, write a fixture-setup script that seeds + starts the server. Total setup effort: S — but S only covers DOM-structure assertions (inline style checks, element presence, HTMX partial responses). Playwright cannot verify perceptual criteria (visual clarity, layout coherence, animation smoothness); those require human review.**

5. What would explicit pre-implementation UI success criteria look like for this codebase?
   → **A more specific version of the lifecycle spec's existing verification strategy section: a list of browser-level assertable behaviors written before implementation begins. For a dashboard feature this would include: element selectors present after fixture load (e.g., `[data-testid="feature-cards"]`), status badges visible per feature, specific text/counts matching seed data, no inline `style=` attributes on newly added elements, HTMX partials swapping without full reload, contrast values on new elements. This is not a "sprint contract" in the article's sense — the article's sprint contract required negotiation between a generator agent and an evaluator agent before implementation. Since this project has no evaluator agent, there is no second party. What's described here is a rigorous acceptance test list: an improvement over the current verification strategy, but not structurally different from it. The lifecycle spec already has "acceptance criteria" and "verification strategy" sections — the gap is that (a) these are often written at low specificity, and (b) no tool executes them automatically against the live UI.**

6. Is a full three-agent harness warranted, or would a simpler change deliver most of the value?
   → **Simpler change first, but the scope of "simpler" matters. A Playwright-based verification step covers only DOM-level consistency checks (one of four rubric criteria). Three of four rubric criteria require human visual judgment. The right framing is not "add Playwright to replace human evaluation" but "add Playwright to automate the one criterion it can verify, and make the remaining three criteria explicit in a human-review checklist." The full harness would cost $200+ per run and is designed for creative aesthetic iteration — neither applies here. A simpler, honest scope: raise the specificity of the verification strategy in lifecycle specs for dashboard features + add Playwright for the DOM-structural criterion + explicitly list the three perceptual criteria as human-review steps.**

7. Does the prior discovery's dismissal of the evaluator ("not applicable — binary test outcomes") hold for UI work?
   → **No. The prior research correctly identified that software delivery tasks have binary test outcomes and dismissed the evaluator for that domain. But UI evaluation genuinely cannot be fully automated with unit tests. The existing unit tests check string presence in rendered HTML (`assertIn("No active session", html)`) — they verify data binding, not visual quality, layout integrity, or operational clarity. The evaluator case is actually stronger here than it was for overnight feature delivery. The prior dismissal applied to the wrong domain.**

## Codebase Analysis

**Dashboard location and structure:**
- Python: `claude/dashboard/` — `app.py` (316 LOC), `data.py` (1,382 LOC), `poller.py` (331 LOC), `alerts.py` (149 LOC), `seed.py` (782 LOC)
- Templates: `claude/dashboard/templates/` — `base.html` (433 LOC), 9 panel templates, 3 reusable pattern macros
- Tests: `claude/dashboard/tests/` — 2,212 LOC across 4 test files; unit-level only (no browser tests)
- Design system: `claude/dashboard/DESIGN.md` — documents color tokens, composition rules, and explicitly lists forbidden patterns

**Technology choices:**
- Server-rendered Jinja2 with HTMX 2.0.4 for partial refreshes (no React, Vue, or client-side framework)
- Tailwind v4 via CDN with custom `@theme` design tokens in `base.html`
- HTMX polls every 5 seconds; Python poller runs asyncio tasks every 1–30 seconds depending on data freshness requirements
- `just dashboard` → `uvicorn` at `localhost:8080`; `just dashboard-seed` generates fixture files for offline development

**Dashboard work history:**
- Git log shows only 2 commits touching `claude/dashboard/` — both from initial project setup, not from overnight agents
- No dashboard UI items exist in the current backlog
- All dashboard work has been done interactively (daytime), not overnight. This is consistent with the project's day/night split: the dashboard *monitors* overnight sessions, so meaningful dashboard evaluation requires a human observer

**What unit tests cover (and don't cover):**
- `test_templates.py`: 10 test classes, all asserting string presence in rendered HTML — verifies data wiring, not visual layout
- `test_data.py`: 1,374 LOC testing data parsers (parse_overnight_state, parse_feature_events, tail_jsonl, etc.)
- `test_alerts.py`, `test_poller.py`, `test_sessions.py`: business logic coverage
- **Not covered**: HTTP routes (no integration tests), visual layout (no CSS snapshot tests), behavioral UI (no browser tests), accessibility (no axe-core integration)

**CSS quality issues identified:**
- Inline `style=` attributes in `swim-lane.html`, `session_panel.html`, `feature_cards.html` — explicitly forbidden by DESIGN.md
- Mixed Tailwind utilities and component classes on same elements (e.g., swim-lane segment `<div>` with both `text-white absolute top-1 h-8` and component-class styling)
- Swim-lane timeline: overlapping event labels at fixed width; degrades when many events cluster; "summary mode" (hides tool ticks >200 events) produces unexplained UX
- No hover states on cards or interactive elements; no loading feedback during HTMX refreshes

**Integration points for evaluator tooling:**
- Dev server URL in `.ui-config.json` (`localhost:8080`)
- Fixture setup via `just dashboard-seed`
- HTMX partition: evaluator can hit individual partial endpoints (`/partials/feature-cards`, `/partials/swim-lane`, etc.) to test specific panel rendering

## Web & Documentation Research

**Anthropic harness design article findings:**

The article describes a GAN-inspired loop for UI generation:
- **Planner**: expands a brief prompt into an ambitious spec; explicitly instructed to avoid implementation details
- **Generator**: implements in sprints; self-evaluates before QA handoff
- **Evaluator**: uses Playwright to interact with the running UI before scoring; tuned to be skeptical after early versions were too lenient
- **Sprint contracts**: generator and evaluator negotiate explicit "done" criteria before implementation begins — the evaluator's negotiating position is what forces criteria to be specific enough to be machine-checkable and non-trivial
- **Rubric** (weighted, with design/originality higher than functionality): design quality, originality, craft, functionality
- **Solo vs. harness cost**: $9 solo (20 min, broken implementation) vs. $200 harness (6 hours, functional + polished)
- **Iterative evolution**: sprint decomposition later removed for Opus 4.6 — evaluator became optional for tasks within model baseline capabilities
- **Key discipline**: "Every component in a harness encodes an assumption about what the model can't do on its own" — regularly stress-test whether components remain load-bearing

**Companion articles:**

*Effective Harnesses for Long-Running Agents*:
- Dual-agent approach: Initializer (sets up infrastructure) + Coding Agent (incremental progress)
- Feature list JSON with pass/fail tracking per feature
- Agents test end-to-end using browser automation before declaring done
- Core principle: each session must leave clear artifacts for the next session (fresh context handoff)

*Effective Context Engineering for AI Agents*:
- "Context rot": as context windows grow, models struggle to recall information from expanded context
- System prompts at the "right altitude": specific enough to guide behavior without brittle hardcoding
- Minimal, high-signal tools with clear purposes
- Dynamic just-in-time retrieval over pre-processing all data
- Three complementary techniques for long-horizon tasks: compaction, structured note-taking, multi-agent architectures

**frontend-design SKILL.md (Anthropic plugin):**

The skill emphasizes bold aesthetic direction, distinctive typography, animation, and unexpected spatial composition. It targets *generative* creative UI for general audiences; it does not map directly onto a monitoring dashboard for a single technical user. Its rubric (design quality, originality, craft, functionality) weights originality highly — the opposite priority from a monitoring dashboard, where consistency and operational clarity matter more than novelty.

**Key divergence from this project's context**: The frontend-design skill and the article's harness were both designed for *creative aesthetic generation* as a primary goal. The dashboard's goal is *operational clarity*. The four-criteria rubric requires adaptation, not direct import.

## Domain & Prior Art Analysis

**Prior discovery coverage and gap:**

The `research/harness-design-long-running-apps/` discovery explicitly analyzed the same Anthropic article but in the context of software delivery via the overnight runner. Its conclusion — "evaluator rubric not applicable, binary test outcomes" — was correct for that domain. The current discovery focuses on the dashboard UI, where that conclusion does not hold.

**The two-domain split:**

| Domain | Test outcomes | Evaluator value |
|--------|---------------|-----------------|
| Overnight feature delivery | Binary (tests pass/fail, no-commit guard, spec compliance via runnable tests) | Low — tighter spec/plan templates address the gap at lower cost |
| Dashboard UI | Partially binary (data binding, route availability) + genuinely qualitative (visual clarity, layout integrity, operational usability) | Moderate — unit tests cannot verify what matters most |

**What the article's harness cost vs. what it delivered:**

The $200 / 6-hour harness run produced a polished creative application with AI-assisted features. For a monitoring dashboard where the primary user is the developer themselves: (a) the user has direct observational feedback and can evaluate the dashboard immediately after implementation; (b) dashboard work has always been done daytime (confirmed by git history); (c) the evaluator role adds most value when the generator cannot access the live UI and no human is present — neither condition is true for this project's current workflow.

**The honest picture of Playwright's value for daytime dashboard work:**

Playwright adds value in two narrow, real ways even for daytime work:
1. **Regression detection**: future CSS changes that introduce inline styles or break element structure are caught automatically, not only by human inspection
2. **Specificity pressure**: writing Playwright assertions before implementation forces acceptance criteria to be machine-checkable rather than prose — even if a human reviews the results, the act of writing assertions that must pass creates a more specific target

It does not replace the perceptual judgment that three of four rubric criteria require.

## Feasibility Assessment

| Approach | Effort | What it actually covers | Risks | Prerequisites |
|----------|--------|------------------------|-------|---------------|
| Add Playwright + write DOM-structure assertions | S | Criterion 2 (consistency) only: inline style checks, element presence, HTMX swap behavior | MCP config is global, not project-scoped; assertions are shallow; three of four rubric criteria remain uncovered | `playwright` installed, MCP server configured in `~/.claude/settings.json` |
| Define acceptance test list (rigorous verification strategy) in lifecycle template for dashboard features | S | Documents criteria for all four rubric dimensions; three of four remain human-evaluated | Criteria specificity depends on author discipline; no tooling enforces criteria granularity | Rubric definition (this research provides the draft) |
| Combined: Playwright assertions + explicit human-review checklist for perceptual criteria | S–M | Full rubric coverage: automated for criterion 2, human-reviewed for criteria 1, 3, 4 | Two-step review process; the human-review steps are as disciplined as the author makes them | Playwright setup + rubric definition |
| Two-agent generator/evaluator loop for dashboard features (overnight) | M–L | Full rubric coverage automated — but overnight runner doesn't start a dashboard server; requires fixture hook + server management in runner | Evaluator agent needs running server; adds new overnight phase; crash handling needed; dashboard work has never been overnight (git history) | Playwright MCP, server-start hook in overnight runner, evaluator prompt, rubric |
| Full three-agent planner/generator/evaluator harness | L | Full rubric + sprint contract negotiation + iterative refinement | High cost per run ($200 equivalent), evaluator skepticism tuning required, evaluator loops need cycle-breaker, rubric must be defined first | All of the above |
| Visual regression testing (Playwright screenshots + diff) | M | Structural/visual regression (catches layout regressions even for perceptual criteria) | Screenshot diffs are noisy; flaky tests reduce trust; requires baseline management; still fails to catch degradation if the baseline itself is weak | Playwright setup, screenshot baseline infrastructure |

## Decision Records

### DR-1: Does the prior discovery's dismissal of the evaluator apply to UI work?

- **Context**: The `harness-design-long-running-apps` discovery concluded the evaluator rubric was "not applicable — software delivery has binary test outcomes." That conclusion was correct for overnight feature delivery. The dashboard is a different domain.
- **Options considered**:
  - Treat UI as identical to feature delivery → evaluator not needed (prior conclusion)
  - Treat UI as genuinely qualitative → some evaluation infrastructure adds value
- **Recommendation**: The prior dismissal does not apply to dashboard UI. Unit tests verify data binding, not visual quality or operational clarity. Some evaluation infrastructure (even a human-applied rubric checklist) adds value here that it does not add in the software delivery domain.
- **Trade-offs**: "Some evaluation infrastructure" is weaker than "a dedicated evaluator agent." The value depends on how much discipline the human reviewer applies to the rubric.

### DR-2: Full three-agent harness vs. lighter-weight evaluation addition

- **Context**: The article's harness cost $200 per run and was designed for creative aesthetic generation with iterative loops. The dashboard is a functional monitoring tool for personal use. Git history confirms dashboard work has always been done daytime, interactively — the human is always present. The overnight scenario, which would make an automated evaluator agent uniquely valuable, has not occurred and is not planned.
- **What each approach actually provides:**
  - Full harness: covers all four rubric criteria via automated evaluation; overkill for current use pattern; calibration work required
  - Playwright assertions only: covers consistency (criterion 2) automatically; does not cover criteria 1, 3, 4
  - Explicit acceptance test list in lifecycle specs: forces criteria to be written precisely before implementation; human-evaluated; covers all four criteria at human-review quality
  - Combined (Playwright + human-review checklist): S–M effort; full rubric coverage at correct fidelity per criterion
- **Recommendation**: The combined approach — Playwright for DOM-structure assertions (criterion 2) and an explicit human-review checklist for the three perceptual criteria — delivers full rubric coverage at appropriate fidelity. The key improvement is raising the specificity of the lifecycle verification strategy for dashboard features, not automating what cannot be automated.
- **Prerequisite gate**: If dashboard UI improvements ever move to the overnight backlog (unattended execution), both the value case for Playwright and the complexity case for a full evaluator agent shift significantly. That transition should trigger a reassessment. It has not happened yet.
- **Trade-offs**: Requires the human to actually apply the checklist rather than rubber-stamping review. The checklist's value is proportional to the reviewer's discipline.

### DR-3: When does a dedicated evaluator agent become warranted?

- **Context**: The article observed that evaluator skepticism required substantial tuning across multiple development cycles. The cost of a miscalibrated evaluator is nontrivial.
- **Triggering conditions for adding a dedicated evaluator agent**:
  1. Dashboard UI improvements are added to the overnight backlog (unattended execution, no human feedback loop) — this is the primary condition; none of the value arguments for an automated evaluator hold without it
  2. A large visual redesign is planned that requires multiple iteration cycles
  3. The human-review checklist (DR-2) produces repeated false negatives — work that passes checklist review but later requires rework — more than twice
- **Recommendation**: Track evaluator need against these three conditions. Condition 1 has not occurred (git history: zero overnight dashboard commits). Do not add the evaluator speculatively.

### DR-4: What should the rubric criteria be, and which can Playwright verify?

- **Context**: The article's rubric (design quality, originality, craft, functionality) was calibrated for consumer-facing creative UI. The dashboard is a monitoring tool for the developer themselves.
- **Adapted criteria, weights, and verifiability:**

  | Criterion | Weight | Playwright-verifiable? | What Playwright can check |
  |-----------|--------|----------------------|--------------------------|
  | Information clarity | High | No — perceptual judgment | Element presence only; cannot verify "readable at a glance" or "visually distinct" |
  | Consistency | High | Partially — DOM structure | Inline `style=` attribute absence; element selector presence. Cannot detect stylesheet-applied violations (e.g., hardcoded color values in CSS rules, not inline) |
  | Operational usefulness | Medium | No — perceptual + workflow judgment | Element presence; cannot verify "alerts prominent," "no visible flicker," or "session history usable" |
  | Purposefulness | Low | No — entirely perceptual | N/A |

- **Implication**: Playwright automates part of criterion 2 (consistency). All other rubric evaluation requires human judgment. The rubric as defined is not an automation target — it is a human-review framework with Playwright as a partial assist on one criterion.
- **Trade-offs**: Accepting this means the evaluation quality is bounded by human reviewer discipline. An evaluator agent with visual reasoning capabilities (not Playwright) would change this calculus, but no such tool is in the current MCP ecosystem.

## Open Questions

- If Playwright MCP is added globally (to `~/.claude/settings.json`), will it interfere with non-dashboard Claude Code sessions? The MCP config is machine-global, not project-scoped — worth checking whether project-scoped MCP configuration is supported before adding it globally.
- The swim-lane "summary mode" (hides tool ticks >200 events) produces an unexplained UX transition. Is this a known issue or by design? Before the human-review checklist can evaluate swim-lane behavior, the correct behavior needs to be defined.
