# Plan: Investigate and fix swim-lane inline styles and layout degradation

## Overview

This plan brings `swim-lane.html` into DESIGN.md compliance by removing static and non-positional inline styles, migrating lane status colors from Python to CSS, adding a shared `--lane-label-width` CSS variable (fixing a tick axis alignment bug), and adding truncation to event boxes. All changes are localized to three files: `claude/dashboard/templates/swim-lane.html`, `claude/dashboard/templates/base.html`, and `claude/dashboard/data.py`.

The implementation follows a bottom-up dependency order: CSS infrastructure is defined in `base.html` first, the Python backend is updated second, and the template is updated last. This ensures every CSS class referenced in the template exists before the template change is written.

---

## Tasks

### Task 1: Add CSS infrastructure to `base.html`

**Files:** `claude/dashboard/templates/base.html`

**What:**

1. Add `--color-lane-tick` CSS variable to the `@theme` block (light-mode default: `rgba(255,255,255,0.3)`) and override it in the dark-mode `@media (prefers-color-scheme: dark) :root` block (same value, since the lane track is dark in both modes, but define it separately for maintainability). Place it directly after the `--color-lane-paused` definition at line 57.

2. Add `--lane-label-width: 200px` to the `:root` block (lines 122+). Place it near the bottom of the `:root` block, before the closing `}`.

3. In the existing `.lane-label` rule (around line 297), change `width: 200px` to `width: var(--lane-label-width)`.

4. Add the following new CSS classes in the `<style type="text/tailwindcss">` block, grouped after `.lane-track` (around line 306):

   ```css
   .lane-tick-axis {
     position: relative;
     height: 20px;
     margin-left: calc(var(--lane-label-width) + 0.75rem);
   }
   .tick-label {
     font-size: 0.7rem;
     color: var(--color-text-secondary);
   }
   .lane-event {
     max-width: 120px;
     overflow: hidden;
     text-overflow: ellipsis;
     background-color: var(--color-status-gray);
   }
   .lane-status-running  { background-color: var(--color-status-blue); }
   .lane-status-merged   { background-color: var(--color-status-green); }
   .lane-status-failed   { background-color: var(--color-status-red); }
   .lane-status-paused   { background-color: var(--color-lane-paused); }
   .lane-status-deferred { background-color: var(--color-lane-paused); }
   .lane-status-pending  { background-color: var(--color-status-gray); }
   .lane-tick-mark {
     background-color: var(--color-lane-tick);
   }
   ```

**Depends on:** None (first task)

**Context:**
- `--color-status-blue` (`#388bfd`), `--color-status-green` (`#2da44e`), `--color-status-red` (`#f85149`), `--color-status-gray` (`#6e7681`), and `--color-lane-paused` are already defined in `@theme` and dark-mode `:root`. No new color values need to be invented.
- The `@theme` block uses `--*: initial` which resets all Tailwind defaults; only tokens declared in `@theme` generate Tailwind utility classes. The new CSS classes are hand-authored in the `<style>` block alongside `.lane-label`, `.lane-track`, etc. — not as `@theme` tokens.
- `--lane-label-width` is a layout variable (not a color), so it goes in `:root` (the shared CSS layer), not `@theme` (Tailwind token layer). The `:root` block at line 122 already exists for Tailwind-alias remappings.
- `0.75rem` = `gap-3` (12px at 16px base) used by the flex lane rows (`gap-3` on line 4 of swim-lane.html).
- The `.lane-event` `max-width: 120px` is intentionally a fixed value — the event box is positioned absolutely within a flexible track, so percentage max-widths are relative to the track width and would not constrain short-duration events correctly.

**Verification:**
- `grep -c '\-\-color-lane-tick' claude/dashboard/templates/base.html` >= 1
- `grep -c '\-\-lane-label-width' claude/dashboard/templates/base.html` >= 3 (definition in `:root` + usage in `.lane-label` + usage in `.lane-tick-axis`)
- `grep 'lane-tick-axis' claude/dashboard/templates/base.html | grep -c 'calc'` >= 1
- `grep -c '\.lane-tick-axis' claude/dashboard/templates/base.html` >= 1
- `grep -c '\.tick-label' claude/dashboard/templates/base.html` >= 1
- `grep -c '\.lane-event' claude/dashboard/templates/base.html` >= 1
- `grep -c 'lane-status-' claude/dashboard/templates/base.html` >= 6
- `grep 'lane-event' claude/dashboard/templates/base.html | grep -c 'color-status-gray'` >= 1

