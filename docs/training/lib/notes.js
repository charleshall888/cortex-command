/* Presenter talk-track cues, per scene, per beat. beats[i] = what to say /
   do at beat i (0 = scene entry). exit = the bridge line into what's next.
   Terse by design — cues, not a script. Full drafted scripts for scenes 1
   and 9 live in cortex/research/training-talk-deck-outline.md, Appendix A. */

const NOTES = {
  "sc-cold-open": {
    beats: [
      "“Every demo tonight lives in one fictional project — Nightline, a little game about setting fishing lines overnight and waking up to your catch.”",
      "“Here's a puzzle. Two agents. Same model. Same tool. Same request.” (request line appears)",
      "LEFT RUN plays (~20s). Then: “Notice — it asked me one question first. Then it nailed it.”",
      "RIGHT RUN plays. “…And this one is patching a file that has nothing to do with the log.”",
      "REVEAL: “Same model. Same harness. Same afternoon. The right one had been at work six hours. That's MY agent — this is a re-enactment of my actual Friday.” THEN the disclosure: “And yes — I staged both, like everything on screen today, so it's clean and nobody's real code gets dunked on. The stories I'll tell over it are real.”",
      "THESIS: “The model sets the ceiling. Everything wrapped around it determines the yield.”",
    ],
    exit: "METR PLANT: “Want independent evidence that yield can go negative? There's a study — experienced engineers, 19% SLOWER with AI. I believe it. Let me show you the mechanism.”",
  },
  "sc-scan": {
    beats: [
      "“Let me show you what six hours did to that agent.” (vessel empty)",
      "Layers pour: system prompt sediment, your chat, and those fat grey slabs — tool results. “Tool output is what eats the window, not your typing.”",
      "SWEEP PLAYS SILENT (~5s) — say nothing. Then over the frozen frame: “Every single turn, it re-reads the entire session. You resend everything, every time.”",
      "Second sweep, hatched: “Caching discounts the re-read — AND it dies on prefix changes. But cost isn't the headline. The research is consistent: effective context is smaller than advertised context.”",
    ],
    exit: "",
  },
  "sc-zones": {
    beats: [
      "POLL (cap 60s, chat not unmute): “Whoever has a session open — what percent are you at? Type it in chat. Nothing open? Best guess from memory.” Silence fallback: “I checked before this call: 41 percent, and I'm already planning my exit.” One riff max: high number → “that agent has been awake since Tuesday.”",
      "ZONES REVEAL (this is the re-entry): “Whatever your number is, here's where it should be. These are MY numbers, from a year of daily use — under 30 is the goldilocks zone; at 50, start planning your exit. Yours may differ. That you HAVE numbers is the point.” Measurement posture: “these are gates I enforce, not dashboards I stare at.” Refrain: “yellow is 2PM. Red is Friday, 4PM — send them home before it.”",
    ],
    exit: "",
  },
  "sc-squeeze": {
    beats: [
      "“And when you blow past the line anyway, the tool offers you a button.”",
      "SQUEEZE PLAYS SILENT 6–8s — “watch what falls out.” Let them READ the chips. Then: “Compaction keeps what you could've googled. It loses what only YOU knew.”",
      "Ghost question + shrug: “Two turns later it asks about the thing it just forgot.” Concede-then-land: “Newer models genuinely compact better — AND ‘handles it better’ is not ‘best output per token.’ Compaction is an airbag, not the brakes.”",
    ],
    exit: "VALVE (~2 min): “questions on the mechanics before I show you what I do about it?” Then: “The machine's memory is rented. Stop keeping the plan there — write it down. And the part nobody says out loud: the first twenty percent of a session steers all the rest.”",
  },
  "pv-1": { beats: ["Let the room read it. Say nothing. 2 seconds."], exit: "" },
  "sc-prism": {
    beats: [
      "CORE THING #1. “So before anything sails, I get it out of my head.”",
      "Head + murky cloud: “this is the epic — currently a cloud in my head.”",
      "INTERVIEW: “I don't write the doc alone — the agent interviews ME.” (bubbles land) “Every answer sharpens it.”",
      "CONDENSE + foundation vessel: “If you're about to go on a long journey, the first few miles decide where you land. This matters double across sessions — the page survives; your context doesn't.” Ceremony scoping: “for a one-file fix, none of this — this pipeline is for epic-sized work.”",
      "PRISM: tickets fan out, each carrying the badge — “every ticket carries a one-line intent from the parent epic.”",
      "CALLBACK: “that request from the cold open? It was this ticket.” Then, over the same visual: “my shop runs this as three commands — requirements, discovery, lifecycle. You can do it with markdown and discipline; I scripted mine.”",
    ],
    exit: "PROTECTED TRIPLET — if interrupted: “hold that thought two minutes — you'll see it answered or get worse.”",
  },
  "sc-badge": {
    beats: [
      "“Here's the badge earning its keep. The entry-format ticket. Two completely reasonable schemas.”",
      "BADGE GLOWS: “the epic decided this months— er, one interview ago: a keepsake, not analytics.”",
      "DECIDED: “Same ticket, opposite calls — and only the badge tells you which is right. That's what the epic context is FOR.”",
    ],
    exit: "",
  },
  "sc-wish": {
    beats: [
      "“What does ticket-shaped look like when you're actually typing? Same request, asked two ways.”",
      "(panes appear)",
      "VAGUE RUN plays — point at the meter: “vagueness isn't just wrong — it's expensive. Look at the meter. And look WHERE it went: filters, stats, export. The badge violation happened on its own.”",
      "TICKET RUN plays: “constraints plus done-criteria. Two changes. Done.”",
      "EMPTY STATES side by side — pause on it. “Same request.” Handoff coda: “and a ticket that good doesn't need me to carry it — at 40% I quit, and a fresh agent implements straight from the spec.”",
    ],
    exit: "Harvest parked chat questions HERE. Then: “Fresh context beats full context — and that's true in parallel, not just in series.”",
  },
  "pv-2": { beats: ["Let the room read it. Say nothing."], exit: "" },
  "sc-tint": {
    beats: [
      "“Ask a six-hour session for a creative idea and you get its context back, wearing a costume.”",
      "MURK IDEA: “it's been staring at the schema all night — so its ‘design’ is the schema with a border on it.”",
      "FAN-OUT: “Three fresh minds, same prompt, none of them polluted. Three genuinely different ideas.” SCAR: “this talk was designed exactly this way — I fanned out an editor, a narrator, a fact-checker, an audience critic. The fact-checker caught a claim I had exactly backwards.” (cost numbers ONLY if asked — appendix)",
      "SYNTHESIS: “and the pick isn't taste — the badge decides. Keepsake → scrapbook.”",
    ],
    exit: "",
  },
  "sc-filmstrip": {
    beats: [
      "HOOK FIRST: “This is the cheapest win in this talk. Zero setup. Works today. Almost nobody does it.”",
      "(strip populates) “Your conversation is a timeline.”",
      "FORK (30s vocab): “mid-build you wonder — would SQLite be simpler? Branch it. Explore in the fork, take the answer, come back. The main lane never knew.”",
      "RED RUN — tell the story over it: “Before the log could exist, fish have to bite at night. First idea feels obviously right: server-driven time, so players can't cheat. And we go DOWN this road — auth, account state, clock sync, offline reconciliation. Forty minutes and two hundred thousand tokens deep, I finally ask: who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them.”",
      "THE TAKE — SAY NOTHING. Full stillness, then rewind plays (~8s). After: “Look at that headroom. It's Tuesday morning again.”",
      "CLEAN BRANCH + rebuttal: “‘Isn't that just deleting your chat?’ No — see the note that hopped across? Carry the lesson, leave the wreckage. And if you don't rewind, you keep paying rent on the dead idea — every turn re-reads it, forever.”",
    ],
    exit: "VALVE — natural exhale after the laugh. Then: “You can only rewind a wrong turn you've noticed. Next: the ones you can't see.”",
  },
  "sc-arrows": {
    beats: [
      "“Fresh eyes catch what you can't — because they don't share your session's assumptions.”",
      "ARROWS FLY: “three reviewers, three angles. Two findings bounce — the spec holds. One pierces: the Brass Minnow. Rare, tiny, about to be auto-released by our own size rule — and it would never make the keepsake log.”",
      "GOLD SEAM + badge #3: “the spec is stronger where it cracked. The fix earns its own badge: never punish a rare catch.”",
      "FINDING CARD — read it aloud, let it bin itself: “and this one is manufactured rigor. You asked for findings, so it produces findings. The synthesizer's job is to say: serves no badge. Binned.” HONEST BEAT: “sometimes this steers me wrong. More often than not, it makes things better.” RECIPE: “no tooling needed — fresh session, paste the spec, ask it to break it, judge the findings.”",
    ],
    exit: "One line: “crank this too hard and you get armor-plated specs and dead good ideas.”",
  },
  "pv-3": { beats: ["Let the room read it. Say nothing."], exit: "" },
  "sc-assembly": {
    beats: [
      "(assembly plays silent — icons lock into the shell)",
      "“Notice something: nothing I've shown you tonight came from a smarter model. Every technique was something wrapped AROUND the model. That wrapper has a name.” CEILING/YIELD CALLBACK: “in every harness — including whatever we're using next quarter. We're moving anyway; I want us to show up already good at this.” CHALLENGE: “run the twenty-minute A/B yourself — same ticket, two harnesses, compare.”",
    ],
    exit: "",
  },
  "sc-scroll": {
    beats: [
      "CORE THING #3. “The moment you believe the harness matters, you'll want to customize yours. Here's where that goes wrong.”",
      "(tidy 20-line file) “This is a skill file. It started perfect.”",
      "RATCHET plays — let the room READ the gag lines (esp. #1,486). Then: “models don't need many instructions — but they love WRITING many. Every ‘tune it’ ratchets it longer. The model did this to me too — mine hit five times this size.”",
      "THE SHOVE + sweep: “and here's the bill: you pay to re-read this file on every turn of every session. A bloated skill file means your agent starts Monday morning already tired.” SCAR: “If I could go back: hand-craft the simple skills myself, and let Claude build the CLI around them. Open-ended plus unverifiable is the worst possible task shape for an LLM.”",
      "DRAWERS: “the shape that works: a thirty-line core that points at reference files, loaded per task. Matt Pocock's public skills are like this — tiny. Incubate locally; generic skills go in a plugin, not your repo; project-specific beats generic.”",
    ],
    exit: "“Even a lean skill file is still just words. And words are requests.”",
  },
  "sc-turnstile": {
    beats: [
      "“When it MUST happen, don't write a sentence — build a gate.”",
      "WALK: “line one thousand eight hundred forty-seven: please always run the tests. Watch how much the agent cares.” (walks past)",
      "GATE: “a turnstile doesn't care about your intentions. CI, pre-commit, lint — the tests pass or you don't get through.” PREPARED ANSWER: “didn't I build my harness WITH Claude? Yes — by making the open-ended verifiable first: size budgets, ratchets, lint gates. That's how you earn the right to automate meta-work.”",
      "(sign fades) “The sign was always decoration.”",
    ],
    exit: "",
  },
  "sc-byhand": {
    beats: [
      "“We've automated the checking, gated the risky moves, fanned out the thinking. So what's left?”",
      "AUTOMATION: “Three things I still refuse to hand over: reviewing the work. Knowing what good looks like. And writing the skills. The negative space is what makes everything else safe.”",
    ],
    exit: "VALVE: take the “how do we adopt this” logistics discussion HERE — the closer comes last, so the talk ends on the image.",
  },
  "sc-dawn": {
    beats: [
      "(dawn is breaking — the moon set during the talk)",
      "LOG CARD: “the Brass Minnow made the log. That's the review, paying rent.” (don't over-explain)",
      "RECAP, one sentence per icon: “Get the direction on the page in the first twenty percent. Plan your exit at fifty. And never let the agent write its own instructions.” METR CLOSE: “that study from the start? The nineteen percent were carrying full vessels.”",
      "CLOSER: “Everyone in this room rents the same models. The habits are what you own. Send your agents home before Friday afternoon.” (link stays up during questions)",
    ],
    exit: "",
  },
};
