# Dashboard navigator — audit and improve (fresh-session brief)

You are picking up a backlog navigator that was designed and built in a prior session. It works
and its tests pass. Your job is to audit it hard, fix the defects listed below, and make it
genuinely better to read — not to rebuild it.

## Getting it running

```
cd /Users/charliehall/Workspaces/cortex-command
uv run cortex dashboard --root ~/Workspaces/wild-light --also-root ~/Workspaces/cortex-command --port 8099
```

Surfaces: `/backlog` (the ranked field), `/epics` (the dependency map). Both are shells; content
arrives from `/partials/navigator` and `/partials/epic-map` on a 30s htmx poll with
`hx-swap="morph"`.

**wild-light is the real corpus** — 512 tickets, 11 active epics, and the only backlog with enough
dependency data to exercise anything. cortex-command's own slice is ~4 items and 0 epics; it is the
degenerate case and every change must still render it correctly.

Code: `cortex_command/dashboard/backlog/{graph,score,bands,epic_layout,view}.py` (pure data, no
HTML), templates `_nav_*.html` / `_epic_*.html` / `navigator.html` / `epic_map.html`, CSS and JS
inline in `base.html`. Tests: `cortex_command/dashboard/tests/test_navigator_*.py`.

**The work is uncommitted.** Run `git status` first. Do not commit unless asked; this repo commits
only through `/cortex-core:commit`.

## Defects to fix

Diagnoses below are measured, not guessed. Verify each before you act on it — one of them may have
moved.

### 1. Epic #263's wiring diagram is incoherent

Measured frame geometry:

```
e#344  children=9  spine=3  pool=6  ext=2  elbows=4
e#263  children=3  spine=0  pool=3  ext=2  elbows=3   <-- 3 edges into a pool with no ordering
e#139  children=3  spine=0  pool=3  ext=1  elbows=1
```

`spine=0` means no child constrains a sibling, so all three children sit in the dashed
`UNDECLARED ORDER` enclosure. But two external blockers still draw three elbows *into* that
enclosure. The result is arrows crossing a box whose label says "any of these may be taken first".

`layout_epic` routes external edges against spine columns; with no spine there is nothing to anchor
the routing channel to, so paths overlap and enter the pool at arbitrary points. Decide what an
external blocker pointing into an unordered pool should look like — it is a real relationship and
should not simply be dropped — and lay it out deliberately.

### 2. Node boxes show only `#id` and a state word, not the title

This was a deliberate constraint and it is the right constraint, but the current answer is too
strict. The rule: **never compute a text width from a character-advance constant.** Fonts are not
bundled, Georgia is what actually renders, and three of the five design prototypes produced
overlapping text by estimating glyph widths. Full titles currently live only in the roster table
under each frame.

The rule forbids *measuring* text, not *showing* it. Both of these satisfy it:

- an HTML layer absolutely positioned from the server-computed node coordinates, letting CSS wrap
  and ellipsize (no measurement anywhere), or
- `<foreignObject>` inside the SVG, same reasoning.

Pick one, keep the coordinates server-computed, and make sure the roster table does not then become
redundant — if it does, delete it.

### 3. "not on this board" is wrong for completed blockers

`view.py:255` returns the literal string `not on this board` for any id outside the active slice.
Ticket #265 is *complete*, and completing it is what discharged the hold on #276. Saying it is not
on the board tells the operator nothing and reads like a data error.

Note the inconsistency: `graph.blocked_by_titles` already resolves blocker titles from the **full
corpus**, so band rows on `/backlog` print the real title while the epic map prints the placeholder.
One of these is right. Make them agree.

### 4. A native browser tooltip competes with the hover card

`_epic_frame.svg.html:87` emits `<title>#{{ n.id }} {{ n.title }}</title>` inside each node anchor.
It was kept as the accessible name, but browsers also render it as an OS tooltip on hover — so the
polished hover card and a grey system tooltip appear together.

Remove the `<title>` and give the anchor an `aria-label` instead. Verify the accessible name
survives (the node must still announce as `#331 Dungeon space: enterable interior + load path`), and
check no other surface has the same double-tooltip problem.

### 5. The prose audit — the important one

