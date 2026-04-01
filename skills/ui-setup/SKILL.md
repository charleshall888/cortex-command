---
name: ui-setup
description: One-time project setup guide for the UI design enforcement toolchain. Reads package.json, detects what's installed, and outputs a checklist with install commands and config snippets for missing items. Use when user says "/ui-setup", "set up UI toolchain", "configure design enforcement", "set up frontend toolchain", or wants to configure ESLint, Prettier, Husky, Stylelint, shadcn, or Playwright for a new project.
disable-model-invocation: true
---

# /ui-setup

Detect UI design enforcement toolchain status for this project. Read project files, then output a `✓`/`✗` checklist with exact install commands and config snippets for missing items. Do not run commands or write files — this skill guides, the human or agent executes.

## Step 1: Read project state

Read `package.json` at the project root. Combine `dependencies` and `devDependencies` into an installed set.

If `package.json` does not exist: exit with "No package.json found — run /ui-setup from the project root."

**Tailwind plugin selection**: check `tailwindcss` version string. If it starts with `4` or `^4`, select `@poupe/eslint-plugin-tailwindcss`; otherwise select `eslint-plugin-tailwindcss`.

**CSS detection**: check whether any `.css` files exist outside `node_modules`. If none, the Stylelint item is not applicable.

## Step 2: Evaluate each checklist item

### A. shadcn/ui initialized

Check: `components.json` present at project root?

If ✗: `npx shadcn@latest init` (recommend new-york style, Base UI or Radix backend)

### B. shadcn MCP (always output — cannot auto-detect)

This is a one-time IDE configuration step. Output the instructions regardless of detected state.

Run once: `npx shadcn@latest mcp`

Then add to IDE settings:

**Claude Code** (`.claude/settings.json` or `~/.claude/settings.json`):
```json
{ "mcpServers": { "shadcn": { "command": "npx", "args": ["shadcn@latest", "mcp"] } } }
```

### C. ESLint

Check for: the selected Tailwind ESLint plugin, `eslint-plugin-jsx-a11y`, and an ESLint config (`eslint.config.mjs`, `eslint.config.js`, `.eslintrc.json`) containing `no-arbitrary-value: "error"` and `jsx-a11y` recommended rules.

If packages missing: `npm install -D <selected-tailwind-plugin> eslint-plugin-jsx-a11y`

If config missing or incomplete, provide this flat config snippet (substitute the actual plugin name):
```js
import tailwind from "<selected-tailwind-plugin>";
import jsxA11y from "eslint-plugin-jsx-a11y";

export default [
  tailwind.configs["flat/recommended"],
  jsxA11y.flatConfigs.recommended,
  {
    rules: {
      "tailwindcss/no-arbitrary-value": "error",
      "tailwindcss/no-contradicting-classname": "error",
      "tailwindcss/no-unnecessary-arbitrary-value": "warn",
    },
  },
];
```

### D. Stylelint

Skip and note "not applicable" if no CSS files detected in Step 1.

Check for: `stylelint`, `stylelint-plugin-rhythmguard`, and a Stylelint config (`.stylelintrc.json`, `stylelint.config.js`).

If packages missing: `npm install -D stylelint stylelint-plugin-rhythmguard`

If config missing:
```json
{
  "plugins": ["stylelint-plugin-rhythmguard"],
  "rules": {
    "rhythmguard/spacing-grid": [true, { "grid": 8 }]
  }
}
```
(write to `.stylelintrc.json`)

### E. Prettier

Check for `prettier-plugin-tailwindcss` in installed packages and a Prettier config (`prettier.config.mjs`, `prettier.config.js`, `.prettierrc.json`) that references it.

If package missing: `npm install -D prettier prettier-plugin-tailwindcss`

If config missing or plugin not referenced, add to `prettier.config.mjs`:
```js
export default { plugins: ["prettier-plugin-tailwindcss"] };
```

### F. Pre-commit hook

Check for `husky` or `lint-staged` in installed packages and a `.husky/pre-commit` script that runs Prettier and ESLint fix passes.

If missing:
```bash
npm install -D husky lint-staged
npx husky init
```

Add to `.husky/pre-commit`:
```bash
npx lint-staged
```

Add to `package.json`:
```json
"lint-staged": {
  "*.{js,jsx,ts,tsx}": ["prettier --write", "eslint --fix"]
}
```

### G. ui-check-results/ gitignore

Check `.gitignore` for a `ui-check-results/` or `ui-check-results` line.

If missing: add `ui-check-results/` to `.gitignore`.

### H. Playwright

Check the combined dependencies for both `@playwright/test` and `@axe-core/playwright`.

Note: the bare `playwright` package is insufficient — `@playwright/test` is the required test runner package. If only `playwright` is present (without `@playwright/test`), treat as ✗.

If ✓: `✓  Playwright (@playwright/test + @axe-core/playwright)` — do not show browser install step.

If ✗: `✗  Playwright` followed by:
```bash
npm install -D @playwright/test @axe-core/playwright
npx playwright install chromium
```

## Step 3: Output

Print a summary header line, then one entry per item:

- `✓  <item-name>` for configured items
- `✗  <item-name>` followed by the exact command or config snippet on the next lines

Item B (shadcn MCP) always prints its instructions — mark it as a manual step rather than ✓/✗.

End with a count: `N/8 items configured.` (exclude item B from the count since it cannot be auto-detected).

If all detectable items are configured, close with:
> All detectable items configured. shadcn MCP requires a one-time manual IDE step (see B above). Next: run `/ui-brief` to generate `DESIGN.md` and design tokens, then `/ui-lint` after building components to verify token conformance.
