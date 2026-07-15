# Context Is the Game — workshop deck

The v1 presenter deck for the team talk on working well with coding agents.
Requirements: `cortex/requirements/training.md` · Story/talk track: `cortex/research/training-talk-deck-outline.md` (rev 10) · Q&A prep: `cortex/research/training-talk-qa-bank.md` · Messaging record: `cortex/research/training-talk-messaging-brief.md`.

## Running it

```bash
cd docs/training && python3 -m http.server 8000
```

- `localhost:8000` — the deck (SHARE this window on a call).
- `localhost:8000/presenter.html` — private notes view (KEEP FOCUS here; its arrow keys remote-control the deck over a BroadcastChannel, which is why `http://` is required — `file://` windows can't share a channel).

Controls: **→/space** one beat · **←** previous scene · **b** blank (valves/Q&A) · **Home/End** · URL hash `#6.4` deep-links to section 6 beat 4 (rehearsal/QA).

## The story (rev 10)

Theme: **the whole game is managing context** — every scene is one of three moves, and the three moves are the section headers, the dock posts, and the retell:

> **keep your context window lean · spawn more agents · keep your workspace clean**

One arc, full circle: the cold open poses the mystery (same model, opposite results, only the context bar differs), the blueprint promises the three pillars, three acts build them (waypoint cards light a post each), and the finale replays Friday with the whole toolkit chained — interview → epic → three tickets → three parallel fresh windows — completing the dock before dawn.

16 sections: 13 scenes + 3 waypoint cards.

| # | Section | Job |
|---|---|---|
| 1 | Friday, 4:00 PM | NIGHTLINE introduced on the title card; fresh vs six-hour session, both at 4:00 PM; the bars (the "whole game" thesis is spoken now, off-screen) |
| 2 | The Whole Game | blueprint: three pillars on three dashed posts |
| 3 | The Gauge | vessel = the bar upright; re-read; zones (goldilocks labeled, no clock labels); exit at 50% |
| 4 | The Squeeze | compaction as a gamble, anchored 2:00 PM; compacts to ~5%; the payoff is the cold open from inside ("attempted after compaction"); bars chain 95→5→58→89→91 |
| 5 | The Death Spiral | one stubborn bug, three laps; the staircase of failed attempts + corrections reddens; bar climbs 58→89 |
| 6 | The Rewind | fork, red run, the unbroken rewind take (money shot: `#6.4`) |
| 7 | waypoint | post 1: keep your context window lean |
| 8 | Write It Down | interview → doc → 3 tickets (pipeline rail: /requirements · /discovery) → the ordered offer (dependency map) |
| 9 | Set More Lines | ONE chart: the gauge laid along a clock — ochre wedge (cliffs = auto-compacts, area = the bill) vs a blue dependency chain (one lane, then two in parallel); two bills; verdict line |
| 10 | Fresh Eyes | prep beat, then one finding per advance (7 beats; manufactured finding: `#10.7`) |
| 11 | waypoint | post 2: spawn more agents (proverb "set more lines"; banks write-it-down · set-more-lines · fresh-eyes) |
| 12 | The Scroll and the Core | exhibit-zoned skill file; the gate beat ticks the count DOWN (`#12.3`); the fix as a second exhibit |
| 13 | The Tackle Box | tooling hygiene, drawn as the dock's shared tackle box (pv-3's proverb, finally shown — no bars): your lean skill is a lure → you land a fish (prove it) → the villain staples it onto every rod, even one that "never casts" (forced, rail reddens) → the box's rule "nothing goes in till it's landed a fish" → a crewmate takes it by choice; PR-vs-opt-in fork; verdict "Rent is what you force on the crew. Tackle is what they choose." |
| 14 | waypoint | post 3: keep your workspace clean; the plank waits for Friday |
| 15 | Friday, 4:00 PM — again | the pipeline finale; five bars, one red retired, four green (`#15.4` results) |
| 16 | Tuesday, 9:00 AM | dawn; the completed dock; the Brass Minnow; recap = the pillars |

