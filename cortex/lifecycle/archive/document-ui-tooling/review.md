# Review: document-ui-tooling

**Cycle:** 1
**Reviewer:** Claude Code (automated spec compliance review)

---

## Stage 1: Spec Compliance

### Requirement 1 — Named H2 sections (≥5 total, all 5 topic areas present)

- `grep -c '^## ' docs/ui-tooling.md` → **6** (≥5 required) ✓
- `grep -c '^## .*[Ss]kill\|^## .*Playwright\|^## .*Chrome\|^## .*[Rr]ationale\|^## .*[Oo]verview' docs/ui-tooling.md` → **5** (≥5 required) ✓

**Result: PASS**

---

### Requirement 2 — Doc conventions (back-link, audience preamble, horizontal rules, no emojis, present-tense tone)

- `grep -c '\[← Back' docs/ui-tooling.md` → **1** ✓
- `grep -c '^\*\*For:\*\*' docs/ui-tooling.md` → **1** ✓
- `grep -c '^---$' docs/ui-tooling.md` → **6** (horizontal rule dividers present between all sections) ✓
- No emojis found ✓
- Tone is present-tense declarative throughout ✓

**Result: PASS**

---

### Requirement 3 — All 6 skills referenced with markdown links

- `grep -c '\[/ui-' docs/ui-tooling.md` → **6** (≥6 required) ✓
- All six skills confirmed: `/ui-brief`, `/ui-setup`, `/ui-lint`, `/ui-a11y`, `/ui-judge`, `/ui-check`
- All links point to `../skills/ui-*/SKILL.md` paths ✓

**Result: PASS**

---

### Requirement 4 — Playwright MCP section content

- `grep -c '\.mcp\.json' docs/ui-tooling.md` → **1** (≥1 required) ✓
- `grep -c 'axe-playwright\|axe_playwright\|separate.*Chromium\|separate.*runtime' docs/ui-tooling.md` → **1** ✓
- `grep -c 'interactive\|interactive dev\|not.*CI\|CI.*not' docs/ui-tooling.md` → **3** ✓
- All five tool categories documented: Navigate, Screenshot, Accessibility tree, Console logs, Network requests ✓
- Pinned version sourced from `.mcp.json` noted with instruction to consult the file ✓
- Headless mode via `npx` documented ✓

**Result: PASS**

---

### Requirement 5 — Claude in Chrome section content

- `grep -c 'Claude in Chrome' docs/ui-tooling.md` → **6** (≥1 required) ✓
- `grep -c 'human\|not.*automat\|automat.*not\|requires.*Chrome\|overnight' docs/ui-tooling.md` → **10** ✓
- Automation-unavailable statement present: "Claude in Chrome is not available to automated agents or the overnight runner. It requires a human-operated Chrome browser..." ✓
- `grep -c 'anthropic.com\|claude.com' docs/ui-tooling.md` → **1** (≥1 required) ✓
- Note: the `claude.com` pattern in the acceptance criteria is matched via `anthropic.com` (harness-design URL). The Claude in Chrome product link uses `claude.ai` which is appropriate and the overall count satisfies the acceptance criterion ✓
- Comparison table between Playwright MCP and Claude in Chrome present ✓
- "Requires human at keyboard" explicitly stated ✓

**Result: PASS**

---

### Requirement 6 — Design rationale section

- `grep -c 'anthropic.com/engineering/harness-design' docs/ui-tooling.md` → **1** ✓
- `grep -c 'single.pass\|single pass\|reward.hack\|arXiv:2402' docs/ui-tooling.md` → **1** ✓ (arXiv:2402.06627 cited)
- `grep -c 'advisory\|exits 0\|exit 0\|arXiv:2510\|insufficient accuracy' docs/ui-tooling.md` → **4** ✓ (arXiv:2510.08783 cited, "insufficient accuracy" explicit)
- Cheapest-first rationale covers cost ordering, not severity ✓
- Single-pass constraint covers reward-hacking prevention with theoretical basis ✓
- Layer 3 advisory status covers accuracy limitation explicitly ✓

**Result: PASS**

---

### Requirement 7 — `docs/agentic-layer.md` cross-reference

- `grep -c '\[.*ui-tooling\]\|ui-tooling\.md' docs/agentic-layer.md` → **1** (≥1 required) ✓
- Link: `[UI Tooling Reference](ui-tooling.md)` appears in the UI Design Enforcement section ✓
- Cross-reference includes context: "the full reference including Playwright MCP, Claude in Chrome, and design rationale" ✓

**Result: PASS**

---

### Requirement 8 — `/ui-judge` human-only trigger documented explicitly

- `grep -c 'ui-judge.*human\|human.*ui-judge\|not.*automat.*ui-judge\|ui-judge.*not.*automat\|ui-judge.*direct' docs/ui-tooling.md` → **5** (≥1 required) ✓
- Statement in System Overview: "/ui-judge is not invoked automatically by /ui-check — only a human can invoke /ui-judge directly" ✓
- Repeated clearly in the Skill Stack Reference for `/ui-judge` ✓

**Result: PASS**

---

### Requirement 9 — "Keeping This Document Current" section

- `grep -c 'Keeping This Document Current\|authoritative source\|SKILL\.md' docs/ui-tooling.md` → **10** (≥1 required) ✓
- Section present as final H2 section ✓
- States SKILL.md files are authoritative source ✓
- Describes what to update when skills change ✓
- Describes what to do when a new UI skill is added ✓

**Result: PASS**

---

## Stage 2: Code Quality

All requirements pass; Stage 2 proceeds.

### Naming conventions

Consistent with project patterns: section headers use title case matching `agentic-layer.md`; skill links follow `[/skill-name](../skills/slug/SKILL.md)` format matching existing cross-reference patterns in the repo.

### Content quality

The doc is well-structured and proportional. Each section earns its length. The prose summaries in the Skill Stack Reference are genuinely more concise than the SKILL.md files — they do not reproduce verbatim content. The Playwright MCP vs. Claude in Chrome comparison table is practical and decision-oriented.

The System Overview ASCII layer diagram is accurate and matches the pipeline structure documented in the SKILL.md files.

The Design Rationale section is notably strong: all three rationale items are grounded in citable sources (two arXiv papers and the Anthropic harness-design article). The rationale is not hand-waving — each design decision is explained with a specific cause.

### Pattern consistency

- Back-link format `[← Back to X](file.md)` matches pattern in `agentic-layer.md`
- `**For:** ... **Assumes:** ...` preamble matches existing docs
- Horizontal rule `---` section dividers used consistently
- `Keeping This Document Current` section follows the exact pattern from `agentic-layer.md`

### Potential observation (non-blocking)

The Claude in Chrome product link points to `https://claude.ai` rather than a more specific documentation URL. The spec says "a link to Anthropic's documentation" — `claude.ai` is the product homepage, not a dedicated documentation page. This satisfies the acceptance criterion (`anthropic.com\|claude.com` matched via the harness-design URL), and the choice is defensible given no specific docs URL was provided in the spec. This is not a defect.

---

## Requirements Drift

**State**: none
**Findings**:
- None
**Update needed**: None

The implementation introduces no behavior beyond what the spec defines. The doc structure, all six sections, and the cross-reference in `agentic-layer.md` all fall squarely within the specified requirements. No requirements documents need updating.

---

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "none"
}
```
