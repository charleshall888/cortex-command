---
name: ui-judge
description: Captures a screenshot of a URL via Playwright, evaluates it against a five-criterion visual quality rubric using Claude Vision (two-call UICrit pattern), and writes a scored JSON verdict to ui-check-results/judge.json. Layer 3 of the design enforcement stack — human-triggered advisory scorecard, never a CI gate. Always exits 0. Use when user says "/ui-judge", "judge the UI", "visual quality score", "score the UI", "run the visual judge", "design scorecard", or wants a scored visual quality report of the current UI.
disable-model-invocation: true
inputs:
  - "url: string (optional) — URL to evaluate; defaults to http://localhost:3000"
  - "--viewports: string (optional) — comma-separated viewport widths in px; defaults to 1440; full run: 375,768,1440"
outputs:
  - "ui-check-results/judge.json — scored verdict with five criteria, top_issues, and affected_selectors"
  - "ui-check-results/judge-screenshot-{viewport}.png — viewport screenshot(s)"
  - "exit code — always 0; this skill is advisory only"
preconditions:
  - "Run from project root"
  - "Playwright is optional — graceful degradation if missing"
  - "Dev server should be running at the target URL"
---

# UI Judge

Capture a screenshot, evaluate against the visual quality rubric, write a scored JSON verdict. Two sequential Vision calls per viewport: critique first, localization second (UICrit pattern — combining them degrades critique quality per arXiv:2407.08850).

## Preconditions

Two graceful-degradation scenarios that exit 0 immediately:

- **Playwright not installed**: Write `{ "error": "Playwright not installed", "score": null }` to `ui-check-results/judge.json`. Print: `"Playwright is required. Install with: npm i -D @playwright/test && npx playwright install chromium"`
- **LLM unavailable**: Write `{ "error": "LLM unavailable", "score": null }` to `ui-check-results/judge.json`.

## Step 1: Parse Arguments and Create Output Directory

Extract the URL (first positional arg; default `http://localhost:3000`) and viewport list (`--viewports` flag; parse as comma-separated integers; default `[1440]`).

```bash
mkdir -p ui-check-results
```

Check URL reachability:

```bash
curl -s --head --max-time 5 {url}
```

If non-zero: exit 0, write `{ "error": "URL not reachable: {url}", "score": null }` to `ui-check-results/judge.json`. Print: `"Could not reach {url}. Is the dev server running?"`

## Step 2: Capture Screenshots

For each viewport in the list:

1. Detect Playwright: `npx playwright --version`. If it fails, execute the **Playwright not installed** graceful exit above.

2. Capture screenshot:

```bash
npx playwright screenshot --browser chromium --viewport-size "{viewport},800" "{url}" "ui-check-results/judge-screenshot-{viewport}.png"
```

## Step 3: LLM Call 1 — Critique

For each viewport screenshot, read the PNG file then perform the critique evaluation pass.

**System:** `"You only speak JSON. Do not write text that is not JSON."`

**Prompt:** Evaluate the screenshot against this rubric. Score each criterion 1–5. Return JSON only.

**Rubric:**

| Criterion | 1 | 5 |
|-----------|---|---|
| `visual_hierarchy` | No clear focal point — eye wanders | One element clearly dominates; hierarchy is immediately readable |
| `spacing_consistency` | Arbitrary spacing — not on a 4px grid | All gaps are multiples of 4px throughout |
| `color_contrast` | Text is unreadable against its background | All text passes WCAG AA visual check |
| `alignment` | Elements float with no visible grid | All elements snap to a consistent column/row grid |
| `component_state_completeness` | No hover/focus/disabled/error states visible | All interactive states are visually distinct and present |

**Expected Call 1 response schema:**

```json
{
  "criteria": [
    { "name": "visual_hierarchy", "score": 4, "justification": "string" },
    { "name": "spacing_consistency", "score": 2, "justification": "string" },
    { "name": "color_contrast", "score": 4, "justification": "string" },
    { "name": "alignment", "score": 3, "justification": "string" },
    { "name": "component_state_completeness", "score": 3, "justification": "string" }
  ],
  "top_issues": ["issue 1", "issue 2"]
}
```

If the response is not valid JSON or the LLM is unavailable, execute the **LLM unavailable** graceful exit.

## Step 4: LLM Call 2 — Localization

For the same screenshot, perform the localization pass using the critiques from Call 1.

**System:** `"You only speak JSON. Do not write text that is not JSON."`

**Prompt:** Given these UI critiques: `{top_issues from Call 1}`. Return the CSS selector or page region most affected by each issue. Return JSON only.

**Expected Call 2 response schema:**

```json
{ "affected_selectors": [".card-grid", ".btn-primary"] }
```

## Step 5: Assemble Output

**`overall_score`**: Mean of the five criterion scores, rounded to nearest integer.

**Recommendation thresholds:**
- ≤ 2 → `"Recommend revisiting before shipping"`
- 3 → `"Acceptable with noted issues"`
- ≥ 4 → `"Looking good"`

**Single-viewport** — write to `ui-check-results/judge.json`:

```json
{
  "url": "http://localhost:3000",
  "viewport": 1440,
  "overall_score": 3,
  "criteria": [
    { "name": "visual_hierarchy", "score": 4, "justification": "..." },
    { "name": "spacing_consistency", "score": 2, "justification": "..." },
    { "name": "color_contrast", "score": 4, "justification": "..." },
    { "name": "alignment", "score": 3, "justification": "..." },
    { "name": "component_state_completeness", "score": 3, "justification": "..." }
  ],
  "top_issues": ["Spacing: card gap is off-grid (13px). Use gap-3 or gap-4.", "Missing hover state on primary button."],
  "affected_selectors": [".card-grid", ".btn-primary"]
}
```

**Multi-viewport** — write per-viewport to `ui-check-results/judge-{viewport}.json` AND write combined `ui-check-results/judge.json` as an array of per-viewport result objects. `overall_score` in the combined file = average of per-viewport `overall_score` values, rounded to nearest integer.

## Step 6: Print Stdout Summary

**Single viewport:**

```
Judge: {overall_score}/5 — {recommendation}
Top issues:
  1. {top_issues[0]}
  2. {top_issues[1]}
Verdict: ui-check-results/judge.json
```

**Multi-viewport** — prefix each block with `[{viewport}px]`.

Do not print the full criteria list to stdout — it is in `judge.json`.

## Behavioral Constraint: Advisory Only

This skill always exits 0. It is a human-triggered design quality scorecard — not a CI gate, not an automated step in `/ui-check`. Do not invoke it in a loop.

Research finding: no documented production CI deployments of multimodal LLM-as-visual-judge; 77% within-one-point accuracy on a 7-point scale is insufficient for automated gating (arXiv:2510.08783). The two-call pattern is required — combining critique and localization into one call degrades critique quality (arXiv:2407.08850).