**Status:** pending

---

### Task 2: Update `data.py` — remove `_color_map`, expose `status` field

**Files:** `claude/dashboard/data.py`

**What:**

1. Remove the `_color_map` dict (lines 631–637).
2. Remove the `color = _color_map.get(status, "#6e7681")` line (line 643). The `status` variable is already computed on the preceding line (`status = feat.get("status", "pending")`) and is retained.
3. In the `lanes.append(...)` call (lines 683–688), replace `"color": color` with `"status": status`.

**Depends on:** None (independent of Task 1)

**Context:**
- `status` is already computed at line 642 as `feat.get("status", "pending")`. The variable is simply repurposed: instead of being passed to `_color_map` to produce a color string, it is passed directly to the template as the status name.
- The `_color_map` dict is entirely local to the `build_swim_lane_data` function. No other function references it.
- After this change, the template will use `lane.status` (not `lane.color`) to select a CSS class. The lane dict docstring at lines 566–567 references `color`; update the comment to reference `status`.

**Verification:**
- `grep '_color_map' claude/dashboard/data.py | wc -l` = 0
- `grep '"color": color' claude/dashboard/data.py | wc -l` = 0
- `grep '"status": status' claude/dashboard/data.py` matches one line in the `lanes.append(...)` block
- Python syntax check: `python3 -m py_compile claude/dashboard/data.py` exits 0

**Status:** pending

---

### Task 3: Rewrite `swim-lane.html` — remove static inline styles, adopt new classes

**Files:** `claude/dashboard/templates/swim-lane.html`

**What:**

Apply all template changes atomically (all are in the same 37-line file):

1. **Line 10 — Event box**: Replace the current element:
   ```html
   <div class="text-white absolute top-1 h-8 py-0.5 px-1.5 whitespace-nowrap rounded-sm text-xs z-1" style="left: {{ event.x_pct }}%; background: {{ lane.color }};"
   ```
   With:
   ```html
   <div class="lane-event lane-status-{{ lane.status }} text-white absolute top-1 h-8 py-0.5 px-1.5 rounded-sm text-xs z-1" style="left: {{ event.x_pct }}%;"
   ```
   Changes: add `lane-event` and `lane-status-{{ lane.status }}`; remove `whitespace-nowrap`; remove `background: {{ lane.color }}` from inline style (leave only `left: {{ event.x_pct }}%`).

2. **Line 17 — Tool tick mark**: Replace the current element:
   ```html
   <div class="absolute top-0 h-10 w-0.5" style="left: {{ x_pct }}%; background: rgba(255,255,255,0.3);"></div>
   ```
   With:
   ```html
   <div class="lane-tick-mark absolute top-0 h-10 w-0.5" style="left: {{ x_pct }}%;"></div>
   ```
   Changes: add `lane-tick-mark` class; remove `background: rgba(255,255,255,0.3)` from inline style.

3. **Line 25 — Tick axis container**: Replace the current element:
   ```html
   <div class="lane-tick-axis" style="position: relative; height: 20px; margin-left: 200px;">
   ```
   With:
   ```html
   <div class="lane-tick-axis">
   ```
   Changes: remove the entire `style=` attribute (all three properties are now in the `.lane-tick-axis` CSS class defined in Task 1).

4. **Line 27 — Tick label span**: Replace the current element:
   ```html
   <span class="phase-label" style="position: absolute; left: {{ tick.x_pct }}%; transform: translateX(-50%); font-size: 0.7rem;">{{ tick.label }}</span>
   ```
   With:
   ```html
   <span class="tick-label absolute -translate-x-1/2" style="left: {{ tick.x_pct }}%;">{{ tick.label }}</span>
   ```
   Changes: replace `phase-label` class with `tick-label`; add Tailwind `absolute` and `-translate-x-1/2`; reduce inline style to only `left: {{ tick.x_pct }}%`.

**Depends on:** Task 1 (CSS classes must exist before template references them), Task 2 (`lane.status` must be present in lane dict before template references it)

