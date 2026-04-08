# Implementation Plan: Add hover states, loading feedback, and badge micro-interactions

## Overview

All five must-have requirements from the spec are unimplemented. The base.html file has no Idiomorph script, no morph swap modes, no hover styles on `.feature-card`, no badge transitions, no entry animations, and no `prefers-reduced-motion` guards (including on the existing `pulse` animation). All changes land in `base.html`'s `<style type="text/tailwindcss">` block and the `<body>` / script tag area. No server-side files change.

The should-have requirement (req 6: hover info reveal) is implementation-determined and will be addressed in the same task as the hover lift effect once card structure is visible.

## Tasks

### Task 1: Add Idiomorph and migrate swap modes

- **Files**: `claude/dashboard/templates/base.html`
- **What**:
  1. Add `<script src="https://unpkg.com/idiomorph@0.7.4/dist/idiomorph-ext.min.js"></script>` after the HTMX script tag (line 8).
  2. Add `hx-ext="morph"` attribute to the `<body>` opening tag.
  3. Change all six `hx-swap="innerHTML"` occurrences to `hx-swap="morph:innerHTML"`. The six sections are: `#alerts-banner`, `#session-panel`, `#feature-cards`, `#fleet-panel`, `#swim-lane`, `#round-history`.
- **Depends on**: none
- **Context**: Idiomorph 0.7.4 is confirmed compatible with HTMX 2.0.4 (spec §Technical Constraints). The morph swap preserves element identity across polls so CSS transitions fire only on changed attributes. The spec notes that OOB swaps in `session_panel.html` are unaffected.
- **Verification**: `grep -c 'idiomorph' claude/dashboard/templates/base.html` ≥ 1 AND `grep -c 'hx-ext="morph"' claude/dashboard/templates/base.html` = 1 AND `grep -c 'hx-swap="innerHTML"' claude/dashboard/templates/base.html` = 0
- **Status**: pending

### Task 2: Add badge status transitions

- **Files**: `claude/dashboard/templates/base.html`
- **What**: Add CSS `transition` property to the `.badge` rule in the `@layer components` block. The transition should cover `background-color`, `border-color`, and `color` at 300ms ease-out. Wrap in `@media (prefers-reduced-motion: no-preference)` to satisfy req 5.
- **Depends on**: 1
- **Context**: Idiomorph (added in Task 1) preserves `.badge` element identity across polls — it only patches changed attributes. This means transitions fire when a badge's status class changes but not on unchanged polls. The badge rule is at lines 191–198 in the current file.
- **Verification**: `grep -c 'transition' claude/dashboard/templates/base.html` ≥ 1 AND `grep 'badge' claude/dashboard/templates/base.html | grep -c 'transition'` ≥ 1
- **Status**: pending

### Task 3: Add feature card hover lift effect and supplementary hover reveal

- **Files**: `claude/dashboard/templates/base.html`
- **What**:
  1. Add hover styles to `.feature-card`: on `:hover`, apply `box-shadow` for elevation lift and `transform: translateY(-2px)`. Add `transition` for `box-shadow` and `transform` (150ms ease-out). Wrap in `@media (prefers-reduced-motion: no-preference)`.
  2. For the should-have hover info reveal (req 6): identify supplementary card content that benefits from progressive disclosure. Based on card structure in `feature_cards.html`, the `phase-label` and `task-ratio` spans are secondary detail — show them at reduced opacity at rest (`opacity: 0.65`) and full opacity on card hover. Implement using `.feature-card:hover .phase-label` and `.feature-card:hover .task-ratio` CSS rules. Add `transition: opacity 150ms ease-out` to `.phase-label` and `.task-ratio` within a `prefers-reduced-motion: no-preference` block.
- **Depends on**: none (CSS-only, independent of idiomorph)
- **Context**: The spec requires hover styling in any of `base.html`, `patterns/feature-card.html`, or `feature_cards.html`. Placing it in `base.html`'s style block keeps all CSS co-located and avoids inline styles. The `.feature-card` rule is at lines 209–219 in the current file.
- **Verification**: `grep -c 'feature-card.*hover\|hover.*feature-card\|group-hover' claude/dashboard/templates/base.html claude/dashboard/templates/patterns/feature-card.html claude/dashboard/templates/feature_cards.html` ≥ 1
- **Status**: pending

