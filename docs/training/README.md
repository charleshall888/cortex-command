# Attention Is the Game — workshop deck

The v1 presenter deck for the team talk on working well with coding agents.
Requirements: `cortex/requirements/training.md` · Story/talk track: `cortex/research/training-talk-deck-outline.md` (rev 3) · Q&A prep: `cortex/research/training-talk-qa-bank.md` · Messaging record: `cortex/research/training-talk-messaging-brief.md`.

## Running it

```bash
cd docs/training && python3 -m http.server 8000
```

- `localhost:8000` — the deck (SHARE this window on a call).
- `localhost:8000/presenter.html` — private notes view (KEEP FOCUS here; its arrow keys remote-control the deck over a BroadcastChannel, which is why `http://` is required — `file://` windows can't share a channel).

Controls: **→/space** one beat · **←** previous scene · **b** blank (valves/Q&A) · **Home/End** · URL hash `#7.2` deep-links to scene 7 beat 2 (rehearsal/QA).

## Architecture

Hand-authored deck over a shared component library — words live with their presentation; only visuals are componentized (see the scene-schema decision in `cortex/requirements/training.md`, Open Questions).

| File | Role |
|---|---|
| `index.html` | All 18 sections (15 scenes + 3 proverb cards), beat markup via `data-beat`/`data-beats` |
| `lib/deck.js` | Engine: beat navigation, per-scene hooks, promise-chained async beats (rapid advances can't interleave), night-sky signature (moon crosses as scenes advance; dawn on the closer), presenter sync |
| `lib/vessel.js` | The context vessel: pour, scan sweep + coin ticker + cache hatching, zones, compaction squeeze |
| `lib/terminal.js` | Scripted mock-terminal player (no recordings, ever — staged beats with technically-real content) |
| `lib/filmstrip.js` | Fork/rewind timeline — deliberately built as the wave-2 Cockpit engine seed |
| `lib/notes.js` | Talk-track cues per scene per beat (feeds presenter.html) |
| `lib/deck.css` | Night edition of the landing-page design language; bundled fonts (offline-safe) |
| `presenter.html` | Synced notes + remote control + timer |

Timing knobs: `CHAR_MS`/`LINE_GAP` (terminal.js), squeeze/sweep durations (vessel.js), the rewind take (`totalMs`, filmstrip.js), per-hook `setTimeout`s (deck.js).

## Status

Built and headless-validated end to end (every scene screenshot-checked; four presentation-race bugs found and fixed that way). Not yet done:

1. **Real-time rehearsal** — animations were validated in fast-forward; pacing feel, the note-icon landing (scene 11 `#11.4`), and the finding-card toss (`#12.3`) deserve a live eyeball.
2. **Q&A prep dependencies** (see qa-bank): real cost numbers for the making-of story (appendix slide), a real merged-PR trail to show, DPA verification before the compliance answer.
3. Volatile content carries `<!-- volatile -->` markers in the research docs; quarterly sweep per `cortex/requirements/training.md`.
