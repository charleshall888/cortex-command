# Plan: Add accessibility foundations (aria-live, multi-modal severity)

## Overview

Add ARIA live regions, semantic status icons, ARIA labels, progressbar semantics, and morph swaps to the dashboard templates and app.py. Nine requirements across 6 files: `base.html` (live regions, morph swaps, idiomorph script), `badge.html` (icon rendering), `app.py` (icon mapping filter), `fleet-panel.html` (aria-label), `round_history.html` (aria-label), `swim-lane.html` (aria-label), and `feature_cards.html` (progressbar role). No structural changes to HTML — only attribute additions, a new Jinja2 filter, a CDN script tag, and a small icon span inside the badge macro.

## Tasks

### Task 1: Add idiomorph extension script to base.html head
- **Files**: `claude/dashboard/templates/base.html`
- **What**: Add `<script src="https://unpkg.com/idiomorph@0.3.0/dist/idiomorph-ext.min.js"></script>` immediately after the existing HTMX script tag (line 8). This loads the HTMX idiomorph extension needed for morph swaps in Task 6.
- **Depends on**: none
- **Context**: The HTMX script is at line 8: `<script src="https://unpkg.com/htmx.org@2.0.4"></script>`. The idiomorph extension must load after HTMX. Also add `hx-ext="morph"` to the `<body>` tag (line 382) to enable the extension globally — this avoids repeating `hx-ext` on each section. The body tag currently has no attributes.
- **Verification**: Load the dashboard in a browser; open DevTools Network tab and confirm idiomorph-ext.min.js loads with 200 status. Console should show no HTMX extension errors.
- **Status**: [ ] not started

### Task 2: Add aria-live="assertive" and role="alert" on alerts-banner section (R1)
- **Files**: `claude/dashboard/templates/base.html`
- **What**: On the `#alerts-banner` section (line 395), add `role="alert"` and `aria-live="assertive"` attributes. The existing `hx-swap="innerHTML"` will be changed to `hx-swap="morph"` in Task 6; this task only adds ARIA attributes.
- **Depends on**: none
- **Context**: Current line 395: `<section id="alerts-banner" hx-get="/partials/alerts-banner" hx-trigger="load, every 5s" hx-swap="innerHTML"></section>`. Add `role="alert" aria-live="assertive"` to the tag.
- **Verification**: `grep -c 'role="alert"' claude/dashboard/templates/base.html` returns >= 1. `grep -c 'aria-live="assertive"' claude/dashboard/templates/base.html` returns >= 1.
- **Status**: [ ] not started

### Task 3: Add aria-live="polite" on session-panel and feature-cards sections (R2)
- **Files**: `claude/dashboard/templates/base.html`
- **What**: Add `aria-live="polite"` to the `#session-panel` section (line 397) and the `#feature-cards` section (line 401).
- **Depends on**: none
- **Context**: Line 397: `<section id="session-panel" class="section-primary" hx-get="/partials/session-panel" hx-trigger="load, every 5s" hx-swap="innerHTML">`. Line 401: `<section id="feature-cards" class="section-primary" hx-get="/partials/feature-cards" hx-trigger="load, every 5s" hx-swap="innerHTML">`.
- **Verification**: `grep -c 'aria-live="polite"' claude/dashboard/templates/base.html` returns >= 2.
- **Status**: [ ] not started

### Task 4: Add status-to-icon mapping filter in app.py (R4)
- **Files**: `claude/dashboard/app.py`
- **What**: Add a `_BADGE_ICON_MAP` dict parallel to `_BADGE_CLASS_MAP` (after line 66) mapping statuses to unicode icons. Add a `_badge_icon` function that returns the icon for a given status, defaulting to "○" for unrecognized statuses and returning `None` when status is `None` (so call sites using `css_class` without `status` render no icon). Register it as `templates.env.filters["badge_icon"]` alongside the existing filter registrations (after line 158).
- **Depends on**: none
- **Context**: Icon mapping per spec: `merged`/`spec-done`/`plan-done`/`plan-approved` -> "✓", `running`/`implementing` -> "●", `failed` -> "✕", `paused`/`deferred` -> "⚠", `pending` -> "○". The function signature: `def _badge_icon(status: str | None) -> str | None`. When `status` is None, return None. When `status` is a non-None string not in the map, return "○" (neutral default). This distinction handles the edge case where badge is called with `css_class` only (status defaults to None in the macro).
- **Verification**: `grep -c 'badge_icon' claude/dashboard/app.py` returns >= 1. `grep -c '_BADGE_ICON_MAP' claude/dashboard/app.py` returns >= 1.
- **Status**: [ ] not started

### Task 5: Add semantic icon to badge macro (R3)
- **Files**: `claude/dashboard/templates/patterns/badge.html`
- **What**: Modify the badge macro to render an `aria-hidden="true"` icon span before the label text, using the `badge_icon` filter. The icon only renders when `status` is not None (i.e., when the filter returns a non-None value). Change the macro body from `{{ label if label is not none else status }}` to `{% set icon = status | badge_icon if status else None %}{% if icon %}<span aria-hidden="true">{{ icon }}</span> {% endif %}{{ label if label is not none else status }}`.
- **Depends on**: [4]
- **Context**: Current macro (single line): `{% macro badge(status=None, css_class=None, label=None) %}<span class="badge {{ css_class if css_class else status | badge_class }}">{{ label if label is not none else status }}</span>{% endmacro %}`. The icon span goes inside the outer `<span class="badge ...">` element. Call site audit: 5 template files use the badge macro, with many call sites passing `css_class` without `status` (model badges, summary count badges). These will correctly render no icon because `status` will be None.
- **Verification**: `grep -c 'aria-hidden="true"' claude/dashboard/templates/patterns/badge.html` returns >= 1. `grep -c 'badge_icon' claude/dashboard/templates/patterns/badge.html` returns >= 1. Load the dashboard and visually confirm status badges (e.g., "running", "merged") show icons while model/count badges (e.g., "opus", "3 merged") do not.
- **Status**: [ ] not started

