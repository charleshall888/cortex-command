# Deck outline: "Attention Is the Game" — v1 workshop deck (rev 4)

> Drafted: 2026-07-13 · rev 3 after two adversarial rounds (dramaturg, seams, continuity, room-sim, hierarchy · performance, delight, Q&A gauntlet, red-team) · **rev 4 same day, after the presenter's slide-by-slide review of the built deck** (four-angle creative fan-out: dramaturg, learning designer, scene doctor, language writer — synthesized and rebuilt; deck at `docs/training/` is the build of THIS rev)
> Source: `training-talk-messaging-brief.md` · Q&A prep: `training-talk-qa-bank.md`
> Timing: rev-3 audit said ~33.5 min material + ~5.5 min valves; rev 4 cut the poll (~1 min) and the second sweep, merged two scenes, folded another, and added the ~90s replay — net roughly flat, but **needs a stopwatch pass**.

## What rev 4 changed and why (the presenter's review)

The built rev-3 deck failed presenter review on cohesion: "loose ideas plopped down randomly… make it one story arc that goes full circle, building a building in people's minds." Root cause: the deck's meaning lived in the spoken track; on screen each scene opened a new unexplained metaphor (the vessel was never even labeled "context window"), scene titles were riddles, and transitions were "felt, never spoken" — i.e. absent. Rev 4's fixes:

