/* Presenter talk-track cues, per scene, per beat. beats[i] = what to say /
   do at beat i (0 = scene entry). exit = the bridge line into what's next.
   Terse by design — cues, not a script. Full drafted scripts for the cold
   open and the rewind live in cortex/research/training-talk-deck-outline.md,
   Appendix A. */

const NOTES = {
  "sc-cold-open": {
    beats: [
      "“Every demo tonight lives in one fictional project — Nightline, a little game about setting fishing lines overnight and waking up to your catch.”",
      "“Here's a puzzle. Two agents. Same model. Same tool. Same request.” (request + panes appear; the two context bars fill — LET the right one finish its sweep before speaking over it)",
      "LEFT RUN plays (~20s). Then: “Notice — it asked me one question first. Then it nailed it.”",
      "RIGHT RUN plays. “…And this one is patching a file that has nothing to do with the log.”",
      "REVEAL (screen dims to the bars): “Same model. Same tools. Same request. The right one had been at work six hours — that's MY agent; this is a re-enactment of my actual Friday.” THEN the disclosure: “And yes — I staged both, like everything on screen today, so it's clean and nobody's real code gets dunked on. The stories I'll tell over it are real.”",
      "THESIS: “The only difference on this screen is that bar. That bar is the whole talk.” Spoken follow: “Nothing about the model changed. Everything it was reading did.”",
    ],
    exit: "METR PLANT: “Want independent evidence? There's a study — experienced engineers, 19% SLOWER with AI. I believe it. By the end you'll know the mechanism.”",
  },
  "sc-blueprint": {
    beats: [
      "“So the whole talk is managing context — managing what the agent reads. That's the job.” Bridge for the jargon: “the window — that's the bar, stood upright. I'll pour you one in a minute.”",
      "(the three pillars land) Read them once, slowly, verbatim: “Know what's in the window. Get the direction on the page. Give every job a clean window.” Then: “Every scene tonight is one of these three moves. We take them in order.”",
    ],
    exit: "“First: what IS in there?”",
  },
  "sc-gauge": {
    beats: [
      "“This is the same bar, stood upright — the context window. Let me show you what six hours pours into it.” (empty tank, bar at 0)",
      "LAYERS POUR, labeled. “System prompt sediment. Your messages — the thin blue bands. And the fat grey slabs: files it read, test output. Tool output is what eats the window, not your typing.” (the bar underneath tracks the tank — same object)",
      "SWEEP PLAYS SILENT (~4s) — say nothing. Then over the frozen frame: “Every single turn, it re-reads the entire tank. You resend everything, every time. Junk in here isn't history — it's rent.”",
      "ZONES + THE DOOR: “MY numbers, from a year of daily use — under 30 is the goldilocks zone; at 50 there's a door, and I plan my exit through it. Yours may differ. That you HAVE numbers is the point.” Refrain #1: “yellow is 2PM. Red is Friday, 4PM.”",
      "FAST-FORWARD past the door (bar goes red, slumped avatar appears): “and if you sail past the door without a plan… there's our friend from the cold open. Mystery solved, mechanically. Now — what fills it can also fight you.”",
    ],
    exit: "",
  },
  "sc-squeeze": {
    beats: [
      "“When you blow past the line anyway, the tool offers you a button: compact. Look what's floating in the tank first — four things only I knew. No search engine has any of them.” (point at the pinned chips, read one or two)",
      "SQUEEZE PLAYS SILENT 6–8s — “watch what falls out.” The chips land in the lost pile; the stripe keeps the gist. Then: “Look at the bar — the NUMBER got better. Compaction keeps what you could've googled. It loses what only YOU knew.”",
      "PAYOFF (mini-terminal fires, the chip glows): “Two turns later: it touches the one file I said never to touch. Biting disabled game-wide — again. The thing it needed was in the pile.” Concede-then-land: “Newer models compact better, AND ‘handles it better’ is not ‘best output per token.’ Compaction is an airbag, not the brakes.”",
    ],
    exit: "“That's what a full tank LOSES. Here's what a full tank DOES — the failure you've all met.”",
  },
  "sc-noloop": {
    beats: [
      "“Earlier that same afternoon. Turn seventy-one. And floating in the tank: two design calls I made forty turns apart — look at them. They disagree.” (point at the two pinned chips)",
      "RUN A plays: “dawn spawns feel wrong, fix them — and it reaches for the older call. Lowers the multiplier. No!” (the NO chip drops into the tank) “Watch where my ‘no’ went. IN.”",
      "RUN B plays — the loop: “now it obeys the OTHER call. Still no. And then—” (the relapse snaps in) “—right back to the first suggestion. Verbatim. You already know what I typed next.” MECHANISM, over the frozen frame: “It's not being stubborn. It's holding two of my own instructions, and my ‘no’ didn't remove either one. Point at the bar: forty minutes of arguing, zero files changed, and the rent went UP.”",
      "ANCHOR (screen dims): “You can't argue it out of the tank. You can only take it out. Here's how.”",
    ],
    exit: "",
  },
  "sc-filmstrip": {
    beats: [
      "HOOK FIRST: “This is the cheapest win in this talk. Zero setup. Works today. Almost nobody does it.”",
      "(strip populates; load bar labels itself) “Your conversation is a timeline. And that bar underneath — that's the gauge again, lying on its side: what the next turn re-reads.”",
      "FORK (30s vocab): “mid-build you wonder — would SQLite be simpler? Branch it. Explore in the fork, take the answer, come back. The main lane never knew.”",
      "RED RUN — tell the story over it: “Before the log could exist, fish have to bite at night. First idea feels obviously right: server-driven time, so players can't cheat. And we go DOWN this road — auth, account state, clock sync, offline reconciliation. Forty minutes deep, I finally ask: who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them.”",
      "THE TAKE — SAY NOTHING. Full stillness, then rewind plays (~8s). After: “Look at that headroom. It's Tuesday morning again. And notice — I didn't argue with it. I took the whole dead branch OUT.”",
      "CLEAN BRANCH + rebuttal: “‘Isn't that just deleting your chat?’ No — see the note that hopped across, and what's written on it? Carry the lesson, leave the wreckage. If you don't rewind, you keep paying rent on the dead idea — every turn re-reads it, forever.”",
    ],
    exit: "VALVE — natural exhale after the laugh (~1.5 min for questions on the mechanics).",
  },
  "pv-1": {
    beats: [
      "Let the room read the proverb. Say nothing.",
      "(post lights) “First post: know what's in the window — the gauge, the squeeze, the no-loop, the rewind.” Bridge: “But everything we just protected lives in a tank that gets emptied every time a session ends. The things that must SURVIVE need to live somewhere else. Not in the tank. On a page.”",
    ],
    exit: "",
  },
  "sc-prism": {
    beats: [
      "PILLAR 2. “The first twenty percent of a session steers all the rest. So before anything sails, I get the direction out of my head — and my shop runs this as commands, but the shape works with markdown and discipline.” (the rail names the steps) PRE-FRAME the triplet: “next three minutes are one continuous story — drop questions in chat, I'll take everything after the punchline.”",
      "(head + cloud) “This is the epic — currently a cloud in my head.”",
      "INTERVIEW (rail step 1): “I don't write the doc alone — the agent interviews ME.” (bubbles land; point at the first one) “Recognize that question? It's the one the fresh agent asked in the cold open. Every answer sharpens the doc.”",
      "CONDENSE (rail step 2): “If you're about to go on a long journey, the first few miles decide where you land. The page survives; your context doesn't — that's the whole point of the page.”",
      "TICKETS + STAMPS (watch the intent line fly onto each): “discovery splits the epic into tickets, and every ticket carries one line of intent from the parent. The last one? That's the request from the cold open. It was never a one-off ask — it was a shard of a plan.”",
      "THE HANDOFF (rail step 3 — the payoff): “here's what the page BUYS you. One ticket, one fresh window — eight percent — and it ships. Constraints, done-when, one line of intent. Six hours of chat: not required. Any fresh window can pick this up cold. Or three windows at once — hold that thought.”",
    ],
    exit: "PROTECTED TRIPLET — if interrupted: “hold that thought two minutes — you'll see it answered or get worse.”",
  },
  "pv-2": {
    beats: [
      "Let the room read it. Say nothing — the next scene cashes this proverb.",
      "(second post lights) “Second post: the direction lives on the page. And once it does, something unlocks — the page can feed more windows than one.”",
    ],
    exit: "",
  },
  "sc-lines": {
    beats: [
      "“Ask a six-hour session for a creative idea and you get its context back, wearing a costume.” (murky vessel, six hours in)",
      "MURK IDEA: “it's been staring at the schema all night — so its ‘design’ is that schema with a border on it.”",
      "SET MORE LINES (beam drops three lines into three fresh vessels): “Don't reel harder on the tired one. Three fresh sessions. Same prompt. Each carries the page and nothing else.”",
      "PARALLEL (the three bars fill at once; the clock ticks 4:00 → 4:20): “and here's the part that changes your afternoon — they run at the same time, while you're somewhere else entirely. Twenty minutes later: three genuinely different ideas.” SCAR: “this talk was designed exactly this way — I fanned out four angles; the fact-checker caught a claim I had exactly backwards.” (cost numbers ONLY if asked — appendix)",
      "SYNTHESIS: “and the pick isn't taste — the intent line decides. Keepsake → scrapbook. The pick goes back on the page — and the same move works for whole tickets. That's how this Friday ends. Hold that thought too.”",
    ],
    exit: "“Parallel windows for ideas. One more use of a clean window — pointing it at your own work.”",
  },
  "sc-arrows": {
    beats: [
      "“Fresh eyes catch what tired eyes miss — because a fresh window doesn't share your session's assumptions.”",
      "PREP (the page hands off; the doc becomes the target): “This is the page we wrote an hour ago. I hand it to a brand-new session that wasn't in the room, and give it ONE job: break it.”",
      "ARROWS 1–2 FLY, cards fill: “two findings bounce — the spec already answers one, the other's out of scope. The spec holds. That's a good outcome, not a failed review.”",
      "ARROW 3 PIERCES, card fills: “this one's real. Rare-but-small gets auto-released by our own size rule — a Brass Minnow would never make the keepsake log. Our rule punishes the best catch of the night.”",
      "GOLD SEAM + new intent line: “the spec is stronger where it cracked — and the fix earns its own line: never punish a rare catch.” HONEST BEAT: “sometimes this steers me wrong. More often it makes things better.”",
      "THE MANUFACTURED ONE — read it aloud, let it bin itself: “frame-accurate input-latency compensation. For a fishing game. It will ALWAYS find something — you asked for findings, so it manufactures findings. Serves no intent — binned. You judge.” RECIPE: “no tooling needed — fresh session, paste the spec, ask it to break it, judge the findings.”",
    ],
    exit: "One line: “crank this too hard and you get armor-plated specs and dead good ideas.” Then: “every window we've opened tonight had a silent passenger — the standing files. Pillar three has a second half.”",
  },
  "sc-scroll": {
    beats: [
      "“The moment you believe the wrapper matters, you'll want to customize yours. Here's where that goes wrong.” (the exhibit frame: everything inside the dashes is the specimen; my lessons land on the right)",
      "(tidy 20-line file) “This is a skill file — standing instructions, poured into every window. It started perfect.”",
      "RATCHET plays — let the room READ the gag lines (esp. #1,486). Then: “models don't need many instructions — but they love WRITING many. Every ‘tune it’ ratchets it longer. The model did this to me too — mine hit five times this size.” Scar: “writing the instructions is the one job I never hand over.”",
      "THE SHOVE + sweep (the gauge callback): “and here's the bill: this file rides in EVERY window, and you re-pay it on every turn. A bloated skill file means your agent starts Monday morning already tired.” SCAR: “If I could go back: hand-craft the simple skills myself, and let Claude build the CLI around them. Open-ended plus unverifiable is the worst possible task shape for an LLM.”",
      "DRAWERS: “the shape that works: a thirty-line core that points at reference files, loaded per task. Matt Pocock's public skills are like this — tiny. Project-specific beats generic.”",
    ],
    exit: "“Even a lean skill file is still just words. And words are requests.”",
  },
  "sc-turnstile": {
    beats: [
      "“When it MUST happen, don't write a sentence — build a gate.” (the 2,041-line chip rides along, top right)",
      "WALK: “line one thousand eight hundred forty-seven: please always run the tests. It's in the window every turn — it costs rent every turn — and watch how much the agent cares.” (walks past; the caption lands)",
      "BLOCKED → FIX → PASS: “a turnstile doesn't care about your intentions. And watch — it doesn't argue with the gate. It goes back, runs the tests, fixes them, and walks through. CI, pre-commit, lint — the tests pass or you don't get through.” PREPARED ANSWER: “didn't I build my harness WITH Claude? Yes — by making the open-ended verifiable first: size budgets, ratchets, lint gates.”",
      "KICKER (sign fades; the counter ticks DOWN): “and now line 1,847 is dead weight — delete it. The gate lives OUTSIDE the window: costs no context, can't be squeezed out, can't be argued with. It's the one rule you never have to manage.”",
    ],
    exit: "",
  },
  "pv-3": {
    beats: [
      "Let the room read it. Say nothing.",
      "(third post lights) “Last post: give every job a clean window — fresh parallel sessions, fresh eyes, and standing tackle lean enough that a clean window STAYS clean. Three posts. One plank missing — and one Friday to draw it.”",
    ],
    exit: "VALVE (~2 min): take the “how do we adopt this” logistics discussion HERE — the finale and the closer come last, so the talk ends on the image.",
  },
  "sc-finale": {
    beats: [
      "(the red pane sweeps back to 91 — LET IT FINISH) “Still Friday. Still four o'clock. We left this agent exactly here. And one more ask just landed — a big one: make Monday's playtest real. Last time, we typed the ask straight into THAT.”",
      "(red pane folds) “First move: read the bar. Past the door. We don't argue, we don't compact — retired.” (interview runs) “The ask is a wish, and wishes are fine — you just don't hand one to a coder. You hand it to an interview. Two questions — and notice it caught that biting is still broken. Friday's wreckage just became a work item.”",
      "(the page rises; three intent lines fly to three tickets — SAY NOTHING during the flights) “One epic, three tickets. Look at the stamps: single-player from the rewind. Keepsake from the interview. Rare catch from the review. Every one of those lines was paid for by a session that's already dead — the page carries the lessons forward. The wreckage stays behind.”",
      "(three fresh windows run in parallel — mostly let them) “4:19, three windows, all at once. Left one is undoing Friday — same file, same line, reversed; and it didn't re-litigate server time, because its ticket told it cheating's allowed. Middle one just bounced off the gate — tests first, then through. And that --offline flag on every run? The scar the squeeze lost — it lives in an instruction file now. Fresh windows are born knowing it.”",
      "(the three fold — SAY NOTHING until the log card lands) “5:58. Three tickets shipped, nothing broken, no working bar ever left the green. And the log is live — empty, and inviting. The night is young. Tonight it means that literally.”",
      "KICKER + the dock completes: “Nothing here needed a better model. Every move you just watched was managing context — what's in the window, what's on the page, who gets a clean window. Same model as the disaster. Run this Friday yourself.”",
    ],
    exit: "into dawn: “So come back Tuesday morning, and let's see what bit.”",
  },
  "sc-dawn": {
    beats: [
      "(dawn is breaking — the moon set during the talk; the dock stands complete) One line if needed: “fish were biting again by sunset — that's the only reason there's anything to see.”",
      "LOG CARD: “first page of the log: the Brass Minnow. Rare, small, kept — that's the review, paying rent.” (don't over-explain)",
      "RECAP, verbatim, one breath each: “Know what's in the window. Get the direction on the page. Give every job a clean window.” METR CLOSE: “that study from the start? The nineteen percent were carrying full windows.”",
      "CLOSER: “Everyone in this room rents the same models. The habits are what you own. Send your agents home before Friday afternoon.” (link stays up during questions)",
    ],
    exit: "",
  },
};
