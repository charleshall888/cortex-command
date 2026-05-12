# Research: Add dashboard visual evaluation criteria to DESIGN.md

## Codebase Analysis

**Current DESIGN.md structure** (93 lines):
1. Header with generation note and brand color reference
2. `## Token Usage Rules` -- semantic token table with use/never-use columns
3. Dark theme note
4. `## Component Composition Rules` -- badges, layout, alerts, new components, "Never" list
5. `## Forbidden Patterns` -- table of forbidden patterns with "use instead" alternatives
6. `## Palette Reference (existing dashboard)` -- hex-to-token mapping table
7. `## Pattern Examples` -- list of Jinja2 macro files in `templates/patterns/`

**Existing quality/evaluation content**: The file already has quality guardrails (forbidden patterns, "Never" lists, token usage rules), but these are all *authoring constraints* -- they tell implementers what to do and not do. There is no section evaluating the *result* of implementation. A `## Visual Evaluation Criteria` section is complementary, not overlapping: authoring rules say "how to build it," evaluation criteria say "how to judge what was built."

**Natural placement**: After `## Pattern Examples` (the final current section). The evaluation criteria are a capstone -- they apply after implementation, referencing the patterns and rules defined above.

**Style conventions**: Sections use `##` headings. Tables are used for structured reference data. Prose is terse and directive. Blockquotes for callouts.

## Dashboard Context

The dashboard has seven live panels that the criteria would evaluate:

- **Session panel** (`session_panel.html`) -- active session status, timing, model info
- **Feature cards** (`feature_cards.html`) -- per-feature status with phase badges (green/blue/red/amber/gray/purple)
- **Agent fleet** (`fleet-panel.html`) -- running agent instances
- **Alerts banner** (`alerts_banner.html`) -- error/warning badges using `.alert-badge-red`, `.alert-badge-amber`
- **Round history** (`round_history.html`) -- tabular round-by-round data
- **Swim-lane** (`swim-lane.html`) -- temporal event visualization with phase-colored segments
- **Pipeline panel** (`pipeline_panel.html`) -- pipeline stage progression

Key visual elements the criteria reference:
- **Status hierarchy**: Badge colors (green=success, blue=running, red=failed, amber=deferred, gray=pending, purple=opus) must be visually distinct at a glance
- **Alerts**: `.alert-badge-red` and `.circuit-breaker-banner` must be prominent -- not buried among less-critical information
- **Design token compliance**: No inline `style=` attributes, no raw hex, no `bg-gray-*`/`text-gray-*` Tailwind defaults
- **HTMX refresh**: 5-second polling partials should swap without visible flicker or layout shift

## Criteria Content Draft

Four criteria adapted from the generative-ui-harness research (DR-4), reweighted for a monitoring dashboard:

### Information clarity (weight: high)

Operational state readable at a glance. Status hierarchy (badge colors) visually distinct without reading labels. Feature phase scannable across all cards simultaneously. Session timing and model info prominent in session panel. Round history sortable by the dimension that matters (outcome, duration, cost).

### Consistency (weight: high)

Design tokens used throughout -- no inline `style=` attributes, no raw hex values, no Tailwind default grays. Badge color meanings stable across all panels (green=success everywhere, not green=success in one panel and green=active in another). Spacing and typography follow the token scale. New components use semantic classes from DESIGN.md, not ad-hoc CSS.

*Partially automatable via Playwright*: inline style absence, element selector presence, forbidden-pattern checks.

### Operational usefulness (weight: medium)

Alerts prominent and not buried -- `.alert-badge-red` and `.circuit-breaker-banner` visually dominate when present. Swim-lane conveys temporal ordering correctly (events don't overlap illegibly when clustered). HTMX partial refresh produces no visible flicker or layout shift. Session history page usable for morning review without requiring additional filtering.

### Purposefulness (weight: low)

Dashboard reads as a purpose-built monitoring tool, not a generic admin panel. Relevant primarily for large visual changes; low weight for incremental functional improvements.

**Usage guidance**: These criteria are a human-review checklist applied after implementation. Three of four (information clarity, operational usefulness, purposefulness) require visual judgment. Consistency can be partially verified via DOM assertions (Playwright or equivalent), but full compliance still requires human review of stylesheet-level violations. When writing lifecycle specs for dashboard features, reference these criteria in the verification strategy section.

## Open Questions

None. The criteria content is well-defined by the generative-ui-harness research (DR-4). The only implementation decision is final wording, which the spec phase will determine.