The pages carry a lot of explanatory copy: section ledes, band rationales, per-epic verdict lines,
the "why it sits here" column, census glosses, ledger term labels. Some of it is load-bearing. Some
is restating what the layout already shows, and some reads as confident-sounding filler.

Audit it against one question per string: **does a reader who has never seen this page make a
different decision because this sentence is there?** If not, cut it.

Specific things to weigh:

- The same explanation should appear **once**. A rejected prototype printed an identical three-line
  paragraph under every epic; check that pattern has not crept back.
- Numbers beat adjectives. `PARTIAL ORDERING — 3 of 9 children constrained by a sibling` earns its
  line. A sentence describing what "partial ordering" means, next to it, does not.
- The typography is an editorial system (serif display, mono data, `§ 01` section numbers, dotted
  leaders). Density is fine; *undifferentiated* density is not. Look hard at whether the section
  breaks fall in the right places and whether the eye can find the three or four things that matter.
- `/backlog` runs §01 pick → §02 alternates → §03 board (10 bands) → §04 census. That is a lot of
  vertical distance. Question the ordering and the granularity, not just the wording.

Screenshot before and after and compare honestly. Prose you wrote is the prose you are least able
to see.

## Constraints — non-negotiable

- **No npm, no build step, no CDN, no new dependencies.** Python + FastAPI + Jinja2 + htmx.
- **All layout computed in Python.** JS may do hover, disclosure and pan; it must never decide a
  coordinate.
- **Never compute text width from a font-metric constant.** See defect 2.
- **Byte-stability**: the same snapshot must render byte-identically, or the 30s morph moves the
  operator's cursor. Nothing may read the wall clock — the staleness term is anchored to
  `max(updated)` across the corpus for exactly this reason.
- **Zero duplicate `id=`, zero nested `<a>`** in rendered output. Both were real defects; both are
  asserted in `test_navigator_render.py`.
- **No test may assert that a phrase appears in skill prose** (`docs/policies.md`). Template value
  assertions are fine; pinning authored copy is not.
- Editing `skills/` or `plugins/cortex-core/**` mirrors: edit canonical sources only. The pre-commit
  hook rebuilds mirrors from staged blobs. `skills/*/references/` carry size pins — after editing,
  run `just ratchet-refs`, then `just build-plugin`, then `just ratchet-refs` again.

## Traps that cost the last session real time

- **Stale bytecode.** A `.pyc` newer than its source produced two phantom test failures and a wrong
  bug diagnosis. `find cortex_command/dashboard -name __pycache__ -type d -exec rm -rf {} +` before
  believing a surprising failure.
- **Jinja macros do not see page context.** `_nav_band.html`, `_nav_pick.html`, `_epic_frame.svg.html`
  and `_epic_tail.html` are imported with `{% from %}` *without* `with context`, so any page-level
  variable is `Undefined` inside them and renders as the empty string — silently. This is why repo
  scoping is applied to hrefs in `view.scope_links` rather than in templates. Do not "simplify" it
  back into the templates.
- **`<dialog>.close()` fires no `close` event in this browser build**, and closing does not restore
  focus. The ticket modal watches the `open` attribute with a MutationObserver instead. Two
  event-based implementations were tried and both failed.
- **The 30s morph swap replaces the panel**, so an element reference held across it is detached.
  Anything that must survive needs a stable server-rendered `id`.
- **The scoring position is deliberate and operator-approved**: leverage outranks declared priority,
  so #331 (low priority) ranks above #147 (high) because it holds 4 of the 5 genuinely blocked
  items. Bands D and E order by score then id. Do not "fix" either without asking.
- Another session may be working in this repo. Check `git status` before assuming a change is yours.

## How to verify

```
uv run pytest cortex_command/dashboard/tests/ -q        # expect ~519 passing
uv run pytest -q                                        # 2 pre-existing worktree-symlink failures
```

Then actually look at the pages, on **both** corpora — wild-light for density, cortex-command for
the degenerate 4-item/0-epic case. Headless screenshots:

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --screenshot=out.png --window-size=1440,2000 --virtual-time-budget=12000 <url>
```

Verify claims by running things, not by reading them. The last session shipped a defect that a
verifier caught only by executing the code path: a ticket blocked by an *off-slice* blocker was
simultaneously the §01 hero pick and drawn as NOT STARTABLE in §03.
