/* Presenter talk-track cues, per scene, per beat. beats[i] = what to say /
   do at beat i (0 = scene entry). exit = the bridge line into what's next.
   Cues, not a script — the presenter riffs, never reads these aloud. Keep
   them short: a trigger + the one phrase that must land verbatim (in quotes)
   + the stage direction. On-screen lines (proverbs, pillars, thesis text)
   are cued as "let it land", not spoken. Full drafted scripts for the cold
   open and the rewind live in cortex/research/training-talk-deck-outline.md,
   Appendix A. */

const NOTES = {
  "sc-cold-open": {
    beats: [
      "“Nightline — set your lines overnight, wake up to your catch. Every demo lives here.”",
      "(request + panes; LET both bars fill — don't talk over the right one's sweep) “Two agents, same request — same model, same tools. Watch the bars.”",
      "(LEFT plays ~20s) “One question first — then it nailed it.”",
      "(RIGHT plays) “This one's patching a file with nothing to do with the log.” (let “biting disabled game-wide” land on its own)",
      "(dims to the two bars) Let “Same model. Same tools. Same request.” land. Then: “six hours in — that's mine, my actual Friday.” DISCLOSURE: “I staged both — the stories I tell over it are real.” Land it: “the only thing that changed on this screen is that bar.”",
    ],
    exit: "PLANT: “one study — experienced engineers, 19% SLOWER with AI. I believe it. By the end you'll know the mechanism I blame.”",
  },
  "sc-blueprint": {
    beats: [
      "(dock sketch + headline land) beat, then: “that's the job.”",
      "(three pillars land) SAY NOTHING — let them read: “keep your context window lean · spawn more agents · keep your workspace clean.” Then: “every scene ahead is one of these three, in order.”",
    ],
    exit: "“First — what's actually in there? Let me pour you one.”",
  },
  "sc-gauge": {
    beats: [
      "“Same bar, stood upright — the context window. Let's pour in six hours.”",
      "(layers pour, labeled) “The fat grey slabs — files it read, test output — that's what eats the window. Not your typing.”",
      "(SWEEP — SILENT ~4s) then: “every turn, it re-reads the whole thing. Junk in here isn't history — it's rent.”",
      "(a sliver pours; the second sweep runs blue, hatching stamps in behind it) “Half of you are thinking: prompt caching. You're right — the unchanged start comes back about ten times cheaper, and faster. But watch the line — it still walks the whole tank. Caching shrinks the bill, not the reading.” Then let “cheaper, not lighter — it still reads all of it” land.",
      "(zones + door) “My numbers, a year of daily use — under 30 goldilocks, at 50 a door I plan my exit through. Yours may differ; having numbers is the point.”",
      "(past the door, red) “No plan past the door — that's the cold open's right pane. Slower answers, higher rent.”",
    ],
    exit: "“Now — what fills it can also fight you.”",
  },
  "sc-squeeze": {
    beats: [
      "(point at the pinned chips, read one or two) “Blow past the line, it offers a deal: compact. First — four things only I knew. No search engine has them.”",
      "(SILENT 6–8s through the squeeze) then: “ninety-five to five. The number got better — it rolled the dice on the chat. Gist survived, four decisions didn't. You don't pick which.”",
      "(payoff fires) “Two hours later my ask lands — and touches the one file I said never touch. The cold open, from the inside: what it needed was in the pile.” (concede) “newer models compact better — but that's an airbag, not the brakes.”",
    ],
    exit: "“That's the gamble a full window forces. What a full window DOES — that has a name.”",
  },
  "sc-noloop": {
    beats: [
      "“Same afternoon. One stubborn bug. Watch the bar on the right.”",
      "(lap 1) “It patches the view — symptom fix. Doesn't work. I correct it — watch where all of it goes: IN.”",
      "(lap 2) “Swings the other way — deletes the events. Breaks stats. That goes in too.”",
      "(relapse — SAY NOTHING till it stamps) “same edit as turn 71.” “Flip-flopping between its own bad ideas — heavier in, worse out.”",
      "(spotlight) SILENT — let “You can only cut it out.” land.",
    ],
    exit: "“Here's how you cut it.”",
  },
  "sc-filmstrip": {
    beats: [
      "“Cheapest win in this talk. Zero setup. Almost nobody does it.”",
      "(strip populates) “Your conversation's a timeline — and that load bar's the gauge again, on its side. New feature: overnight fishing, in the player's REAL night. First turns scope it — and the cheating question shows up immediately.”",
      "(fork — ghost lane, the answer comes home) “First idea, tried in a branch: trust the device clock. The branch comes back with its answer — players travel, timezones shift, a cheater just moves the clock. The main lane never carried the dead end.”",
      "(red run) “So the main lane grinds on server-enforced time. Forty minutes down that hole — sync, drift, spoofed timezones — before the real question lands: who am I even defending against?” “Single-player — cheating's allowed.”",
      "(rewind — SILENT ~8s) then: “All that rent, gone. I didn't argue — I cut the branch.”",
      "(clean branch, note hops across) “Rewound to the clean point: device clock, no anti-cheat, done by morning. Not just deleting your chat — that note's the lesson. Carry it, leave the wreckage.”",
    ],
    exit: "VALVE — let the laugh land; ~1.5 min for questions on the mechanics.",
  },
  "pv-1": {
    beats: [
      "SAY NOTHING — let them read the proverb.",
      "(post lights) SILENT — let “keep your context window lean” land: the gauge, the squeeze, the spiral, the rewind.",
    ],
    exit: "“But that window empties when the session ends. What has to survive lives somewhere else — a doc.”",
  },
  "sc-prism": {
    beats: [
      "(the crossing, seen from above — the spot lit) “The first 20% of a session steers all the rest. Here's that, drawn as a night crossing.”",
      "(the bearing draws — one ruler stroke) “Before casting off: sight the spot, write the bearing down.”",
      "(both wakes run — SILENT ~5s till the gap opens) “Same speed, same water, nothing goes wrong out there. The boat that plotted lands on the light. The other one's miss was decided back at the dock — an angle too small to see.”",
      "(the sea folds; the rail lights) “So I spend that first 20% deliberately — three steps.”",
      "(head + cloud) “The epic — still just a cloud in my head.”",
      "(interview bubbles) “It interviews ME. First question — recognize it? Cold open. Last one — the death-spiral bug, asked here instead of fought over at turn 79.”",
      "(doc + intent) SILENT — let “a keepsake, not analytics” land. “The doc survives; your context doesn't.”",
      "(tickets, stamps fly) “Discovery splits the epic into three, each carrying one line of intent. Last ticket — the cold-open ask. Never a one-off; a shard of a plan. You see it run end-to-end at the finale — here, just the shape.”",
    ],
    exit: "“That's the setup — the epic broken into tickets, one per fresh window. And a fresh window has one more use: point it at your own work.”",
  },
  "sc-arrows": {
    beats: [
      "“Fresh eyes catch what tired eyes miss — a fresh window doesn't share your assumptions.”",
      "(doc alone) “The requirements, from an hour ago.”",
      "(narrate over the 2s slide) “Handed to a session that wasn't in the room. One job: break it.”",
      "(finding 1 struck out) “It wants the log page rewritten in Rust. For a keepsake. No.”",
      "(finding 2 struck out) “Cloud sync and leaderboards — single-player game. No. Saying no fast is the job — a wild swing costs you one word.”",
      "(finding 3, the crack) “This one's real — the Brass Minnow. Rare, under the size limit, auto-released. Never reaches the log. Our own rule punishes the best catch of the night.”",
      "(gold seam, badge) SILENT — let “never punish a rare catch” land. SCAR: “sometimes this steers me wrong. More often it makes things better.”",
      "(the judge line lands) “It'll always find something — two wild swings and one real crack. You judge what counts.”",
    ],
    exit: "“Crank it too hard and you get armor-plated docs and dead good ideas.” Then: “fresh windows built it, fresh eyes checked it — a fact-checker window even caught a claim I'd gotten exactly backwards — that's the whole second post.”",
  },
  "pv-2": {
    beats: [
      "SAY NOTHING — let them read the proverb.",
      "(post lights) SILENT — let “spawn more agents” land: “write it down, then fan out — a fresh window per ticket, and one to check your own work.”",
    ],
    exit: "“But every window carries passengers — instruction files, tooling. Keep those clean, and a fresh window stays fresh.”",
  },
  "sc-scroll": {
    beats: [
      "(exhibit frame) “The moment you think the wrapper matters, you'll tune it. Here's the trap.”",
      "(tidy 20-line file) “Standing instructions, poured into every window. Twenty lines. Started perfect.”",
      "(ratchet to 6,000 — let them read the bloat) “Models don't need many instructions — they love writing them. Every ‘tune it’ adds a line, till it contradicts itself and needs a rule just to sort the rules.” SCAR: “writing the instructions is the one job I never hand over.”",
      "(sweep — the file stays up) “All six thousand lines ride in every window, and you re-pay them every turn. A bloated skill file means Monday starts tired.” SCAR: “if I could go back — hand-craft the simple skills myself, let Claude build the CLI around them.”",
      "(the fix, beside the monster) “Same skill, rebuilt: a 30-line core, detail in files you open per task. Reviewing a plan? The window gets the core plus plans.md — nothing else.”",
    ],
    exit: "“The instructions stay lean — and they stay yours. Now step to the end of the dock — it keeps something of its own out on the water.”",
  },
  "sc-buoys": {
    beats: [
      "(the buoys land — let them read all three) “Out past the dock it keeps markers — notes it writes to itself, one lesson each. Nobody typed these.” SEAM: “the scroll was instructions — those stay yours. Its own notes? That's what memory is for.”",
      "(lamps come up — SAY it, it's not on screen) “Every session loads all of them. What one session learns, the next one already knows.”",
      "(FishManager struck, CatchService inked) “It re-tunes them too — but only the conflict it happens to notice. Mid-task it caught the rename and re-inked the tag. Nobody asked.”",
      "Let “it only re-inks the ones it catches fighting reality” land. Then: “the ones it never notices just sit there — steering every session. And a wrong marker glows just as bright as a right one.”",
      "(verdicts land — slow down on the strike) “So now and then, you sift. This warning — keep it. The middle one it already fixed. This last one was never true — it watched rares vanish and wrote it down as the rule. The Brass Minnow bug — weeks of agents ‘knowing’ the wrong thing, and you'd never guess why from the outside. Cut it loose.”",
      "SILENT — let “A stale note steers you quietly — and you won't know why. Sift them, now and then.” land. Then: “ten minutes, once in a while. That's the whole habit.”",
    ],
    exit: "“Markers honest, core lean — now, the tackle. When do you hand it to everyone else?”",
  },
  "sc-tackle": {
    beats: [
      "“Not the crew yet — just my line. The review skill's the lure, committed to nothing.”",
      "(fish rises) “Fished my own repo's weak spots a while. It catches. Nobody else has paid a thing.”",
      "(SILENT as the rail goes red) “The reflex: staple it onto every rod. Someone's MCP, someone's plugin, this week's shiny thing. Even the one that never casts here — carries it anyway, every window, every turn. Don't be that.”",
      "(drops into the box) “Into the box instead. Rule: nothing goes in till it's landed a fish. Fits these waters — PR it in. Works anywhere — its own kit, opt-in.”",
      "(a crewmate lifts it, green) “Now only the line that chose it carries it. Everyone else stays clean.”",
      "(verdict) SILENT — let “Rent is what you force on the crew. Tackle is what they choose.” land.",
    ],
    exit: "(cut into pv-3) “keep the box sharp — proven, lean, opt-in — and your tackle takes care of you AND the crew.”",
  },
  "pv-3": {
    beats: [
      "SAY NOTHING — let them read the proverb.",
      "(post lights) SILENT — let “keep your workspace clean” land: lean instruction files, a memory you audit, and tooling you prove on your own bench first.",
    ],
    exit: "“Three posts down. One plank missing on that dock — and one Friday to lay it.”",
  },
  "sc-finale": {
    beats: [
      "(tasks reveal as the bar climbs — LET IT CLIMB) “Still Friday, four o'clock, same tired agent — you hand it the cold open's exact ask again: add an empty-state to the catch log. In one window it balloons — record the catches, the log page, then the empty state itself — stacking up. Task 1, near-empty context, green — clean. Task 2, half-full, amber — ships, but it slips. Task 3, ninety-one percent, red — no room left to think; it skips the tests and, watch, disables biting game-wide — the exact cold open. Same agent every time; the only thing that changed is how full the window got. Hold those three numbers; they come back, one to a window.”",
      "(red pane folds; discovery runs) “Read the bar — past the door. We don't argue, we don't compact. Retired. Hand the same ask to discovery: it interviews, researches, writes the epic — and it even catches that biting's still broken from this afternoon and quietly fixes it. That's the note on the doc.”",
      "(doc rises, the lessons ride onto the work — SAY NOTHING during the flights) “The doc keeps all three lessons, each from a dead session — but only two fit these tickets: never-punish-a-rare rides onto how we record catches, keepsake onto the log page. The third, single-player from the rewind, is what fixed the biting. And the last ticket — empty state — needs no lesson; it's the very thing Friday first asked for.”",
      "(three windows, parallel) “4:19 — the same three, now one to a window. Task 1 records every catch — a rare under the size limit still reaches the log. Task 2 flip-through bounces off the gate, then ships. Task 3 is the empty state itself — the cold open's ask, done right. And that --offline scar? Lives in an instruction file now — every fresh window's born knowing it.”",
      "(fold — the scorecard centers, alone) “5:58. Three tickets, nothing broken, no bar ever left the green — and biting's back.” (let the two rows land — they're the whole talk)",
      "(thesis) SILENT — let “Nothing here needed a better model.” land: “same model as the disaster.”",
    ],
    exit: "into dawn: “come back Tuesday morning — let's see what bit.”",
  },
  "sc-dawn": {
    beats: [
      "(dawn; dock complete) only if the beat needs filling: “fish were biting again by sunset — the only reason there's anything to see.”",
      "(log card) “First page of the log: the Brass Minnow. Rare, small, kept.”",
      "(recap) SILENT — let “keep your context window lean · spawn more agents · keep your workspace clean” land. Then: “that study from the start? My bet — the 19% were carrying full windows.”",
      "CLOSER (say it): “everyone in this room rents the same models. The habits are what you own. Send your agents home before Friday afternoon.”",
    ],
  },
};
