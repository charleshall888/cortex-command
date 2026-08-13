[← Back to Agentic Layer](agentic-layer.md)

# Overnight Dashboard

**For:** Users running overnight sessions who want real-time visibility into session progress.  **Assumes:** The overnight runner is set up and you have at least one session running or recently completed.

The dashboard is a real-time FastAPI web app that monitors overnight autonomous development sessions. It reads the same files the overnight runner writes and displays live state in a browser via HTMX polling. It is optional but recommended for unattended sessions — open it on a second monitor before you go to bed.

Both launch paths bind `127.0.0.1` (loopback only) by default: the shipped `cortex dashboard` verb always binds loopback, and the contributor recipe `just dashboard` defaults to loopback with LAN exposure available only as an explicit opt-in — `DASHBOARD_HOST=0.0.0.0 just dashboard`, or equivalently `just dashboard_host=0.0.0.0 dashboard`.

---

## Launching the Dashboard

```
cortex dashboard
```

Starts a detached server at `http://localhost:8080` (or `$DASHBOARD_PORT` if set, or `--port <int>`), opens your browser to it, and returns the terminal. If something is already serving that port, the command opens that one and exits without starting a second server.

Detached is the default because a dashboard is something you glance at beside the work; holding the terminal that launched it is the wrong trade. Two flags adjust it:

- `--foreground` blocks in this terminal instead, serving until interrupted. Use it in scripts and recipes that are supposed to stay in the foreground — `just dashboard-demo` passes it for exactly that reason.
- `--no-open` skips the browser. Implied by `--format json` and by a non-TTY stdout, so scripted and agent callers need not pass it.

`--background` is still accepted and does nothing, since it now names the default. It is kept because the `dashboard_open` MCP tool passes it explicitly and that tool's argv is version-locked to the plugin rather than to this wheel.

### The machine-readable envelope

```
cortex dashboard --format json
```

Emits a versioned envelope (`status` of `started` / `already_running` / `failed`, plus `url` and `port`; a `started` result also carries `pid` and `roots`), which is what the `dashboard_open` MCP tool consumes. Idempotent — a second invocation reports the running server rather than racing it for the port. `roots` lists every root the server tracks, including those named by `CORTEX_DASHBOARD_ROOTS`.

"Already running" means *something is serving that port*, which is the only question with a caller — not whether a PID file exists. A PID file names a process that may be dead, cannot name a port, and is global where ports are not, so it would refuse a second dashboard on a different port for no reason.

The launch waits for the port to accept a connection before returning, so the URL it hands back is one that already serves.

### Tracking several repositories

```
cortex dashboard --root ~/src/my-app --also-root ~/src/my-other-app
```

`--root` is the default repo; each `--also-root` adds another, and the flag repeats. `CORTEX_DASHBOARD_ROOTS` holds the same list as a path-separated string and composes with the flags rather than being overridden by them.

**To make `cortex dashboard` a bare command**, export that variable from your shell profile and pass nothing:

```
export CORTEX_DASHBOARD_ROOTS="$HOME/src/my-app:$HOME/src/my-other-app"
```

