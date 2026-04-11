# Specification: document-ui-tooling

## Problem Statement

The UI enforcement system (6 skills, Playwright MCP integration, Claude in Chrome) exists but has no single coherent reference. Knowledge is scattered across `docs/agentic-layer.md` (brief layer diagram), `docs/skills-reference.md` (one-liners), individual `SKILL.md` files (full protocols), and `.mcp.json` (Playwright MCP config). A developer or agent starting UI work must read 4+ files to understand the toolchain, why it's structured the way it is, and when to use Playwright MCP vs. Claude in Chrome. This doc eliminates that friction.

## Requirements

1. **`docs/ui-tooling.md` created** with the following named H2 sections: system overview, skill stack reference, Playwright MCP, Claude in Chrome, design rationale.
   Acceptance criteria:
   - `grep -c '^## ' docs/ui-tooling.md` ≥ 5
   - `grep -c '^## .*[Ss]kill\|^## .*Playwright\|^## .*Chrome\|^## .*[Rr]ationale\|^## .*[Oo]verview' docs/ui-tooling.md` ≥ 5 _(all five named section topics present)_

2. **Doc follows established conventions**: back-link header pointing to `agentic-layer.md`, bold `**For:** ... **Assumes:** ...` audience preamble directly after title, `---` horizontal rule section dividers, no emojis, present-tense declarative tone.
   Acceptance criteria: `grep -c '\[← Back' docs/ui-tooling.md` = 1; `grep -c '^\*\*For:\*\*' docs/ui-tooling.md` = 1

3. **All 6 skills referenced** by name with markdown links to their SKILL.md files — not bare name mentions.
   Acceptance criteria: `grep -c '\[/ui-' docs/ui-tooling.md` ≥ 6 _(markdown link format, not bare text)_

4. **Playwright MCP section covers**: what `.mcp.json` configures (headless mode, pinned version sourced from the file), that MCP is for interactive dev (not the CI skill stack), and an overview of the available tools (navigate, screenshot, accessibility tree, console logs, network requests). Must also clarify that `@playwright/mcp` and `axe-playwright-python` use separate Chromium runtimes.
   Acceptance criteria:
   - `grep -c '\.mcp\.json' docs/ui-tooling.md` ≥ 1
   - `grep -c 'axe-playwright\|axe_playwright\|separate.*Chromium\|separate.*runtime' docs/ui-tooling.md` ≥ 1
   - `grep -c 'interactive\|interactive dev\|not.*CI\|CI.*not' docs/ui-tooling.md` ≥ 1

5. **Claude in Chrome section covers**: what it is (Anthropic Chrome extension, live browser, authenticated sessions), when to use it vs. Playwright MCP, a link to Anthropic's documentation, and an explicit statement that it requires human operation and is not available to automated agents or the overnight runner.
   Acceptance criteria:
   - `grep -c 'Claude in Chrome' docs/ui-tooling.md` ≥ 1
   - `grep -c 'human\|not.*automat\|automat.*not\|requires.*Chrome\|overnight' docs/ui-tooling.md` ≥ 1 _(automation-unavailable statement present)_
   - `grep -c 'anthropic.com\|claude.com' docs/ui-tooling.md` ≥ 1

6. **Design rationale section covers**: why layers are ordered cheapest-first (fail fast), the single-pass constraint in `/ui-lint` (reward-hacking prevention, citing arXiv or "single-pass"), why Layer 3 is advisory-only (insufficient accuracy or "exits 0"), and a brief attribution to the Anthropic harness article with its URL.
   Acceptance criteria:
   - `grep -c 'anthropic.com/engineering/harness-design' docs/ui-tooling.md` ≥ 1
   - `grep -c 'single.pass\|single pass\|reward.hack\|arXiv:2402' docs/ui-tooling.md` ≥ 1
   - `grep -c 'advisory\|exits 0\|exit 0\|arXiv:2510\|insufficient accuracy' docs/ui-tooling.md` ≥ 1

7. **`docs/agentic-layer.md` updated** to add a cross-reference link to `docs/ui-tooling.md` in or adjacent to the existing UI Design Enforcement section.
   Acceptance criteria: `grep -c '\[.*ui-tooling\]\|ui-tooling\.md' docs/agentic-layer.md` ≥ 1 _(link format, not just string match)_

8. **`/ui-judge` human-only trigger documented explicitly** — the doc must state that `/ui-judge` is not invoked automatically by `/ui-check` and must be called directly by a human or explicit invocation.
   Acceptance criteria: `grep -c 'ui-judge.*human\|human.*ui-judge\|not.*automat.*ui-judge\|ui-judge.*not.*automat\|ui-judge.*direct' docs/ui-tooling.md` ≥ 1

9. **Doc includes a "Keeping This Document Current" section** noting that SKILL.md files are the authoritative source and describing what to update when skills change, following the pattern in `docs/agentic-layer.md`.
   Acceptance criteria: `grep -c 'Keeping This Document Current\|authoritative source\|SKILL\.md' docs/ui-tooling.md` ≥ 1

## Non-Requirements

- Does not update any `SKILL.md` files — skills are referenced, not redocumented
- Does not reproduce the full skill inventory table verbatim from `agentic-layer.md` or `skills-reference.md` — the doc writes its own prose summaries that are more concise and contextualized; inline markdown links are the cross-reference mechanism
- Does not include setup instructions for Claude in Chrome — those are on Anthropic's site; the doc links out and clarifies the automation boundary
- Does not include a step-by-step project onboarding walkthrough — the doc is reference content; decision guidance (when to use which tool) is allowed
- Does not create a second architecture doc — all content in one file with sections
- Does not update `docs/skills-reference.md` — a link from `agentic-layer.md` is sufficient cross-referencing at that level

## Edge Cases

- **Playwright MCP version**: `.mcp.json` pins `@playwright/mcp@0.0.70` — the doc must reference `.mcp.json` as the authoritative source for the current pinned version, not hardcode the version number as a permanent fact
- **`/ui-judge` is human-triggered only**: never invoked automatically by `/ui-check`; the doc must make this explicit (covered by Requirement 8)
- **Dev server prerequisite for `/ui-a11y`**: doc should note that the dev server must be running; Layer 2 skips cleanly if no dev server is found (not an error — designed behavior)
- **Separate Chromium binaries**: `@playwright/mcp` (Node.js) and `axe-playwright-python` (Python) use separate Chromium installations; doc must clarify this (covered by Requirement 4)
- **Claude in Chrome is not available to automated agents**: requires a human-operated Chrome browser with the Anthropic extension installed; cannot be invoked by the overnight runner or any autonomous skill (covered by Requirement 5)

## Changes to Existing Behavior

- ADDED: `docs/ui-tooling.md` — new reference doc for the UI tooling system
- MODIFIED: `docs/agentic-layer.md` — cross-reference link added to the UI Design Enforcement section

## Technical Constraints

- All skill output artifacts write to `ui-check-results/` (per `/ui-setup` checklist; gitignored)
- `/ui-a11y` uses `axe-playwright-python` via `uv run --script` (PEP 723 inline Python script) — requires `uv`, not just npm
- All six UI skills have `disable-model-invocation: true` — they are deterministic script-execution skills, not LLM prompting workflows; this is worth noting in the doc as it affects how they're invoked
- Playwright MCP requires `enableAllProjectMcpServers: false` approval prompt on first use per session (configured in `settings.json`)
- The "install all six or none" bundle constraint is documented in `docs/setup.md` — the new doc should cross-reference this rather than restate it

## Open Decisions

_None — all decisions resolved at spec time._
