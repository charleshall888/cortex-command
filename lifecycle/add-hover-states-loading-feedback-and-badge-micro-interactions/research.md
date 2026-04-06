# Research: Add hover states, loading feedback, and badge micro-interactions

## Codebase Analysis

### Dashboard Template Structure

All templates live in `claude/dashboard/templates/`. Key files for this feature:

- `base.html` — Master layout containing all CSS (embedded `<style type="text/tailwindcss">` block, lines 10-379), HTMX polling configuration (lines 395-417), and section containers
- `feature_cards.html` — Feature card list (108 lines), iterates over features and renders cards with status/model/complexity badges, progress bars, alert badges
- `patterns/feature-card.html` — Macro defining the `.feature-card` container (flex column, border, padding)
- `patterns/badge.html` — Macro for status badges: `<span class="badge {{ css_class }}">{{ label }}</span>`
- `session_panel.html`, `fleet-panel.html`, `swim-lane.html`, `alerts_banner.html`, `round_history.html`, `pipeline_panel.html` — Other polling sections

### HTMX Polling Implementation

All six polling sections use identical configuration:
```html
hx-trigger="load, every 5s"
hx-swap="innerHTML"
```

Polling endpoints are defined in `app.py` (lines 252-316). Each `<section>` tag has a stable `id` — HTMX replaces inner children on every poll, preserving the container element. No swap delay, settle delay, or transition configuration exists.

One out-of-band swap exists: `session_panel.html` line 2 uses `hx-swap-oob="true"` to update the header's live indicator independently.

### Feature Card Structure

```
.feature-card (flex column, gap 0.35rem)
  ├── .card-row: title + phase-label + status badge + model badge + complexity badge
  ├── .card-row: phase-specific content (progress bar, elapsed time, error text)
  ├── .card-row: alert badges (deferred, slow, rework, stall, failed)
  └── .card-row (failed only): recovery attempt count
```

Running cards get a left border accent: `.feature-card--running { border-left: 3px solid var(--color-brand-primary); }`

No hover states, transitions, or interactive elements exist on cards.

### Badge System

Badge CSS (`base.html` lines 191-204):
```css
.badge { display: inline-block; padding: 0.15em 0.5em; border-radius: 4px; font-size: var(--text-xs); font-weight: var(--font-weight-semibold); color: var(--color-status-on-badge); }
.badge-green  { background-color: var(--color-status-green); }
.badge-blue   { background-color: var(--color-status-blue); }
.badge-red    { background-color: var(--color-status-red); }
.badge-amber  { background-color: var(--color-status-amber); }
.badge-gray   { background-color: var(--color-status-gray); }
.badge-purple { background-color: var(--color-status-purple); }
```

Status-to-class mapping in `app.py` (lines 55-66): merged/spec-done/plan-done/plan-approved → green, running/implementing → blue, failed → red, paused/deferred → amber, pending → gray.

No transitions on any badge property. Color changes are instantaneous when HTMX swaps new HTML.

### Existing Animation and Accessibility

Only animation: `.live-dot` pulse (`@keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.4 } }`, 2s infinite). No `prefers-reduced-motion` support anywhere in the dashboard.

CSS custom properties are well-established (14 color tokens, typography scale, spacing, radii). Dark mode via `@media (prefers-color-scheme: dark)`. No existing transitions or transform effects.

### "Secondary Actions" Assessment

Examining the feature card templates, there are no elements that function as user-triggerable actions. Cards are read-only status displays. The closest candidates for "hover reveal" would be:
- Alert badge details (currently always visible in row 3)
- Phase label / slug (currently always visible)
- Progress bar numerical values

Since no actual interactive actions exist on cards, the "subtle reveal of secondary actions" deliverable has no clear target. This is a design gap that needs resolution in the spec.

## Web Research

### HTMX Swap Lifecycle Classes

HTMX applies CSS classes through the swap lifecycle:
1. Request issued → `htmx-request` on source element
2. Response received → `htmx-swapping` applied to target
3. Swap delay elapses (configurable via `hx-swap="innerHTML swap:500ms"`)
4. Content swaps → `htmx-swapping` removed
5. `htmx-settling` applied to target (default 20ms, configurable)
6. Settle delay elapses → `htmx-settling` removed

These classes work with all swap modes including `innerHTML`. The swap delay is key for showing loading feedback — extend it to give the shimmer time to display.

### Change Detection for Polling

HTMX replaces content on every poll by default, even when the response is identical. Three approaches to skip unchanged swaps:

**1. `htmx:beforeSwap` event (simplest, client-side):**
```javascript
document.body.addEventListener('htmx:beforeSwap', function(evt) {
    if (evt.detail.xhr.response === evt.detail.target.innerHTML) {
        evt.detail.shouldSwap = false;
    }
});
```
Compares response text against current innerHTML. Zero server changes required. May have minor performance cost on large HTML sections.

