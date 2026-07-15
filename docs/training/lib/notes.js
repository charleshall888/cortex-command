/* Presenter talk-track cues, per scene, per beat. beats[i] = what to say /
   do at beat i (0 = scene entry). exit = the bridge line into what's next.
   Terse by design — cues, not a script. Full drafted scripts for the cold
   open and the rewind live in cortex/research/training-talk-deck-outline.md,
   Appendix A. */

const NOTES = {
  "sc-cold-open": {
    beats: [
      "“Every demo you'll see lives in one fictional project — Nightline, a little game about setting fishing lines overnight and waking up to your catch.”",
      "“Here's a puzzle. Two agents. Same model. Same tool. Same request.” (request + panes appear; the two context bars fill — LET the right one finish its sweep before speaking over it)",
      "LEFT RUN plays (~20s). Then: “Notice — it asked me one question first. Then it nailed it.”",
      "RIGHT RUN plays. “…And this one is patching a file that has nothing to do with the log.”",
      "REVEAL (screen dims to the bars): “Same model. Same tools. Same request. The right one had been at work six hours — that's MY agent; this is a re-enactment of my actual Friday.” THEN the disclosure: “And yes — I staged both, like everything on screen here, so it's clean and nobody's real code gets dunked on. The stories I'll tell over it are real.” LAND IT over the two bars (the thesis is spoken now, not on screen): “The only difference on this screen is that bar. That bar is the whole game. Nothing about the model changed — everything it was reading did.”",
    ],
    exit: "METR PLANT: “Want independent evidence? There's a study — experienced engineers, 19% SLOWER with AI. I believe it. By the end you'll know the mechanism I blame.”",
  },
  "sc-blueprint": {
    beats: [
      "“So the whole game is managing context — managing what the agent reads. That's the job.” Bridge for the jargon: “the window — that's the bar, stood upright. I'll pour you one in a minute.”",
      "(the three pillars land) Read them once, slowly, verbatim: “Keep your context window lean. Spawn more agents. Keep your workspace clean.” Then: “Every scene from here is one of these three moves. We take them in order.”",
    ],
    exit: "“First: what IS in there?”",
  },
  "sc-gauge": {
    beats: [
      "“This is the same bar, stood upright — the context window. Let me show you what six hours pours into it.” (empty tank, bar at 0)",
      "LAYERS POUR, labeled. “System prompt sediment. The chat — yours and its — the thin blue bands. And the fat grey slabs: files it read, test output. Tool output is what eats the window, not your typing.” (the bar underneath tracks the tank — same object)",
      "SWEEP PLAYS SILENT (~4s) — say nothing. Then over the frozen frame: “Every single turn, it re-reads the entire window. You resend everything, every time. Junk in here isn't history — it's rent.”",
      "ZONES + THE DOOR: “MY numbers, from a year of daily use — under 30 is the goldilocks zone; at 50 there's a door, and I plan my exit through it. Yours may differ. That you HAVE numbers is the point.”",
      "FAST-FORWARD past the door (bar goes red): “and if you sail past the door without a plan… you get the cold open's right-hand pane: slower answers, higher rent. Mystery solved, mechanically. Now — what fills it can also fight you.”",
    ],
    exit: "",
  },
  "sc-squeeze": {
    beats: [
      "“When you blow past the line anyway — ninety-five percent — the tool offers you a button: compact. Look what's floating in the window first — four things only I knew. No search engine has any of them.” (point at the pinned chips, read one or two)",
      "SQUEEZE PLAYS SILENT 6–8s — “watch what falls out.” The chips land in the lost pile; the stripe keeps the gist. Then: “Look at the bar — ninety-five to five. The NUMBER got better. It summarized the chat and rolled the dice: the gist survived, four decisions didn't. You don't get to pick which.”",
      "PAYOFF (mini-terminal fires, the chip glows): “Two hours later, my 4:00 ask lands — and it touches the one file I said never to touch. Biting disabled game-wide. That's the cold open, from the inside: the thing it needed was in the pile.” Concede-then-land: “Newer models compact better, AND ‘handles it better’ is not ‘best output per token.’ Compaction is an airbag, not the brakes — lean on it every session and you're running your Fridays on chance. The rest of this deck is how you stay in control instead.”",
    ],
    exit: "“That's the gamble a full window forces. Here's what a full window DOES — it has a name.”",
  },
  "sc-noloop": {
    beats: [
      "“Earlier that same afternoon — the failure you've all met. It has a name: the death spiral. One stubborn bug, and watch the window on the right while this plays.”",
      "LAP 1: “escaped fish are showing up in the log. It patches the VIEW — a symptom fix. Doesn't work. I correct it — and watch where the whole thing goes: IN. The failed attempt, my correction, all of it.”",
      "LAP 2: “so it swings to the opposite extreme — deletes the events at the source. That breaks tackle stats. NO. In that goes too. The window is filling with wreckage.”",
      "THE RELAPSE snaps — SAY NOTHING until the row lands. Then: “lap two. The SAME patch as turn 71 — check it yourself. It's flip-flopping between its own bad ideas, and every lap it re-reads MORE junk: dead attempts, my corrections, its apologies. Heavier in, worse out. Look at the bar.”",
      "ANCHOR (screen dims): “That's the spiral. You can't argue your way out of it — every argument makes the window heavier. You can only cut it out. Here's how.”",
    ],
    exit: "",
  },
  "sc-filmstrip": {
    beats: [
      "HOOK FIRST: “This is the cheapest win I'll show you. Zero setup. Works today. Almost nobody does it.”",
      "(strip populates; load bar labels itself) “Your conversation is a timeline. And that bar underneath — that's the gauge again, lying on its side: what the next turn re-reads.”",
      "FORK (30s vocab): “mid-build you wonder — would SQLite be simpler? Branch it. Explore in the fork, take the answer, come back. The main lane never knew.”",
      "RED RUN — tell the story over it: “Before the log could exist, fish have to bite at night. First idea feels obviously right: server-driven time, so players can't cheat. And we go DOWN this road — auth, account state, clock sync, offline reconciliation. Forty minutes deep, I finally ask: who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them.”",
      "THE TAKE — SAY NOTHING. Full stillness, then rewind plays (~8s). After: “Look at that headroom — every one of those cents was rent I'd have kept paying. It's morning again. And notice — I didn't argue with it. I took the whole dead branch OUT.”",
      "CLEAN BRANCH + rebuttal: “‘Isn't that just deleting your chat?’ No — see the note that hopped across, and what's written on it? Carry the lesson, leave the wreckage. If you don't rewind, you keep paying rent on the dead idea — every turn re-reads it, forever.”",
    ],
    exit: "VALVE — natural exhale after the laugh (~1.5 min for questions on the mechanics).",
  },
  "pv-1": {
    beats: [
      "Let the room read the proverb. Say nothing.",
      "(post lights) “First post: keep your context window lean — the gauge, the squeeze, the death spiral, the rewind.” Bridge: “But everything we just protected lives in a window that empties when the session ends. The things that must SURVIVE need to live somewhere else. Not in the window. In a doc.”",
    ],
    exit: "",
  },
  "sc-prism": {
    beats: [
      "PILLAR 2. “The first twenty percent of a session steers all the rest. So before anything sails, I get the direction out of my head — and my shop runs this as commands, but the shape works with markdown and discipline.” (the rail names the steps) PRE-FRAME the triplet: “next three minutes are one continuous story — drop questions in chat, I'll take everything after the punchline.”",
      "(head + cloud) “This is the epic — currently a cloud in my head.”",
      "INTERVIEW (rail step 1): “I don't write the doc alone — the agent interviews ME.” (bubbles land; point at the first one) “Recognize that question? It's the one the fresh agent asked in the cold open. And the last one? That's the death-spiral bug — asked as a planning question, instead of argued about at turn seventy-nine. Every answer sharpens the doc.”",
      "CONDENSE (rail step 2): “If you're about to go on a long journey, the first few miles decide where you land. The doc survives; your context doesn't — that's the whole point of writing it down.”",
      "TICKETS + STAMPS (watch the intent line fly onto each): “discovery splits the epic into three tickets, and every ticket carries one line of intent from the parent. The last one? That's the request from the cold open. It was never a one-off ask — it was a shard of a plan.”",
      "THE OFFER (rail step 3): “and this is the planning session's LAST job. It doesn't build anything — it hands off, in order: catch events has no dependencies, so it's ready now; flip-through needs those events; empty state can ride alongside. Constraints, done-when, one line of intent — each ticket is everything a fresh window needs. Next scene we cash all three.”",
    ],
    exit: "PROTECTED TRIPLET — if interrupted: “hold that thought two minutes — you'll see it answered or get worse.”",
  },
  "pv-2": {
    beats: [
      "Let the room read the proverb. Say nothing.",
      "(second post lights) “Second post: spawn more agents — write it down, then fan out. One ticket, one fresh window; and a fresh window to check your own work. You don't catch more by reeling harder.” Bridge: “But every window you spawn carries silent passengers — the instruction files and tooling bolted onto it. Keep those clean, and a fresh window STAYS clean.”",
    ],
    exit: "",
  },
  "sc-lines": {
    beats: [
      "“Same epic, two ways — and one clock for both. Top lane: hand the whole thing to one window and say go — the road we didn't take, played out.”",
      "(SILENT ~5s while the wedge climbs, then) “That's the gauge again — the same bar, laid along a clock. Every turn re-reads the whole height of it. Watch it climb… past the door. No plan.”",
      "(let the sawtooth land) “Full — compact — keep going. Full again — compact again. The squeeze from an hour ago, twice, uninvited. It DOES finish. Five and a quarter hours.”",
      "THE DEBT: “look where the ✗s sit — everything written up there, deep past the door: a helper that already existed, a format it had already decided against, tests that hang without --offline. All of it ships.”",
      "(SILENT while the chain draws) “The other way: the three tickets we cut last scene, run in dependency order. Catch events first — fifty minutes, and its finish unblocks the other two. Flip-through and empty state, side by side, fresh windows both. None of them ever sees the door. Read the two bills.”",
      "VERDICT: “An eighth of the tokens. A third of the clock. Nothing written in the red. And when tickets don't depend on each other at all, the lanes just start together — the finale runs three at once.” SCAR: “same move works for ideas, not just tickets — this deck was designed by fanning out four angles; the fact-checker caught a claim I had exactly backwards.” (cost numbers ONLY if asked — appendix)",
    ],
    exit: "“That's the fan-out — one fresh window per ticket. One more use of a fresh window: point it at your own work.”",
  },
  "sc-arrows": {
    beats: [
      "“Fresh eyes catch what tired eyes miss — because a fresh window doesn't share your session's assumptions.”",
      "(the doc appears, alone) “These are the requirements from an hour ago — the direction, written down.”",
      "(the doc slides onto the target stand — narrate OVER the 2s move) “I hand it to a brand-new session that wasn't in the room, and give it ONE job: break it. No shared assumptions — that's the point.”",
      "FINDING 1 (arrow bounces, then the stamp): read it aloud — “log writes need retry logic — bounced. The requirements already cover it.”",
      "FINDING 2: “entries need pagination — bounced. Out of scope for v1. Two bounces is not a failed review — the requirements HELD.”",
      "FINDING 3 (the pierce, the crack): “this one's real. A rare fish under the size limit gets auto-released — a Brass Minnow would never reach the log. Our own rule punishes the best catch of the night.”",
      "GOLD SEAM + new intent line: “the doc is stronger where it cracked — and the fix earns its own line: never punish a rare catch.” HONEST BEAT: “sometimes this steers me wrong. More often it makes things better.”",
      "THE MANUFACTURED ONE — read it aloud, let it bin itself: “frame-accurate input-latency compensation. For a fishing game. It will ALWAYS find something — you asked for findings, so it manufactures findings. Serves no intent — binned. You judge.” RECIPE: “no tooling needed — fresh session, paste the requirements, ask it to break them, judge the findings.”",
    ],
    exit: "One line: “crank this too hard and you get armor-plated docs and dead good ideas.” Then hand to the waypoint: “fresh windows built it, and fresh eyes checked it — that's the whole second post.”",
  },
  "sc-scroll": {
    beats: [
      "“The moment you believe the wrapper matters, you'll want to customize yours. Here's where that goes wrong.” (the exhibit frame: everything inside the dashes is the specimen; my lessons land on the right)",
      "(tidy 20-line file) “This is a skill file — standing instructions, poured into every window. Twenty lines. It started perfect.”",
      "RATCHET plays — let the room READ the file (esp. #1,486 vs #212). Then: “models don't need many instructions — but they love WRITING many. Almost every ‘tune it’ grows the file — it bloats — until it contradicts itself and needs a precedence rule. Line 2,041 is real governance for a rulebook nobody reads. The exhibit's exaggerated for the joke — but the model did this to me too: mine genuinely kept growing until the day I cut it.” Scar: “writing the instructions is the one job I never hand over.”",
      "THE GATE (line 1,847 appears, gets struck; the count ticks DOWN): “one line in there is different — ALWAYS run the tests. If it MUST happen, a sentence is the wrong tool: it rides in every window, costs rent every turn, and gets obeyed sometimes. I made it a pre-commit hook. Runs every time. Costs zero context. Argues with no one. And the file got fifty-three lines shorter — the rule plus its exception thicket.”",
      "THE SHOVE + sweep (the gauge callback): “and here's the bill for everything still in there: this file rides in EVERY window, and you re-pay it on every turn. A bloated skill file means your agent starts Monday morning already tired.” SCAR: “If I could go back: hand-craft the simple skills myself, and let Claude build the CLI around them. Open-ended plus unverifiable is the worst possible task shape for an LLM.”",
      "THE FIX (second exhibit lands): “same skill, rebuilt. SKILL.md shrinks to a thirty-line core; the detail moves into reference files — specs, plans, code — opened per task. Reviewing a plan? The window gets the core plus plans.md, nothing else. Matt Pocock's public skills are like this — tiny. Project-specific beats generic.”",
    ],
    exit: "“That's your standing tackle sharp: a lean core, per-task files, and gates for the must-happens. Last question — when do you hand that tackle to everyone else?”",
  },
  "sc-tackle": {
    beats: [
      "“Last slide's exit asked: when do you hand that lean tackle to everyone else? You don't — not yet. Here's my rod, rigged with that review skill as its lure. Committed to nothing.”",
      "(the fish rises) “First I prove it on my OWN line — fished it on my repo's weak spots for a while. It catches. Nobody else has paid a thing.”",
      "(SILENT as the clamps snap red) “Then the reflex: staple it onto everyone. And it's never just mine — her MCP, his plugin, this week's shiny thing, all forced onto every rod. See that one — never casts this way, never runs a review. Carries it anyway, every window, every turn. That's the engineer tossed by every wave of the industry. Don't be him.”",
      "(the lure drops into the box) “Instead — it goes in the box. And the box has a rule: nothing goes in till it's landed a fish. Rigged for these waters? PR it in; everyone here fishes them. Works any water? Ship it as its own kit the crew opts into.”",
      "(a crewmate lifts it out) “Now only the line that CHOSE it carries it. She reviews a lot — she reaches in and takes it. Every other line stays clean. Prove the value first, or the crew stops trusting your tackle.”",
      "(let the verdict land — say nothing; the room reads it)",
    ],
    exit: "into pv-3: “Keep your box sharp — proven, lean, open — and your tackle takes care of you AND the crew.”",
  },
  "pv-3": {
    beats: [
      "Let the room read it. Say nothing.",
      "(third post lights) “Last post: keep your workspace clean — lean instruction files, gates for the must-happens, and tooling you prove on your own bench before it rides in anyone else's window. Three posts. One plank missing — and one Friday to draw it.”",
    ],
    exit: "VALVE (~2 min): take the “how do we adopt this” logistics discussion HERE — the finale and the closer come last, so the deck ends on the image.",
  },
  "sc-finale": {
    beats: [
      "(the red pane sweeps back to 91 — LET IT FINISH) “Still Friday. Still four o'clock. We left this agent exactly here. And one more ask just landed — a big one: make Monday's playtest real. Last time, we typed the ask straight into THAT.”",
      "(red pane folds) “First move: read the bar. Past the door. We don't argue, we don't compact — retired.” (discovery runs) “The ask is a wish, and wishes are fine — you just don't hand one to a coder. You hand it to discovery: it interviews you, researches the code, and writes the epic. Notice it caught that biting is still broken — Friday's wreckage just became the first ticket.”",
      "(the doc rises; three intent lines fly to three tickets — SAY NOTHING during the flights) “One epic, three tickets. Look at the stamps: single-player from the rewind. Keepsake from the interview. Rare catch from the review. Every one of those lines was paid for by a session that's already dead — the doc carries the lessons forward. The wreckage stays behind.”",
      "(three fresh windows run in parallel — mostly let them) “4:19, three windows, all at once. Left one is undoing Friday — same file, same line, reversed; and it didn't re-litigate server time, because its ticket told it cheating's allowed. Middle one just bounced off the gate — tests first, then through. And that --offline flag on every run? The scar the squeeze lost — it lives in an instruction file now. Fresh windows are born knowing it.”",
      "(the three fold — SAY NOTHING until the log card lands) “5:58. Three tickets shipped, nothing broken, no working bar ever left the green. And the log is live — empty, and inviting. The night is young — and in the game, that's literally true.”",
      "KICKER + the dock completes: “Nothing here needed a better model. Every move you just watched was managing context — what's in the window, what's written down, who gets a clean window. Same model as the disaster. Run this Friday yourself.”",
    ],
    exit: "into dawn: “So come back Tuesday morning, and let's see what bit.”",
  },
  "sc-dawn": {
    beats: [
      "(dawn is breaking — the moon has set; the dock stands complete) One line if needed: “fish were biting again by sunset — that's the only reason there's anything to see.”",
      "LOG CARD: “first page of the log: the Brass Minnow. Rare, small, kept — that's the fresh-eyes review, paying off.” (don't over-explain)",
      "RECAP, verbatim, one breath each: “Keep your context window lean. Spawn more agents. Keep your workspace clean.” METR CLOSE: “that study from the start? My bet: the nineteen percent were carrying full windows.”",
      "CLOSER: “Everyone in this room rents the same models. The habits are what you own. Send your agents home before Friday afternoon.” (link stays up during questions)",
    ],
    exit: "",
  },
};
