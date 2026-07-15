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
      "(relapse — SAY NOTHING till it stamps) “same patch as turn 71.” “Flip-flopping between its own bad ideas — heavier in, worse out.”",
      "(spotlight) SILENT — let “You can only cut it out.” land.",
    ],
    exit: "“Here's how you cut it.”",
  },
  "sc-filmstrip": {
    beats: [
      "“Cheapest win in this talk. Zero setup. Almost nobody does it.”",
      "(strip populates) “Your conversation's a timeline — and that load bar's the gauge again, on its side.”",
      "(fork) “Wonder if SQLite's simpler, mid-build? Branch it, find out, come back. The main lane never knows.”",
      "(red run) “First idea: server-driven time, so nobody cheats. Forty minutes down that hole before I ask who I'm even defending against.” “Single-player — cheating's allowed.”",
      "(rewind — SILENT ~8s) then: “morning again. All that rent, gone. I didn't argue — I cut the branch.”",
      "(clean branch, note hops across) “Not just deleting your chat — that note's the lesson. Carry it, leave the wreckage.”",
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
      "“The first 20% of a session steers all the rest — so I get the direction out of my head first.” (next three scenes are one story — ask the room to hold questions)",
      "(head + cloud) “The epic — still just a cloud in my head.”",
      "(interview bubbles) “It interviews ME. First question — recognize it? Cold open. Last one — the death-spiral bug, asked here instead of fought over at turn 79.”",
      "(doc + intent) SILENT — let “a keepsake, not analytics” land. “The doc survives; your context doesn't.”",
      "(tickets, stamps fly) “Discovery splits the epic into three, each carrying one line of intent. Last ticket — the cold-open ask. Never a one-off; a shard of a plan.”",
      "(handoff) “Its last job: hand off, not build. Catch events first, ready now; flip-through waits on it; empty state rides alongside.”",
    ],
    exit: "(protected triplet) if interrupted: “hold that thought — two minutes, you'll see it answered.”",
  },
  "sc-lines": {
    beats: [
      "“Same epic, two ways, one clock. Top lane: hand it all to one window and say go.”",
      "(SILENT ~5s, wedge climbs) then: “the gauge again, laid along a clock — climbing past the door. No plan.”",
      "(sawtooth) “Full, compact, full, compact — the squeeze, twice, uninvited. It does finish. Five and a quarter hours.”",
      "(point at the ✗s) “Written up there in the red — a helper that existed, a format it already rejected, tests that hang without --offline. All of it ships.”",
      "(SILENT while the chain draws) “Same three tickets, dependency order. Catch events first — unblocks the other two, side by side. None ever sees the door.” (read the two bills)",
      "SILENT — let “an eighth of the tokens · a third of the clock · nothing in the red” land. SCAR: “same move works on ideas — this deck was built by fanning out four angles; the fact-checker caught a claim I had exactly backwards.”",
    ],
    exit: "“That's the fan-out. One more use for a fresh window — point it at your own work.”",
  },
  "sc-arrows": {
    beats: [
      "“Fresh eyes catch what tired eyes miss — a fresh window doesn't share your assumptions.”",
      "(doc alone) “The requirements, from an hour ago.”",
      "(narrate over the 2s slide) “Handed to a session that wasn't in the room. One job: break it.”",
      "(finding 1 bounces) “Retry logic — bounced. Already covered.”",
      "(finding 2 bounces) “Pagination — bounced, out of scope. Two bounces isn't a failed review — the requirements held.”",
      "(finding 3, the crack) “This one's real — the Brass Minnow. Rare, under the size limit, auto-released. Never reaches the log. Our own rule punishes the best catch of the night.”",
      "(gold seam, badge) SILENT — let “never punish a rare catch” land. SCAR: “sometimes this steers me wrong. More often it makes things better.”",
      "(manufactured finding bins itself) “Frame-accurate input-latency compensation — for a fishing game. It'll always find something. You judge what counts.”",
    ],
    exit: "“Crank it too hard and you get armor-plated docs and dead good ideas.” Then: “fresh windows built it, fresh eyes checked it — that's the whole second post.”",
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
    exit: "“Tackle's sharp — a lean core and per-task files. Last question: when do you hand it to everyone else?”",
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
      "(post lights) SILENT — let “keep your workspace clean” land: lean instruction files, and tooling you prove on your own bench first.",
    ],
    exit: "“Three posts down. One plank missing on that dock — and one Friday to lay it.”",
  },
  "sc-finale": {
    beats: [
      "(red pane sweeps to 91 — LET IT FINISH) “Still Friday, four o'clock. Same agent we left here. One more ask just landed — make Monday's playtest real.”",
      "(red pane folds; discovery runs) “Read the bar — past the door. We don't argue, we don't compact. Retired. Hand the wish to discovery: it interviews, researches, writes the epic. It caught that biting's still broken — Friday's wreckage is ticket one.”",
      "(doc rises, three stamps fly — SAY NOTHING during the flights) “Three lines: single-player from the rewind, keepsake from the interview, rare catch from the review. Each one paid for by a session that's already dead.”",
      "(three windows, parallel) “4:19, one per ticket. Night biting doesn't relitigate server time — its ticket says cheating's allowed. Flip-through bounces off the gate, then ships. And that --offline scar? Lives in an instruction file now — every fresh window's born knowing it.”",
      "(fold — SAY NOTHING till the log card lands) “5:58. Three tickets, nothing broken, no bar ever left the green.” (scorecard is the whole talk in two columns) Let “No catches yet. The night is young.” land.",
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