1. **One running object — the context bar** (`lib/contextbar.js`): born on the cold open's twin terminals (presenter's explicit ask), calibrated against the vessel once in the gauge scene, reused in squeeze/wish/replay. All cost/health readouts unify on it; the coin ticker and money units died.
2. **The structure is on screen**: a blueprint card (three habits as three dashed dock posts) right after the cold open; the act-break proverb cards became waypoints that light a post each; the dock completes in the replay and stands in the dawn. Posts are never numbered (teaching order ≠ retell order — deliberate; the gauge must answer the cold open's mystery first).
3. **Full circle**: the abstract assembly/"harness." scene (presenter: "doesn't mean much") was replaced by **"Friday, 4:00 PM — again"** placed after ALL three habits are taught: same red 91% bar, the operator exits, a fresh agent ships from the handoff ticket, bar falls 91→8 on screen. Its kicker keeps assembly's one good line: "nothing here needed a better model." The word "harness" no longer appears on screen.
4. **Every title is its takeaway** ("Get the direction on the page first", not "get it out of your head"), and every scene carries a plain-language on-screen anchor. The sparseness bar still holds — anchors are labels, not paragraphs.
5. **Thesis replaced** (old ceiling/yield line killed on review): on screen — *"The only difference on this screen is that bar. That bar is the whole talk."* — spoken follow: *"Nothing about the model changed. Everything it was reading did."*
6. **Cuts**: the audience percentage poll (presenter kill; the zones/exit-at-50 teaching moved into the merged gauge scene) · the scan scene's coin ticker + cached second sweep (cost was never the headline) · the separate badge scene (folded into the prism scene as its fork payoff; the noun on screen is now "the intent line", never "badge") · the foundation-vessel cameo (overload) · the fathoms chip (replaced; see squeeze).
7. **The filmstrip moved into Act I** (rewind is context surgery, not "more minds"): squeeze = the lossy exit, rewind = the surgical one. Bonus: "a tangled line catches nothing" now sits directly after the red run it describes.
8. **"Set more lines" is elaborated, not just quoted** (presenter liked the proverb, wanted it cashed): the card hands directly into the rebuilt parallel-agents scene — a beam drops three fishing lines into three fresh mini-vessels; title "Three fresh agents beat one tired one".

## The three things (unchanged; wording now LOCKED and repeated verbatim on screen)

1. **get the direction on the page** — the first 20% steers everything after; interview → doc → tickets.
2. **plan your exit at 50%** — watch the gauge; hand off to a fresh agent.
3. **write your own instructions** — never let the agent write its own job description.

Target retell: *"Get the direction on the page in the first 20%, plan your exit at 50%, and never let the agent write its own instructions."*

## Story mechanics that survive from rev 3

- **Animation-vs-speech rule**: high-salience animations play SILENT, then talk over the settled frame. Applies hard to: the cold open's bar sweep, the gauge's scan sweep, the squeeze, the rewind take, the replay's 91→8 drop.
- **Staging realism**: mock-terminal content technically real; staging disclosure spoken once (cold open), never referenced again. Desk fire appears once (scene 1); its absence at the end is never pointed out.
- **Pronoun discipline** ("my agent," never "yours") · refrain drops ("red is Friday, 4PM") at gauge, scroll, dawn · METR plant (cold-open exit) and METR close (dawn).
- **Proverb cards stay verbatim and unspoken**; they now also carry the dock progress caption (the anti-jerkiness device).
- **Vessel cameo rule** becomes **bar cameo rule**: the gauge appears only where context-state is the point (1, 3, 4, 5-loadbar, 8, 13-sweep, 16). No persistent HUD.

## The 17 sections (deck section numbers; deep-link `#N.beat`)

**Act 0 — the mystery (3.5 min)**
1. **Friday, 4:00 PM** — twin terminals + context bars (8% green "started fresh" vs 91% red "six hours deep"; the right bar's fill sweeps green→amber→red on entry — six hours in three seconds). Runs ≤20–25s each. Reveal (screen dims to the bars): "Same model. Same tools. Same request." Thesis (above). Script in Appendix A.
2. **Three Habits** — blueprint card: dashed dock, three posts labeled with the locked habit lines + one-line subtitles. "Everything else tonight is one of these three."

**Act I — the gauge (9 min)**
3. **The Gauge** *(merges rev-3 scan+zones; poll and coins cut)* — title "Watch the gauge — plan your exit at 50%". The vessel is captioned **"the context window"**; a live bar underneath tracks it (the one-time calibration that makes every later bar legible). Labeled pour (system prompt / your messages / files it read / test output — the grey slabs dwarf the blue). ONE silent sweep, then the caption "every turn, the whole tank is re-read" (this beat is load-bearing for scenes 5, 10, 13 — never cut). Zones + etched 9AM/2PM/4PM + door labeled "hand off here". Fast-forward pours past 50 into the red; the slumped 4PM avatar appears: mystery mechanically solved.
4. **The Squeeze** — title "Compaction loses what only you knew". Four chips PINNED inside the tank first (possessions before loss): `DON'T touch catch_odds.js` · `FishManager → CatchService` · `empty state invites first cast` · `tests hang without --offline` (a prohibition, a rename, a decision, a scar — the taxonomy of what only you knew). Squeeze plays silent; chips land in a persistent **lost pile**; stripe labeled `kept: "building a fishing game"`; the bar improves 95→30 while the mind got worse. Payoff: next-turn mini-terminal edits catch_odds.js — "biting disabled game-wide — again" (the cold open's own disaster file) — while the lost chip glows red. Anchor: "the one thing it needed was in the pile."
5. **The Rewind** *(moved from Act III)* — unchanged mechanics; the load bar now labels itself ("next turn re-reads this much" — the gauge on its side) and the carried note shows its text on landing: **"single-player — cheating's allowed"** (intent line #2 born on screen). Money shot: one unbroken ~8s silent take (`#5.4`). Script in Appendix A.
6. **Waypoint** — "A tangled line catches nothing." + post lit: *plan your exit at 50%*.

**Act II — the page (8 min)**
7. **The Page** *(prism; absorbs the rev-3 badge scene; foundation cameo cut)* — title "Get the direction on the page first". Staged pipeline, one stage bright at a time: head-cloud ("the plan, in your head") → the agent interviews YOU (first bubble is the cold open's own question, verbatim) → doc ("the plan, on the page — it outlives the session") → tickets fan out and the intent line **visibly stamps itself onto each** ("a keepsake, not analytics"); ticket 4 labeled "the request from the open" → the fork: two reasonable schemas, "the intent line makes this call."
8. **Wish vs Ticket** — title "Write the ticket, not the wish"; header "two fresh sessions · same model · only the ask differs" (the deliberate inverse of scene 1: there the ask was constant and the context differed). Prompts shown first; identical 8% green bars; wish burns to 68% red across 6 files, ticket ends 18% green and 1 file; scorecard: files 6·1 / context 68%·18% / matches the intent ✗·✓. Optional lightweight checkpoint: show-of-hands on "which side wins?" before the runs.
9. **Waypoint** — "You don't catch more by reeling harder. You set more lines." + post lit: *get the direction on the page*. Hands directly into…

**Act III — more lines (5.5 min)**
10. **Set More Lines** *(rebuilt tint scene)* — title "Three fresh agents beat one tired one". Left: the tired 6-hour vessel; its one idea is "the schema, with a border on it" (kept — best label in the deck); caption "it can only see what it's been staring at". Right: a beam drops three fishing lines into three fresh mini-vessels (each carrying only the page, 9%); three genuinely different ideas; "the intent picks: keepsake → scrapbook." Scar: this talk was designed exactly this way. Cost numbers only if asked (appendix).
11. **Fresh Eyes** *(arrows, rebuilt with readable findings)* — title "It will always find something. Judge what counts." A finding rail fills as arrows land: "log writes need retry logic" → *bounced — the spec already covers it* · "entries need pagination" → *bounced — out of scope for v1* · "a rare fish under the size limit is auto-released — it never reaches the log" → *confirmed — the Brass Minnow* (named on screen; the dawn payoff depends on it). Gold seam + intent line #3: "never punish a rare catch". The manufactured finding ("frame-accurate input-latency compensation") gets read aloud, stamped *serves no intent → binned*, and tossed (`#11.4`).
12. **Waypoint** — "Take care of your tackle and it takes care of you." + the plank draws across the standing posts (the techniques: fork, rewind, parallel lines, fresh eyes); third post waits, dashed.

**Act IV — your instructions (5.5 min)**
13. **The Scroll and the Drawers** — title "Never let it write its own instructions" (otherwise as built in rev 3 — it was already the deck's best accumulator: 2,041 lines, the gag lines, the sweep bill, the drawers).
14. **Sign vs Turnstile** — title "If it must happen, build a gate" (as built; the sign is §1,847 of the scroll).
15. **The By-Hand List** — title "Keep three things by hand" (as built).

**Full circle (3.5 min)**
16. **Friday, 4:00 PM — again** *(new; replaces assembly; placed after all three habits)* — header "same request · same model · new habits". One pane, bar climbs to 91% (where the cold open left it), new request arrives; the operator stops it, the handoff ticket is written, session closes; the terminal retitles to "fresh session · 4:04 PM" and the bar falls 91→8 (say nothing during the drop); the fresh agent ships a 2-file diff from the ticket, 16% at finish. Three checklist chips tick with the locked habit wording. Kicker: **"Nothing here needed a better model."** The dock completes behind it.
17. **Tuesday, 9:00 AM** — dawn; the completed dock; the Brass Minnow on the log's last page; recap icons with the locked habit lines, verbatim; METR close; "Send your agents home before Friday afternoon."

## Cut-first order (if rehearsal runs long)

1. Scene 10's schema-with-a-border gag (keep the beam + scar).
2. Scene 5's cleanBranch beat (end on the headroom).
3. Waypoint 12 (its proverb can move onto scene 13's entry).
Never cut: 1, 2, 3, 4, 5's rewind take, 7, 13, 16, 17 — and the gauge scene's single labeled sweep (scenes 5, 10, 13 causally depend on it).

## Prep dependencies (hard, before the talk)

1. Real token/cost numbers for the making-of story → appendix slide (Q&A #2).
2. One real morning report / merged-PR trail ready to show after (Q&A #14).
3. Verify org data-handling/DPA terms before the compliance answer (Q&A #6).
4. Pre-time all mock-terminal runs ≤20–25s (now five runs: cold open ×2, wish ×2, replay ×1 — the replay's two scripts together must stay ≤25s).
5. Stopwatch pass on the full rev-4 deck.

## Open items

> **Build status (2026-07-13, rev 4): REBUILT** — all 17 sections live at `docs/training/`; presenter view re-synced (notes.js rewritten per-beat). Validated headless: console-clean across all sections, CDP real-time end-state assertions, per-section screenshots at 1280×720. See `docs/training/README.md` for the rev-3→rev-4 slide renumbering.

- **Real-time rehearsal**: re-validated headless only; pacing feel, the rewind take (`#5.4`), the toss (`#11.4`), and the replay's bar drop (`#16.3`) deserve a live eyeball, and the redistributed talk track needs a read-aloud pass.
- **Interactive-checkpoint decision**: the poll died with rev 4; `cortex/requirements/training.md` still lists 2–3 interactive checkpoints as workshop acceptance criteria. Either bless the lightweight show-of-hands moments (scene 8 prompts-first; scene 15 "what would you keep?") or amend the requirement — don't leave it silently out of spec.
- **Q&A prep (human)**: cost numbers, merged-PR trail, DPA check (above).
- Wave 2 (per `cortex/requirements/training.md`): self-serve guide page, Cockpit engine (grow from `lib/filmstrip.js` + `lib/terminal.js`), retention kit.

---

## Appendix A — Drafted talk tracks (rehearsal material)

### Scene 1 (~3.5 min; runs ≤20–25s each; rehearse to the word)

> "Every demo tonight lives in one fictional project — Nightline, a little game about setting fishing lines overnight and waking up to your catch.
> Here's a puzzle. Two agents. Same model. Same tool. Same request: 'add an empty-state to the catch log.' [left run plays] Notice — it asked me one question first: 'should the empty state invite them to cast their first line, or stay blank?' Then it nailed it.
> Same request. [right run plays] …And this one is patching a file that has nothing to do with the log.
> Same model. Same tools. Same afternoon. The only difference — the one on the right had been at work for six hours. [avatar slumps, clock hits 4:00, desk fire] That's my agent. This is a re-enactment of my actual Friday.
> And yes — I staged both, like everything you'll see on screen today, so it's clean and nobody's real code gets dunked on. The stories I'll tell over it are real.
> [the screen dims to the two bars] The only difference on this screen is that bar. That bar is the whole talk. Nothing about the model changed — everything it was reading did."
>
> [Act plant] "Want independent evidence? There's a study where experienced engineers got nineteen percent slower with AI. I believe it. By the end of tonight you'll know the mechanism."

### Scene 5 — The Rewind (~3.5 min incl. ~25s pure animation)

> "This next one is the cheapest win in this talk. Zero setup. Works today. Almost nobody does it.
> Quick vocabulary first. Your conversation is a timeline. [filmstrip appears] And that bar under it — that's the gauge again, lying on its side: what the next turn re-reads. Sometimes mid-build you wonder — 'wait, would SQLite be simpler here?' You don't have to derail the main thread. Branch it. [ghost lane] Explore in a fork, take the answer, come back. The main lane never knew.
> Now the real skill. Before the catch log could exist, fish have to actually bite at night. So we're designing overnight activation, and the first idea feels obviously right: drive time from the server, so players can't cheat by changing their device clock. And we go DOWN this road. [strip reddens] Auth. Account state. Clock sync. Offline reconciliation. We are forty minutes and two hundred thousand tokens deep when I finally ask the real question: who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them.
> Here's the move almost everyone misses. Don't say 'okay, scrap that' and keep going — that dead design is still IN the context. It's not history. It's contamination. Instead — [SILENT: full stillness, then the unbroken take: scrub, shear, gravity, track thins, avatar straightens] — rewind. Back to the fork. Take the other branch. Look at that headroom. It's Tuesday morning again.
> 'Isn't that just deleting your chat?' No — see the little note that hopped across, and what's written on it? 'Single-player — cheating's allowed.' You carry the lesson. You leave the wreckage. And if you don't rewind? You keep paying rent on that dead idea — every turn re-reads it, forever."