### Task 6: Switch aria-live sections to morph swaps (R8)
- **Files**: `claude/dashboard/templates/base.html`
- **What**: Change `hx-swap="innerHTML"` to `hx-swap="morph"` on the three sections that carry `aria-live` attributes: `#alerts-banner` (line 395), `#session-panel` (line 397), and `#feature-cards` (line 401). Leave the other three polled sections (`#fleet-panel`, `#swim-lane`, `#round-history`) unchanged — they don't carry `aria-live` and morph swaps are not required for them.
- **Depends on**: [1]
- **Context**: Morph swap uses the idiomorph extension (loaded in Task 1) to diff the DOM and only mutate changed nodes. This prevents screen readers from re-announcing unchanged content on every 5-second poll cycle. The `hx-ext="morph"` attribute on `<body>` (from Task 1) enables the extension; individual sections just need `hx-swap="morph"`.
- **Verification**: `grep -c 'hx-swap="morph"' claude/dashboard/templates/base.html` returns >= 3. Load the dashboard, open DevTools Elements panel, observe that only changed DOM nodes flash on poll updates (not entire section contents).
- **Status**: [ ] not started

### Task 7: Add aria-label on fleet panel (R5)
- **Files**: `claude/dashboard/templates/base.html`
- **What**: Add `aria-label="Agent fleet"` to the `#fleet-panel` section (line 405).
- **Depends on**: none
- **Context**: Line 405: `<section id="fleet-panel" hx-get="/partials/fleet-panel" hx-trigger="load, every 5s" hx-swap="innerHTML">`.
- **Verification**: `grep -c 'aria-label="Agent fleet"' claude/dashboard/templates/base.html` returns >= 1.
- **Status**: [ ] not started

### Task 8: Add aria-label on round history table (R6)
- **Files**: `claude/dashboard/templates/round_history.html`
- **What**: Add `aria-label="Round history"` to the `<table class="round-table">` element (line 3).
- **Depends on**: none
- **Context**: Line 3: `<table class="round-table">`.
- **Verification**: `grep -c 'aria-label="Round history"' claude/dashboard/templates/round_history.html` returns >= 1.
- **Status**: [ ] not started

### Task 9: Add aria-label on swim-lane container (R7)
- **Files**: `claude/dashboard/templates/swim-lane.html`
- **What**: Add `aria-label="Feature timeline"` to the `<div class="overflow-x-auto">` container (line 2) which wraps all swim lanes.
- **Depends on**: none
- **Context**: Line 2: `<div class="overflow-x-auto">`. This is the top-level container inside the conditional — the section wrapper is in `base.html`, but the semantic content container is this div.
- **Verification**: `grep -c 'aria-label="Feature timeline"' claude/dashboard/templates/swim-lane.html` returns >= 1.
- **Status**: [ ] not started

### Task 10: Add ARIA progressbar on feature card progress bar (R9)
- **Files**: `claude/dashboard/templates/feature_cards.html`
- **What**: Add `role="progressbar"`, `aria-valuenow="{{ plan_prog[0] }}"`, `aria-valuemax="{{ plan_prog[1] }}"`, and `aria-label="Task progress"` to the progress bar `<div>` at line 44.
- **Depends on**: none
- **Context**: Line 44: `<div class="progress-bar"><div class="progress-bar-fill" style="width: {% if plan_prog[1] > 0 %}{{ (plan_prog[0] / plan_prog[1] * 100) | int }}{% else %}0{% endif %}%"></div></div>`. The ARIA attributes go on the outer `<div class="progress-bar">`. `plan_prog` is a tuple of `(completed, total)` set at line 11. Note: `aria-valuemin` is not needed because it defaults to 0 per WAI-ARIA spec.
- **Verification**: `grep -c 'role="progressbar"' claude/dashboard/templates/feature_cards.html` returns >= 1. `grep -c 'aria-valuenow' claude/dashboard/templates/feature_cards.html` returns >= 1. `grep -c 'aria-valuemax' claude/dashboard/templates/feature_cards.html` returns >= 1. `grep -c 'aria-label="Task progress"' claude/dashboard/templates/feature_cards.html` returns >= 1.
- **Status**: [ ] not started

## Verification Strategy

1. Start the dashboard (`just dashboard` or `python -m claude.dashboard.app`) and load it in a browser
2. View page source and confirm: `role="alert"` and `aria-live="assertive"` on `#alerts-banner`; `aria-live="polite"` on `#session-panel` and `#feature-cards`; `hx-swap="morph"` on all three aria-live sections; `aria-label="Agent fleet"` on `#fleet-panel`
3. Inspect `round_history.html` partial (via `/partials/round-history`) for `aria-label="Round history"` on the table
4. Inspect `swim-lane.html` partial for `aria-label="Feature timeline"` on the container
5. Confirm status badges show icons (checkmark for merged, circle for running, etc.) while model/count badges do not
6. Confirm progress bars in running feature cards have `role="progressbar"` with correct `aria-valuenow`/`aria-valuemax` values
7. Use a screen reader (VoiceOver on macOS: Cmd+F5) to verify alerts are announced assertively and status changes are announced politely
8. Observe DevTools Elements panel during poll cycles: only changed nodes should flash (morph swap), not entire section contents