**2. Server-side ETag/content hash:**
Server computes a hash of the response content, sends as `ETag` header. Client sends `If-None-Match` on subsequent polls. Server returns 304 if unchanged. Requires server-side changes to `app.py` partial endpoints.

**3. HTMX PTag extension:**
Server-managed per-element polling tags. More infrastructure than needed for this use case.

Recommendation: The `htmx:beforeSwap` approach is simplest and requires no server changes. Suitable for a dashboard where HTML sections are small (~1-5KB).

### CSS Transitions on HTMX-Swapped Elements

When HTMX replaces innerHTML, child elements are destroyed and recreated. CSS transitions on child elements (like badges) do **not** survive — new elements start in their final state with no "from" value to transition.

**Approaches to animate replaced content:**

1. **`htmx-settling` class on the container**: Animate the target element (not children) during the settle phase. Works for opacity/transform on the whole section.

2. **Idiomorph extension**: Morphs DOM in-place instead of replacing. Preserves node identity so CSS transitions on children work naturally. Swap mode: `hx-swap="morph:innerHTML"`.

3. **View Transitions API**: Native browser animation API. HTMX supports `hx-swap="innerHTML transition:true"`. Works in Chrome/Edge; limited Firefox/Safari support.

For badge color transitions specifically: Idiomorph is the most natural fit — it mutates existing badge elements rather than replacing them, so CSS `transition: background-color 300ms` works as-is. Without Idiomorph, badge transitions are impossible with innerHTML swap mode.

### Shimmer Skeleton Pattern

Tailwind's built-in `animate-pulse` provides a basic skeleton (opacity pulse). The ticket specifies a left-to-right wave shimmer, which requires custom CSS keyframes:

```css
@keyframes shimmer {
    0% { background-position: -1000px 0; }
    100% { background-position: 1000px 0; }
}
```

Applied via gradient background: `bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 bg-[length:200%_100%]`.

Accessibility: wrap with `motion-safe:` prefix or `@media (prefers-reduced-motion: no-preference)` so users with motion sensitivity see a static skeleton instead.

## Dependency Verification

### HTMX Version

`base.html` line 8 loads HTMX from unpkg CDN:

```html
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
```

The dashboard uses **HTMX 2.0.4**. Idiomorph is not currently included anywhere in the dashboard — no script tag, no `hx-ext` attribute, no reference to `morph` in any template file.

### Idiomorph Compatibility with HTMX 2.x

Idiomorph (`idiomorph-ext`) is the official HTMX-maintained extension for morphing-based DOM swaps. The HTMX extensions docs (htmx.org/extensions/idiomorph/) reference it alongside htmx@2.0.8, confirming HTMX 2.x is the supported major version. The extension registers via `htmx.defineExtension("morph", ...)`, an API unchanged between 1.x and 2.x. HTMX 2.0.4 (used here) predates 2.0.8 but is within the 2.x line and fully compatible.

### How to Include Idiomorph

Add a second script tag immediately after the existing HTMX script:

```html
<script src="https://unpkg.com/idiomorph@0.7.4/dist/idiomorph-ext.min.js"></script>
```

Then enable the extension on `<body>` (or any ancestor element of the polling sections):

```html
<body hx-ext="morph">
```

With that in place, swap mode changes from `hx-swap="innerHTML"` to `hx-swap="morph:innerHTML"` on the polling `<section>` elements. This preserves node identity so CSS `transition` properties on badges and cards survive across polls.

### Verified Capabilities

| Capability | Status |
|---|---|
| Idiomorph works with HTMX 2.0.4 | Confirmed — `htmx.defineExtension` API is stable across 2.x |
| `morph:innerHTML` swap mode | Confirmed — morphs inner children, leaves container element intact |
| CDN availability | Confirmed — `unpkg.com/idiomorph@0.7.4/dist/idiomorph-ext.min.js` |
| Idiomorph already in dashboard | Not present — requires adding one script tag and `hx-ext="morph"` |

## Open Questions

All resolved during exit gate:

- **"Secondary actions" target**: Resolved — reinterpret as revealing supplementary info on hover (e.g., full slug, timestamps, agent ID) rather than interactive actions. Cards are read-only; the hover reveal shows detail that's currently either always visible or absent.
- **Idiomorph adoption scope**: Resolved — adopt dashboard-wide. Simpler configuration, consistent swap behavior across all polling sections.
- **Loading feedback approach**: Resolved — no shimmer skeleton. The dashboard polls local files with near-zero latency, so a shimmer on every 5s poll is pointless visual noise. Instead, use `htmx:beforeSwap` change detection to skip unchanged swaps, and `htmx-settling` CSS transitions to fade in content when it actually changes. This provides loading feedback only when meaningful.
