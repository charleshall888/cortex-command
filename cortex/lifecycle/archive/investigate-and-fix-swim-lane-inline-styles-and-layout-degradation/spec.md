# Specification: Investigate and fix swim-lane inline styles and layout degradation

## Problem Statement

`swim-lane.html` contains four inline `style=` attributes — mixing static layout properties, data-driven positional values, and raw hex color codes — violating the dashboard's DESIGN.md guidelines. Three of five `_color_map` entries use raw hex (running, merged, failed); two (paused, deferred) already use the CSS variable `var(--color-lane-paused)`. Additionally, event labels overlap when many events cluster in a narrow time window, degrading readability. This ticket brings the swim-lane template into DESIGN.md compliance, fixes a pre-existing tick axis alignment bug, and adds basic overlap mitigation, without changing swim-lane functionality.

## Requirements

### Must-have

1. **Remove static inline styles from tick axis container (line 25)**: Replace `style="position: relative; height: 20px; margin-left: 200px;"` with the `.lane-tick-axis` CSS class defined in Req 6. The class encapsulates all three static properties — do not use Tailwind utilities for this element.
   - AC: `grep 'style=' claude/dashboard/templates/swim-lane.html | grep -v 'left:.*%' | wc -l` = 0 (no inline styles remain except those containing only `left: {{ ... }}%`)

2. **Remove static inline styles from tick labels (line 27)**: Replace `position: absolute`, `transform: translateX(-50%)`, and `font-size: 0.7rem` with Tailwind classes (`absolute -translate-x-1/2`) and the `.tick-label` CSS class (for font-size). Keep only `style="left: {{ tick.x_pct }}%"` as data-driven positional. Replace the `.phase-label` class on tick spans with `.tick-label`.
   - AC: `grep 'phase-label.*style=' claude/dashboard/templates/swim-lane.html | wc -l` = 0 (tick labels no longer combine class with multi-property inline style)

3. **Replace static background on tool ticks (line 17)**: Define `--color-lane-tick` CSS variable (dark mode: `rgba(255,255,255,0.3)`; light mode variant as appropriate) and apply via a `.lane-tick-mark` class in `base.html`. Replace the inline `background: rgba(255,255,255,0.3)` with this class. Keep only `style="left: {{ x_pct }}%"`.
   - AC: `grep 'rgba' claude/dashboard/templates/swim-lane.html | wc -l` = 0
   - AC: `grep -c '\-\-color-lane-tick' claude/dashboard/templates/base.html` >= 1

4. **Migrate lane colors from Python `_color_map` to CSS classes**: Remove `_color_map` dict and `color` field from lane dict in `data.py`. Add `status` field to lane dict (value from `feat.get("status", "pending")`). Define `lane-status-{running,merged,paused,deferred,failed,pending}` CSS classes in `base.html` using DESIGN.md tokens:
   - `lane-status-running` → `--color-status-blue` (`#388bfd`)
   - `lane-status-merged` → `--color-status-green` (`#2da44e`) — **note: this shifts the merged color from the current `#3fb950` to `#2da44e`, consolidating with the DESIGN.md badge token. This is an intentional change for design consistency.**
   - `lane-status-failed` → `--color-status-red` (`#f85149`)
   - `lane-status-paused`, `lane-status-deferred` → `--color-lane-paused` (already used in current code)
   - `lane-status-pending` → `--color-status-gray` (`#6e7681`)

   Additionally, define a base rule on `.lane-event` that sets `background-color: var(--color-status-gray)` as a catch-all default. This ensures that if `lane.status` produces a value not in the defined set, the event box still gets a visible background. The lane-status-specific classes override this default. This replaces the current Python-level fallback (`_color_map.get(status, "#6e7681")`).

   Template selects class via `lane-status-{{ lane.status }}`.

   - AC: `grep '_color_map' claude/dashboard/data.py | wc -l` = 0 (color map removed)
   - AC: `grep 'lane\.color' claude/dashboard/templates/swim-lane.html | wc -l` = 0 (template no longer references lane.color)
   - AC: `grep -c 'lane-status-' claude/dashboard/templates/base.html` >= 6 (one class per status)
   - AC: `grep 'lane-event' claude/dashboard/templates/base.html | grep -c 'color-status-gray'` >= 1 (catch-all fallback defined)

5. **Define shared `--lane-label-width` CSS variable and fix tick axis alignment**: Add `--lane-label-width: 200px` to `:root` in `base.html`. Update `.lane-label` width to `var(--lane-label-width)`. The `.lane-tick-axis` class (Req 6) uses `margin-left: calc(var(--lane-label-width) + 0.75rem)` to account for the `gap-3` (12px) between the label and track in each lane row. **Bug fix**: the current `margin-left: 200px` is 12px short of the track's actual left edge because `gap-3` is not accounted for. This fix corrects the pre-existing misalignment.
   - AC: `grep -c '\-\-lane-label-width' claude/dashboard/templates/base.html` >= 3 (definition + two usages)
   - AC: `grep 'lane-tick-axis' claude/dashboard/templates/base.html | grep -c 'calc'` >= 1 (gap-aware margin)

