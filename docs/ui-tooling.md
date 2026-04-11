[← Back to Agentic Layer](agentic-layer.md)

# UI Tooling Reference

**For:** Developers and agents working on frontend projects that use the design enforcement pipeline. **Assumes:** Familiarity with the cortex-command skill system and basic frontend tooling (ESLint, Playwright, accessibility auditing).

This document is the single reference for the UI tooling system: two setup tools and a three-layer enforcement pipeline, plus two browser automation options for interactive development. Read this before starting UI work on a new project. Consult the individual SKILL.md files linked below for the full protocol of any given skill.

See `docs/setup.md` for the "install all six or none" bundle constraint — the six UI skills are designed as a cohesive set and should not be installed partially.

---

## System Overview

The UI tooling system enforces design conformance in AI-assisted frontend development. When AI agents generate components, they can introduce token drift (hardcoded colors instead of CSS variables), accessibility regressions, or visual inconsistency. The enforcement pipeline catches these mechanically, before they reach review.

The system has two parts: setup tools that establish the design system once at project start, and an enforcement pipeline that runs on every PR or review cycle.

The enforcement pipeline runs three layers in order, cheapest first:

```
/ui-check  (pipeline orchestrator)
    |
    |-- Layer 0: DESIGN.md + shadcn presence check  (warns only, never blocks)
    |-- Layer 1: /ui-lint    (ESLint + Stylelint, blocking)
    |-- Layer 2: /ui-a11y   (axe-core WCAG 2.1 AA, conditional on Layer 1 passing)
    +-- Layer 3: /ui-judge  (Vision scorecard, advisory only — human-triggered)
```

Layer 1 is blocking: failures stop the pipeline. Layer 2 is conditional: it runs only when Layer 1 passes, and skips cleanly if no dev server is found (this is designed behavior, not an error). Layer 3 is advisory: it always exits 0 and never blocks anything. `/ui-judge` is not invoked automatically by `/ui-check` — only a human can invoke `/ui-judge` directly.

All six UI skills have `disable-model-invocation: true`. They are deterministic script-execution skills, not LLM prompting workflows. The Claude agent executes the embedded scripts rather than reasoning about what to do — invocation is mechanical, not conversational.

---

## Skill Stack Reference

### Setup Tools

These two skills run once at project setup. They are not enforcement layers.

**[/ui-brief](../skills/ui-brief/SKILL.md)** interviews the project author about design intent and generates two outputs: a `DESIGN.md` describing the visual language (palette, typography, spacing, component conventions) and a `globals.css` `@theme` block with the concrete CSS design tokens. Run this once when starting a frontend project or overhauling the design system. It establishes the design contract that the enforcement pipeline checks against.

**[/ui-setup](../skills/ui-setup/SKILL.md)** reads `package.json`, detects which toolchain components are installed, and outputs a checklist of missing items with exact install commands and config snippets. It does not run commands or write files — it guides; the human or agent executes. Run this once after `/ui-brief` to get the project into a state where the enforcement pipeline can run.

### Enforcement Pipeline

These four skills form the enforcement pipeline. Run them via `/ui-check` for a standard pipeline pass, or individually when targeting a specific layer.

**[/ui-lint](../skills/ui-lint/SKILL.md)** (Layer 1) runs ESLint and Stylelint in auto-fix-then-report mode. It attempts fixes first, then reports remaining failures. Results write to `ui-check-results/lint.json`. Exit code equals the total failure count — non-zero stops the pipeline. This layer is blocking.

**[/ui-a11y](../skills/ui-a11y/SKILL.md)** (Layer 2) launches a Playwright browser, renders pages against the running dev server, and runs axe-core for WCAG 2.1 AA compliance. Results write to `ui-check-results/a11y.json`. A dev server must be running before invocation — this skill does not start one. If no dev server is reachable, the layer skips cleanly. This layer is conditional on Layer 1 passing.

**[/ui-judge](../skills/ui-judge/SKILL.md)** (Layer 3) captures Playwright screenshots and submits them to Claude Vision twice — once for a design quality scorecard and once for cross-check — using the UICrit two-call pattern. Results write to `ui-check-results/judge.json`. This layer always exits 0 and never blocks. It is advisory only. `/ui-judge` must be called directly by a human; it is not invoked automatically by `/ui-check`.

**[/ui-check](../skills/ui-check/SKILL.md)** orchestrates Layer 0 through Layer 2 in sequence and writes `ui-check-results/summary.json` after every run, including partial runs. Pass `--only lint|a11y|judge` to run a single layer in isolation. Layer 3 (`/ui-judge`) is not included in the automated pipeline — invoke it separately when a visual quality scorecard is needed.

