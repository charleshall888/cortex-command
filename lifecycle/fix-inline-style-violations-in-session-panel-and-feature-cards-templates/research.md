# Research: Fix inline style violations in session_panel and feature_cards templates

## Codebase Analysis

### DESIGN.md Prohibition Scope

The dashboard's `DESIGN.md` (`claude/dashboard/DESIGN.md`) does **not** prohibit all inline `style=` attributes. The Forbidden Patterns section specifically targets:

1. Raw hex color values (e.g., `style="color: #7d8590"`)
2. Hardcoded non-token values where design tokens exist (e.g., raw font-weight numbers when `--font-weight-*` tokens are available)
3. Arbitrary Tailwind values (e.g., `p-[13px]`, `text-[#ff0000]`)

Inline styles using `var(--color-*)` and `var(--text-*)` CSS custom properties are the **recommended** approach per DESIGN.md. Using `var()` in a `style=` attribute is not a violation.

### Inline Styles Inventory

#### session_panel.html

| Line | Style | Classification |
|------|-------|---------------|
| 33 | `width: {{ ((ns.merged + ns.running * 0.5) / total * 100) \| int if total > 0 else 0 }}%` | **Data-driven** — dynamic progress bar width computed from template variables. Not a violation; cannot be expressed as a class. |
| 36 | `color: var(--color-warning); font-weight: 600;` | **Partial violation** — `color: var(--color-warning)` is correct token usage. `font-weight: 600` is a hardcoded value; should use `var(--font-weight-semibold)` or a semantic class. |
| 44 | `color: var(--color-warning);` | **Not a violation** — uses CSS custom property token correctly per DESIGN.md. |

#### feature_cards.html

| Line | Style | Classification |
|------|-------|---------------|
| 44 | `width: {% if plan_prog[1] > 0 %}{{ (plan_prog[0] / plan_prog[1] * 100) \| int }}{% else %}0{% endif %}%` | **Data-driven** — dynamic progress bar width computed from template variables. Not a violation; cannot be expressed as a class. |
| 76 | `font-size: var(--text-primary-size, 1rem); color: var(--color-error);` | **Partial violation** — `color: var(--color-error)` is correct token usage. `font-size: var(--text-primary-size, 1rem)` references an undefined token (`--text-primary-size` does not exist in the token system); the `1rem` fallback is what actually renders. Should use a defined token like `--text-base`. |

### Available Design Tokens

Defined in `claude/dashboard/templates/base.html`:

**Color tokens**: `--color-warning`, `--color-error`, `--color-success`, `--color-text-primary`, `--color-text-secondary`, etc.

**Typography tokens**: `--text-xs`, `--text-sm`, `--text-base`, `--text-md`, `--text-lg`, `--text-xl` through `--text-4xl`

**Font weight tokens**: `--font-weight-normal`, `--font-weight-medium`, `--font-weight-semibold`, `--font-weight-bold`

**Notable**: `--text-primary-size` is NOT defined. The closest match is `--text-base`.

### Existing Patterns in Other Templates

- Other dashboard templates (base.html, session_detail.html, fleet-panel.html, sessions_list.html) use semantic token classes exclusively — no raw hex or hardcoded values.
- swim-lane.html uses inline styles for dynamic positioning (percentages, absolute positioning) — these are data-driven and acceptable per DESIGN.md.
- The `.phase-label` class provides `color` and `font-size` styling for metadata text.
- Token utility classes like `.text-text-secondary` are available for color styling.

### Scope Revision

The ticket assumed all 5 inline `style=` attributes across the two files are violations. Research shows only **2 actual violations** (partial violations on lines with mixed valid/invalid properties):

1. **session_panel.html:36** — `font-weight: 600` should use a token
2. **feature_cards.html:76** — `font-size: var(--text-primary-size, 1rem)` references an undefined token

The remaining 3 inline styles are either data-driven (progress bars) or correctly use CSS custom property tokens per DESIGN.md.

### Recommended Approach

For each partial violation, the fix is to replace only the non-compliant property within the inline style:

1. **session_panel.html:36**: Replace `font-weight: 600` with `font-weight: var(--font-weight-semibold)` — or extract to a utility class if one exists for semibold text.
2. **feature_cards.html:76**: Replace `var(--text-primary-size, 1rem)` with `var(--text-base)` (the defined token equivalent).

Alternatively, if the goal is to eliminate inline `style=` attributes entirely (stricter than DESIGN.md requires), each could be converted to a semantic class. But DESIGN.md does not require this for `var()` references.

## Open Questions

- ~~Should the fix be minimal or maximal?~~ **Resolved**: Minimal — fix only the 2 actual DESIGN.md violations. `var()` inline styles are compliant per the design system and should be left as-is. DESIGN.md intentionally endorses `var()` in inline styles as the recommended approach.
