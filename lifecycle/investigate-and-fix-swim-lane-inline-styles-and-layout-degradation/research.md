# Research: Investigate and fix swim-lane inline styles and layout degradation

## Codebase Analysis

### Inline Style Inventory (`claude/dashboard/templates/swim-lane.html`)

Four `style=` attributes exist in the template. Each is classified below.

**Line 10 — Event box** (data-driven positional + data-driven non-positional):
```html
style="left: {{ event.x_pct }}%; background: {{ lane.color }};"
```
- `left: {{ event.x_pct }}%` — data-driven positional. Computed in `data.py` line 651 as `(elapsed / total_elapsed_secs) * 100`, clamped to [0, 100]. Cannot be replaced with a static class.
- `background: {{ lane.color }}` — data-driven non-positional. Color comes from `_color_map` in `data.py` lines 631–637: running=`#388bfd`, merged=`#3fb950`, failed=`#f85149`, paused/deferred=`var(--color-lane-paused)`. Three of four values are raw hex codes violating DESIGN.md; one already uses a CSS variable.

**Line 17 — Tool tick vertical line** (data-driven positional + static):
```html
style="left: {{ x_pct }}%; background: rgba(255,255,255,0.3);"
```
- `left: {{ x_pct }}%` — data-driven positional. From `lane.tool_tick_xs`, currently always empty (reserved for future agent-activity integration, `data.py` line 687). Cannot be replaced with a static class.
- `background: rgba(255,255,255,0.3)` — static. A semi-transparent white that should use a CSS token (e.g., `var(--color-tick-mark)` or a Tailwind utility like `bg-white/30`).

**Line 25 — Tick axis container** (all static):
```html
style="position: relative; height: 20px; margin-left: 200px;"
```
- `position: relative` — static. Replaceable with Tailwind `relative`.
- `height: 20px` — static. Replaceable with Tailwind `h-5`.
- `margin-left: 200px` — static. Hardcoded to match `.lane-label` width (defined in `base.html` line 285 as `width: 200px`). Both should reference a shared CSS variable (e.g., `var(--lane-label-width)`) to avoid silent drift.

**Line 27 — Tick label** (mixed static + data-driven positional):
```html
style="position: absolute; left: {{ tick.x_pct }}%; transform: translateX(-50%); font-size: 0.7rem;"
```
- `position: absolute` — static. Replaceable with Tailwind `absolute`.
- `left: {{ tick.x_pct }}%` — data-driven positional. Cannot be replaced with a static class.
- `transform: translateX(-50%)` — static. Replaceable with Tailwind `-translate-x-1/2`.
- `font-size: 0.7rem` — static. Replaceable with a custom Tailwind utility or CSS variable. The existing `.phase-label` class (base.html line 230) uses `0.8rem`; this is intentionally smaller.

### Classification Summary

| Location | Property | Classification | Replacement Strategy |
|----------|----------|---------------|---------------------|
| Line 10 | `left: {{ event.x_pct }}%` | Data-driven positional | Keep as inline `style=` (accepted pattern per session_panel/feature_cards precedent) |
| Line 10 | `background: {{ lane.color }}` | Data-driven non-positional | Keep as inline `style=` but fix the color source: replace raw hex in Python `_color_map` with CSS variables matching DESIGN.md status tokens |
| Line 17 | `left: {{ x_pct }}%` | Data-driven positional | Keep as inline `style=` |
| Line 17 | `background: rgba(255,255,255,0.3)` | Static | Replace with Tailwind `bg-white/30` or a CSS token |
| Line 25 | `position: relative` | Static | Replace with Tailwind `relative` |
| Line 25 | `height: 20px` | Static | Replace with Tailwind `h-5` |
| Line 25 | `margin-left: 200px` | Static | Define `--lane-label-width` CSS variable; reference in both `.lane-label` and tick axis |
| Line 27 | `position: absolute` | Static | Replace with Tailwind `absolute` |
| Line 27 | `left: {{ tick.x_pct }}%` | Data-driven positional | Keep as inline `style=` |
| Line 27 | `transform: translateX(-50%)` | Static | Replace with Tailwind `-translate-x-1/2` |
| Line 27 | `font-size: 0.7rem` | Static | Define as `.tick-label` class or use Tailwind `text-[0.7rem]` — but DESIGN.md forbids arbitrary Tailwind values; prefer a CSS class |

### Data-Driven Inline Style Strategy

The codebase already accepts data-driven positional inline styles — `session_panel.html` (line 33) and `feature_cards.html` (line 44) both use `style="width: {{ pct }}%"` for progress bars. These templates also use `style="color: var(--color-*)"` for CSS-variable-driven values. This establishes the precedent:

- **Data-driven positional values**: inline `style=` with the dynamic property only (e.g., `style="left: {{ x_pct }}%"`)
- **Data-driven non-positional values** (colors): either inline `style=` with CSS variables (`style="background: var(--color-status-running)"`) or move color assignment to a CSS class selected by Jinja conditional

The cleanest approach for `lane.color` is to map feature status → CSS class in the template (e.g., `bg-status-running`, `bg-status-merged`) rather than passing raw color values from Python. This moves the color decision to the CSS layer where DESIGN.md tokens live.