---

## Playwright MCP

Playwright MCP is for interactive development use, not the CI skill stack. It provides a live browser connection inside a Claude conversation, letting the agent navigate pages, take screenshots, read accessibility trees, and inspect network activity in real time.

Configuration is in `.mcp.json` at the repo root. The pinned version is sourced from `.mcp.json` — consult that file for the current version rather than treating any version number here as authoritative. The server runs in headless mode via `npx`.

Available tools through the Playwright MCP server:

- **Navigate** — load a URL in the browser
- **Screenshot** — capture the current viewport as an image
- **Accessibility tree** — read the full ARIA/accessibility tree of the current page
- **Console logs** — retrieve browser console output
- **Network requests** — inspect HTTP requests and responses made by the page

**Chromium runtime separation**: `@playwright/mcp` (Node.js) and `axe-playwright-python` (Python, used by `/ui-a11y`) use separate Chromium installations. Installing one does not satisfy the other. The Node.js Playwright installs its Chromium binary into `node_modules`; the Python `axe-playwright-python` package manages its own binary via `uv run --with playwright python -m playwright install chromium`. Both may need to be installed independently.

---

## Claude in Chrome

Claude in Chrome is the Anthropic Chrome extension (released August 2025). It embeds a Claude interface directly in the browser, giving it access to the live page DOM, network activity, and authenticated session state — capabilities that headless Playwright cannot replicate.

Claude in Chrome is not available to automated agents or the overnight runner. It requires a human-operated Chrome browser with the Anthropic extension installed. Autonomous skills and scheduled agents cannot invoke it.

Product page: [https://claude.ai](https://claude.ai)

### Playwright MCP vs. Claude in Chrome

| Capability | Playwright MCP | Claude in Chrome |
|---|---|---|
| Available to automated agents | Yes | No |
| Available to overnight runner | Yes | No |
| Requires human at keyboard | No | Yes |
| Authenticated session state | Only with explicit cookie setup | Yes — uses the live browser session |
| Interactive debugging requiring authenticated session state | Not practical | Primary use case |
| DOM access | Via accessibility tree and screenshots | Live DOM inspection |
| Console and network access | Yes | Yes |
| Works in CI / headless environment | Yes | No |

Use Playwright MCP when running automated checks, scripted audits, or any pipeline that runs without a human present. Use Claude in Chrome when the task requires an already-authenticated browser session, live DOM context, or interactive back-and-forth on a page that requires login.

---

## Design Rationale

### Cheapest-First Layer Ordering

The pipeline runs ESLint/Stylelint (Layer 1) before Playwright a11y (Layer 2) and Vision scoring (Layer 3) because static analysis is orders of magnitude cheaper than browser rendering. Failing fast on lint errors avoids spinning up Playwright for code that would never pass anyway. The ordering is not about severity — it is about cost.

### Single-Pass Constraint in `/ui-lint`

`/ui-lint` runs auto-fix once, then reports. It does not iterate: fix, re-run, fix, re-run. This single-pass constraint prevents reward-hacking, where an agent in a feedback loop learns to exploit the linter's auto-fix rather than write correct code. The theoretical basis is arXiv:2402.06627, which shows that iterative tool-call loops on verifiable tasks create incentives to game the verifier rather than solve the problem. The fix is to close the loop: run once, report, stop.

### Layer 3 Advisory-Only Status

`/ui-judge` always exits 0 and is never used as an automated gate. This is not a temporary limitation — it reflects current LLM vision accuracy. arXiv:2510.08783 documents that vision-language models achieve insufficient accuracy for automated pass/fail gating on visual design quality tasks. Using advisory output as a hard gate would introduce false positives that block valid work. The layer is kept advisory until accuracy thresholds support automation.

### Harness Design

The overall architecture of deterministic script execution with `disable-model-invocation: true` follows the Anthropic harness design pattern for long-running app components. See: [https://www.anthropic.com/engineering/harness-design-long-running-apps](https://www.anthropic.com/engineering/harness-design-long-running-apps)

---

## Keeping This Document Current

The SKILL.md files inside `skills/ui-*/` are the authoritative source for each skill's protocol, inputs, outputs, and preconditions. This document provides orientation, rationale, and cross-references — it does not reproduce the full skill protocols.

When a skill changes: update any prose summary in the Skill Stack Reference section that describes that skill's behavior, and update the System Overview layer diagram if the pipeline structure changes. When a new UI skill is added: add it to the appropriate group (setup tools or enforcement pipeline) with a one-paragraph prose summary and a markdown link to its SKILL.md. Do not reproduce SKILL.md content verbatim — summarize and link.
