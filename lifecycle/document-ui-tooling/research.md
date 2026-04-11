# Research: Document UI Tooling System

## Codebase Analysis

### Files That Will Change

- **`docs/ui-tooling.md`** — new file to create (does not exist)
- **`docs/agentic-layer.md`** — minor update: replace the existing UI Design Enforcement section (lines 323–346) with a cross-reference link to the new doc, or add a link without removing the existing content
- **`docs/skills-reference.md`** — optional minor update: add a link to the new doc from the "UI Design Enforcement" group

### What Each UI Skill Does

**`/ui-brief`** (Design foundation — run once)
- Collects project name, brand hue (oklch 0–360), and lightness preference
- Generates `DESIGN.md` with semantic color/typography/spacing tokens and appends a `@theme` block to `globals.css`
- Idempotent (skips or confirms overwrite if markers are already present)
- Inputs: interactive prompts; Outputs: `DESIGN.md`, `globals.css` `@theme` block
- Not an enforcement layer — feeds design constraints into the toolchain

**`/ui-setup`** (Toolchain detection — run once per project)
- Reads `package.json` and evaluates 8 checklist items: shadcn, shadcn MCP, ESLint (Tailwind + jsx-a11y), Stylelint (rhythmguard), Prettier (tailwindcss plugin), pre-commit hook (Husky + lint-staged), `ui-check-results/` gitignore, Playwright
- Outputs exact install commands and config snippets for missing items; never runs commands itself
- Not an enforcement layer — detects toolchain state and provides setup instructions

**`/ui-lint`** (Layer 1 — blocking gate)
- ESLint + Stylelint: `tailwindcss/no-arbitrary-value: error`, `no-contradicting-classname: error`, jsx-a11y recommended ruleset
- Single-pass: never loops (reward-hacking prevention — arXiv:2402.06627)
- Output: `ui-check-results/lint.json` with `{ passed, autofixed_count, failure_count, failures[] }`
- Exit code = failure_count; `/ui-check` stops here if non-zero

**`/ui-a11y`** (Layer 2 — conditional on lint passing + dev server running)
- Writes and runs a PEP 723 inline Python script using `axe-playwright-python` via `uv run --script`
- Targets WCAG 2.1 AA (`wcag2a`, `wcag2aa`, `wcag21aa`); sorts violations by impact
- Probes ports 3000, 3001, 5173, 4173 for dev server (or reads `.ui-config.json`)
- Output: `ui-check-results/a11y.json` with `{ passed, url, violation_count, violations[] }`
- Layer skips cleanly if no dev server is found (not an error)
- Uses Python Playwright/Chromium binaries, separate from `@playwright/mcp`

**`/ui-judge`** (Layer 3 — advisory only, never automated)
- Two sequential Claude Vision calls per viewport (UICrit pattern — arXiv:2407.08850): Call 1 = critique on 5-criterion rubric (visual_hierarchy, spacing_consistency, color_contrast, alignment, component_state_completeness, scored 1–5); Call 2 = CSS localization
- Always exits 0 — never a CI gate (insufficient accuracy for automated gating — arXiv:2510.08783)
- Output: `ui-check-results/judge.json` + per-viewport screenshots
- Must be invoked directly; never called by `/ui-check`

**`/ui-check`** (Pipeline orchestrator)
- Layer 0 (design presence check — warns, never blocks) → Layer 1 (`/ui-lint`, blocking) → Layer 2 (`/ui-a11y`, conditional)
- Stops at first layer failure; writes `ui-check-results/summary.json` after each run including partial
- `--only lint|a11y|judge` flag for isolated runs
- `/ui-judge` is NOT invoked automatically — human-triggered only

### How Playwright MCP Is Configured

`.mcp.json` at repo root (project-scoped):
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@0.0.70", "--headless"]
    }
  }
}
```

- `enableAllProjectMcpServers: false` in `settings.json` — requires approval on first use per session
- This MCP serves the **dashboard project** during interactive development — gives Claude the ability to navigate and screenshot the dashboard UI in real time
- **Distinct from the skill stack**: `/ui-a11y` and `/ui-judge` use Python Playwright (`axe-playwright-python`/`npx playwright screenshot`) with separate Chromium binaries; they do not go through `@playwright/mcp`

### "Claude Chrome" Term

The term "Claude Chrome" does not appear in the codebase — no documentation, no config files, no skill files. This is likely the user's informal term for the Playwright MCP capability (the ability to give Claude a live browser during interactive development). **This should be surfaced as an open question in the spec phase** to confirm what should be documented under this label.

### Conventions to Follow

1. Open with `[← Back to Agentic Layer](agentic-layer.md)` back-link
2. Bold `**For:** ... **Assumes:** ...` audience preamble after the title
3. Horizontal rule `---` section dividers
4. ASCII or table-based layer diagrams (matching `agentic-layer.md` style)
5. Direct, declarative tone — no hedging, present tense, no emojis
6. Code blocks for commands, JSON schemas, config snippets
7. Do NOT restate the existing agentic-layer.md skill inventory verbatim — link to it
8. All output artifacts go in `ui-check-results/` per the bundle convention

---

## Web Research

### Anthropic Harness Design Article — Key Takeaways

The article (`https://www.anthropic.com/engineering/harness-design-long-running-apps`) describes design principles for multi-agent harnesses applied to long-running applications. The ideas most relevant to this system:

