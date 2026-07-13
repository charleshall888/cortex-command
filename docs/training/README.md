# Attention Is the Game — workshop deck

The v1 presenter deck for the team talk on working well with coding agents.
Requirements: `cortex/requirements/training.md` · Story/talk track: `cortex/research/training-talk-deck-outline.md` (rev 5) · Q&A prep: `cortex/research/training-talk-qa-bank.md` · Messaging record: `cortex/research/training-talk-messaging-brief.md`.

## Running it

```bash
cd docs/training && python3 -m http.server 8000
```

- `localhost:8000` — the deck (SHARE this window on a call).
- `localhost:8000/presenter.html` — private notes view (KEEP FOCUS here; its arrow keys remote-control the deck over a BroadcastChannel, which is why `http://` is required — `file://` windows can't share a channel).

Controls: **→/space** one beat · **←** previous scene · **b** blank (valves/Q&A) · **Home/End** · URL hash `#6.4` deep-links to section 6 beat 4 (rehearsal/QA).

## The story (rev 5)

Theme: **the whole talk is managing context** — every scene is one of three moves, and the three moves are the section headers, the dock posts, and the retell:

> **know what's in the window · get the direction on the page · give every job a clean window**

One arc, full circle: the cold open poses the mystery (same model, opposite results, only the context bar differs), the blueprint promises the three pillars, three acts build them (waypoint cards light a post each), and the finale replays Friday with the whole toolkit chained — interview → epic → three tickets → three parallel fresh windows — completing the dock before dawn.

16 sections: 13 scenes + 3 waypoint cards.

| # | Section | Job |
|---|---|---|
| 1 | Friday, 4:00 PM | the mystery + the context bars + thesis |
| 2 | The Whole Talk | blueprint: three pillars on three dashed posts |
| 3 | The Gauge | vessel = the bar upright; re-read; zones; exit at 50% |
| 4 | The Squeeze | compaction loses the pinned chips; the lost one detonates |
| 5 | The No-Loop | conflicting context = the NO! → still-no → relapse loop |
| 6 | The Rewind | fork, red run, the unbroken rewind take (money shot: `#6.4`) |
| 7 | waypoint | post 1: know what's in the window |
| 8 | The Page | interview → doc → tickets (pipeline rail: /requirements · /discovery) → the handoff payoff |
| 9 | waypoint | post 2: get the direction on the page |
| 10 | Set More Lines | three parallel fresh sessions, clock ticks, you're elsewhere |
| 11 | Fresh Eyes | prep beat (spec → fresh session, "break it") then readable findings |
| 12 | The Scroll and the Drawers | exhibit-zoned skill file vs deck-voice lessons |
| 13 | Sign vs Turnstile | ignored sign → blocked → fix → pass; the line count ticks DOWN |
| 14 | waypoint | post 3: give every job a clean window; the plank waits for Friday |
| 15 | Friday, 4:00 PM — again | the pipeline finale; five bars, one red retired, four green (`#15.4` results) |
| 16 | Tuesday, 9:00 AM | dawn; the completed dock; the Brass Minnow; recap = the pillars |

Rev-4 → rev-5 renumbering: 1→1 · 2→2 (re-worded) · 3→3 · 4→4 · NEW→5 (No-Loop) · 5→6 · 6→7 (new proverb) · 7→8 (fork cut, handoff added) · 8→cut (wish; its ticket-anatomy lesson lives in 8) · 9→9 · 10→10 (+parallel beat) · 11→11 (+prep beat, retitled) · 13→12 · 14→13 (completed story) · 12→14 (moved after turnstile) · 15→cut (by-hand) · 16→15 (rebuilt as pipeline finale) · 17→16.

## Architecture

Hand-authored deck over a shared component library — words live with their presentation; only visuals are componentized (see the scene-schema decision in `cortex/requirements/training.md`, Open Questions).

| File | Role |
|---|---|
| `index.html` | All 16 sections, beat markup via `data-beat`/`data-beats` |
| `lib/deck.js` | Engine: beat navigation, per-scene hooks, promise-chained async beats, dock builder, intent-line flights, night-sky signature, presenter sync |
| `lib/contextbar.js` | The context bar: zone-banded gauge reused in sections 1, 3, 4, 5, 8, 10, 15 |
| `lib/vessel.js` | The context vessel: labeled pours, scan sweep, zones + exit door, pinned chips (squeeze pile, No-loop conflicts) |
| `lib/terminal.js` | Scripted mock-terminal player; `append` continues a session, `snap` lands a punchline instantly |
| `lib/filmstrip.js` | Fork/rewind timeline — deliberately built as the wave-2 Cockpit engine seed |
| `lib/notes.js` | Talk-track cues per scene per beat (feeds presenter.html) |
| `lib/deck.css` | Night edition of the landing-page design language; bundled fonts (offline-safe) |
| `presenter.html` | Synced notes + remote control + timer |

Timing knobs: `CHAR_MS`/`LINE_GAP` (terminal.js), squeeze/sweep durations (vessel.js), the rewind take (`totalMs`, filmstrip.js), context-bar animation `ms` per `set()` call (deck.js hooks), per-hook `setTimeout`s (deck.js).

## Status

Rev-5 rebuild (2026-07-13) after the presenter's second review: context-management theme with pillar-level section headers, new No-Loop scene, page-scene handoff payoff with the real workflow named on the rail, completed turnstile story, exhibit-zoned scroll, pipeline finale; wish-vs-ticket and by-hand cut. Validated headless: console-clean on all 16 sections, CDP real-time end-state assertions, screenshots at 1280×720 (no overflow). Not yet done:

1. **Real-time rehearsal with a human eyeball** — notes.js was redistributed again and needs a read-aloud pass; live checks: the No-Loop's snap-back (`#5.2`), the rewind take (`#6.4`), the finale's fold cadence and triple parallel typing (`#15.3`), and a stopwatch pass (~36 min on paper).
2. **Q&A prep dependencies** (see qa-bank): real cost numbers for the making-of story (appendix slide), a real merged-PR trail to show, DPA verification before the compliance answer. Consider adding "is 4:19-to-5:58 realistic for three tickets?" to the bank — the finale's timestamps invite it.
3. Volatile content: the `/requirements` and `/discovery` chips on the page-scene rail carry `<!-- volatile -->` markers; quarterly sweep per `cortex/requirements/training.md`.