Rev-8 → rev-9 changes (the pattern-lens audit — the presenter's five review rounds distilled into a seven-principle lens, three audit agents run against the deck, verified findings applied): four contradictions fixed (both cold-open panes at 4:00 PM; the squeeze anchored 2:00 PM with its payoff revealed as the cold open from inside — bars now chain 95→30→58→89→91 across scenes 4→5→1; finale scorecard "without/with the habits"; scene 11 says "requirements" like scene 8) plus the should-fix list (one name for flip-through everywhere, no auth in the fiction, "wasn't in the room", the Minnow stamp gloss mirroring dawn, "planned last scene" restored, METR hedged as a bet, "instruction files", the dock's one-line intro, "The Scroll and the Core", the skill-size confession defused, the death-spiral interview callback, chart bracket "peaks ≤18%"). Declined by design: an on-screen compaction definition, trio-stagger changes, edits to the thesis or closer. Full rationale in the outline doc.

## Architecture

Hand-authored deck over a shared component library — words live with their presentation; only visuals are componentized (see the scene-schema decision in `cortex/requirements/training.md`, Open Questions).

| File | Role |
|---|---|
| `index.html` | All 15 sections, beat markup via `data-beat`/`data-beats` |
| `lib/deck.js` | Engine: beat navigation, per-scene hooks, promise-chained async beats, dock builder, intent-line flights, night-sky signature, presenter sync |
| `lib/contextbar.js` | The context bar: zone-banded gauge reused in sections 1, 3, 4, 5, 8, 10, 14 |
| `lib/vessel.js` | The context vessel: labeled pours, scan sweep, zones + exit door, pinned chips (squeeze pile, No-loop conflicts) |
| `lib/terminal.js` | Scripted mock-terminal player; `append` continues a session, `snap` lands a punchline instantly |
| `lib/filmstrip.js` | Fork/rewind timeline — deliberately built as the wave-2 Cockpit engine seed |
| `lib/notes.js` | Talk-track cues per scene per beat (feeds presenter.html) |
| `lib/deck.css` | Night edition of the landing-page design language; bundled fonts (offline-safe) |
| `presenter.html` | Synced notes + remote control + timer |

Timing knobs: `CHAR_MS`/`LINE_GAP` (terminal.js), squeeze/sweep durations (vessel.js), the rewind take (`totalMs`, filmstrip.js), context-bar animation `ms` per `set()` call (deck.js hooks), the econ chart's clip-reveal transitions (deck.css `.eg-clip-*` + `sc-lines` hook), `flyArrow` per-call `ms`, per-hook `setTimeout`s (deck.js), the arrival choreography + lobby-idle periods (deck.css `.arrive` delays; every idle period is incommensurate on purpose), the plink/glint jitter (`schedulePlink`/`scheduleGlint`, deck.js), the dawn sunrise (deck.css `.dawn-glow` transition + `post-light` delays).

## Status

Rev-11 (2026-07-14), the presenter's seventh review: the three posts renamed to name the move in the reader's words — **keep your context window lean · spawn more agents · keep your workspace clean** — each now aligned with its own proverb (cut-and-retie / set-more-lines / take-care-of-your-tackle). Act II ("spawn more agents") absorbs Set More Lines + Fresh Eyes, so pv-2 closes the act like the other two waypoints ("write the direction down" is now post 2's sub-line). New scene **The Tackle Box** (13) added in Act III — tooling hygiene the scroll doesn't cover: prove a skill on your own work, then share by kind (project-specific → PR; generic → opt-in kit), never force it. Drawn as the dock's shared tackle box (the object pv-3's proverb names but the deck never drew — no bars): your skill is a lure, you land a fish to prove it, the villain staples it onto every rod (even one that never casts — the rail reddens), the box's rule is "nothing goes in till it's landed a fish," and a crewmate takes it by choice. Verdict "Rent is what you force on the crew. Tackle is what they choose." A first crew-of-five-bars draft was cut after a critique/redesign fan-out (six creative + two critical agents) found it overbuilt and restating scene 12's picture; the tackle box unifies prove-first + opt-in into one house rule and cashes pv-3's own noun. The cold-open thesis moved off-screen (spoken only). Direct fixes: squeeze pane-tag → "attempted after compaction"; the "↑ the request from the open" caption cut; empty-state no longer listed twice in the Write-It-Down handoff; pipe-rail spacing under that title relaxed. Validated headless (fresh-profile Chrome): 0 console errors, screenshots of every changed scene (no overflow). Includes now carry `?v=14` (deck.css, deck.js, notes.js) — hard-refresh once. Rehearsal-with-a-human still owed (re-time: one scene added).

Rev-10 rebuild (2026-07-13), the presenter's sixth review: anatomy card labeled as the empty-state ticket's zoom (it read as a fourth ticket); token bills grounded (~4M vs ~500k — the eighth ratio holds); compaction lands at ~5% everywhere (squeeze bar, wedge cliffs); the finale scorecard drops " by 5:58"; the dawn recap wears the blueprint's 1·2·3 numbering; all script/CSS includes carry `?v=N` cache-busters — hard-refresh (Cmd+Shift+R) once, then stale builds can't recur. Validated headless: console-clean on all 15 sections, CDP real-time end-state assertions, screenshots at 1280×720 (no overflow).

Bookend animation layer (2026-07-14), built from a 3-creative-angle + 2-research-agent fan-out: the **arrival** — on a cold load of `/`, the dock draws itself in, the line drops, and the title surfaces on the frame the ripple blooms (~7s; plays once — deep links and re-visits land on the finished card); the **lobby idle** — jittered ripple plinks, incommensurate star/moon/sway/shimmer periods, and a rare silver moon-glint across the title, so five pre-talk minutes never visibly repeat, all compositor-cheap CSS so it never fights the call encoder; the **dawn** — the 2.4s glow becomes an 8s sunrise (`linear()` curve), stars go out one by one, the posts take first light in sequence, the line tugs as the Brass Minnow's page lands, and the closer arrives by the title's exact glint gesture in gold (the first and last words of the talk lit by the same light). `prefers-reduced-motion` collapses everything to the static card via the existing global kill-switch; deck.css/deck.js are now `?v=11`. Validated headless same day: 20 assertions + all-scene console sweep, all green. Not yet done:

1. **Real-time rehearsal with a human eyeball** — notes.js was redistributed again and needs a read-aloud pass; live checks: the Death Spiral's relapse snap (`#5.3`), the rewind take (`#6.4`), the econ wedge's sawtooth cadence (`#10.2`), the finale's fold cadence and triple parallel typing (`#14.3`), and a stopwatch pass (~34.5 min on paper).
2. **Q&A prep dependencies** (see qa-bank): real cost numbers for the making-of story (appendix slide), a real merged-PR trail to show, DPA verification before the compliance answer, the finale-timestamps question ("is 4:19-to-5:58 realistic for three tickets?"), and the presenter's REAL skill-file line count for the scroll confession. The economics scene adds one: be ready to defend the ~4M-vs-500k arithmetic — rent is window-size × turns; the figures are staged, the ratio is what daily use looks like.
3. Volatile content: the `/requirements` and `/discovery` chips on the Write-It-Down rail carry `<!-- volatile -->` markers; quarterly sweep per `cortex/requirements/training.md`.
