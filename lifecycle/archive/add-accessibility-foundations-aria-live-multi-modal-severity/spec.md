# Specification: Add accessibility foundations (aria-live, multi-modal severity)

## Problem Statement

The dashboard communicates state via color alone in status badges and alert banners, failing WCAG 4.1.3 (Status Messages) and being inaccessible to color-blind users. No live region announcements exist for dynamic content — screen readers receive no signal when HTMX-polled updates change status every 5 seconds. This feature adds aria-live regions for screen reader announcements, semantic icons alongside operational status badges, ARIA labels on unlabeled interactive regions, and progressbar semantics — establishing the accessibility foundation for the dashboard.

## Requirements

1. **R1 — aria-live="assertive" on alerts section**: The `#alerts-banner` section in `base.html` must have `role="alert"` and `aria-live="assertive"` so screen readers immediately announce critical failures (stall, circuit breaker). Note: `role="alert"` implies `aria-live="assertive"` and `aria-atomic="true"` per WAI-ARIA spec; the explicit `aria-live="assertive"` is added for clarity, and the implicit `aria-atomic="true"` means the entire alert region is announced as a unit on change.
   - Acceptance: `grep -c 'role="alert"' claude/dashboard/templates/base.html` >= 1 AND `grep -c 'aria-live="assertive"' claude/dashboard/templates/base.html` >= 1

2. **R2 — aria-live="polite" on status sections**: The `#session-panel` and `#feature-cards` sections in `base.html` must have `aria-live="polite"` so screen readers announce status changes non-disruptively.
   - Acceptance: `grep -c 'aria-live="polite"' claude/dashboard/templates/base.html` >= 2

3. **R3 — Semantic icons in badge macro**: The badge macro (`templates/patterns/badge.html`) must render a status-semantic icon alongside each status text label. Icons must be `aria-hidden="true"` — the text label carries the accessible meaning. Icon mapping by status group:
   - Success (merged, spec-done, plan-done, plan-approved) → ✓
   - Active (running, implementing) → ●
   - Error (failed) → ✕
   - Warning (paused, deferred) → ⚠
   - Neutral (pending, default) → ○
   - Acceptance: `grep -c 'aria-hidden="true"' claude/dashboard/templates/patterns/badge.html` >= 1 AND `grep -c 'badge_icon' claude/dashboard/templates/patterns/badge.html` >= 1

4. **R4 — Icon-to-status mapping in app.py**: `app.py` must expose a status-to-icon mapping (paralleling the existing `_BADGE_CLASS_MAP` pattern and registered as a Jinja2 filter) so the badge macro can look up the correct icon for each operational status.
   - Acceptance: `grep -c 'badge_icon' claude/dashboard/app.py` >= 1

5. **R5 — aria-label on fleet panel**: The `#fleet-panel` section in `base.html` must have `aria-label="Agent fleet"`.
   - Acceptance: `grep -c 'aria-label="Agent fleet"' claude/dashboard/templates/base.html` >= 1

6. **R6 — aria-label on round history table**: The round history `<table>` element must have `aria-label="Round history"`.
   - Acceptance: `grep -c 'aria-label="Round history"' claude/dashboard/templates/round_history.html` >= 1

7. **R7 — aria-label on swim-lane container**: The swim-lane container must have `aria-label="Feature timeline"`.
   - Acceptance: `grep -c 'aria-label="Feature timeline"' claude/dashboard/templates/swim-lane.html` >= 1

8. **R8 — Morph swaps on aria-live sections**: All HTMX-polled sections that carry `aria-live` attributes (R1: `#alerts-banner`, R2: `#session-panel`, `#feature-cards`) must use a DOM-diffing swap strategy (e.g., HTMX idiomorph extension with `hx-swap="morph"`) instead of the default `innerHTML` swap. This ensures only actually-changed DOM nodes are mutated, preventing screen readers from re-announcing unchanged content on every 5-second poll cycle.
   - Acceptance: `grep -c 'morph\|hx-swap="morph"' claude/dashboard/templates/base.html` >= 3