With it set, the verb works from any directory: when the working directory is not inside a cortex project, the **first** entry becomes the default repo and the rest are tracked alongside it. That fallback is the only supported way to launch from outside a checkout — do not reach for `CORTEX_REPO_ROOT`, for the reason given under [Viewing fixture data](#viewing-fixture-data).

The first entry is used verbatim rather than searched for a valid one, so a typo there fails loudly naming the path. Advancing quietly to the second entry would hide the typo behind a dashboard that looks correct and is simply missing a repo.

One process serves them all, each with its own polling loop writing into its own state — a slow disk under one repo cannot stall another's poll. A repo switcher appears in the masthead, and every link and 30s poll on the page carries the repo it belongs to, so switching view keeps the repo and switching repo keeps the view. The switcher is suppressed entirely when one repo is tracked, which is the common case.

An `--also-root` that does not resolve to a directory is dropped: those are typos rather than empty repos, and a switcher entry leading to a permanently blank page is worse than no entry. The primary `--root` is always kept even without a `cortex/` directory, since a freshly-initialised repo is a legitimate thing to point at.

**Prerequisite**: `cortex dashboard` requires a cortex-registered project — run `cortex init` once in your project before launching the dashboard, or name a registered project as the first entry of `CORTEX_DASHBOARD_ROOTS`. The verb fails with a `RuntimeError` if `.claude/` is not present in the resolved root. Resolution order for that root is: `--root` if passed, else the cortex project containing the working directory, else the first `CORTEX_DASHBOARD_ROOTS` entry.

Contributors with a clone of cortex-command can alternatively run `just dashboard` (requires a clone of cortex-command) from the repo root.

### Prerequisites

- Python 3.12+ and the project uv venv (`just python-setup` — same prerequisite as the overnight runner)
- No additional setup required

### Viewing the Dashboard Remotely

Loopback-only is deliberate for the shipped `cortex dashboard` verb, which offers no `--host` flag. Remote viewing is served by port-forwarding over the existing Tailscale mesh rather than by binding another interface:

```
ssh -L 8080:127.0.0.1:8080 <host>
```

With the tunnel open, browse to `http://localhost:8080` on the viewing machine — the dashboard stays bound to loopback on the machine running the session, and the Tailscale mesh supplies the secure channel.

---

## Seeding Fixture Data

```
just dashboard-demo
```

`dashboard-demo` is the single command: it seeds the fixture corpus into an isolated per-user root and serves the dashboard against that root in one invocation. Without the justfile, run the same two steps directly:

```
cortex-dashboard-seed                    # writes the fixture root, then prints the serve command
cortex dashboard --root <printed root>   # serves the dashboard against that root
```

### Where the fixtures land

The seeder writes to `${XDG_STATE_HOME:-$HOME/.local/state}/cortex-command/dashboard-seed/`. Seeding no longer writes into your own repo. Earlier versions targeted the operator's real repository so fixtures would appear alongside real work, and that is what made them dangerous: they clobbered canonical lifecycle files, replaced the single-active-session `overnight-state.json` symlink with a regular file, installed a fake `executing` session that the launchd guardian treated as an unattended recovery target, and leaked fixture output into git history. Containing the seeder to an isolated root removes all of it by construction — `--clean` can no longer reach a tracked file, and the 990–999 backlog ID reservation the old regime required is gone rather than replaced.

`cortex-dashboard-seed --root PATH` overrides the default root; `--print-root` prints the resolved root and exits; `--clean` removes only what the seeder wrote, under that same resolved root. If you ran the pre-containment seeder against a project repo, `cortex-dashboard-seed --sweep-legacy` removes the stray `99[0-9]-seed-*.md` backlog files it left behind — a one-time migration, not part of normal use.

The seeder also publishes `cortex/lifecycle/sessions/latest-overnight` as a relative symlink to the seeded session, mirroring what the runner does at startup. That pointer is what the dashboard poller's fallback path resolves; without it the seeded dashboard rendered as an idle, sessionless page — every panel downstream of the session state showing its empty branch — while the fixture files sat on disk unread. `--clean` removes the link only while it still resolves to a seed session, so a `--clean` pointed at a real repository cannot unlink the runner's own pointer.

`cortex dashboard --root PATH` sets the root for that one process only. Do not export or inline-prefix `CORTEX_REPO_ROOT` to view fixtures: it is the unvalidated root funnel for most of the codebase, and a fixture root satisfies every marker check that guards it — so any persistence beyond one command silently redirects backlog creation, lifecycle verbs, and overnight writes into the throwaway tree.

**Behavioral note**: `just dashboard-seed` alone no longer populates your own dashboard. `just dashboard-demo` is the replacement.

### Seeded and unseeded runs cover different regimes

Both regimes matter, and neither substitutes for the other:

| Run | Corpus | What it exercises |
|-----|--------|-------------------|
| Unseeded (`cortex dashboard`) | your real project | An unseeded project is the only exercise of the near-empty and degraded rendering path the panels commit to |
| Seeded (`just dashboard-demo`) | isolated fixture root | Seeded runs cover volume and state variety — epics and children, every blocker outcome, both deferral vocabularies, lifecycle artifacts, and rendered markdown |

---

## What It Shows

The dashboard is divided into three peer views, reachable from the masthead nav: **Overnight** (`/`), **Backlog** (`/backlog`), and **History** (`/sessions`). Section numbering (`§ 01`, `§ 02`, …) restarts in each view, because the register is per-view rather than per-app, and counts the sections a given corpus actually draws. On the two views with suppressible sections — the navigator and the ticket page — the ordinals are assigned at render, so a repo with no epics reads `§ 01 · § 02 · § 03` rather than skipping the number the epic section would have taken. A gap in a numbered register reads as a section that failed to draw.

The split is what the two groups of panels are *for*. Overnight answers "what is the runner doing right now" and refreshes every 3–5 s; Backlog answers "what is queued, what is ready, and what is blocked on what" — a question that outlives any one session and that an operator asks while nothing is running at all — and refreshes every 30 s. The backlog panels previously sat at the bottom of the overnight page as § 10 and § 11 of eleven, which read as an overnight subsection.

## Overnight view (`/`)

Nine panels plus an Alerts Banner.

### Alerts Banner

Circuit breaker status and per-feature alert indicators with severity-coded colors. A tripped circuit breaker means the runner has paused new dispatches due to repeated failures.

### 1. Session Panel

Live indicator, session ID, phase status, current round, elapsed time, progress bar, and feature counts broken down by status (merged / running / pending / paused / failed / deferred). When no session is active, the panel falls back to showing the last completed session.

### 2. Open Questions / Escalations

Surfaces worker-to-orchestrator escalations for the active session — open questions, deferred work, and blocking items that require human review. Reads from the per-session `escalations.jsonl` file.

### 3. Feature Cards

One card per feature in the session. Each card shows the feature title, status badge, model tier, and complexity. Running features display the current phase and a task progress bar. Failed features show the error message and recovery attempt count. Alert badges surface deferred questions, stalls, rework, and failures at a glance.

An expanded card's artifact row links to the feature's ticket page — `backlog #N` to `/tickets/{id}`, and `spec.md` / `plan.md` to that page's `#spec` and `#plan` panels. All three depend on the feature's `backlog_id`, which is legitimately absent for a feature not sourced from a numbered backlog file; those labels then render without a link rather than pointing nowhere, since the page is keyed on an id and a bare lifecycle path carries only a slug.

### 4. Recent Activity Stream

Tails the most recent entries from `overnight-events.log`, surfacing the live event stream so operators can see what the runner is doing right now without scanning the full log.

### 5. Agent Fleet Panel

Count of active agents and, for each agent: its feature slug, current phase, duration, and last activity timestamp. Useful for confirming that agents are making progress and not stalled.

### 6. Swim-Lane Timeline

Horizontal timeline of feature execution, color-coded by phase (spec, plan, implement, review), with time ticks along the axis. Gives a visual overview of how features overlapped and where time was spent.

### 7. Metrics Baseline

API cost and token-usage rollups read from `metrics.json`. Provides at-a-glance spend tracking for the active session and a baseline for comparing against prior runs.

### 8. Round History Table

Chronological list of completed rounds with feature counts and per-round durations. Shows how the session has progressed over time.

### 9. Pipeline Panel

Monitors active interactive pipeline execution (separate from overnight). Visible only when an interactive pipeline session is running alongside the overnight session.

---

## Backlog view (`/backlog`)

One page, four sections, all served from the same 30 s slow-poll snapshot so the
reconciliation can never close over a partition a different swap produced.

It answers two questions and refuses a third. It says **what is on this board**
and **how that work is structured**. It does not say what you should work on —
there is no pick, no alternate, no swap condition, no counterfactual and no
ledger. Ranking by points and drawing the dependency structure is the whole job;
choosing is `/cortex-core:dev`'s.

**Epics lead the page.** The order is Epics, Ready, Blocked, Not ranked.
Structure before list: the groups say what the board is made of, and a reader
who scrolls past thirty loose rows to reach them has already formed the wrong
picture of the board. On a corpus with no epic the section does not exist and
Ready leads, which is the same rule rather than a special case — three of the
four sections are conditional and the register numbers what rendered.

**One record, one appearance.** A ticket whose `parent` resolves to a real
ticket is drawn inside that epic's map and nowhere else. An epic container is a
section heading and never a row. So the Ready and Blocked lists are *loose*
records only, and the Epics section is where everything else lives. The rule is
applied in exactly one place (`view._partition`); a second site is how the same
ticket comes to read one thing in a list and another in a frame.

A parent that does **not** resolve to a real ticket is treated as no parent, so
a typo in a `parent` field leaves its ticket loose and visible rather than
moving it into a phantom epic named after the typo and off the board entirely.

### 1. Epics

One collapsed `<details>` per parent group. Groups with startable children come
first, and largest first within each half — size alone had put a group of five
deferred children above four groups that had ready work. A group with nothing
startable keeps its place in this list rather than moving to a section of its
own: it is already one shut line whose summary says "5 deferred", and the fix
for a bad ordering is the ordering.

The head line carries the only things that could make you open it: how many
children are ready, held or deferred, and — when it applies — the head's own
status, which is a grooming finding rather than something to bury. That word
appears when the head has closed or been deferred while its children are still
live; a head in the ordinary live case needs no word.

**The head state is the head's own status, never an inference from the
children.** A group whose children are all deferred is already reported as "5
deferred", which is a count and cannot be wrong. Calling the head deferred
because of them would print a status the ticket does not carry — and the corpus
has that case: a head at `backlog` over five deferred children, where the
derivation would state a falsehood and bury the grooming defect that produced
it. The head is what is wrong there, and the board's job is to show it.

Opening a group draws its children exactly once, in one of two ways:

- **A group that declares a dependency gets the SVG frame** — longest-path wave
  columns, a reserved lane per external blocker, right-angled elbows routed
  through lanes the layout knows are empty, a dashed enclosure for the children
  no sibling constrains, and a per-epic arrowhead marker. Marked `⇄` in the head
  line.
- **A group that declares none gets a plain grid of child tiles.** No dashed
  box, no "no ordering declared" verdict.

That gate is the whole answer to the measurement this renderer was once retired
over. It was removed because five frames drew two arrows between them — but what
it emitted for a group with *no* edges was a dashed box around an unordered
list, and those boxes were most of its output. Fed the same corpus today the
engine draws **nine arrows across four groups**, including a three-wave spine
and a populated external-blocker lane. So the geometry stays and is gated on
whether there is anything to draw.

External blockers are drawn, and they are the majority case: on the largest real
corpus 3 of 5 live edges point into an epic from a ticket that is not one of its
children. The lane that places them is why a per-epic frame can draw them at
all.

Every coordinate comes from `epic_layout` and **nothing measures text**. A node
is a `<foreignObject>` the server sized and placed, holding ordinary HTML; CSS
wraps and clamps the title inside a box whose dimensions were already decided.
The fonts are not bundled and Georgia is what renders — which is harmless,
because a wider font wraps sooner instead of overflowing a box sized to a
guessed advance.

### 2. Ready

Every loose startable record, ordered by points, highest first — across bands
rather than within them, because a band boundary in the middle of a
points-sorted run is an inversion a reader can see and cannot explain.

Four columns: points, id, title, type. The board previously printed seven. Two
of the three that went were blank most of the time — "why it sits here" was
empty on 54 of 78 rows and the rank on 46 of 51 startable ones — and between
them they took the width that wrapped half the titles onto a second line. The
band letter went because the section a row sits in already says what the letter
said.

What survives of the band is a single glyph in the points cell, on three bands
out of eleven: `⚷` holds other work, `▸` already in flight, `✓` its declared
blocker has already closed. Sparse by construction, so a mark reads as an
exception rather than as a column.

No per-row "reason" column. The dominant scoring term is `priority` on 49 of 51
startable rows on the largest real corpus, so such a column would print the same
word forty-nine times. The points number is the ordering claim; the hover card
carries the working for any single row on demand.

### 3. Blocked

Loose records waiting on a live blocker, each naming what holds it. A blocker
that has already closed is struck through rather than hidden: the edge is why
the row was ever held, and its closing is the news.

A ref that names no ticket the corpus knows — a bare uuid left behind by a
deleted or never-created item — is printed as the ref plus "names no known
ticket", and is deliberately **not** a link: `/tickets/{that-ref}` is a 404,
and the section's own promise is that each row names its blocker. The epic maps
draw the same dangling reference the same way, as an off-board node.

On a corpus where every held ticket belongs to an epic this list is empty and
**the section is not drawn at all**. The fact survives as a clause on the Epics
lede — "5 tickets here are held by a live blocker, drawn with the arrow that
holds them" — beside the maps that draw the records. A heading, a "5 held"
count and a body whose only sentence was that the records were somewhere else
is a section that reads as a rendering failure.

A board where nothing is held keeps its section, because "nothing on this board
waits on a live blocker" is a finding about the board and the count is what
proves it. Empty-because-elsewhere and empty-because-none are different facts
and only the first one loses its section.

### 4. Not ranked

Collapsed panels for what is on the board and out of the running, **one panel
per reason**: deferred, untriaged, off the board, unrecognised status. Each
count is readable without opening a panel.

A panel is labelled with the thing it holds. "Held by decision" was a coined
phrase for `status: deferred`, and a reader had to translate it back; a label
that restates the status costs nothing to read and cannot drift from it. Where
the label is the whole fact, the gloss beside it is omitted rather than made up.

Out of the running is not the same as not worth doing. Band H tests
`status: new` before any startability rule, so an untriaged row is excluded on
its status alone and may be the highest-pointed unstarted work on the board —
the lede says so rather than claiming nothing here is a candidate.

The single panel this replaced was labelled "untriaged · closed in place ·
off-board" — three unrelated findings under one heading, so no row in it could
be read without opening the ticket. The split runs on the same facts, tested in
the same order, that `bands._RULES` used to assign the band, so it cannot
disagree with the banding: off-board is tested before untriaged because the
band is assigned that way, and a split that tested `new` first would file a
record under a reason the banding did not use.

There is deliberately no "closed in place" panel. `collect_items` drops a
terminal-status record before it reaches `active_items`, so no such record is
ever in the board's ordering; the only terminal records that reach the board at
all are the closed epic heads the feed adds to `items` alone, and those are
off-board by the test that runs first. A panel for it would be a label no row
can carry.

### The filter

A strip above the Ready list narrows every **loose** list on the page at once —
Ready, Blocked, and each collapsed panel — on a free-text match over id and
title plus a toggle per `type`. Each list reports "showing N of M" while a
filter is applied, and a shut panel's own count reads "0 of 10" rather than
appearing empty over its matches.

The chips are built from the values the rendered rows actually carry rather
than from a fixed vocabulary: `type` is an open field, and a hardcoded
feature/bug/chore strip offers a consumer repo three filters that match nothing
while hiding the two it uses.

It does not reach the epic maps. A frame's geometry is computed server-side and
hiding one node would leave its arrows pointing at nothing.

The filtering is client-side and the state lives in `sessionStorage`, re-applied
after each swap. That is what keeps an unfiltered poll byte-identical to the
last one — a server-side filter would make the fragment differ per operator and
take that property with it. The strip ships `hidden` and JS unhides it, so a
reader without JS is never shown a filter that cannot filter.

### Hover and click

Every ticket on the page — list row, frame node, epic child tile — is a
`.js-ticket` element carrying its own `data-t-*` payload. Hovering paints a card
from values this render already computed, so it costs no request and cannot lag
behind the pointer; clicking opens the ticket in a `<dialog>`.

**In a list the whole row is the target**, not the id cell: the payload and the
hook sit on the `<tr>`. A title column holding 70% of the table's width and
doing nothing when clicked is a target the eye reads as live and the pointer
does not. The id stays a real anchor inside it, marked `js-ticket-self` so the
delegated handler can tell it from the blocker refs in the same row — those
point at *other* tickets and navigate rather than opening this one.

The three shapes expose the *same* keys (`view._hover` is merged flat into each).
That is load-bearing: nesting the payload under a `preview` key on nodes but not
on rows made a single shared macro read four of six attributes as `Undefined` on
every node in every frame, which renders as the empty string with no error
anywhere.

The card and the dialog live **outside** the poll target. An element inside it
is destroyed every 30 seconds — a dialog would be torn out from under a reader
mid-sentence, and a card would be left describing a row that no longer exists.

The anchors keep working as anchors: only an unmodified left-click is
intercepted, so cmd-click, middle-click, "open in new tab" and a browser with no
JS all still reach `/tickets/{id}`. Keyboard Enter *is* intercepted, so the
keyboard has the same capability the pointer does.

### The reconciliation footer

`78 on this board · 32 ready · 30 inside epics · 5 epic heads · 0 blocked · 11
not ranked ✓`

Decomposed by **where on the page a reader can find the record**, so it doubles
as the table of contents the page otherwise lacks. It compares the set of ids
the partition actually routed against the slice it was handed.

The line it replaced compared the sum of the band counts against the sum of the
band counts — the same expression on both sides — so it printed "every record on
this board is in exactly one band" unconditionally, including on a board that
had dropped one. Its failure branch was unreachable code. The structural
guarantee that no record can vanish is the catch-all routing rule in `bands.py`,
and it always was.

**Dependency cycles.** When two records block each other the page names the ring
(`#a → #b → #a`) in the error colour. The graph has always detected these —
Tarjan's SCC, on every poll — and for a long time nothing rendered the result,
which is worse than not looking: both tickets land in "behind a live blocker"
and the per-row explanation is true of each and actionable for neither. The line
costs nothing on a healthy corpus, where it does not render at all.

**Ticket descriptions.** A ticket's markdown body is not carried in the 30 s
snapshot: this repo's backlog is ~1.5 MB across 400+ files, so embedding bodies
would morph hundreds of KB into the DOM twice a minute to show prose nobody
asked for. The body is fetched per modal open, and the per-ticket reader is
`/tickets/{id}`.


---

## Ticket page (`/tickets/{id}`)

A detail page for one ticket, reached by link rather than from the nav — the same shape as `/sessions/{id}`, which is likewise absent from the masthead. It renders a frontmatter badge strip (status, priority, type, plus parent and areas where present), the ticket body through the same loader the board's expandable row uses, and, on an epic, its children as links to their own pages. An unknown id returns 404; a non-local backlog backend renders an unavailable state rather than raising.

Badges here use the backlog vocabulary (`complete`, `refined`, `backlog`, `wontfix`, `superseded`, …), not the overnight feature-pipeline vocabulary the feature cards use — the two sets differ, and the page shares the board's mapping through `templates/patterns/backlog_badges.html` rather than carrying a third copy.

**Lifecycle artifacts.** Research, spec, plan, and review each get a `<details>` panel, fetched from `/partials/ticket/{id}/artifact/{kind}` when that panel is opened. Only the kinds actually present get a panel; absent ones are not rendered as empty shells. Opening the page fetches no artifact at all — rendering all five documents eagerly measured 77.8 ms against a 7.5 ms median per artifact, so the operator pays only for what they open. Arriving with a `#spec` or `#plan` anchor opens that one panel, which is what makes the feature cards' artifact links land somewhere.

The directory holding those artifacts is found by a two-key join: the `spec:` frontmatter value's parent directory first, then a `lifecycle_slug` probe of `cortex/lifecycle/<slug>/` and `cortex/lifecycle/archive/<slug>/`. Measured over this repo's corpus, the two keys together resolve 290 tickets where `spec:` alone resolves 262; a stale `spec:` pointing at a deleted directory falls through to the probe instead of dead-ending. Tickets carrying neither key render body and badges with no artifact section.

Both routes are declared as plain `def` rather than `async def`. The dashboard's other handlers are coroutines doing synchronous disk work, which holds the event loop for the render's full duration; Starlette dispatches a non-coroutine handler to a threadpool instead. Measured against a 50 ms-tick background loop, a 300 ms handler starved the tick to a 306 ms gap as `async def` versus 52 ms as `def`. These are the first routes rendering artifact-sized documents, so they are the first where it shows.

---

## History view (`/sessions`)

Navigate to `/sessions` to list past sessions. `/sessions/{session_id}` shows the per-session detail view for any completed session. Both views are read-only.

The list carries session id, start, duration and outcome counts. Duration is the span from `started_at` to `updated_at` in the session's own `overnight-state.json`, rendered at session scale (`3h 17m`, `42m`) by the same helper the detail page uses — one function, so a session cannot report two different lengths of itself. It reads `—` only when a state file carries no usable pair of timestamps.

---

## Data Sources

The dashboard reads directly from files written by the overnight runner — no separate data pipeline is needed:

**Session state**

- `~/.local/share/overnight-sessions/active-session.json` — session pointer. Resolves which session directory the state and event files live in; the dashboard falls back to the local `cortex/lifecycle/` copies when the pointer is absent.
- `overnight-state.json` — session metadata and per-feature statuses. Key fields: `session_id` (unique session identifier), `phase` (session phase: `planning` | `executing` | `complete` | `paused`), `current_round` (1-based round number), `started_at` (ISO 8601 UTC timestamp), `features` (mapping of feature slug → status object with `status`, `started_at`, `completed_at`, `error`, and `recovery_attempts`), `round_history` (list of completed round summaries).
- `overnight-events.log` — NDJSON event stream (one JSON object per line). Each line has the form: `{"v": 1, "ts": "<ISO-8601>", "event": "<type>", "session_id": "...", "round": N}` with optional `"feature"` and `"details"` fields. Event types include `session_start`, `feature_start`, `feature_complete`, `feature_failed`, `circuit_breaker`, and others.
- `pipeline-state.json` — interactive pipeline state, read from `cortex/lifecycle/sessions/latest-pipeline/`. Absent is the normal "no active pipeline" signal, and the Pipeline panel reflects that.
- `pipeline-events.log` — `dispatch_start` events supplying each feature's model tier, complexity, budget, and criticality.
- `metrics.json` — API cost and token-usage data

**Per-feature files** (under `cortex/lifecycle/{slug}/`)

- `plan.md` — task-level progress for each feature
- `events.log` — phase transitions and per-phase timings
- `agent-activity.jsonl` — tool activity, last-activity timestamps, and incremental cost deltas (read by offset, so no double-counting). This file lives under the **feature**, not the session, and is appended to rather than recreated, so it outlives any one run. That is what makes the session boundary below load-bearing.
- `escalations.jsonl` — open questions and worker-to-orchestrator escalations
- `exit-reports/*.json` — per-task worker exit reports
- `pr.json` — the feature's PR artifact
- `learnings/progress.txt` — recovery attempt history for failed and paused features

**Backlog and configuration**

- `cortex/backlog/*.md` — feature titles and frontmatter status fields
- `cortex/backlog/archive/*.md` — archived items, so a blocker pointing at a terminal ticket resolves as resolved rather than missing
- `cortex/lifecycle.config.md` — backlog backend. The `cortex/backlog/` reads above happen only while `resolve_backlog_backend(root)` resolves to `cortex-backlog`; under any other backend the dashboard stands down rather than showing stale local counts.

For the schemas, state machine, and lifecycle of these files, see [overnight-operations.md](overnight-operations.md).

### Polling Intervals

The dashboard uses two polling layers:

| Layer | Target | Interval |
|-------|--------|----------|
| Backend `_poll_state_files` | `overnight-state.json`, `pipeline-state.json`, and per-feature files | every 2 s |
| Backend `_poll_jsonl_events` | `overnight-events.log` (NDJSON tail) | every 1 s |
| Backend `_poll_alerts` | Alert evaluation (stalls, failures, circuit breaker) | every 5 s |
| Backend `_poll_slow` | Backlog counts, ticket feed, dispatch details, metrics | every 30 s |
| HTMX (browser-side) | Alerts Banner, Session, Feature Cards, Agent Fleet, Swim-Lane, Round History, Escalations | every 5 s |
| HTMX (browser-side) | Recent Activity Stream | every 3 s |
| HTMX (browser-side) | Metrics Baseline (Overnight); the navigator — all four sections in one fragment (Backlog view) | every 30 s |
| HTMX (browser-side) | Ticket description (`/partials/ticket/{id}`) | once, on first expand |

Total state-change latency is up to approximately 7 seconds (2 s backend read + 5 s HTMX refresh) for panels on the 5 s HTMX interval. For 30 s-polling panels (Metrics Baseline and the navigator), end-to-end latency is up to approximately 32 seconds.

The backend pollers are view-independent: all four run for the process, so switching views costs a page load but never a cold start.

### The session boundary

The dashboard process is meant to run for weeks, so it outlives many sessions. When `_poll_state_files` sees the active session's identity change it calls `DashboardState.reset_for_new_session()`, which drops the running cost totals and the `overnight-events.log` offset.

Two details are easy to get backwards, and both have bitten:

- **The boundary is keyed on the session's own id**, not on the path it was read through. The runner repoints `sessions/latest-overnight` at each new session, and that symlink is the path the poller falls back to whenever the active-session pointer is not `executing` — so a path-derived key is the same string every night and the boundary never fires after the first poll.
- **Per-session offsets reset; per-feature offsets do not.** `overnight-events.log` is a new file each session and must be re-read from byte 0. `agent-activity.jsonl` is cumulative under the feature, so its offset is exactly the mark dividing previous sessions' rows from this one's — zeroing it re-reads last night's spend and inflates the § 01 cost KPI, which is the failure the reset exists to prevent.

The alert state resets here too. `evaluate_alerts` only ever *sets* `circuit_breaker_active`, so "fires once per session" holds only because the boundary re-arms it; and `alerts` is keyed `(slug, condition)` and cleared only for slugs in the current session's feature list, so an alert for a feature that does not run again is unreachable by the code that would clear it.

---

## Visual Evaluation with Playwright MCP

Playwright MCP gives Claude interactive browser access to the running dashboard — navigate, screenshot, and inspect the UI using Claude's multimodal vision. This closes the feedback loop between code changes and visual outcomes during interactive development.

### Prerequisites

- **Node.js 18+** must be installed (`node --version` to verify). All Python-based skills (`ui-judge`, `ui-a11y` — now in the `cortex-ui-extras` plugin from the `cortex-command` marketplace) work without Node.js; only Playwright MCP requires it.
- On first use, the MCP server automatically downloads Chromium browser binaries (~150MB). No manual setup step is required, but the first tool call will be slower while the download completes.

### Per-Session Setup

Before using Playwright MCP tools, start the dashboard with fixture data:

```
just dashboard-demo   # seed the fixture root and serve the dashboard against it
```

The server comes up at `http://localhost:8080`. See [Seeding Fixture Data](#seeding-fixture-data) for what the fixtures cover and where they live.

Then ask Claude to navigate and screenshot the dashboard — for example: *"Take a screenshot of the dashboard at localhost:8080 and describe what you see."*

### Playwright MCP and Existing Evaluation Skills

The three visual evaluation tools are complementary and serve different purposes:

| Tool | Purpose | When to use |
|------|---------|-------------|
| `ui-judge` skill (plugin) | Structured rubric-based evaluation (UICrit pattern) | Overnight sessions, automated quality gates, scoring against defined criteria |
| `ui-a11y` skill (plugin) | Accessibility checking against WCAG guidelines | Verifying accessibility compliance |
| Playwright MCP | Ad-hoc interactive visual access | Development-time inspection, iterating on UI changes, exploratory visual debugging |

`ui-judge` and `ui-a11y` are no longer bundled by default. They ship in the `cortex-ui-extras` plugin from the `cortex-command` marketplace and require the plugin to be installed and enabled (`/plugin install cortex-ui-extras@cortex-command`; see [docs/setup.md](setup.md) for the full install walkthrough).

Playwright MCP is a development tool for interactive sessions — it is **not** used in overnight or autonomous agent runs. Overnight evaluation uses `ui-judge` and `ui-a11y` (when the plugin is enabled), which produce structured output compatible with unattended execution. Playwright MCP's per-session approval prompt makes it incompatible with unattended use.

### Bumping the Playwright MCP Version

The MCP server is pinned to a specific version in `.mcp.json` to avoid regressions. To update, edit `.mcp.json` and change the `@playwright/mcp@<version>` string to the desired version, then restart Claude Code to pick up the change.

---

## Known Limitations

- No authentication layer — both launch paths bind `127.0.0.1` (loopback only) by default, so the dashboard is reachable only from the local machine. The contributor recipe `just dashboard` can bind other interfaces via an explicit opt-in (`DASHBOARD_HOST=0.0.0.0 just dashboard`); the shipped `cortex dashboard` verb offers no equivalent, and remote viewing goes through the `ssh -L` port-forward described above.
- Session history is read-only — the dashboard cannot trigger retries or modify session state.
- Visual layout may vary between active and idle states; with no active session the Agent Fleet and Pipeline panels stay in place and render empty-state text (`fleet stood down · no session`, `no pipeline · refinement queue empty`) rather than disappearing.

### Threat model

The loopback default is defense-in-depth, not a sanitizer. The dashboard renders agent-generated markdown as unescaped HTML and validates neither the `Host` nor the `Origin` header, so a residual DNS-rebinding risk against an unauthenticated local service remains accepted rather than closed. What the bind default changes is who can reach the server at all.

With the default in place, only the local machine can. Once the `DASHBOARD_HOST` opt-in binds another interface, anyone on the same layer-2 broadcast domain can read session state, feature names, and log excerpts without authenticating. Do not expose that port to the public internet, and do not treat "local network" as equivalent to "home network" — hotel Wi-Fi, coworking Wi-Fi, and shared office VLANs are all "local" to a non-loopback bind and are not trusted peers. The framing trap bites hardest at 2am, so the corollary is worth stating plainly: the opt-in assumes a peer set the operator controls end-to-end, and every other case is better served by the `ssh -L` port-forward above.
