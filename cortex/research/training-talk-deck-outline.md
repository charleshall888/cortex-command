# Deck outline: "Attention Is the Game" — v1 workshop deck (rev 3)

> Drafted: 2026-07-13 · rev 3 after two adversarial rounds (round 1: dramaturg, seams, continuity, room-sim, hierarchy · round 2: performance, delight, Q&A gauntlet, red-team)
> Source: `training-talk-messaging-brief.md` · Q&A prep: `training-talk-qa-bank.md`
> **Honest timing: ~33.5 min material + ~5.5 min budgeted valves ≈ 39–45 delivered in the 60-min slot.** (Rev 2's "36 min" did not survive audit; the 5-minute cut is pre-applied, not held in reserve.)

## The three things (everything else is supporting texture)

1. **The direction discipline** — the first ~20% of a session steers everything after it: interview back and forth, extract what's in your head onto the page, spec before you sail. Doubly true for multi-session work — the page is what survives; your context doesn't.
2. **The exit discipline** — watch the gauge; under 30% goldilocks, at 50% plan your exit.
3. **Never let the agent write its own job description.**

(Rewind stays in the deck as a technique and the wonder bet — but it's a context-management side note, not a core concept.)

Target retell: *"Get the direction on the page in the first 20%, plan your exit at 50%, and never let the agent write its own instructions."*

## Story mechanics — SPEAK vs FEEL

**Felt, never spoken** (presenter notes only; the audience experiences these as styling):
- Zoom-out ladder (turn → session → epic → many minds → what the team owns) — carried by the visuals scaling up and by three proverb cards (below); never say "zooming out."
- Badge grammar: exactly THREE story badges, identical lanyard style — keepsake (sc 6) / cheat-note (sc 9) / rare-catch (sc 10). Rule: *badge = a one-line intent that decided something.* The drawers index card is NOT badge-styled (it's a table of contents, not an intent).
- Vessel cameo rule: gauge appears only where context-state is the point (2, 3, 4, 5-foundation, 7, 8, 12, 15). No persistent HUD.
- Callback stitching, pronoun discipline ("my agent," never "yours"), staging realism (mock-terminal content technically real: real prompt shapes, real diff hunks).

**Spoken, once each**: staging disclosure (sc 1, never referenced again) · METR plant (Act 0→I) and METR close (sc 15) · act-plant lines (inline below) · refrain drops at 3, 12, 15 only (visual-only at 9; desk fire appears ONCE, sc 1; its absence at the end is never pointed out).

**Proverb cards** (act transitions I→II, II→III, IV→V): static 2-second cards styled as Nightline loading-screen tips; the room reads them, the presenter never does.
- I→II: *"A tangled line catches nothing."*
- II→III: *"You don't catch more by reeling harder. You set more lines."*
- IV→V: *"Take care of your tackle and it takes care of you."*

**Animation-vs-speech rule**: high-salience animations play SILENT, then talk over the settled frame (or talk first, then fire). Applies hard to: scene 2's sweep, scene 4's chips, scene 7's staggered runs, scene 9's rewind shear, scene 11's assembly. Presenter has a blank/freeze key for valves and Q&A.

---

## Act 0 — Cold open (3 min)

**1. "Friday, 4:00 PM"** *(minimum-viable order — the runs come FIRST; disclosure after the reveal, or the reveal dies)*
- Beat 1 — one-sentence world intro: "Every demo tonight lives in one fictional project — Nightline, a little game about setting fishing lines overnight and waking up to your catch." [dock silhouette]
- Beat 2 — cold, no preamble: twin mock terminals, identical request — *"add an empty-state to the catch log."* Left: crisp, asks one clarifying question, nails it. Right: rambles (optional garnish: opens "Great idea!" — once, neutral), patches an unrelated file. Runs ≤20–25s each.
- Beat 3 — reveal: "Same model. Same harness. The one on the right has been at work for six hours — this is my agent at 4PM on a Friday." [avatar slumps, clock, tiny desk fire — only appearance]
- Beat 4 — disclosure: "And yes — I staged both, like everything you'll see on screen today, so it's clean and nobody's real code gets dunked on. The stories I'll tell over it are real."
- Beat 5 — thesis: "The model sets the ceiling. Everything wrapped around it determines the yield."
- Components: mock-terminal ×2, avatar poses. Full drafted script in Appendix A. Rehearse to the word — zero ad-lib headroom.

*Act plant → I (METR lives here now, so scene 2 resolves it instead of it dangling):* "Want independent evidence that yield can go negative? There's a study where experienced engineers got 19% **slower** with AI. I believe it. Let me show you the mechanism."

## Act I — The gauge (8.5 min) — zoom: ONE TURN

**2. "The Scan"**
- Visual: vessel fills by layers (ambient, low-salience). Then ONE full scan-line sweep plays SILENT (~5s) with coin ticker → freeze → explain the frozen frame → fire sweep #2 to show cached layers hatched (skimmed at a discount, still covered).
- Talk track: stateless resend. Concede-then-land: "caching helps, AND it dies on prefix changes — and cost isn't even the headline." Quality evidence in ONE sentence: "the research is consistent: effective context is smaller than advertised context." <!-- volatile: cache multipliers/TTLs if quoted -->
- Components: vessel, scan line, coin ticker (ticker rests until scene 9).

**3. "The Zones"** — *CORE THING #2 lives here*
- Visual: zones tint on (green <30 / yellow 30–50 / warm above); exit door lights at 50%. Time labels ETCHED at zone boundaries — 9AM / 2PM / 4PM (label, don't animate a clock).
- Talk track: owned numbers — "mine, from a year of daily use; yours may differ — that you HAVE numbers is the point." Measurement posture, one line: "these are gates I enforce, not dashboards I stare at." Refrain drop #1: "yellow is 2PM; red is Friday, 4PM — send them home before it."
- **Participation beat (hard cap 60s, chat not unmute)**: "Thirty seconds — whoever has a session open: what percent are you at? Type the number. Nothing open? Type your best guess from memory." Silence fallback: "I checked before this call: 41 percent, and I'm already planning my exit." Riff lines (one, never both): high number → "that agent has been awake since Tuesday"; all low → "a room of well-rested agents — someone's been rehearsing." Re-entry IS the zones reveal: "whatever your number is, here's where it should be." (Zones must not be visible before the poll.)
- Components: vessel (reuse), zone overlay, etched labels.

**4. "The Squeeze"**
- Visual: piston labeled "compact" descends; chips squirt out and dissolve — PLAYS SILENT 6–8s ("watch what falls out"), audience reads the chips: *"depth is in fathoms, not feet" · "user prefers tabs" · "we renamed FishManager → CatchService" · "DON'T touch prod config"* — the amber stripe retains only *"building a fishing game."* Ghost-question payoff: the follow-up code renders in spaces.
- Talk track: *compaction is an airbag, not the brakes.* Concede: newer models handle it better, AND "better" ≠ best output per token. Line the chips buy: **"Compaction keeps what you could've googled. It loses what only you knew."**
- Components: vessel (reuse), piston + readable chips.

*Valve (~2 min): "questions on the mechanics before I show you what I do about it?"*
*Act plant → II:* "The machine's memory is rented. Stop keeping the plan there — write it down. And here's the part nobody says out loud: the first twenty percent of a session steers all the rest." → proverb card I→II.

## Act II — Portion the work (8 min) — zoom: ONE SESSION → ONE EPIC

**5. "Condense → Prism → Badge"** — *CORE THING #1 lives here* *(protected triplet 5→6→7 — pre-frame: "the next three minutes are one continuous story; drop questions in chat, I'll take everything right after the punchline")*
- Visual: glowing head-cloud over a head — but the condensation is NOT one-way: question bubbles from the agent poke the cloud and it visibly sharpens with each answer ("the agent interviews ME — 'what should happen when the log is empty?' — every answer sharpens the doc"). The cloud condenses into one bright doc. Foundation cameo: a fresh vessel beside it fills its first 20% with the doc's glowing layers — what goes in first is what everything else settles on. Then the doc prisms into ticket cards; a thin stripe peels off the parent and clips onto each like a lanyard badge. The fourth ticket is visibly the cold-open request — "that request from the open? It was this ticket."
- Case: Catch Log epic → record events / entry format / flip-through UI / empty state.
- Talk track: interview → extract → decompose → execute. Scripted (restored): *"If you're about to go on a long journey, the first few miles decide where you land."* Multi-session stake: "this matters double when work spans sessions — the page is what survives; your context doesn't." Ceremony scoping, one line: "for a one-file fix, none of this — this pipeline is for epic-sized work."
- Components: doc-prism + badge motif, interview bubbles, fan-out grammar, vessel (foundation cameo).

**6. "The Badge Moment"**
- Visual: the schema ticket's agent at a fork — keepsake-shaped entry vs a 12-column analytics schema (`barometric_pressure`, `moon_phase_at_catch` scrolling off-frame); the badge glows: *"the log is a keepsake, not analytics"*; correct branch lights.
- Talk track: same code, opposite call — only the badge tells you which. Then: "my shop runs this as three commands" (names spoken once, never on screen).
- Components: reuse scene 5.

**7. "Wish vs Ticket"**
- Visual: split mock terminal, the exact cold-open request text — runs STAGGERED (left plays ≤20s → freeze → right plays → freeze → compare on the double freeze-frame). Left "make the log better" → filters, sort dropdowns, a stats chart (badge violation = the punchline); its transcript is visibly LONGER, and its mini-gauge burns faster — "vagueness isn't just wrong — it's expensive; look at the meter." Right: ticket-shaped prompt → the two changes that matter. Ending empty-states side by side: left *"No data available. [Export CSV]"* / right *"No catches yet. The night is young."*
- Closing beat (absorbs old shift-change scene, one sentence): "and a ticket that good doesn't need you to carry it — at 40% I quit, and a fresh agent implements straight from the spec."
- Components: mock-terminal ×2 (reuse), paired mini-gauges.

*Harvest parked chat questions here, then act plant → III:* "Fresh context beats full context — and that's true in parallel, not just in series." → proverb card II→III.

## Act III — More minds, cleaner minds (7 min) — zoom: ONE AGENT → MANY

**8. "Tint Transfer"**
- Visual: main vessel half-full of murky sediment (scene-2 layer palette, over-accumulated) gets "design the log page" → ONE idea bubble, tinted the same murk — containing *the database schema with a border around it* ("it's been staring at the schema all night — so its 'design' is the schema with a border on it"). Fan to three crystal vessels — bubbles appear SIMULTANEOUSLY (trimmed choreography) → scrapbook / stats table / story journal → synthesis picks scrapbook *because the badge says keepsake*.
- Talk track: "kick off a few agents from creative angles." Scar: *this talk was designed exactly this way.* Don't volunteer cost numbers — hold as appendix slide for the inevitable question (see Q&A bank #2).
- Components: vessel + tint, fan-out, idea bubbles.

**9. "The Filmstrip"** — *THE WONDER BET (technique, not core concept — the "cheapest win" billing is a scene-level hook, not a talk-level claim)*
- Hook first: "This is the cheapest win in this talk. Zero setup. Works today. Almost nobody does it."
- Fork vocabulary (30s, clean): "mid-build you wonder 'would SQLite be simpler?' — branch it [ghost lane], explore, take the answer, come back; the main lane never knew."
- Rewind story (flashback framing: "before the log could exist, fish have to actually bite at night"): server-driven time → auth, account state, clock sync, offline reconciliation — strip reddens — "who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them." [badge-family cheat-note]
- The money shot: **one unbroken ~8s SILENT take, full stillness before it** — playhead drags back, segments resist then shear and fall with slight gravity, track thins, avatar straightens (posture only, ~300ms, no face change). No cut, no dissolve.
- Closing beat (rebuttal + rent fused): "'Isn't that just deleting your chat?' No — see the note that hopped across? You carry the lesson; you leave the wreckage. And if you don't rewind, you keep paying rent on that dead idea — every turn re-reads it, forever." [sheared segments show their per-turn coins — no refund shown]
- Components: filmstrip scrubber (biggest build; Cockpit seed). Full drafted script in Appendix A.

*Valve (~1.5 min): natural exhale after the laugh. Act plant → IV:* "You can only rewind a wrong turn you've noticed. Next: the ones you can't see."

## Act IV — Fresh eyes (3 min)

**10. "Arrows and the Gold Seam"** *(dieted to 7 beats)*
- Visual: the "throw small fish back" spec as a target; three reviewer arrows — two bounce, one pierces: *rare-but-small gets auto-released and never makes the keepsake log* — "a **Brass Minnow** — rare, tiny, about to be auto-released." Crack repairs with a gold seam; the fix earns badge #3: *"never punish a rare catch."* The synthesizer bins one finding with a satisfying toss (frame-accurate latency compensation — "serves no badge").
- Talk track: "you asked it for findings, so it manufactures findings — synthesize, don't obey." Honest scar. Overcorrection in ONE spoken line (no bunker flash): "crank this too hard and you get armor-plated specs and dead good ideas." Monday recipe in ONE sentence: "no tooling needed — fresh session, paste the spec, ask it to break it, judge the findings."
- Components: arrows/spec-target, gold seam.

*Act pivot → V is scene 11 itself.* → proverb card IV→V.

## Act V — What you own (8.5 min) — zoom: YOUR WORK → WHAT THE TEAM OWNS

**11. "Nothing Here Needed a Better Model"** *(2 min; twin-terminal beat CUT — asks-vs-infers was already shown in scene 1)*
- Visual: retrospective assembly, SILENT — vessel, badge, filmstrip, arrow icons fly together and lock into a shell around a glowing engine core; as it locks, exactly one on-screen word appears: **"harness."**
- Talk track: "notice — nothing I've shown you came from a smarter model; every technique was something wrapped AROUND the model. That wrapper has a name." Ceiling/yield callback, now with the deferred clause: "in every harness — including whatever we're using next quarter. We're moving anyway; I want us to show up already good at this." Challenge: "run the twenty-minute A/B yourself." <!-- volatile: harness behavior comparisons -->
- Components: icon assembly (reuses existing icons).

**12. "The Scroll and the Drawers"** — *CORE THING #3; the scar gets the time (hygiene list dropped to leave-behind)*
- Visual: tidy 20-line skill file; "tune it" bubbles fire like passing days; counter ticks to 2,041; the time-lapse PAUSES on real lines — #12 *"Keep skills short and focused."* · #1,003 *"NEVER use the word 'delve'."* · #1,486 *"If unsure, re-read lines 1–1,485."* · final line #2,041 *"Do not add more instructions to this file."* Callback: the scene-2 scan line sweeps the full scroll inside a vessel — "you pay to re-read this on every turn of every session" — and the receiving agent tints one step toward Friday-slump before any work starts (refrain drop #2: "a bloated skill file means your agent starts Monday morning already tired"). Alternative: one plain mini-file index card threaded to five drawers; the agent pulls exactly ONE; vessel stays green.
- Talk track: *never let the agent write its own job description* — open-ended + unverifiable is the worst LLM task shape, and models ratchet ("the model did this to me too" — grace note). Scar with numbers: "if I could go back: hand-craft the simple skills, let Claude build the CLI around them." Pocock name-check.
- Components: file-scroll, drawers, vessel + scan (reuse).

**13. "Sign vs Turnstile"** *(~90s)*
- Visual: agent breezes past a polite sign — its text is literally line #1,847 of the scroll: *"please always run the tests"* — then hits a turnstile that won't turn until tests pass. Sign fades; turnstile stays.
- Talk track: structure beats prose. Prepared answer: "didn't I build my harness with Claude? Yes — by making the open-ended verifiable first: size budgets, ratchets, lint gates." Tool-agnostic vocabulary: "a gate — CI, pre-commit, lint — not a sentence in the rules file."
- Components: turnstile (the act's one new prop); sign = scroll page (reuse).

**14. "The By-Hand List"** *(~90s)*
- Visual: a wall of ticket-species cards dims and automates away (small gate icons stamping beside the automated ones); three hand-drawn cards stay lit: *reviewing the work · knowing what good design/UX is · writing skills.*
- Talk track: the negative space — what I still refuse to hand over, and why that's what makes the rest safe.
- Components: ticket-card grammar (reuse).

*Valve (~2 min): take the "how do we adopt this" logistics discussion HERE — the closer comes last so the talk ends on the image.*

## Closer (2 min)

**15. "Tuesday, 9:00 AM"**
- Visual: dawn over the Nightline dock; the night's artifacts quietly present — green vessel, the three badges, the gold seam — and the flip-through log's final page: **the Brass Minnow** (silent proof the review mattered). No desk fire; never pointed out. Recap icons, one at a time, one sentence each — **the bright doc (get the direction on the page first) / the gauge (plan your exit at 50%) / hand-written card eclipsing a scroll (write your own instructions)** — all taught objects. METR close: "that study from the start? The 19% were carrying full vessels."
- Talk track: "everyone rents the same models; the habits are what you own. Send your agents home before Friday afternoon." Final frame: landing-page link + QR, small. Don't talk over the dawn reveal.
- Components: reuse + dawn composition.

---

## Component build list (~11 motifs)

| Component | Scenes | Notes |
|---|---|---|
| Context vessel (+zones, scan, ticker, tint, etched labels) | 2,3,4,7,8,12,15 | Workhorse — build first |
| Mock terminal | 1,7 | Scripted beat player; Cockpit seed |
| Ticket-card family + THREE story badges | 5,6,9,10,14,15 | Badge = one-line intent that decided something |
| Avatar poses (crisp/slumped/straighten/shrug) | 1,4,9,12,15 | Poses, not animation |
| Filmstrip scrubber | 9 | Biggest build; the wonder bet; Cockpit engine seed |
| Doc-prism | 5,6 | |
| Piston + readable chips | 4 | Chips play silent; audience reads |
| Arrows/spec-target + gold seam | 10,11 (icons reused in assembly) | |
| File-scroll + drawers | 12,13 | Sign = a scroll page; index card plain, NOT badge-styled |
| Proverb cards ×3 | act transitions | Static, unspoken, 2s |
| One-offs: turnstile, dawn composition | 13,15 | |

## Cut-first order (if rehearsal still runs long)

1. Scene 8's schema-with-a-border gag (keep fan-out + scar).
2. Scene 2's second sweep (caching spoken over the single frozen frame).
3. Proverb cards (lose the ladder's visual vehicle last).
Never cut: 1, 3, 4, 9, 12, 15.

## Prep dependencies (hard, before the talk)

1. Real token/cost numbers for the making-of story → appendix slide (Q&A #2).
2. One real morning report / merged-PR trail ready to show after (Q&A #14).
3. Verify org data-handling/DPA terms before the compliance answer (Q&A #6).
4. Pre-time all mock-terminal runs ≤20–25s.

## Open items

- Scene 11 assembly concept art (icons locking into the "harness" shell).
- Night-edition art direction (deep ink ground, parchment text, blue/ochre accents, fonts bundled locally).
- Presenter's-choice list: "Great idea!" garnish (sc 1), improvised refrain touches. (First-miles/ship line: restored to script in sc 5 — it states core thing #1.)

---

## Appendix A — Drafted talk tracks (rehearsal material)

### Scene 1 (~3 min; runs ≤20–25s each; rehearse to the word)

> "Every demo tonight lives in one fictional project — Nightline, a little game about setting fishing lines overnight and waking up to your catch.
> Here's a puzzle. Two agents. Same model. Same tool. Same request: 'add an empty-state to the catch log.' [left run plays] Notice — it asked me one question first: 'should the empty state invite them to cast their first line, or stay blank?' Then it nailed it.
> Same request. [right run plays] …And this one is patching a file that has nothing to do with the log.
> Same model. Same harness. Same afternoon. The only difference — the one on the right had been at work for six hours. [avatar slumps, clock hits 4:00, desk fire] That's my agent. This is a re-enactment of my actual Friday.
> And yes — I staged both, like everything you'll see on screen today, so it's clean and nobody's real code gets dunked on. The stories I'll tell over it are real.
> The frame for everything tonight: the model sets the ceiling. Everything wrapped around it — what it sees, what it remembers, how you ask, when you start fresh — determines the yield."
>
> [Act plant] "Want independent evidence that yield can go negative? There's a study where experienced engineers got nineteen percent slower with AI. I believe it. Let me show you the mechanism."

### Scene 9 (~3.5 min incl. ~25s pure animation)

> "This next one is the cheapest win in this talk. Zero setup. Works today. Almost nobody does it.
> Quick vocabulary first. Your conversation is a timeline. [filmstrip appears] Sometimes mid-build you wonder — 'wait, would SQLite be simpler here?' You don't have to derail the main thread. Branch it. [ghost lane] Explore in a fork, take the answer, come back. The main lane never knew.
> Now the real skill. Before the catch log could exist, fish have to actually bite at night. So we're designing overnight activation, and the first idea feels obviously right: drive time from the server, so players can't cheat by changing their device clock. And we go DOWN this road. [strip reddens] Auth. Account state. Clock sync. Offline reconciliation. We are forty minutes and two hundred thousand tokens deep when I finally ask the real question: who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them.
> Here's the move almost everyone misses. Don't say 'okay, scrap that' and keep going — that dead design is still IN the context. It's not history. It's contamination. Instead — [SILENT: full stillness, then the unbroken take: scrub, shear, gravity, track thins, avatar straightens] — rewind. Back to the fork. Take the other branch. Look at that headroom. It's Tuesday morning again.
> 'Isn't that just deleting your chat?' No — see the little note that hopped across? You carry the lesson — one line: device clock, single-player, cheating's allowed. You leave the wreckage. And if you don't rewind? You keep paying rent on that dead idea — every turn re-reads it, forever."