**Context:**
- `whitespace-nowrap` is replaced by the `.lane-event` truncation (`overflow: hidden; text-overflow: ellipsis`) which is a better behavior for clustered events.
- `-translate-x-1/2` is a standard Tailwind utility. Since `@theme` in base.html uses `--*: initial`, only tokens declared in `@theme` generate Tailwind classes. The standard spacing/transform utilities like `-translate-x-1/2` are restored via Tailwind CDN defaults — verify this works as expected. If `-translate-x-1/2` doesn't resolve (because it depends on a reset token), use a manual CSS approach: add `transform: translateX(-50%)` to the `.tick-label` class in base.html instead. The spec allows either approach; adding to `.tick-label` avoids CDN reset ambiguity.
- `absolute` is also a standard Tailwind utility subject to the same concern. The existing template already uses `absolute` on event boxes (line 10) without issue, confirming the CDN provides this despite `--*: initial`.
- After this task, exactly three inline `style=` attributes remain in the file, each containing only `left: {{ ... }}%`.

**Verification:**
- `grep 'style=' claude/dashboard/templates/swim-lane.html | grep -v 'left:.*%' | wc -l` = 0
- `grep 'phase-label.*style=' claude/dashboard/templates/swim-lane.html | wc -l` = 0
- `grep 'rgba' claude/dashboard/templates/swim-lane.html | wc -l` = 0
- `grep 'lane\.color' claude/dashboard/templates/swim-lane.html | wc -l` = 0
- `grep 'whitespace-nowrap' claude/dashboard/templates/swim-lane.html | wc -l` = 0
- `grep 'lane-event' claude/dashboard/templates/swim-lane.html | wc -l` >= 1
- `grep -c 'style="left:' claude/dashboard/templates/swim-lane.html` = 3

**Status:** pending

---

## Verification Strategy

After all three tasks are complete, run the following checks to confirm compliance:

**Acceptance criteria (from spec):**

```sh
# Req 1: No inline styles remain except those containing only left: {{ ... }}%
grep 'style=' claude/dashboard/templates/swim-lane.html | grep -v 'left:.*%' | wc -l
# Expected: 0

# Req 2: Tick labels no longer combine phase-label class with multi-property inline style
grep 'phase-label.*style=' claude/dashboard/templates/swim-lane.html | wc -l
# Expected: 0

# Req 3a: No raw rgba() values remain in swim-lane template
grep 'rgba' claude/dashboard/templates/swim-lane.html | wc -l
# Expected: 0

# Req 3b: --color-lane-tick defined in base.html
grep -c '\-\-color-lane-tick' claude/dashboard/templates/base.html
# Expected: >= 1

# Req 4a: _color_map removed from data.py
grep '_color_map' claude/dashboard/data.py | wc -l
# Expected: 0

# Req 4b: Template no longer references lane.color
grep 'lane\.color' claude/dashboard/templates/swim-lane.html | wc -l
# Expected: 0

# Req 4c: Six lane-status-* classes defined in base.html
grep -c 'lane-status-' claude/dashboard/templates/base.html
# Expected: >= 6

# Req 4d: .lane-event base rule includes fallback background-color
grep 'lane-event' claude/dashboard/templates/base.html | grep -c 'color-status-gray'
# Expected: >= 1

# Req 5: --lane-label-width appears at least 3 times (definition + 2 usages)
grep -c '\-\-lane-label-width' claude/dashboard/templates/base.html
# Expected: >= 3

# Req 5 (calc check): .lane-tick-axis uses calc()
grep 'lane-tick-axis' claude/dashboard/templates/base.html | grep -c 'calc'
# Expected: >= 1

# Req 6: Three new CSS classes defined in base.html
grep -c '\.lane-tick-axis' claude/dashboard/templates/base.html
# Expected: >= 1
grep -c '\.tick-label' claude/dashboard/templates/base.html
# Expected: >= 1
grep -c '\.lane-event' claude/dashboard/templates/base.html
# Expected: >= 1

# Req 7: .lane-event class applied to event boxes in template
grep 'lane-event' claude/dashboard/templates/swim-lane.html | wc -l
# Expected: >= 1

# Req 7: whitespace-nowrap removed from template
grep 'whitespace-nowrap' claude/dashboard/templates/swim-lane.html | wc -l
# Expected: 0

# Req 8: Exactly 3 inline style attributes remain (all data-driven positional left only)
grep -c 'style="left:' claude/dashboard/templates/swim-lane.html
# Expected: 3
```

**Python syntax check:**
```sh
python3 -m py_compile claude/dashboard/data.py
# Expected: exit 0, no output
```

**Manual visual check (if Playwright MCP is available):**
- Navigate to the live dashboard; confirm swim lane renders with correct status colors.
- Confirm tick axis aligns with lane tracks (no longer 12px left of track start).
- Confirm long event labels are truncated with ellipsis rather than overflowing.
- Confirm tool tick marks render correctly (currently always empty, so no visible change expected).
