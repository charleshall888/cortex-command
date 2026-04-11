# Plan: document-ui-tooling

## Overview
Create `docs/ui-tooling.md` as a single-file reference document covering the 6-skill UI tooling system (2 setup tools + 3-layer enforcement pipeline), Playwright MCP, and Claude in Chrome; update `docs/agentic-layer.md` to add a cross-reference. Both tasks are independent and can execute in parallel.

## Tasks

### Task 1: Write `docs/ui-tooling.md`
- **Files**: `docs/ui-tooling.md`
- **What**: Create the complete UI tooling reference document with all six required sections: System Overview, Skill Stack Reference, Playwright MCP, Claude in Chrome, Design Rationale, and Keeping This Document Current. Satisfies spec requirements R1–R6, R8–R9.
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Doc must open with the back-link line `[← Back to Agentic Layer](agentic-layer.md)` and immediately follow the title with `**For:** ... **Assumes:** ...` audience preamble — follow the pattern in `docs/agentic-layer.md` (lines 1–10)
  - Sections use `---` horizontal rule dividers; no emojis; present-tense declarative tone
  - **System Overview section**: describe the system's purpose (enforcing design conformance in AI-assisted frontend development), the 3-layer enforcement pipeline (/ui-lint Layer 1 blocking, /ui-a11y Layer 2 conditional, /ui-judge Layer 3 advisory), the role of /ui-check as pipeline orchestrator, and the distinction between enforcement layers and setup tools. Include a text-based layer diagram following the pattern in `docs/agentic-layer.md` lines 327–335.
  - **Skill Stack Reference section**: distinguish two groups explicitly — (a) Setup tools: /ui-brief (generates DESIGN.md and CSS @theme tokens, run once at project setup) and /ui-setup (detects toolchain state and outputs setup checklist, run once at project setup); (b) Enforcement pipeline: /ui-lint (Layer 1), /ui-a11y (Layer 2), /ui-judge (Layer 3 advisory), /ui-check (orchestrator). Do not describe /ui-brief or /ui-setup as enforcement layers.
  - All six skills are referenced with markdown links whose display text is the slash-prefixed command name: `[/ui-brief](../skills/ui-brief/SKILL.md)`, `[/ui-setup](../skills/ui-setup/SKILL.md)`, `[/ui-lint](../skills/ui-lint/SKILL.md)`, `[/ui-a11y](../skills/ui-a11y/SKILL.md)`, `[/ui-judge](../skills/ui-judge/SKILL.md)`, `[/ui-check](../skills/ui-check/SKILL.md)`
  - **Playwright MCP section**: state in this section specifically that Playwright MCP is for interactive development use, not the CI skill stack; source the pinned version from `.mcp.json` (do not hardcode it as a fact); list available tools (navigate, screenshot, accessibility tree, console logs, network requests); explicitly state that `@playwright/mcp` (Node.js Chromium) and `axe-playwright-python` (Python Chromium) use separate Chromium installations
  - **Claude in Chrome section**: describe it as the Anthropic Chrome extension (August 2025); include a statement in this section specifically that Claude in Chrome is not available to automated agents or the overnight runner — use phrasing that places "Claude in Chrome" adjacent to "not automated", "not available", or "overnight runner" on the same line; link to the Claude in Chrome product page at `https://claude.ai` (not `anthropic.com`); include a comparison table vs. Playwright MCP with use cases including authenticated session state (e.g., "interactive debugging requiring authenticated session state" as a row)
  - **Design Rationale section**: explain cheapest-first layer ordering (fail fast); explain single-pass constraint in `/ui-lint` citing arXiv:2402.06627 (reward-hacking prevention); explain why Layer 3 (`/ui-judge`) is advisory-only citing arXiv:2510.08783 (insufficient accuracy for automated gating); include attribution and URL for Anthropic harness design article: `https://www.anthropic.com/engineering/harness-design-long-running-apps`
  - **`/ui-judge` human-only trigger**: must be stated in the doc — `/ui-judge` is not invoked automatically by `/ui-check` and must be called directly by a human; write as one of: "only a human can invoke /ui-judge directly", "/ui-judge is not invoked automatically by /ui-check", or "/ui-judge must be called directly" — ensure `/ui-judge` appears in the same sentence as the human-only or not-automated qualifier
  - **"Keeping This Document Current" section**: this is a required H2 section with the exact heading `## Keeping This Document Current`; note that SKILL.md files are the authoritative source and describe what to update when skills change; follow the pattern in `docs/agentic-layer.md` lines 349–354
  - All six UI skills have `disable-model-invocation: true` — they are script-execution skills, not LLM prompting workflows; note this briefly in the doc
  - Cross-reference `docs/setup.md` for the "install all six or none" bundle constraint rather than restating it
  - Do NOT reproduce the skill inventory table verbatim from `docs/agentic-layer.md` or `docs/skills-reference.md` — write prose summaries and link out
