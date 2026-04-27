# Research: Add accessibility foundations (aria-live, multi-modal severity)

## Codebase Analysis

### Badge System

The badge macro (`templates/patterns/badge.html`) renders `<span class="badge {{ css_class }}">{{ label }}</span>`. Badges carry both color and text (the operational status name), so they are not purely color-dependent — but lack icons.

`_BADGE_CLASS_MAP` in `app.py:55-66` maps 10 operational statuses to 5 CSS color classes:

| Status | CSS Class | Color |
|--------|-----------|-------|
| merged, spec-done, plan-done, plan-approved | badge-green | #2da44e |
| running, implementing | badge-blue | #388bfd |
| failed | badge-red | #f85149 |
| paused, deferred | badge-amber | #d29922 |
| pending (+ default) | badge-gray | #6e7681 |

Model badges use a separate mapping: opus → purple, haiku → gray, others → blue.

Badge colors are defined as CSS custom properties in `base.html:46-51`. Badge CSS classes at `base.html:191-204`.

**Templates using badges** (5 files):
- `feature_cards.html:22-32,50,65,84`
- `pipeline_panel.html:6,12`
- `session_panel.html:8,37-42,60-62`
- `session_detail.html:50-56`
- `sessions_list.html:33-40`

### Alert System

Alert macro (`templates/patterns/alert-banner.html`) renders `<span class="alert-badge alert-badge-{{ level }}">{{ text }}</span>`. Two severity levels: `red` (error surface) and `amber` (warning surface). CSS at `base.html:252-268`.

Alert conditions from `alerts.py:28-95`:
- `stall` → red (running + no activity > 5min)
- `circuit_breaker` → red (session-level halt)
- `deferred` → amber (status == "deferred")
- `high_rework` → amber (rework_cycles >= 2)

Alert badges in feature cards already use unicode icons + text: `&#9201; slow`, `&#9888; stall`. These are partially accessible already — they pair a symbol with readable text.

Circuit breaker banner is a plain `<div class="circuit-breaker-banner">` with text only (no icon).

### HTMX Swap Architecture

All 6 polled sections exist as `<section>` elements in `base.html:395-417` on page load:

| Section ID | Endpoint | Swap |
|------------|----------|------|
| `alerts-banner` | `/partials/alerts-banner` | innerHTML |
| `session-panel` | `/partials/session-panel` | innerHTML |
| `feature-cards` | `/partials/feature-cards` | innerHTML |
| `fleet-panel` | `/partials/fleet-panel` | innerHTML |
| `swim-lane` | `/partials/swim-lane` | innerHTML |
| `round-history` | `/partials/round-history` | innerHTML |

**Key finding**: All containers already exist in the DOM before HTMX injects content. This means `aria-live` attributes can be added directly to these `<section>` elements — no DOM restructuring needed. The `innerHTML` swap strategy replaces content inside the container, which is the correct pattern for aria-live announcements.

Live indicator in session panel uses `hx-swap-oob="true"` for out-of-band updates to the header.

### Existing Accessibility State

**Zero ARIA attributes** across all templates. No `aria-label`, `aria-live`, `role`, or other accessibility attributes exist anywhere in the template set.

Semantic HTML baseline is reasonable:
- `<section>` elements for major content areas
- `<h2>` section headings
- `<table>` with `<thead>` and `<th>` for round history
- Semantic `<span>` elements for badges

### Unlabeled Interactive Regions

| Region | File | ARIA Status |
|--------|------|-------------|
| Fleet panel | `fleet-panel.html` | No aria-label, no role |
| Round history table | `round_history.html` | Table structure with headers, no aria-label |
| Swim-lane container | `swim-lane.html` | No aria-label, no role on lanes |
| Feature cards | `feature_cards.html` | No aria-label |
| Session panel | `session_panel.html` | No aria-label |
| Alerts banner | `alerts_banner.html` | No role="alert", no aria-live |

### Color-Only Indicators

**Swim-lane segments** (`swim-lane.html:10`) use inline `background: {{ lane.color }}` with dynamic colors from `data.py:631-637`. They do have text labels (`{{ event.label }}`), so they're not purely color-dependent, but the color carries semantic meaning (status) that the text label doesn't always convey (e.g., label might be "start" while color indicates running/merged/failed).

**Status badges** use color + text (status name). Not purely color-only, but the color carries additional semantic weight (success/failure/warning) that reinforces the text. Adding icons would provide a third modality.

**Progress bars** (`feature_cards.html:44`) are color-only fills but have adjacent text labels (`N/M tasks`).

### DESIGN.md

`claude/dashboard/DESIGN.md` documents color contrast ratios (WCAG AA/AAA compliant for badge-on-surface) and semantic token usage, but contains no ARIA guidance, keyboard navigation patterns, or screen reader testing requirements.

### Ticket 035 Rubric Relevance

Ticket 035 defines 4 evaluation criteria. Two are directly relevant to accessibility:
- **Information clarity** (high weight): WCAG 1.4.1 (Use of Color) — status conveyed by color alone fails this
- **Operational usefulness** (medium weight): WCAG 2.1/2.4 (Operable, Navigable) — keyboard/screen-reader accessible

Note: the backlog item's ticket prose references "Ticket 028" for the evaluation rubric, but 028 is a test-fix ticket. Ticket 035 is the correct reference, consistent with the `blocked-by: ["035"]` in the YAML frontmatter. This is a typo in the backlog item.

### Semantic Icon Mapping (Clarify Decision)

Per clarify phase, the approach is semantic icons per operational status — no new severity taxonomy. Proposed mapping based on status semantics:

| Status Group | Statuses | Semantic Meaning | Suggested Icon |
|-------------|----------|------------------|----------------|
| Success | merged, spec-done, plan-done, plan-approved | Completed successfully | Checkmark (✓) |
| Active | running, implementing | In progress | Spinner/circle (●) |
| Error | failed | Terminal failure | Cross (✕) |
| Warning | paused, deferred | Suspended/delayed | Warning triangle (⚠) |
| Neutral | pending (+ default) | Awaiting action | Dash or circle (○) |

Model badges (opus/haiku/sonnet) don't need severity icons — they're informational labels.

## Open Questions

- Should the progress bar (`feature_cards.html:44`) get an `aria-valuenow`/`aria-valuemax` treatment, or is the adjacent text label sufficient?
- The swim-lane tick marks (`swim-lane.html:17`) are purely decorative — confirm they should be `aria-hidden="true"` or simply ignored.
