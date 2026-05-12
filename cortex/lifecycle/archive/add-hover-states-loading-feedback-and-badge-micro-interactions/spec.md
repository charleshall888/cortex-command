# Specification: Add hover states, loading feedback, and badge micro-interactions

## Problem Statement

The overnight dashboard has no visual feedback for user interaction or state changes — feature cards have no hover response, status badge color changes are instantaneous and jarring when HTMX replaces content, and there is no indication when polled content actually updates. These gaps reduce the dashboard's effectiveness as a monitoring tool by making state changes hard to notice and the interface feel inert. Adding micro-interactions closes quality gaps identified against the operational usefulness rubric (ticket 033 epic).

## Requirements

### Must-have

1. **Feature card hover lift effect**: Feature cards display a lift effect on hover using shadow elevation and vertical translate, with a smooth transition. Acceptance: `grep -c 'feature-card.*hover\|hover.*feature-card\|group-hover' claude/dashboard/templates/base.html claude/dashboard/templates/patterns/feature-card.html claude/dashboard/templates/feature_cards.html` ≥ 1 (hover styling may be in CSS rules or Tailwind utility classes in any of these files).

2. **Idiomorph extension added dashboard-wide**: Add the Idiomorph HTMX extension (`idiomorph@0.7.4` via unpkg CDN) and enable it on the `<body>` element with `hx-ext="morph"`. Change all six polling section swap modes from `hx-swap="innerHTML"` to `hx-swap="morph:innerHTML"`. Idiomorph diffs new HTML against existing DOM and only patches differences — unchanged content is left untouched, so CSS transitions only fire when element attributes actually change. Acceptance: `grep -c 'idiomorph' claude/dashboard/templates/base.html` ≥ 1 AND `grep -c 'hx-ext="morph"' claude/dashboard/templates/base.html` = 1 AND `grep -c 'hx-swap="innerHTML"' claude/dashboard/templates/base.html` = 0 (six existing instances must all be migrated).

3. **Badge status transitions**: Add CSS transitions on `.badge` class for `background-color`, `border-color`, and `color` properties (300ms ease-out). Idiomorph preserves badge element identity across swaps and only patches attributes that changed, so transitions fire naturally when status changes and not on unchanged polls. Acceptance: `grep -c 'transition' claude/dashboard/templates/base.html` ≥ 1 AND `grep 'badge' claude/dashboard/templates/base.html | grep -c 'transition'` ≥ 1.

4. **Element-level entry animations**: When Idiomorph inserts new elements (e.g., a new feature card appears, a new alert badge is added) or removes elements, apply CSS entry animations to the newly added elements. Use `@keyframes` for fade-in on new elements. Idiomorph natively adds/removes elements as part of its diff — this requirement adds visual transitions to those structural changes. Acceptance: `grep -c '@keyframes.*fade-in\|fadeIn\|entry' claude/dashboard/templates/base.html` ≥ 1.

5. **prefers-reduced-motion support**: Wrap all new animations and transitions with Tailwind `motion-safe:` prefix or `@media (prefers-reduced-motion: no-preference)`. Retrofit the existing `.live-dot` pulse animation with the same guard. Acceptance: `grep -c 'prefers-reduced-motion' claude/dashboard/templates/base.html` ≥ 1 AND `grep -c 'reduced-motion\|motion-safe' claude/dashboard/templates/base.html` ≥ 2 (at least one for new animations, at least one covering the existing pulse).

### Should-have

6. **Feature card hover info reveal**: On hover, reveal supplementary information on feature cards that is hidden at rest to reduce visual density. Specific content to reveal is determined during implementation based on which card elements benefit most from progressive disclosure. Acceptance: Interactive/session-dependent — requires visual inspection of hover behavior in a running dashboard; the specific elements are implementation-determined.

## Non-Requirements

- **Shimmer skeleton loader**: Explicitly excluded. The dashboard polls local files with near-zero latency; a shimmer animation on every 5s poll would be visual noise with no informational value.
- **Server-side state hashing**: Not needed. Idiomorph's DOM diffing already handles change detection at the element level — unchanged elements are not modified, so transitions don't fire on unchanged content. No changes to `app.py` are required.
- **Client-side swap skip (htmx:beforeSwap)**: Not needed for the same reason. No JavaScript event handlers are added.
- **Interactive card actions**: Feature cards are read-only status displays. No buttons, links, or triggerable actions are added.
- **Touch/mobile interaction states**: The dashboard is a desktop monitoring tool accessed via browser. Touch-specific hover alternatives are out of scope.
- **View Transitions API**: Limited browser support (no Firefox/Safari). Not adopted; Idiomorph morph swap provides the needed DOM preservation.
- **HTMX version upgrade**: The dashboard remains on HTMX 2.0.4. No version bump is part of this feature.

## Edge Cases

- **Idiomorph CDN unavailable**: If the Idiomorph script fails to load, `hx-swap="morph:innerHTML"` falls back to standard `innerHTML` swap (HTMX ignores unknown swap modifiers). Badge transitions and entry animations will not fire (elements replaced instead of morphed), but the dashboard remains functional. No explicit fallback code needed.
- **Empty feature list**: When no overnight session is active, the feature-cards section renders empty. Hover states have no effect (nothing to hover). No special handling needed.
- **Multiple status changes within one poll interval**: Only the final state is rendered. A feature going pending → running → failed within 5s shows only the failed badge with no intermediate transitions. This is acceptable — the dashboard reflects point-in-time state, not a transition log.
- **Existing out-of-band swap**: `session_panel.html` uses `hx-swap-oob="true"` for the live indicator. Idiomorph's morph extension does not interfere with OOB swaps — OOB uses `outerHTML` swap style which bypasses the morph extension's `isInlineSwap` check. The OOB live indicator continues to work as before.
- **Entry animation on initial page load**: On the first HTMX response, Idiomorph inserts all elements (since the container is empty or has placeholder text). Entry animations should not fire on initial load — only on subsequent polls where new elements appear. Use a CSS class or data attribute set after the first swap to gate entry animations.

## Technical Constraints

- **HTMX 2.0.4**: Dashboard uses HTMX 2.0.4 loaded from unpkg CDN. Idiomorph extension (`idiomorph@0.7.4`) is confirmed compatible with the 2.x line.
- **CSS location**: All styles live in `base.html`'s `<style type="text/tailwindcss">` block (lines 10-379). New styles go in this block.
- **Tailwind utilities or CSS custom properties only**: No inline `style=` attributes. This aligns with blocker ticket 034's violation-free baseline.
- **No server-side changes**: All changes are in templates and CSS. `app.py` and `poller.py` are not modified.
- **Polling interval unchanged**: HTMX polling remains at 5s (`hx-trigger="load, every 5s"`). Idiomorph's DOM diffing handles the change detection that was previously proposed as a server-side hash.

## Open Decisions

None — all decisions resolved during spec interview and critical review.
