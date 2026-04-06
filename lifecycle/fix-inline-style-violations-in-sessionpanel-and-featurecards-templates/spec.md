# Specification: Fix inline style violations in session_panel and feature_cards templates

## Problem Statement

Two dashboard templates (`session_panel.html` and `feature_cards.html`) contain inline `style=` attributes with hardcoded or undefined token values that violate the dashboard's `DESIGN.md` forbidden patterns. These violations block ticket 031 (hover states), which requires a violation-free baseline. Fixing them ensures the templates are fully compliant with the design token system.

## Requirements

1. **Replace hardcoded font-weight in session_panel.html:36**: Change `font-weight: 600` to `font-weight: var(--font-weight-semibold)` within the existing inline style attribute. Acceptance: `grep -c 'font-weight: 600' claude/dashboard/templates/session_panel.html` = 0, pass if true.

2. **Replace undefined token in feature_cards.html:76**: Change `font-size: var(--text-primary-size, 1rem)` to `font-size: var(--text-base)` within the existing inline style attribute. Acceptance: `grep -c 'text-primary-size' claude/dashboard/templates/feature_cards.html` = 0, pass if true.

3. **No visual regression**: Both fixes must produce identical or near-identical visual output. `--font-weight-semibold` maps to `600` and `--text-base` maps to `1rem`, so rendered output should not change. Interactive/session-dependent: visual regression requires rendering the dashboard in a browser.

## Non-Requirements

- Removing or converting inline `style=` attributes that correctly use `var()` CSS custom property tokens (e.g., `color: var(--color-warning)`) — these are compliant per DESIGN.md.
- Fixing inline styles in `swim-lane.html` — excluded per ticket scope (deferred to ticket 030).
- Fixing data-driven inline styles (dynamic progress bar widths on session_panel.html:33 and feature_cards.html:44) — these are template-computed values that cannot be expressed as classes.
- Creating new semantic CSS classes — the minimal fix replaces non-compliant values within existing inline styles.

## Edge Cases

- **Token value mismatch**: If `--font-weight-semibold` does not resolve to `600` or `--text-base` does not resolve to `1rem`, the visual output will change. Verify token definitions in `base.html` before applying the fix.
- **Other consumers of `--text-primary-size`**: If any other template references `--text-primary-size`, those would also need updating. Research found no other references, but a codebase grep should confirm.

## Technical Constraints

- Design tokens are defined in `claude/dashboard/templates/base.html` (lines 10-120) as CSS custom properties in a `:root` block.
- The dashboard uses Jinja2 templating with HTMX; inline styles coexist with Tailwind utility classes.
- Changes are limited to 2 lines across 2 files — no shared infrastructure or template inheritance is affected.