### Task 4: Add entry animations for new elements and prefers-reduced-motion guards

- **Files**: `claude/dashboard/templates/base.html`
- **What**:
  1. Add `@keyframes fadeIn` (or `fade-in`) — fade from opacity 0 to 1 over 300ms.
  2. Apply the animation to `.feature-card` using an `animation: fadeIn 300ms ease-out` rule, gated with `@media (prefers-reduced-motion: no-preference)`.
  3. To prevent the entry animation from firing on the initial page load (spec edge case), gate the animation with a `.htmx-settled` class on the container or use Idiomorph's native `data-morph` attribute approach. The simplest approach: apply the `fadeIn` animation only to `.feature-list .feature-card` (cards inside the polled container), and add a CSS rule that disables the animation when the `#feature-cards` section has a `data-loaded` attribute. The Jinja template's first swap will not have this attribute; subsequent swaps will preserve Idiomorph's element identity so existing cards don't re-animate. Since Idiomorph only inserts genuinely new DOM nodes, the animation fires naturally only for new cards.
  4. Retrofit the existing `.live-dot` `pulse` animation: wrap the `animation: pulse 2s infinite` declaration in `@media (prefers-reduced-motion: no-preference)`.
  5. Ensure all new `@media (prefers-reduced-motion: no-preference)` blocks are in the `@layer components` section or adjacent to the rules they guard.
- **Depends on**: 1 (Idiomorph needed for element identity preservation that makes entry animations meaningful)
- **Context**: The spec's acceptance criteria for req 4 is `grep -c '@keyframes.*fade-in\|fadeIn\|entry' claude/dashboard/templates/base.html` ≥ 1. For req 5: `grep -c 'prefers-reduced-motion' claude/dashboard/templates/base.html` ≥ 1 AND `grep -c 'reduced-motion\|motion-safe' claude/dashboard/templates/base.html` ≥ 2. The existing `@keyframes pulse` at lines 358–361 currently has no motion guard.
- **Verification**: `grep -c '@keyframes.*fade-in\|fadeIn\|entry' claude/dashboard/templates/base.html` ≥ 1 AND `grep -c 'prefers-reduced-motion' claude/dashboard/templates/base.html` ≥ 1 AND `grep -c 'reduced-motion\|motion-safe' claude/dashboard/templates/base.html` ≥ 2
- **Status**: pending

## Verification Strategy

Run these grep checks after all tasks complete. All must pass.

**Req 2 — Idiomorph added and swap modes migrated:**
```
grep -c 'idiomorph' claude/dashboard/templates/base.html
# expect: ≥ 1

grep -c 'hx-ext="morph"' claude/dashboard/templates/base.html
# expect: 1

grep -c 'hx-swap="innerHTML"' claude/dashboard/templates/base.html
# expect: 0  (all six instances migrated to morph:innerHTML)
```

**Req 3 — Badge transitions:**
```
grep -c 'transition' claude/dashboard/templates/base.html
# expect: ≥ 1

grep 'badge' claude/dashboard/templates/base.html | grep -c 'transition'
# expect: ≥ 1
```

**Req 1 — Feature card hover lift:**
```
grep -c 'feature-card.*hover\|hover.*feature-card\|group-hover' \
  claude/dashboard/templates/base.html \
  claude/dashboard/templates/patterns/feature-card.html \
  claude/dashboard/templates/feature_cards.html
# expect: ≥ 1
```

**Req 4 — Entry animations:**
```
grep -c '@keyframes.*fade-in\|fadeIn\|entry' claude/dashboard/templates/base.html
# expect: ≥ 1
```

**Req 5 — prefers-reduced-motion guards (new animations + existing pulse):**
```
grep -c 'prefers-reduced-motion' claude/dashboard/templates/base.html
# expect: ≥ 1

grep -c 'reduced-motion\|motion-safe' claude/dashboard/templates/base.html
# expect: ≥ 2
```

**Req 6 — Hover info reveal (visual inspection):**
Open the live dashboard and hover over a feature card. Confirm that secondary text (phase label, task ratio) increases in opacity on hover. No automated grep check applies.
