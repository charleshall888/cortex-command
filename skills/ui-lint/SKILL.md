---
name: ui-lint
description: Run ESLint and Stylelint in auto-fix-then-report mode and write results to ui-check-results/lint.json. Use when user says "/ui-lint", "lint the UI", "run UI linting", "check frontend lint", or asks to fix and report frontend code style issues.
disable-model-invocation: true
inputs:
  - "target: string (optional) — path or glob to lint; defaults to src"
outputs:
  - "ui-check-results/lint.json — compact JSON with ESLint and Stylelint results"
  - "exit code — non-zero when failure_count > 0, zero when failure_count === 0"
preconditions:
  - "Run from project root"
  - "eslint must be installed in node_modules"
  - "eslint-plugin-tailwindcss (Tailwind v3) or @poupe/eslint-plugin-tailwindcss (Tailwind v4) must be installed"
  - "eslint-plugin-jsx-a11y must be installed"
  - "callees: [\"cn\", \"clsx\", \"cva\", \"classnames\"] must appear in the ESLint Tailwind plugin settings"
  - "stylelint must be installed"
  - "stylelint-plugin-rhythmguard must be installed"
  - "ui-check-results/ directory will be created if absent"
---

# UI Lint

Run ESLint and Stylelint in auto-fix-then-report mode. Write compact JSON results to `ui-check-results/lint.json`. Exit with the total failure count as the signal.

## Preconditions

The target project must have the following npm packages installed:

- `eslint`
- `eslint-plugin-tailwindcss` (Tailwind v3) or `@poupe/eslint-plugin-tailwindcss` (Tailwind v4)
- `eslint-plugin-jsx-a11y`
- `stylelint`
- `stylelint-plugin-rhythmguard`

The ESLint Tailwind plugin configuration must include `callees: ["cn", "clsx", "cva", "classnames"]` to detect class merging utilities.

## Detection

Before running, detect the Tailwind version and config:

**Tailwind version detection:** Read `package.json`. Check `dependencies.tailwindcss` and `devDependencies.tailwindcss`. If the version string starts with `4` or `^4`, select `@poupe/eslint-plugin-tailwindcss`. Otherwise select `eslint-plugin-tailwindcss`.

**Tailwind config detection:** Check whether `tailwind.config.js`, `tailwind.config.ts`, or `tailwind.config.mjs` exists, OR whether `globals.css` contains `@theme`. If neither is found, skip Tailwind-specific rules and warn: "No Tailwind config detected — skipping Tailwind rules. jsx-a11y rules still apply."

Report which plugin was selected at the start of output.

**Stylelint plugin config detection:** Look for the project's stylelint config file: `.stylelintrc`, `.stylelintrc.json`, `.stylelintrc.js`, `stylelint.config.js`, or a `stylelint` key in `package.json`. If a stylelint config is found, check whether `stylelint-plugin-rhythmguard` appears in the config's `plugins` array. If the plugin is NOT present in the config (even if it exists in `node_modules`), print: `"Warning: stylelint-plugin-rhythmguard not found in stylelint config — 8px grid rules will not run. Add the plugin to your stylelint config."` and skip the Stylelint pass (Step 4) for this run.

**ESLint Tailwind callees config detection:** Look for the project's ESLint config file: `.eslintrc.json`, `.eslintrc.js`, `eslint.config.js`, `eslint.config.mjs`, or an `eslint` key in `package.json`. If a config is found, search for `callees` in the Tailwind plugin settings. If `callees` is NOT found, print: `"Warning: callees not configured in ESLint Tailwind plugin settings — violations inside cn()/clsx()/cva() calls will not be detected. Add callees: [\"cn\", \"clsx\", \"cva\", \"classnames\"] to the tailwindcss plugin options."` Continue running — this is an advisory warning only, not a fatal error.

## Workflow

Execute the following 6 steps in order. Do not loop. Do not re-run after reporting.

### Step 1: Create output directory

```bash
mkdir -p ui-check-results
```

### Step 2: ESLint auto-fix pass

Run ESLint with `--fix` using the detected plugin. Use `{{target}}` as the source glob (default: `src`).

```bash
npx eslint --fix {{target}} || true
```

This modifies files in place. Record any files changed. Count of violations before this step minus violations after is `autofixed_count` — compute it in Step 4.