9. **R9 — ARIA progressbar on feature card progress bar**: The progress bar in `feature_cards.html` must have `role="progressbar"`, `aria-valuenow` (set to completed task count), `aria-valuemax` (set to total task count), and `aria-label="Task progress"`.
   - Acceptance: `grep -c 'role="progressbar"' claude/dashboard/templates/feature_cards.html` >= 1 AND `grep -c 'aria-valuenow' claude/dashboard/templates/feature_cards.html` >= 1 AND `grep -c 'aria-valuemax' claude/dashboard/templates/feature_cards.html` >= 1 AND `grep -c 'aria-label="Task progress"' claude/dashboard/templates/feature_cards.html` >= 1

## Non-Requirements

- No keyboard navigation — tab order, focus management, and skip links are a separate concern from ARIA/screen-reader foundations
- No automated accessibility testing integration (axe-core, pa11y, Lighthouse) — validation is manual inspection
- No comprehensive WCAG 2.1 AA compliance audit — this is targeted accessibility foundations, not a full audit
- No DESIGN.md updates — keep focused on template changes; ARIA guidance in DESIGN.md is a follow-up
- No model badge icons — model badges (opus/haiku/sonnet) are informational labels, not status indicators requiring severity icons
- No aria-live on fleet panel, swim-lane, or round history — these sections update frequently or contain historical/visual data not suited for live announcements; aria-live on these would be excessively chatty
- No swim-lane segment icon treatment — swim-lane event segments already have text labels (`{{ event.label }}`); they are not pure color-only indicators

## Edge Cases

- **Empty sections (no active session)**: aria-live containers exist but are empty. Screen readers announce nothing — correct behavior per WAI-ARIA spec. No special handling.
- **Unknown/default status**: Badge renders with `badge-gray` class and neutral icon (○). The `_BADGE_CLASS_MAP` default already returns `badge-gray`; the icon map must also default to ○.
- **HTMX swap failure**: aria-live regions retain last-good content since HTMX only swaps on successful responses. No additional handling.
- **Identical-content re-swap**: With morph swaps (R8), if no DOM nodes change between poll cycles, no mutations occur and no aria-live announcement fires — correct behavior. Without morph swaps, every poll triggers re-announcement of all content.
- **Swim-lane decorative tick marks**: Purely visual separators with no semantic content. No ARIA treatment needed — separate tick labels are rendered as semantic content already.
- **Circuit breaker banner**: Text-only content ("Circuit breaker active — overnight runner has been halted.") inside the `#alerts-banner` section. The `role="alert"` on the parent section covers this — screen readers will announce it as an alert.
- **Badge macro called with css_class override**: Some call sites pass `css_class` directly instead of `status`. When `status` is None (parameter not passed), the icon lookup must gracefully return no icon rather than erroring — this is distinct from an unrecognized status string, which renders the neutral icon (○). The plan phase must audit existing badge call sites across the 5 template files to determine how many use `css_class` without `status` and whether any produce misleading icon/label combinations.

## Technical Constraints

- HTMX polling sections in `base.html:395-417` already exist in the DOM on page load — `aria-live` and `role` attributes can be added directly to the `<section>` elements. However, the default `innerHTML` swap removes and re-inserts all child nodes, which triggers screen reader re-announcements even when content is identical. Sections with `aria-live` must use morph swaps (DOM diffing) to avoid redundant announcements
- Badge macro is a single Jinja2 macro imported across 5 template files — the icon must be added inside the macro definition to avoid modifying all call sites individually
- `aria-live="assertive"` is reserved exclusively for the `#alerts-banner` section per WCAG guidance; all other polled sections use `polite`
- Icons must be `aria-hidden="true"` — the text label is the accessible name, not the icon
- Alert badges in feature cards already pair unicode symbols with text (e.g., `&#9201; slow`, `&#9888; stall`) — these are already multi-modal and do not need changes
- The existing `_BADGE_CLASS_MAP` in `app.py:55-66` provides the pattern to follow for the icon mapping — a parallel dict registered as a Jinja2 filter

## Open Decisions

(none)
