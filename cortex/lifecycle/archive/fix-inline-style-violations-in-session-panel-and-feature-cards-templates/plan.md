# Plan: Fix inline style violations in session_panel and feature_cards templates

## Overview

Replace two DESIGN.md-violating inline style values across two dashboard templates: a hardcoded `font-weight: 600` in session_panel.html and an undefined token reference `var(--text-primary-size, 1rem)` in feature_cards.html. Each fix substitutes the non-compliant value with the equivalent defined design token within the existing inline `style=` attribute. The surrounding compliant `var()` properties are left untouched.

## Tasks

### Task 1: Replace hardcoded font-weight in session_panel.html
- **Files**: `claude/dashboard/templates/session_panel.html`
- **What**: On line 36, change `font-weight: 600` to `font-weight: var(--font-weight-semibold)` within the existing inline style attribute. The `color: var(--color-warning)` property on the same element is compliant and must not be changed.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: `--font-weight-semibold: 600` is defined in `base.html` line 76, so rendered output is identical. The current line reads: `<span style="color: var(--color-warning); font-weight: 600;">{{ ns.failed }} failed</span>`. After the fix it should read: `<span style="color: var(--color-warning); font-weight: var(--font-weight-semibold);">{{ ns.failed }} failed</span>`.
- **Verification**: `grep -c 'font-weight: 600' claude/dashboard/templates/session_panel.html` -- pass if output is `0`
- **Status**: [ ] not started

### Task 2: Replace undefined token in feature_cards.html
- **Files**: `claude/dashboard/templates/feature_cards.html`
- **What**: On line 76, change `font-size: var(--text-primary-size, 1rem)` to `font-size: var(--text-base)` within the existing inline style attribute. The `color: var(--color-error)` property on the same element is compliant and must not be changed.
- **Depends on**: none
- **Complexity**: trivial
- **Context**: `--text-primary-size` is not defined in the token system; the `1rem` fallback is what actually renders. `--text-base: 1rem` is defined in `base.html` line 65, so the replacement produces identical rendered output. The current line reads: `<span style="font-size: var(--text-primary-size, 1rem); color: var(--color-error);">`. After the fix it should read: `<span style="font-size: var(--text-base); color: var(--color-error);">`.
- **Verification**: `grep -c 'text-primary-size' claude/dashboard/templates/feature_cards.html` -- pass if output is `0`
- **Status**: [ ] not started

### Task 3: Confirm no remaining violations in changed files
- **Files**: (none -- verification only)
- **What**: Run a grep across both templates to confirm no hardcoded font-weight values and no undefined token references remain.
- **Depends on**: [1, 2]
- **Complexity**: trivial
- **Context**: The spec acceptance criteria require zero matches for `font-weight: 600` in session_panel.html and zero matches for `text-primary-size` in feature_cards.html. This task also checks that no new violations were accidentally introduced.
- **Verification**: `grep -cE 'font-weight: [0-9]' claude/dashboard/templates/session_panel.html` -- pass if output is `0`; `grep -c 'text-primary-size' claude/dashboard/templates/feature_cards.html` -- pass if output is `0`
- **Status**: [ ] not started

## Verification Strategy

After all tasks complete, run the spec's acceptance criteria:
1. `grep -c 'font-weight: 600' claude/dashboard/templates/session_panel.html` -- must output `0`
2. `grep -c 'text-primary-size' claude/dashboard/templates/feature_cards.html` -- must output `0`
3. Visual spot-check: both `--font-weight-semibold` (= 600) and `--text-base` (= 1rem) resolve to the same values as the originals, so no visual regression is expected