ESLint rules to enforce:
- `tailwindcss/no-arbitrary-value: "error"` — forbid arbitrary CSS values in class strings
- `tailwindcss/no-contradicting-classname: "error"` — forbid conflicting utility classes
- `tailwindcss/no-unnecessary-arbitrary-value: "warn"` — warn when a token exists for an arbitrary value
- Full `eslint-plugin-jsx-a11y` recommended ruleset — covers missing alt text, unlabeled inputs, heading hierarchy, interactive element roles

### Step 3: ESLint report pass

Run ESLint in report mode (no fix) against the same glob and capture JSON output:

```bash
npx eslint --format json {{target}} > ui-check-results/eslint-raw.json 2>/dev/null || true
```

Parse `ui-check-results/eslint-raw.json`. Extract:
- `errorCount`: total across all `results[].errorCount`
- `warningCount`: total across all `results[].warningCount`
- Per-violation entries from `results[].messages`: file path, line, rule id, message

### Step 4: Stylelint pass

Check whether any `*.css` files exist in the project:

```bash
ls **/*.css 2>/dev/null | head -1
```

If no CSS files are found, skip this step cleanly — no output, no failure.

If CSS files exist, run Stylelint:

```bash
npx stylelint "**/*.css" --formatter json > ui-check-results/stylelint-raw.json 2>/dev/null || true
```

Parse `ui-check-results/stylelint-raw.json`. Extract violations (rule, severity, text, line, source) and merge into the shared `failures` array.

### Step 5: Compute counts and build output

Compute:
- `failure_count`: total ESLint errors + ESLint warnings + Stylelint warnings
- `autofixed_count`: violations eliminated by the `--fix` pass; approximate as (violations reported before fix) - (violations reported after fix). If a before-fix count is not available, set to 0.
- `passed`: `true` if `failure_count === 0`, otherwise `false`

Build the `failures` array. Each entry:

```json
{ "file": "<relative path>", "line": <int>, "rule": "<rule-id>", "message": "<message>" }
```

### Step 6: Write output JSON

Write `ui-check-results/lint.json` with this exact schema:

```json
{
  "passed": <bool>,
  "autofixed_count": <int>,
  "failure_count": <int>,
  "failures": [
    { "file": "<str>", "line": <int>, "rule": "<str>", "message": "<str>" }
  ]
}
```

Example for a passing run with auto-fixes:

```json
{ "passed": true, "autofixed_count": 3, "failure_count": 0, "failures": [] }
```

Example for a failing run:

```json
{
  "passed": false,
  "autofixed_count": 1,
  "failure_count": 2,
  "failures": [
    { "file": "src/components/Button.tsx", "line": 14, "rule": "tailwindcss/no-arbitrary-value", "message": "Arbitrary value [#3b82f6] is not allowed. Use a design token instead." },
    { "file": "src/components/Card.tsx", "line": 8, "rule": "jsx-a11y/alt-text", "message": "img elements must have an alt prop." }
  ]
}
```

## Behavioral Constraint: No Iterative Loop

This skill runs ESLint exactly once in auto-fix mode (Step 2) and exactly once in report mode (Step 3). It does NOT run ESLint a second time after reporting, does NOT re-check after writing results, and does NOT loop based on failure count.

The agent reads `ui-check-results/lint.json` once and acts on the results. Do not re-invoke this skill in a loop based on the contents of `lint.json`.

Iterative lint-fix-recheck loops produce in-context reward hacking where agents optimize for the linter metric rather than actual code quality, leading to hidden failures (arXiv:2402.06627). This constraint is a correctness requirement, not a style preference.

## Stdout Format

Print exactly one summary line to stdout after writing `lint.json`:

```
Lint: <failure_count> failures (<autofixed_count> autofixed) — see ui-check-results/lint.json
```

Examples:

```
Lint: 0 failures (3 autofixed) — see ui-check-results/lint.json
Lint: 2 failures (1 autofixed) — see ui-check-results/lint.json
Lint: 5 failures (0 autofixed) — see ui-check-results/lint.json
```

Do not print full violation details to stdout. They are in `lint.json`.

## Exit Codes

- `0` — `failure_count === 0` (passes even if `autofixed_count > 0`)
- non-zero — `failure_count > 0`; use `failure_count` as the exit value