### Color Map in Python Backend (`data.py` lines 631–637)

```python
_color_map = {
    "running": "#388bfd",
    "merged": "#3fb950",
    "paused": "var(--color-lane-paused)",
    "deferred": "var(--color-lane-paused)",
    "failed": "#f85149",
}
```

Three of five entries use raw hex codes (DESIGN.md violation). One uses a CSS variable. Two approaches:

1. **Replace hex with CSS variables**: Change to `var(--color-status-blue)`, `var(--color-status-green)`, `var(--color-status-red)` — these tokens exist in DESIGN.md's status palette. Keep the inline `style="background: var(--color-...)"` in the template.
2. **Move to CSS classes**: Pass status name instead of color from Python, use Jinja conditional to select a Tailwind/custom class (e.g., `{% if lane.status == 'running' %}bg-status-running{% endif %}`). Define `bg-status-*` classes in base.html using DESIGN.md tokens.

Approach 2 is more aligned with DESIGN.md's philosophy (color decisions in CSS, not Python), but approach 1 is simpler and follows the `session_panel.html` precedent.

### Summary Mode Investigation

**Implementation** (`data.py` line 629):
```python
summary_mode = total_event_count > 200
```
Where `total_event_count = len(overnight_events) + sum(phase_transitions per feature)`.

**Effect** (`swim-lane.html` line 15): When `summary_mode` is true, the `{% if not summary_mode %}` block skips rendering tool tick vertical lines.

**User visibility** (`swim-lane.html` line 32): A gray help-text message is displayed: "Summary mode — tool ticks hidden (>200 events)".

**Assessment**: This is intentional behavior with a user-visible explanation. It was designed as a performance/readability optimization. However, `tool_tick_xs` is currently always empty (`data.py` line 687) — summary mode currently hides nothing since there are no tool ticks to show. When tool ticks are eventually populated, the summary mode will activate. No changes needed to the summary mode logic itself; it's correctly implemented for its intended use.

### Label Overlap Investigation

**Cause**: Event boxes at line 10 use `position: absolute` with `left: {{ event.x_pct }}%`. Each box has `whitespace-nowrap` and no max-width constraint. When multiple events occur close together in time, their `x_pct` values cluster, causing overlapping boxes with overlapping text.

**Current state**: The `.lane-track` container (base.html line 293) is `position: relative; flex: 1; height: 56px`. Events are positioned absolutely within this container. There is no collision detection, z-index stacking order for overlapping events, or truncation of event labels when they would overlap.

**Viable CSS-only fixes within current architecture**:

1. **Truncate labels with max-width**: Add `max-width` and `overflow: hidden; text-overflow: ellipsis` to event boxes. This doesn't prevent positional overlap but limits the visual extent of each label. Simplest fix, reduces overlap severity.

2. **Tooltip-only labels at density threshold**: When events are closer than a threshold (e.g., < 2% apart), render event boxes as narrow markers (width: 4px) with full labels in `title` attribute tooltips only. Requires Jinja logic to detect adjacency in the template or pre-computation in Python.

3. **Alternating vertical offset**: Alternate events between `top-1` and `top-6` (or similar) to create two visual rows within the lane track. Reduces overlap when adjacent events have different offsets. Simple CSS change but doubles the visual height needed.

**Assessment**: Option 1 (truncate labels) is the simplest fix within the current layout strategy and doesn't require a fundamentally different approach. It can be combined with option 2 for a density-aware enhancement if needed. Option 3 changes the visual design significantly. A completely different layout strategy (e.g., virtualized scrolling, dynamic label placement) is out of scope per the ticket's scope boundary.

### Files Affected

| File | Change Type |
|------|-------------|
| `claude/dashboard/templates/swim-lane.html` | Replace static inline styles with Tailwind classes; reduce inline styles to data-driven-only properties |
| `claude/dashboard/templates/base.html` | Add `.lane-tick-axis` class, `.tick-label` class, and `--lane-label-width` CSS variable; optionally add `bg-status-*` classes |
| `claude/dashboard/data.py` | Replace raw hex codes in `_color_map` with CSS variables or status names |

### Conventions to Follow

- DESIGN.md mandates semantic CSS tokens for all color decisions — no raw hex
- DESIGN.md forbids arbitrary Tailwind values (`text-[0.7rem]`) — use CSS classes for non-standard sizes
- Existing templates accept inline `style=` for data-driven positional values (progress bar widths)
- Existing templates use CSS variables in inline styles for color (e.g., `style="color: var(--color-warning)"`)

## Open Questions

- Should `lane.color` be migrated to CSS classes (approach 2, more DESIGN.md-aligned) or CSS variables in inline styles (approach 1, simpler, matches session_panel precedent)? Both are valid; approach 1 is sufficient for compliance, approach 2 is more architecturally clean. Deferred: will be resolved in Spec by asking the user.
- Should label overlap mitigation be limited to truncation (option 1) or include density-aware narrow markers (option 2)? Option 1 is the minimum viable fix; option 2 is a significant enhancement. Deferred: will be resolved in Spec by asking the user.