6. **Define `.lane-tick-axis`, `.tick-label`, and `.lane-event` CSS classes in `base.html`**: `.lane-tick-axis` encapsulates `position: relative`, `height`, and `margin-left: calc(var(--lane-label-width) + 0.75rem)`. `.tick-label` provides the `0.7rem` font-size (smaller than `.phase-label`'s `0.8rem`). `.lane-event` provides truncation (`max-width`, `overflow: hidden`, `text-overflow: ellipsis`) and the fallback `background-color: var(--color-status-gray)`.
   - AC: `grep -c '\.lane-tick-axis' claude/dashboard/templates/base.html` >= 1
   - AC: `grep -c '\.tick-label' claude/dashboard/templates/base.html` >= 1
   - AC: `grep -c '\.lane-event' claude/dashboard/templates/base.html` >= 1

7. **Add `.lane-event` class to event boxes (line 10)**: Replace the long inline Tailwind class list with the `.lane-event` CSS class (which provides truncation and fallback background) plus the `lane-status-{{ lane.status }}` class for the status-specific background color. Retain Tailwind utilities that are standard layout/typography (`absolute top-1 h-8 py-0.5 px-1.5 rounded-sm text-xs text-white z-1`). Keep only `style="left: {{ event.x_pct }}%"` as the inline style.
   - AC: `grep 'lane-event' claude/dashboard/templates/swim-lane.html | wc -l` >= 1
   - AC: `grep 'whitespace-nowrap' claude/dashboard/templates/swim-lane.html | wc -l` = 0 (replaced by `.lane-event` truncation)

### Should-have

8. **Remaining inline styles contain only data-driven positional `left` properties**: After all changes, exactly three inline `style=` attributes remain, each containing only `left: {{ ... }}%`. No other CSS properties in inline styles.
   - AC: `grep -c 'style="left:' claude/dashboard/templates/swim-lane.html` = 3

## Non-Requirements

- **No swim-lane feature enhancements**: This ticket does not add zoom, pan, filtering, or any new interactive capabilities.
- **No density-aware label rendering**: Label overlap is mitigated by truncation only. Density-aware narrow markers or alternating row offsets are deferred to a future enhancement ticket.
- **No changes to summary mode logic**: Summary mode (>200 events hides tool ticks) is intentional and correctly implemented. It remains unchanged.
- **No changes to tool tick data population**: `tool_tick_xs` is reserved for future agent-activity integration and remains empty. The rendering path is updated but the data source is not.
- **No Playwright test authoring**: This ticket depends on ticket 029 (Playwright toolchain) for regression baseline, but does not itself write new Playwright tests. Test assertions for the new DOM structure will be a follow-up.

## Edge Cases

- **Unknown lane status**: If `feat.get("status")` returns a value not in the defined set, the template renders `lane-status-{value}` which has no matching CSS class. The `.lane-event` base class provides `background-color: var(--color-status-gray)` as a catch-all default, ensuring the event box is always visible with sufficient contrast against `text-white`. No crash, no invisible text.
- **Empty lanes (no events)**: Lane renders with label and track but no event boxes. Truncation styles are on event boxes, so no effect on empty lanes.
- **Very long event labels**: With truncation via `.lane-event`, long labels are cut with ellipsis. The full label remains accessible via the existing `title="{{ event.tooltip }}"` attribute.
- **Zero elapsed seconds**: `total_elapsed_secs` is guaranteed >= 1.0 (`data.py` line 621), so division-by-zero in `x_pct` calculation is not possible. No change needed.
- **Light mode contrast**: All lane-status colors and the fallback gray are chosen from the DESIGN.md token palette, which was designed for sufficient contrast in both light and dark modes. The `text-white` foreground on `--color-status-gray` (`#6e7681`) passes WCAG AA for large text (~4.8:1).

## Technical Constraints

- **DESIGN.md compliance**: All colors must use CSS custom properties (`var(--color-*)`). No raw hex in templates. No arbitrary Tailwind values. Non-standard sizes require named CSS classes. `bg-white/30` and similar raw-color Tailwind utilities are not semantic tokens and must not be used for color decisions.
- **Existing token palette**: Status colors map to existing tokens: `--color-status-blue` (running), `--color-status-green` (merged — shifts from current `#3fb950` to token value `#2da44e`), `--color-status-red` (failed), `--color-lane-paused` (paused/deferred — already in use), `--color-status-gray` (pending/fallback). One new token needed: `--color-lane-tick` for tool tick marks.
- **Data-driven positional inline styles are accepted**: The codebase already uses inline `style="width: {{ pct }}%"` in session_panel.html and feature_cards.html for progress bars. Data-driven `left` positioning follows the same pattern.
- **Blocked by ticket 029**: Playwright MCP must be in place before implementation begins to provide a visual evaluation baseline.

## Open Decisions

None — all decisions resolved at spec time.