**Generator-Evaluator Separation**: Separating work agents from judging agents is described as a "strong lever" for quality. Evaluators maintain independent skepticism that self-critiquing agents lack. This maps directly to having separate enforcement layers rather than asking the code-generating agent to also validate its own output.

**Converting Subjective Judgment Into Gradable Criteria**: Subjective quality (visual craft, spacing, contrast) must be operationalized as concrete, checkable criteria before AI evaluators can apply them reliably. Without explicit rules, evaluators exhibit "generosity bias." This justifies the rubric in `/ui-judge` and the explicit WCAG level targeting in `/ui-a11y`.

**Harnesses Encode Model Limitations — Strip Them As Models Improve**: Each layer embeds an assumption about where AI-generated code fails. The linting layer exists because AI tools generate structurally invalid CSS. The accessibility layer exists because structural validity doesn't imply WCAG compliance. The visual layer exists because WCAG compliance doesn't imply rendered correctness. This framing is the core architectural rationale.

**Structured Artifact Handoffs**: Each layer produces a structured JSON artifact (`lint.json`, `a11y.json`, `judge.json`) rather than flowing conversation context. This allows inspection, CI integration, and session-independent resumption.

**Specialist Isolation**: Each layer owns one domain to prevent scope creep — syntax/structure (lint), standards compliance (a11y), rendered correctness (visual AI).

### Prior Art Alignment

| Pattern | Where It Appears in This System |
|---|---|
| Layer-by-layer responsibility separation | Three enforcement layers with distinct tools and domains |
| Structured JSON artifacts per layer | `lint.json`, `a11y.json`, `judge.json`, `summary.json` |
| Advisory-only for AI visual review | `/ui-judge` always exits 0; never a gate |
| Explicit rubric for AI evaluators | 5-criterion scoring rubric in `/ui-judge` |
| CLI over MCP for repeatable pipelines | `/ui-a11y` uses Python Playwright CLI; MCP for interactive dev only |
| No iterative loops in enforcement | Single-pass constraint in `/ui-lint` (arXiv:2402.06627) |

---

## Requirements & Constraints

### From `requirements/project.md`

- UI skills are in-scope as part of "AI workflow orchestration (skills, lifecycle, pipeline, discovery, backlog)"
- **Maintainability through simplicity**: docs must be clear enough for agents to use. No structure for its own sake.
- **Complexity must earn its place**: documentation should not add sections without a real need.
- **Out of scope boundary**: the doc should clarify that UI skills operate on *target projects being built*, not on cortex-command itself
- No `requirements/ui.md` or `requirements/docs.md` exists — no area-level constraints to observe beyond the project-level rules

### Existing Documentation Structure

- `docs/agentic-layer.md` already has a UI Design Enforcement section (lines 323–346) with the layer diagram and per-skill descriptions
- `docs/skills-reference.md` already has a "UI Design Enforcement" group (lines 149–191) with per-skill entries and SKILL.md links
- `docs/setup.md` mentions the "install all six or none" bundle constraint (lines 54, 66–75)
- New doc should NOT duplicate the existing inventory — link to it and go deeper on rationale and architecture

### Technical Constraints from SKILL.md Files

- All six UI skills have `disable-model-invocation: true` — they are script-execution skills, not LLM prompting workflows
- `/ui-a11y` requires `uv` (not just npm) for `axe-playwright-python` PEP 723 scripts
- `/ui-judge` two-call Vision pattern (UICrit arXiv:2407.08850) — combining calls degrades critique quality; this is documented rationale
- `/ui-lint` single-pass constraint (arXiv:2402.06627) — iterative lint-fix loops cause reward hacking; this is documented rationale
- `/ui-a11y` requires dev server to be running (does not start it)
- shadcn MCP config writes to `settings.json` — intersects with settings architecture

---

## Claude in Chrome vs Playwright MCP

A supplemental research pass clarified the "Claude Chrome" question. These are two distinct capabilities:

**Playwright MCP** (`@playwright/mcp` — already in `.mcp.json`): Headless, structured, ephemeral browser. Primary interaction model is the accessibility tree (structured text, 2–5 KB per page). Screenshots are explicit opt-in. No stored sessions or auth. Ideal for reproducible navigation, screenshot capture, and developer-alongside-Claude evaluation during interactive development.

**Claude in Chrome** (official Anthropic Chrome extension, launched August 2025): Embeds Claude as a sidebar in your real Chrome instance. Uses your authenticated sessions and cookies. Primary model is also accessibility tree (via CDP), with screenshot fallback for elements that can't render in the tree (canvas, custom renderers). Designed for interactive, human-alongside-Claude workflows where real session state matters.

| Use case | Better tool |
|---|---|
| Accessibility checks | Playwright MCP (or axe-playwright-python for CI) |
| Screenshot capture for visual review | Playwright MCP (clean, reproducible, no auth exposure) |
| Interactive debugging requiring auth state | Claude in Chrome |
| Reproducible offline rendering | Playwright MCP |

Neither is "computer use" (Anthropic API OS-level screen control) — that is a separate, unrelated capability.

The doc should explain both, clarify they are complementary, and describe when to use each.

## Open Questions

_Both questions resolved during the research exit gate:_

- **"Claude Chrome" resolved**: Claude in Chrome is an official Anthropic Chrome extension (August 2025), distinct from Playwright MCP. Both should be documented. See the "Claude in Chrome vs Playwright MCP" section above.

- **One doc or two? Resolved**: One doc with sections (`docs/ui-tooling.md`).
