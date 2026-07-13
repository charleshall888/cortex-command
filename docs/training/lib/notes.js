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
      "“Three habits. That's the whole talk.” (dock blueprint alone — three dashed posts)",
      "(labels land) Read them once, slowly, verbatim: “Get the direction on the page. Plan your exit at 50%. Write your own instructions.” Then: “Everything else tonight is one of these three. We build them in the order the mystery demands — gauge first.”",
    ],
    exit: "“So what IS that bar? Let me pour you one.”",
  },
  "sc-gauge": {
    beats: [
      "“This is the same bar, stood upright — the context window. Let me show you what six hours pours into it.” (empty tank, bar at 0)",
      "LAYERS POUR, labeled. “System prompt sediment. Your messages — the thin blue bands. And the fat grey slabs: files it read, test output. Tool output is what eats the window, not your typing.” (the bar underneath tracks the tank — same object)",
      "SWEEP PLAYS SILENT (~4s) — say nothing. Then over the frozen frame: “Every single turn, it re-reads the entire tank. You resend everything, every time. Junk in here isn't history — it's rent.”",
      "ZONES + THE DOOR: “MY numbers, from a year of daily use — under 30 is the goldilocks zone; at 50 there's a door, and I plan my exit through it. Yours may differ. That you HAVE numbers is the point. These are gates I enforce, not dashboards I stare at.” Refrain #1: “yellow is 2PM. Red is Friday, 4PM.”",
      "FAST-FORWARD past the door (bar goes red, slumped avatar appears): “and if you sail past the door without a plan… there's our friend from the cold open. Mystery solved — now the habits.”",
    ],
    exit: "",
  },
  "sc-squeeze": {
    beats: [
      "“When you blow past the line anyway, the tool offers you a button: compact. Look what's floating in the tank first — four things only I knew. No search engine has any of them.” (point at the pinned chips, read one or two)",
      "SQUEEZE PLAYS SILENT 6–8s — “watch what falls out.” The chips land in the lost pile; the stripe keeps the gist. Then: “Look at the bar — the NUMBER got better. Compaction keeps what you could've googled. It loses what only YOU knew.”",
      "PAYOFF (mini-terminal fires, the chip glows): “Two turns later: it touches the one file I said never to touch. Biting disabled game-wide — again. The thing it needed was in the pile.” Concede-then-land: “Newer models compact better, AND ‘handles it better’ is not ‘best output per token.’ Compaction is an airbag, not the brakes.”",
    ],
    exit: "“So if pushing through is bad and the airbag is lossy — what's the surgical option?”",
  },
  "sc-filmstrip": {
    beats: [
      "HOOK FIRST: “This is the cheapest win in this talk. Zero setup. Works today. Almost nobody does it.”",
      "(strip populates; load bar labels itself) “Your conversation is a timeline. And that bar underneath — that's the gauge again, lying on its side: what the next turn re-reads.”",
      "FORK (30s vocab): “mid-build you wonder — would SQLite be simpler? Branch it. Explore in the fork, take the answer, come back. The main lane never knew.”",
      "RED RUN — tell the story over it: “Before the log could exist, fish have to bite at night. First idea feels obviously right: server-driven time, so players can't cheat. And we go DOWN this road — auth, account state, clock sync, offline reconciliation. Forty minutes and two hundred thousand tokens deep, I finally ask: who are we defending against? It's a single-player fishing game. If someone wants to lie to their own fishing game about what time it is… let them.”",
      "THE TAKE — SAY NOTHING. Full stillness, then rewind plays (~8s). After: “Look at that headroom. It's Tuesday morning again.”",
      "CLEAN BRANCH + rebuttal: “‘Isn't that just deleting your chat?’ No — see the note that hopped across, and what's written on it? Carry the lesson, leave the wreckage. If you don't rewind, you keep paying rent on the dead idea — every turn re-reads it, forever.”",
    ],
    exit: "VALVE — natural exhale after the laugh (~1.5 min for questions on the mechanics).",
  },
  "pv-1": {
    beats: [
      "Let the room read the proverb. Say nothing.",
      "(post lights) One line only: “First post: watch the gauge, exit at fifty.” Bridge: “But a session that ends at 50% raises a question — where does the plan LIVE, if not in the machine's memory? It's rented. Write it down.”",
    ],
    exit: "",
  },
  "sc-prism": {
    beats: [
      "CORE HABIT #1. “The first twenty percent of a session steers all the rest. So before anything sails, I get the direction out of my head.” PRE-FRAME the triplet: “next three minutes are one continuous story — drop questions in chat, I'll take everything after the punchline.”",
      "(head + cloud) “This is the epic — currently a cloud in my head.”",
      "INTERVIEW: “I don't write the doc alone — the agent interviews ME.” (bubbles land; point at the first one) “Recognize that question? It's the one the fresh agent asked in the cold open. Every answer sharpens the doc.”",
      "CONDENSE: “If you're about to go on a long journey, the first few miles decide where you land. This matters double across sessions — the page survives; your context doesn't.” Ceremony scoping: “for a one-file fix, none of this — this pipeline is for epic-sized work.”",
      "PRISM + STAMPS (watch the intent line fly onto each ticket): “the doc splits into tickets, and every ticket carries one line of intent from the parent — a keepsake, not analytics. And the last ticket? That's the request from the cold open. It was never a one-off ask — it was a shard of a plan.” Then: “my shop runs this as three commands — requirements, discovery, lifecycle. Markdown and discipline work too.”",
      "THE FORK (the payoff): “Same ticket. Two completely reasonable schemas. Only the intent line tells you which is right — THAT's what the epic context is for.” (the analytics card dims on its own — let it)",
    ],
    exit: "PROTECTED TRIPLET — if interrupted: “hold that thought two minutes — you'll see it answered or get worse.”",
  },
  "sc-wish": {
    beats: [
      "“What does the page buy you when you're actually typing? A controlled experiment. Cold open held the ask constant and varied the context. Now: same fresh context, and only the ask differs.”",
      "PROMPTS FIRST (panes + both bars settle at 8%, identical): let the room READ the two asks. Optional checkpoint (hands or chat): “which side wins, and by how much?”",
      "WISH RUN plays — point at the bar: “vagueness isn't just wrong — it's expensive. Look at the bar climb. And look WHERE it went: filters, stats, export. It violated the intent line all by itself.”",
      "TICKET RUN plays: “constraints plus done-criteria. One file. Eighteen percent.”",
      "SCORECARD + empty states side by side — pause on it. “Same request, in spirit. Six files against one; sixty-eight percent against eighteen.” Handoff coda: “and a ticket this good doesn't need ME to carry it — at 50% I quit, and a fresh agent implements straight from the spec.”",
    ],
    exit: "Harvest parked chat questions HERE. Then: “Fresh context beats full context — and that's true in parallel, not just in series.”",
  },
  "pv-2": {
    beats: [
      "Let the room read it. Say nothing — this proverb is the next scene's title.",
      "(second post lights) “Second post: the direction lives on the page. And once it does, something new unlocks — the page can feed more agents than one.”",
    ],
    exit: "",
  },
  "sc-lines": {
    beats: [
      "“Ask a six-hour session for a creative idea and you get its context back, wearing a costume.” (murky vessel, six hours in)",
      "MURK IDEA: “it's been staring at the schema all night — so its ‘design’ is the schema with a border on it.”",
      "SET MORE LINES (beam drops three lines into three fresh vessels): “Don't reel harder on the tired one. Three fresh sessions, same prompt, same page — none of them polluted. Three genuinely different ideas, in parallel, while you do something else.” SCAR: “this talk was designed exactly this way — I fanned out an editor, a narrator, a fact-checker, an audience critic. The fact-checker caught a claim I had exactly backwards.” (cost numbers ONLY if asked — appendix)",
      "SYNTHESIS: “and the pick isn't taste — the intent line decides. Keepsake → scrapbook.”",
    ],
    exit: "“Parallel minds for ideas. Same trick works for critique — fresh eyes on the spec itself.”",
  },
  "sc-arrows": {
    beats: [
      "“Fresh eyes catch what you can't — because they don't share your session's assumptions. But hear the second half: it will ALWAYS find something. You asked for findings, so it manufactures findings. You judge.”",
      "ARROWS 1–2 FLY, cards fill: “two findings bounce — the spec already answers one, the other's out of scope. The spec holds. That's a good outcome, not a failed review.”",
      "ARROW 3 PIERCES, card fills: “this one's real. Rare-but-small gets auto-released by our own size rule — a Brass Minnow would never make the keepsake log. Our rule punishes the best catch of the night.”",
      "GOLD SEAM + new intent line: “the spec is stronger where it cracked — and the fix earns its own line: never punish a rare catch.” HONEST BEAT: “sometimes this steers me wrong. More often it makes things better.”",
      "THE MANUFACTURED ONE — read it aloud, let it bin itself: “frame-accurate input-latency compensation. For a fishing game. Serves no intent — binned.” RECIPE: “no tooling needed — fresh session, paste the spec, ask it to break it, judge the findings.”",
    ],
    exit: "One line: “crank this too hard and you get armor-plated specs and dead good ideas.”",
  },
  "pv-3": {
    beats: [
      "Let the room read it. Say nothing.",
      "(the plank draws across the posts; the third post waits, dashed) “The plank is the techniques — fork, rewind, parallel lines, fresh eyes — laid across the first two habits. One post left, and it's the one people get wrong first: your tackle is your instruction files.”",
    ],
    exit: "",
  },
  "sc-scroll": {
    beats: [
      "CORE HABIT #3. “The moment you believe the wrapper matters, you'll want to customize yours. Here's where that goes wrong.”",
      "(tidy 20-line file) “This is a skill file. It started perfect.”",
      "RATCHET plays — let the room READ the gag lines (esp. #1,486). Then: “models don't need many instructions — but they love WRITING many. Every ‘tune it’ ratchets it longer. The model did this to me too — mine hit five times this size.”",
      "THE SHOVE + sweep (the gauge callback): “and here's the bill: you pay to re-read this file on every turn of every session. A bloated skill file means your agent starts Monday morning already tired.” SCAR: “If I could go back: hand-craft the simple skills myself, and let Claude build the CLI around them. Open-ended plus unverifiable is the worst possible task shape for an LLM.”",
      "DRAWERS: “the shape that works: a thirty-line core that points at reference files, loaded per task. Matt Pocock's public skills are like this — tiny. Incubate locally; project-specific beats generic.”",
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
      "“We've gated the risky moves and fanned out the thinking. So what's left?”",
      "(the wall of chores appears — let it read for a breath)",
      "AUTOMATION: “Three things I still refuse to hand over: reviewing the work. Knowing what good looks like. And writing the instructions. The negative space is what makes everything else safe.”",
    ],
    exit: "VALVE (~2 min): take the “how do we adopt this” logistics discussion HERE — the replay and the closer come last, so the talk ends on the image.",
  },
  "sc-replay": {
    beats: [
      "(title alone — let the dread land) “It's Friday again. Four o'clock again. Same model. Watch what's different.”",
      "(one pane, bar climbs to 91% — exactly where the cold open left it) “There's my agent, six hours deep, and a new request just arrived. Last time, this went badly.”",
      "RUN A plays: “this time I don't push through. Write the handoff ticket. Stop.” (chip 1 ticks) “The direction is on the page now — the session can die.”",
      "THE SWAP — say nothing while the bar falls 91 → 8. Then: “fresh agent, four minutes later, reads the ticket, ships the small right change. Sixteen percent at the finish.” (chips 2–3 tick)",
      "KICKER + the dock completes: “Nothing here needed a better model. Every move you just watched was a habit — in every harness, including whatever we're using next quarter. We're moving anyway; I want us to show up already good at this. Run the twenty-minute A/B yourself.”",
    ],
    exit: "",
  },
  "sc-dawn": {
    beats: [
      "(dawn is breaking — the moon set during the talk; the dock stands complete)",
      "LOG CARD: “the Brass Minnow made the log. That's the review, paying rent.” (don't over-explain)",
      "RECAP, one sentence per icon, verbatim: “Get the direction on the page. Plan your exit at fifty percent. Write your own instructions.” METR CLOSE: “that study from the start? The nineteen percent were carrying full vessels.”",
      "CLOSER: “Everyone in this room rents the same models. The habits are what you own. Send your agents home before Friday afternoon.” (link stays up during questions)",
    ],
    exit: "",
  },
};