- **Verification**:
  - `grep -c '^\[← Back\|^\[← ' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c '^\*\*For:\*\*' docs/ui-tooling.md` = 1 — pass if count = 1
  - `grep -c '^## ' docs/ui-tooling.md` ≥ 5 — pass if count ≥ 5
  - `grep -c '^## .*[Ss]kill\|^## .*Playwright\|^## .*Chrome\|^## .*[Rr]ationale\|^## .*[Oo]verview' docs/ui-tooling.md` ≥ 5 — pass if count ≥ 5
  - `grep -c '^## Keeping This Document Current' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c '\[/ui-' docs/ui-tooling.md` ≥ 6 — pass if count ≥ 6
  - `grep -c '\.mcp\.json' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'separate.*Chromium\|separate.*runtime\|axe-playwright' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'Playwright MCP.*interactive\|MCP.*interactive\|interactive.*MCP' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1 _(MCP-for-interactive-dev boundary in Playwright MCP section)_
  - `grep -c 'Claude in Chrome' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'Claude in Chrome.*not.*automat\|not.*automat.*Claude in Chrome\|Claude in Chrome.*overnight\|overnight.*Claude in Chrome\|Claude in Chrome.*not.*available' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1 _(automation-unavailable statement anchored to Claude in Chrome)_
  - `grep -c 'claude\.ai' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1 _(Claude in Chrome product page link)_
  - `grep -c 'auth.*state\|authenticated.*session\|session.*authenticat' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1 _(authenticated-session use case in comparison table)_
  - `grep -c 'anthropic\.com/engineering/harness-design' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'arXiv:2402\|reward.hack' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'arXiv:2510\|insufficient accuracy' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'ui-judge.*human\|human.*ui-judge\|not.*automat.*ui-judge\|ui-judge.*not.*automat\|ui-judge.*direct\|must.*call.*ui-judge\|ui-judge.*must.*call\|only.*human.*ui-judge' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1
  - `grep -c 'Keeping This Document Current\|authoritative source' docs/ui-tooling.md` ≥ 1 — pass if count ≥ 1 _(section body content)_
- **Status**: [ ] pending

### Task 2: Add cross-reference link to `docs/agentic-layer.md`
- **Files**: `docs/agentic-layer.md`
- **What**: Add a markdown link to `docs/ui-tooling.md` in or adjacent to the UI Design Enforcement section (currently lines 323–346) so readers following the agentic layer overview can navigate to the deeper reference.
- **Depends on**: none
- **Complexity**: simple
- **Context**:
  - Target section: `## UI Design Enforcement` at line 323 of `docs/agentic-layer.md`
  - Add a sentence or short line after the section description (lines 325–326) pointing to the new doc, e.g.: `See [UI Tooling Reference](ui-tooling.md) for the full reference including Playwright MCP, Claude in Chrome, and design rationale.`
  - The link must use the format `[...](ui-tooling.md)` (relative, same docs/ directory) — this is what the grep check targets: `\[.*ui-tooling\]\|ui-tooling\.md`
  - Follow the phrasing style of existing cross-references in `docs/agentic-layer.md` (brief inline sentence, not a separate section)
- **Verification**:
  - `grep -c '\[.*ui-tooling\]\|ui-tooling\.md' docs/agentic-layer.md` ≥ 1 — pass if count ≥ 1
- **Status**: [ ] pending

## Verification Strategy
After both tasks complete, run all spec acceptance criteria checks in sequence:

```
grep -c '^## ' docs/ui-tooling.md                            # ≥ 5
grep -c '^## .*[Ss]kill\|^## .*Playwright\|^## .*Chrome\|^## .*[Rr]ationale\|^## .*[Oo]verview' docs/ui-tooling.md  # ≥ 5
grep -c '^\[← Back' docs/ui-tooling.md                      # ≥ 1
grep -c '^\*\*For:\*\*' docs/ui-tooling.md                  # = 1
grep -c '^## Keeping This Document Current' docs/ui-tooling.md  # ≥ 1
grep -c '\[/ui-' docs/ui-tooling.md                         # ≥ 6
grep -c '\.mcp\.json' docs/ui-tooling.md                    # ≥ 1
grep -c 'axe-playwright\|axe_playwright\|separate.*Chromium\|separate.*runtime' docs/ui-tooling.md  # ≥ 1
grep -c 'Playwright MCP.*interactive\|MCP.*interactive\|interactive.*MCP' docs/ui-tooling.md  # ≥ 1
grep -c 'Claude in Chrome' docs/ui-tooling.md               # ≥ 1
grep -c 'Claude in Chrome.*not.*automat\|not.*automat.*Claude in Chrome\|Claude in Chrome.*overnight' docs/ui-tooling.md  # ≥ 1
grep -c 'claude\.ai' docs/ui-tooling.md                     # ≥ 1
grep -c 'auth.*state\|authenticated.*session' docs/ui-tooling.md  # ≥ 1
grep -c 'anthropic\.com/engineering/harness-design' docs/ui-tooling.md  # ≥ 1
grep -c 'arXiv:2402\|reward.hack' docs/ui-tooling.md        # ≥ 1
grep -c 'arXiv:2510\|insufficient accuracy' docs/ui-tooling.md  # ≥ 1
grep -c 'ui-judge.*human\|human.*ui-judge\|not.*automat.*ui-judge\|ui-judge.*direct\|must.*call.*ui-judge' docs/ui-tooling.md  # ≥ 1
grep -c 'Keeping This Document Current\|authoritative source' docs/ui-tooling.md  # ≥ 1
grep -c '\[.*ui-tooling\]\|ui-tooling\.md' docs/agentic-layer.md  # ≥ 1
```

All checks passing confirms every spec requirement is satisfied.
