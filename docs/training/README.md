# Attention Is the Game — workshop deck

The v1 presenter deck for the team talk on working well with coding agents.
Requirements: `cortex/requirements/training.md` · Story/talk track: `cortex/research/training-talk-deck-outline.md` (rev 4) · Q&A prep: `cortex/research/training-talk-qa-bank.md` · Messaging record: `cortex/research/training-talk-messaging-brief.md`.

## Running it

```bash
cd docs/training && python3 -m http.server 8000
```

- `localhost:8000` — the deck (SHARE this window on a call).
- `localhost:8000/presenter.html` — private notes view (KEEP FOCUS here; its arrow keys remote-control the deck over a BroadcastChannel, which is why `http://` is required — `file://` windows can't share a channel).

Controls: **→/space** one beat · **←** previous scene · **b** blank (valves/Q&A) · **Home/End** · URL hash `#5.4` deep-links to section 5 beat 4 (rehearsal/QA).

## The story (rev 4)

One arc, full circle: the cold open poses a mystery (same model, same ask, opposite results — the only visible difference is a context bar), a blueprint card promises three habits, three acts build them (each act-break card lights a post of a dock), and a replay of the cold open — run with the habits — closes the circle before dawn. The three habits, verbatim everywhere they appear: **get the direction on the page · plan your exit at 50% · write your own instructions**.

17 sections: 14 scenes + 3 waypoint cards.

| # | Section | Job |
|---|---|---|
| 1 | Friday, 4:00 PM | the mystery + the context bars + thesis |
| 2 | Three Habits | the blueprint (dashed dock) |
| 3 | The Gauge | vessel = the bar magnified; re-read; zones; exit at 50% |
| 4 | The Squeeze | compaction loses the pinned chips; the lost one detonates |
| 5 | The Rewind | fork, red run, the unbroken rewind take (money shot: `#5.4`) |
| 6 | waypoint | post lit: plan your exit at 50% |
| 7 | The Page | interview → doc → tickets stamped with the intent line → the fork |
| 8 | Wish vs Ticket | controlled experiment: same fresh session, only the ask differs |
| 9 | waypoint | post lit: get the direction on the page |
| 10 | Set More Lines | three fresh agents beat one tired one |
| 11 | Fresh Eyes | readable findings; two bounce, one confirms; one binned (`#11.4`) |
| 12 | waypoint | plank drawn (the techniques); third post pending |
| 13 | The Scroll and the Drawers | 2,041 lines; never let it write its own instructions |
| 14 | Sign vs Turnstile | gates, not prose |
| 15 | The By-Hand List | what stays human |
| 16 | Friday, 4:00 PM — again | the full-circle replay; bar 91% → exit → fresh 8% |
| 17 | Tuesday, 9:00 AM | dawn; recap; the Brass Minnow |

Rev-3 → rev-4 renumbering (the rev-3 deck's slide numbers): 1→1 · 2+3→3 (merged; audience poll cut) · 4→4 · 5→6 · 6+7→7 (badge scene folded in) · 8→8 · 9→9 · 10→10 · 11→5 (moved into Act I) · 12→11 · 13→12 · 14→cut (replaced by 16) · 15→13 · 16→14 · 17→15 · 18→17.

## Architecture

Hand-authored deck over a shared component library — words live with their presentation; only visuals are componentized (see the scene-schema decision in `cortex/requirements/training.md`, Open Questions).

| File | Role |
|---|---|
| `index.html` | All 17 sections, beat markup via `data-beat`/`data-beats` |
| `lib/deck.js` | Engine: beat navigation, per-scene hooks, promise-chained async beats (rapid advances can't interleave), dock builder, night-sky signature, presenter sync |
| `lib/contextbar.js` | The context bar: zone-banded gauge reused in sections 1, 3, 4, 8, 16 — the deck's connective tissue |
| `lib/vessel.js` | The context vessel: labeled pours, scan sweep, zones + exit door, pinned chips + compaction squeeze into the lost pile |
| `lib/terminal.js` | Scripted mock-terminal player (no recordings, ever — staged beats with technically-real content) |
| `lib/filmstrip.js` | Fork/rewind timeline — deliberately built as the wave-2 Cockpit engine seed |
| `lib/notes.js` | Talk-track cues per scene per beat (feeds presenter.html) |
| `lib/deck.css` | Night edition of the landing-page design language; bundled fonts (offline-safe) |
| `presenter.html` | Synced notes + remote control + timer |

Timing knobs: `CHAR_MS`/`LINE_GAP` (terminal.js), squeeze/sweep durations (vessel.js), the rewind take (`totalMs`, filmstrip.js), context-bar animation `ms` per `set()` call (deck.js hooks), per-hook `setTimeout`s (deck.js).

## Status

Rev-4 rebuild (2026-07-13) after the presenter's slide-by-slide review: one story arc, on-screen anchors on every scene, poll/coin-ticker/assembly cut, context bars added, replay scene added. Validated headless: console-clean on all 17 sections, end-states asserted over CDP with real-time animation, every section screenshot-checked at 1280×720 (no overflow). Not yet done:

1. **Real-time rehearsal with a human eyeball** — the beat pacing, the scene-5 rewind take, and the scene-11 toss (`#11.4`) were re-validated headless only; the animations deserve a live pass, and the talk track (notes.js) was redistributed onto new beats and needs a read-through out loud.
2. **Interactive checkpoints**: the audience poll was cut on presenter feedback; `cortex/requirements/training.md` still asks for 2–3 interactive checkpoints. The wish scene's prompts-first beat carries an optional show-of-hands; decide whether that satisfies the requirement or amend it.
3. **Q&A prep dependencies** (see qa-bank): real cost numbers for the making-of story (appendix slide), a real merged-PR trail to show, DPA verification before the compliance answer.
4. Volatile content carries `<!-- volatile -->` markers in the research docs; quarterly sweep per `cortex/requirements/training.md`.
