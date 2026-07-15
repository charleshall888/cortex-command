/* Deck engine: keyboard-driven present mode.
   → / space  advance one beat (then next scene)
   ←          previous scene
   b          blank screen (for valves and Q&A)
   Home/End   first / last scene */

(function () {
  const sections = [...document.querySelectorAll(".scene, .card")];
  const hud = document.getElementById("hud");
  const blank = document.getElementById("blank");
  let idx = 0;
  let beat = 0;

  /* ---------- scene hooks ---------- */

  const state = {};
  const chains = {};

  /* serialize a scene's async beats: each starts only after the previous
     finishes, so rapid key presses (or deep links) can't interleave */
  function chain(key, fn) {
    chains[key] = (chains[key] || Promise.resolve()).then(fn).catch(() => {});
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  /* ---------- the arrival + the lobby idle ----------
     The cast plays once, on a cold load of scene 1 only — deep links and
     re-visits land on the finished card. The ripple and the moon-glint are
     scheduled with spawn-time jitter (never randomized per-frame), so the
     idle has no discoverable loop; each timer kills itself the moment the
     title card is no longer what's on screen. */

  const REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  let introPending = !/^#\d/.test(location.hash || "");
  let plinkTimer = null;
  let glintTimer = null;

  function lobbyVisible() {
    const sec = document.getElementById("sc-cold-open");
    return !!sec && sec.classList.contains("active") && !sec.classList.contains("staged");
  }

  /* re-trigger a one-shot CSS animation */
  function replay(el, cls) {
    if (!el) return;
    el.classList.remove(cls);
    void el.getBoundingClientRect();
    el.classList.add(cls);
  }

  /* something's down there — long gaps, the occasional quick double */
  function schedulePlink(delay) {
    clearTimeout(plinkTimer);
    plinkTimer = setTimeout(() => {
      if (!lobbyVisible()) return;
      replay(document.querySelector("#sc-cold-open .title-card .dock"), "plink");
      const r = Math.random();
      schedulePlink(r < 0.16 ? 2400 : 6500 + r * 9000 + (r > 0.85 ? 8000 : 0));
    }, delay);
  }

  /* moonlight crosses the title — weather, not a loop */
  function scheduleGlint(delay) {
    clearTimeout(glintTimer);
    glintTimer = setTimeout(() => {
      if (!lobbyVisible()) return;
      replay(document.querySelector("#sc-cold-open .title-card h1"), "glint");
      scheduleGlint(75000 + Math.random() * 45000);
    }, delay);
  }

  const LEFT_SCRIPT = [
    { t: "user", text: "add an empty-state to the catch log" },
    { t: "ask", text: "One question — should the empty log invite the first cast, or stay blank?", pause: 300 },
    { t: "user", text: "invite the first cast" },
    { t: "tool", text: "Read catch_log_view.js" },
    { t: "add", lines: ["+ if (entries.length === 0)", '+   return EmptyState("No catches yet.", "The night is young.")'] },
    { t: "done", text: "✓ empty state renders · tests pass" },
  ];

  const RIGHT_SCRIPT = [
    { t: "user", text: "add an empty-state to the catch log" },
    { t: "agent", text: "Great idea! Refactoring the logging pipeline for empty states…", pause: 300 },
    { t: "tool", text: "Edit catch_odds.js" },
    { t: "del", lines: ["- const BASE_ODDS = 0.12"] },
    { t: "add", lines: ["+ const BASE_ODDS = 0.0   // empty state"] },
    { t: "warn", text: "✗ modified catch_odds.js — biting disabled game-wide" },
  ];

  /* the death spiral: each failed attempt AND each correction stays in the
     window, so every lap starts heavier — and the third attempt is the
     first one again, verifiable by eye */
  const SPIRAL_A = [
    { t: "user", text: "bug: escaped fish are showing up in the catch log" },
    { t: "agent", text: "Filtering escapes out of the log view.", pause: 250 },
    { t: "tool", text: "Edit log_view.js" },
    { t: "add", lines: ["+ if (entry.escaped) skip(entry)"] },
    { t: "warn", text: "✗ still logged — the flip-through page renders them" },
    { t: "user", text: "no — fix the source, not the view" },
  ];
  const SPIRAL_B = [
    { t: "agent", text: "Right — removing escape events at the source.", pause: 250 },
    { t: "tool", text: "Edit catch_events.js" },
    { t: "del", lines: ['- emit("escape", fish)'] },
    { t: "warn", text: "✗ tackle stats broke — they count escapes" },
    { t: "user", text: "NO — put the events back" },
  ];
  const SPIRAL_C = [
    { t: "agent", text: "Restoring events; filtering the view instead.", pause: 250 },
    { t: "add", lines: ["+ if (entry.escaped) skip(entry)"], snap: true },
    { t: "warn", text: "✗ turn 79 · the same patch as turn 71 · bug still alive", snap: true },
  ];

  /* the finale: Friday run right — the red pane is a freeze-frame of the
     cold open, then interview → tickets → three parallel fresh windows */
  const FIN_RED_FREEZE = [
    { t: "user", text: "add an empty-state to the catch log" },
    { t: "tool", text: "Edit catch_odds.js" },
    { t: "del", text: "- const BASE_ODDS = 0.12" },
    { t: "add", text: "+ const BASE_ODDS = 0.0   // empty state" },
    { t: "warn", text: "✗ biting disabled game-wide" },
  ];
  const FIN_INTERVIEW = [
    { t: "user", text: "/discovery make Monday's playtest real" },
    { t: "ask", text: "quick scope — what should a player wake up to?", pause: 250 },
    { t: "user", text: "a catch in the log — and fish actually biting" },
    { t: "tool", text: "Research: catch log · biting odds · release rules" },
    { t: "agent", text: "found it — biting's broken; that's the first ticket" },
    { t: "tool", text: "Write first-night-epic.md · split into 3 tickets" },
    { t: "done", text: "✓ epic + 3 tickets · every lesson attached" },
  ];
  const FIN_A = [
    { t: "user", text: "ticket: restore night biting" },
    { t: "agent", text: "night = device clock (single-player)" },
    { t: "del", lines: ["- const BASE_ODDS = 0.0"] },
    { t: "add", lines: ["+ const BASE_ODDS = 0.12"] },
    { t: "tool", text: "Run night_sim --offline" },
    { t: "done", text: "✓ fish bite after dark · 1 file" },
  ];
  const FIN_B = [
    { t: "user", text: "ticket: flip-through log page" },
    { t: "tool", text: "Edit log_view.js" },
    { t: "add", lines: ["+ page.flip(direction)"] },
    { t: "warn", text: "✗ gate: run the tests first" },
    { t: "tool", text: "Run tests --offline" },
    { t: "done", text: "✓ gate open · 2 files" },
  ];
  const FIN_C = [
    { t: "user", text: "ticket: spare rare catches" },
    { t: "tool", text: "Edit release_rules.js" },
    { t: "add", lines: ["+ if (fish.isRare) keep(fish)"] },
    { t: "tool", text: "Run tests --offline" },
    { t: "done", text: "✓ a Brass Minnow would be kept", pause: 2400 },
  ];

  /* the exhibit stays in-domain: every line is believable review-skill
     content — the comedy is the self-contradiction, not meta-jokes */
  const SCROLL_START = [
    { n: "#1", text: "Review the spec from an adversarial angle." },
    { n: "#7", text: "Quote the line you’re challenging — no paraphrase." },
    { n: "#12", text: "If the spec already answers it, drop the finding." },
  ];
  const SCROLL_GAGS = [
    { n: "#348", text: "Always begin findings with a severity emoji." },
    { n: "#2,970", text: "NEVER use the word “delve” in a finding." },
    { n: "#4,401", text: "No emoji in security findings (overrides #348).", gag: true },
    { n: "#5,994", text: "If two rules conflict, the higher line number wins.", gag: true },
  ];

  function skillLine(l) {
    return `<div><span class="lnum">${l.n}</span><span class="${l.gag ? "gag" : ""}">${l.text}</span></div>`;
  }

  const GAUGE_BASE = [
    { kind: "system", pct: 6, label: "system prompt" },
    { kind: "chat", pct: 8, label: "chat — yours and its" },
    { kind: "tool", pct: 18, label: "files it read" },
    { kind: "chat", pct: 4 },
    { kind: "tool", pct: 8, label: "test output" },
  ]; // 44% — amber, the door in sight
  const GAUGE_LATER = [
    { kind: "tool", pct: 12, label: "more files" },
    { kind: "tool", pct: 10, label: "more test output" },
  ]; // → 66% — past the door, into the red

  function setRail(sec, n) {
    [1, 2, 3].forEach((i) => {
      const el = sec.querySelector("#pipe-" + i);
      if (el) el.classList.toggle("lit", i === n);
    });
  }

  const hooks = {
    "sc-cold-open": (sec, b) => {
      if (b === 0) {
        sec.classList.remove("staged", "spotlight");
        if (introPending) {
          sec.classList.add("arrive"); // the cast — first cold show only
          introPending = false;
          if (!REDUCED) {
            schedulePlink(9200); // first plink waits for the arrival to finish
            scheduleGlint(6100); // the surfacing complete, moonlight passes once
          }
        } else {
          sec.classList.remove("arrive");
          if (!REDUCED) {
            schedulePlink(4500);
            scheduleGlint(30000);
          }
        }
        if (state.termLeft) state.termLeft.clear();
        if (state.termRight) state.termRight.clear();
        if (state.cbLeft) state.cbLeft.set(0, { ms: 0 });
        if (state.cbRight) state.cbRight.set(0, { ms: 0 });
      }
      if (b === 1) {
        sec.classList.add("staged");
        if (!state.termLeft) {
          state.termLeft = makeTerminal(document.getElementById("term-left"), { title: "fresh session · 4:00 PM" });
          state.termRight = makeTerminal(document.getElementById("term-right"), { title: "six-hour session · 4:00 PM" });
          state.cbLeft = makeContextBar(document.getElementById("cbar-left"), { h: 12 });
          state.cbRight = makeContextBar(document.getElementById("cbar-right"), { h: 12 });
        }
        state.cbLeft.set(8, { ms: 900 });
        state.cbRight.set(91, { ms: 2600 }); // six hours, compressed into one sweep
      }
      if (b === 2) {
        state.termLeft.play(LEFT_SCRIPT);
        state.cbLeft.set(13, { ms: 11000 });
      }
      if (b === 3) state.termRight.play(RIGHT_SCRIPT); // the bar parks at 91 — the finale echoes it
      if (b === 4) sec.classList.add("spotlight"); // dim everything but the two bars
    },

    "sc-blueprint": (sec, b) => {
      if (b === 0) state.bpDock = buildDock(document.getElementById("blueprint-dock"), { sketch: true });
    },

    "sc-gauge": (sec, b) => {
      if (b === 0) {
        const slot = document.getElementById("cbar-gauge");
        if (!state.cbGauge) state.cbGauge = makeContextBar(slot, { h: 26, big: true, label: "" });
        if (!state.vGauge)
          state.vGauge = makeVessel(document.getElementById("vessel-gauge"), {
            onLevel: (pct) => state.cbGauge.set(pct, { ms: 700 }),
          });
        state.vGauge.reset();
        state.cbGauge.set(0, { ms: 0 });
        state.cbGauge.el.classList.remove("bands-strong");
      }
      if (b === 1) chain("gauge", () => state.vGauge.pour(GAUGE_BASE));
      if (b === 2) chain("gauge", () => state.vGauge.sweep()); // plays silent; caption lands after
      if (b === 3) {
        chain("gauge", async () => {
          state.vGauge.zones();
          state.cbGauge.el.classList.add("bands-strong");
        });
      }
      if (b === 4)
        chain("gauge", async () => {
          await state.vGauge.pour(GAUGE_LATER);
          state.cbGauge.flash();
        });
    },

    "sc-squeeze": (sec, b) => {
      if (b === 0) {
        if (!state.vSqueeze) state.vSqueeze = makeVessel(document.getElementById("vessel-squeeze"));
        if (!state.cbSqueeze) state.cbSqueeze = makeContextBar(document.getElementById("cbar-squeeze"), { h: 26, big: true, label: "" });
        state.vSqueeze.reset();
        state.vSqueeze.setFill([
          { kind: "system", pct: 8 },
          { kind: "chat", pct: 18 },
          { kind: "tool", pct: 26 },
          { kind: "chat", pct: 10 },
          { kind: "tool", pct: 20 },
          { kind: "tool", pct: 13 },
        ]); // 95% — the moment the tool offers you the button
        state.vSqueeze.pinChips([
          "DON'T touch catch_odds.js",
          "FishManager → CatchService",
          "empty state invites first cast",
          "tests hang without --offline",
        ]);
        state.cbSqueeze.set(95, { ms: 800 });
      }
      if (b === 1)
        chain("squeeze", async () => {
          state.cbSqueeze.set(5, { ms: 2600 }); // the number improves; the mind got worse
          await state.vSqueeze.squeeze({ stripeLabel: 'kept: "building a fishing game"' });
        });
      if (b === 2)
        chain("squeeze", async () => {
          await sleep(2200); // the mini-term lines land first
          const chip = state.vSqueeze.box.querySelector(".chip");
          if (chip) chip.classList.add("needed");
        });
    },

    /* one lap per keypress: each failed attempt + your correction lands as
       a step in the frame — the staircase descends and reddens; the bar
       climbs the whole time */
    "sc-noloop": (sec, b) => {
      const lap = (i) => document.getElementById("lap-" + i);
      if (b === 0) {
        sec.classList.remove("spotlight");
        chains["noloop"] = Promise.resolve();
        if (!state.termLoop) {
          state.termLoop = makeTerminal(document.getElementById("term-noloop"), { title: "same session · 3:00 PM · turn 71" });
          state.cbLoop = makeContextBar(document.getElementById("cbar-noloop"), { h: 12 });
        }
        state.termLoop.clear();
        [1, 2, 3].forEach((i) => lap(i).classList.remove("on"));
        state.cbLoop.set(58, { ms: 600 });
      }
      if (b === 1)
        chain("noloop", async () => {
          await state.termLoop.play(SPIRAL_A);
          lap(1).classList.add("on");
          state.cbLoop.set(67, { ms: 800 });
        });
      if (b === 2)
        chain("noloop", async () => {
          await state.termLoop.play(SPIRAL_B, { append: true });
          lap(2).classList.add("on");
          state.cbLoop.set(78, { ms: 800 });
        });
      if (b === 3)
        chain("noloop", async () => {
          await state.termLoop.play(SPIRAL_C, { append: true }); // the relapse snaps in — no crawl
          lap(3).classList.add("on");
          state.cbLoop.set(89, { ms: 800 });
        });
      if (b === 4) sec.classList.add("spotlight");
    },

    "sc-filmstrip": (sec, b) => {
      if (b === 0) {
        if (!state.film) state.film = makeFilmstrip(document.getElementById("filmstrip"));
        chains["film"] = Promise.resolve();
        state.film.reset();
      }
      if (b === 1) chain("film", () => state.film.populate());
      if (b === 2) chain("film", () => state.film.fork());
      if (b === 3) chain("film", () => state.film.badRun());
      if (b === 4) chain("film", () => state.film.rewind()); // the unbroken take — plays silent
      if (b === 5) chain("film", () => state.film.cleanBranch());
    },

    "pv-1": (sec, b) => {
      if (b === 0) state.wp1 = buildDock(document.getElementById("wp-dock-1"), { sketch: true });
      if (b === 1) state.wp1.posts.window.classList.add("lit");
    },
    "pv-2": (sec, b) => {
      if (b === 0) state.wp2 = buildDock(document.getElementById("wp-dock-2"), { sketch: true, lit: ["window"] });
      if (b === 1) state.wp2.posts.spawn.classList.add("lit");
    },
    "pv-3": (sec, b) => {
      if (b === 0) state.wp3 = buildDock(document.getElementById("wp-dock-3"), { sketch: true, lit: ["window", "spawn"] });
      if (b === 1) state.wp3.posts.clean.classList.add("lit"); // the plank waits for Friday
    },

    "sc-prism": (sec, b) => {
      const cloud = sec.querySelector(".cloud");
      const bubbles = [...sec.querySelectorAll(".qbubble")];
      const tickets = [...sec.querySelectorAll(".prism-tickets .ticket")];
      if (b === 0) {
        cloud.classList.remove("sharp", "condensed");
        bubbles.forEach((q) => q.classList.remove("on"));
        tickets.forEach((t) => t.classList.remove("on"));
        sec.querySelectorAll(".prism-tickets .badge-clip").forEach((c) => c.classList.remove("stamped"));
        sec.querySelector(".ticket.callback").classList.remove("lit");
        sec.querySelector(".prism-mid .doc").classList.remove("on");
        sec.classList.remove("past-top", "past-mid", "handoff-mode");
        setRail(sec, 1);
      }
      if (b === 2) {
        bubbles.forEach((q, i) => setTimeout(() => q.classList.add("on"), 300 + i * 900));
        setTimeout(() => cloud.classList.add("sharp"), 1400);
      }
      if (b === 3) {
        cloud.classList.add("condensed");
        sec.classList.add("past-top");
        sec.querySelector(".prism-mid .doc").classList.add("on");
        setRail(sec, 2);
      }
      if (b === 4) {
        sec.classList.add("past-mid");
        tickets.forEach((t) => t.classList.add("on"));
        stampTickets(sec);
        setTimeout(() => sec.querySelector(".ticket.callback").classList.add("lit"), 2200);
      }
      if (b === 5) {
        sec.classList.add("handoff-mode");
        setRail(sec, 3);
      }
    },

    /* the economics as ONE picture: the gauge laid along a clock — a heavy
       ochre wedge (cliffs = auto-compacts, area = tokens re-read) vs three
       blue slivers sharing the same origin. Widgets became annotations. */
    "sc-lines": (sec, b) => {
      const g = (cls) => document.querySelector("#econ-svg ." + cls);
      if (b === 0) {
        buildEcon();
        chains["econ"] = Promise.resolve();
      }
      if (b === 1)
        chain("econ", async () => {
          g("eg-clip-solo").style.width = "284px"; // the climb to the first ceiling — silent
          await sleep(4700);
        });
      if (b === 2)
        chain("econ", async () => {
          const clip = g("eg-clip-solo");
          clip.style.transition = "width 5s cubic-bezier(0.4, 0, 0.6, 1)";
          clip.style.width = "1000px"; // sawtooth to the end, one motion
          setTimeout(() => g("eg-cliff1").classList.add("on"), 500);
          setTimeout(() => g("eg-cliff2").classList.add("on"), 3000);
          setTimeout(() => g("eg-done").classList.add("on"), 4600);
          await sleep(5200);
        });
      if (b === 3) chain("econ", async () => g("eg-debt").classList.add("on"));
      if (b === 4)
        chain("econ", async () => {
          g("eg-trio").classList.add("on");
          g("eg-clip-trio").style.width = "355px"; // the chain draws in true time order — silent
          setTimeout(() => g("eg-dep").classList.add("on"), 1700); // as the clock passes the unblock
          setTimeout(() => g("eg-bills").classList.add("on"), 3800); // both bills pop together
          await sleep(4000);
        });
      /* beat 5: the verdict line is data-beat markup */
    },

    /* one state change per keypress: the doc's move to the target stand is
       its own slow beat, and each finding lands (arrow, then card, then
       stamp) on its own advance — pacing the presenter can narrate */
    "sc-arrows": (sec, b) => {
      const card = (id, delay) => setTimeout(() => document.getElementById(id).classList.add("on"), delay);
      const stamp = (id, delay) => setTimeout(() => document.getElementById(id).classList.add("stamped"), delay);
      if (b === 0) {
        buildArrows();
        sec.classList.remove("spec-docked");
        ["fcard-1", "fcard-2", "fcard-3"].forEach((id) => document.getElementById(id).classList.remove("on", "stamped"));
        sec.querySelector(".finding-card").classList.remove("binned");
      }
      if (b === 2) sec.classList.add("spec-docked"); // one slow readable move — narrate over it
      if (b === 3) {
        flyArrow("a1", 575, 160, 14, true, 900);
        card("fcard-1", 1000);
        stamp("fcard-1", 2000);
      }
      if (b === 4) {
        flyArrow("a2", 572, 205, -4, true, 900);
        card("fcard-2", 1000);
        stamp("fcard-2", 2000);
      }
      if (b === 5) {
        flyArrow("a3", 585, 270, -18, false, 900);
        setTimeout(() => document.querySelector("#arrows-svg .crack").classList.add("show"), 1000);
        card("fcard-3", 1100);
        stamp("fcard-3", 2100);
      }
      if (b === 6) document.querySelector("#arrows-svg .crack").classList.add("gold");
      if (b === 7) {
        const fc = sec.querySelector(".finding-card");
        fc.classList.remove("binned");
        setTimeout(() => fc.classList.add("binned"), 3600); // room to read it aloud first
      }
    },

    "sc-scroll": (sec, b) => {
      const body = document.getElementById("skill-body");
      const count = document.getElementById("line-count");
      const thumb = document.getElementById("scroll-thumb");
      if (b === 0) {
        body.innerHTML = SCROLL_START.map(skillLine).join("");
        count.textContent = "20 lines";
        thumb.style.height = "82%";
        document.getElementById("tune-col").innerHTML = "";
        sec.querySelector(".drawers-block").classList.remove("on");
      }
      if (b === 2)
        chain("scroll", async () => {
          const tunes = ["tune it", "be stricter about evidence", "add the edge cases", "catch perf issues too"];
          tunes.forEach((t, i) =>
            setTimeout(() => {
              const el = document.createElement("span");
              el.className = "tune-bubble";
              el.textContent = t;
              document.getElementById("tune-col").appendChild(el);
              requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("on")));
            }, i * 800)
          );
          thumb.style.height = "2%"; // 20 lines of 6,000 — a sliver
          const STEPS = 80;
          const D = 3800;
          let gagIdx = 0;
          for (let step = 1; step <= STEPS; step++) {
            await sleep(D / STEPS);
            const p = step / STEPS;
            const n = Math.round(20 + (6000 - 20) * p * p);
            count.textContent = n.toLocaleString() + " lines";
            const due = Math.min(SCROLL_GAGS.length, Math.floor(p * (SCROLL_GAGS.length + 0.99)));
            while (gagIdx < due) {
              body.innerHTML += skillLine(SCROLL_GAGS[gagIdx]);
              while (body.children.length > 5) body.firstChild.remove();
              gagIdx++;
            }
          }
        });
      /* the rent beat: the whole 6,000-line file stays on screen and rides
         in the window — the vessel fills and the scan re-reads it every turn */
      if (b === 3)
        chain("scroll", async () => {
          if (!state.vSkill) state.vSkill = makeVessel(document.getElementById("vessel-skill"), { scale: 0.8 });
          state.vSkill.reset();
          await sleep(300);
          state.vSkill.setFill([
            { kind: "system", pct: 8 },
            { kind: "tool", pct: 20 },
            { kind: "chat", pct: 8 },
            { kind: "tool", pct: 12 },
          ]);
          await state.vSkill.sweep({ duration: 2600 });
        });
      if (b === 4) {
        sec.querySelector(".drawers-block").classList.add("on");
        if (!state.vDrawers) state.vDrawers = makeVessel(document.getElementById("vessel-drawers"), { scale: 0.5 });
        state.vDrawers.reset();
        state.vDrawers.setFill([
          { kind: "spec", pct: 8 },
          { kind: "chat", pct: 7 },
        ]);
      }
    },

    /* the shared tackle box (the object pv-3 names but never draws): your lean
       skill is the lure; you prove it (a fish, b1); the villain staples it onto
       every rod, even one that never casts (b2, forced/red); the fix is the box
       — nothing goes in till it's landed a fish (b3); a crewmate lifts it out by
       choice (b4). No bars — prove-first and opt-in are one house rule. */
    "sc-tackle": (sec, b) => {
      const g = (cls) => document.querySelector("#tackle-svg ." + cls);
      const st = document.getElementById("tackle-state");
      const setState = (t, cls) => {
        if (!st) return;
        st.textContent = t;
        st.classList.remove("forced-state", "optin-state");
        if (cls) st.classList.add(cls);
      };
      if (b === 0) {
        buildTackle();
        sec.classList.remove("forced");
        setState("rigged on my own line · committed to nothing yet");
      }
      if (b === 1) {
        g("tk-fish").classList.add("on");
        setState("landed a fish · proven on my own line");
      }
      if (b === 2) {
        sec.classList.add("forced");
        g("tk-clamp").classList.add("on"); // stapled onto every rod, even the one that never casts
        setState("forced onto every rod — even the ones that never cast", "forced-state");
      }
      if (b === 3) {
        sec.classList.remove("forced");
        g("tk-clamp").classList.remove("on");
        g("tk-youlure").classList.add("gone"); // your proven lure drops into the box
        g("tk-inbox").classList.add("on");
        setState("dropped in the shared box · nothing forced", "optin-state");
      }
      if (b === 4) {
        g("tk-take").classList.add("on"); // a crewmate lifts it by choice
        setState("taken by the one who wanted it · every other line stays clean", "optin-state");
      }
      // b5: the verdict is data-beat markup
    },

    "sc-finale": (sec, b) => {
      if (b === 0) {
        sec.classList.remove("f1", "f2", "f3", "f4", "f5");
        if (!state.finRed) {
          state.finRed = makeTerminal(document.getElementById("term-fin-red"), { title: "six-hour session · 4:00 PM" });
          state.finInt = makeTerminal(document.getElementById("term-fin-int"), { title: "fresh session · 4:05 PM · discovery" });
          state.finT = ["a", "b", "c"].map((k) =>
            makeTerminal(document.getElementById("term-fin-" + k), { title: "fresh session · 4:19 PM" })
          );
          state.cbFinRed = makeContextBar(document.getElementById("cbar-fin-red"), { h: 12 });
          state.cbFinInt = makeContextBar(document.getElementById("cbar-fin-int"), { h: 12 });
          state.cbFinT = ["a", "b", "c"].map((k) => makeContextBar(document.getElementById("cbar-fin-" + k), { h: 10 }));
        }
        prefill(state.finRed, FIN_RED_FREEZE); // a freeze-frame, not a rerun
        state.finInt.clear();
        state.finT.forEach((t) => t.clear());
        [state.cbFinInt, ...state.cbFinT].forEach((cb) => cb.set(0, { ms: 0 }));
        sec.querySelectorAll(".ticket-intent").forEach((t) => t.classList.remove("stamped"));
        sec.querySelectorAll(".finale-trio .badge-clip").forEach((c) => c.classList.remove("stamped"));
        state.cbFinRed.set(91, { ms: 1800 }); // the last red sweep of the night — plays silent
      }
      if (b === 1)
        chain("fin", async () => {
          sec.classList.add("f1"); // the red pane folds: retired
          await sleep(900);
          state.cbFinInt.set(7, { ms: 600 });
          state.cbFinInt.set(12, { ms: 9000 });
          await state.finInt.play(FIN_INTERVIEW);
        });
      if (b === 2)
        chain("fin", async () => {
          sec.classList.add("f2"); // the interview folds; the page stands
          await sleep(700);
          flyIntentLines(sec); // three lessons, each paid for by a dead session — silent
        });
      if (b === 3)
        chain("fin", async () => {
          sec.classList.add("f3");
          state.cbFinT[0].set(14, { ms: 8000 });
          state.cbFinT[1].set(18, { ms: 9500 });
          state.cbFinT[2].set(11, { ms: 9000 });
          const runs = [state.finT[0].play(FIN_A)];
          await sleep(800);
          runs.push(state.finT[1].play(FIN_B));
          await sleep(800);
          runs.push(state.finT[2].play(FIN_C));
          await Promise.all(runs);
        });
      if (b === 4) sec.classList.add("f4"); // triple fold — silent; results land via data-beat
      if (b === 5) {
        sec.classList.add("f5");
        state.wpFinal = buildDock(document.getElementById("wp-dock-final"), {
          lit: ["window", "spawn", "clean"],
          plank: true,
        });
      }
    },

    "sc-dawn": (sec, b) => {
      if (b === 0) sec.classList.remove("tug");
      if (b === 1) sec.classList.add("tug"); // the line answers as the first page lands
    },
  };

  /* ---------- scene-specific builders ---------- */

  const NS = "http://www.w3.org/2000/svg";

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  }

  /* write finished terminal lines instantly — a freeze-frame */
  function prefill(term, lines) {
    const body = term.el.querySelector(".term-body");
    body.innerHTML = lines.map((s) => `<div class="term-line ${s.t}">${s.text}</div>`).join("");
  }

  /* the dock diagram: three posts = the three pillars (left → right:
     window · spawn · clean — teaching order IS retell order now), the
     plank = the pipeline, drawn only when Friday runs end-to-end. */
  function buildDock(container, { sketch = false, lit = [], plank = false } = {}) {
    container.innerHTML = "";
    const svg = el("svg", { viewBox: "0 0 640 210", class: "dock-diagram" });
    container.appendChild(svg);
    el("line", { class: "bp-water", x1: 0, y1: 158, x2: 640, y2: 158 }, svg);
    const posts = {};
    const XS = { window: 101, spawn: 315, clean: 529 };
    for (const [key, x] of Object.entries(XS)) {
      posts[key] = el("rect", { class: "bp-post" + (sketch ? " sketch" : ""), x, y: 84, width: 10, height: 74 }, svg);
      if (lit.includes(key)) posts[key].classList.add("lit");
    }
    const plankEl = el("rect", { class: "bp-plank" + (sketch ? " sketch" : ""), x: 70, y: 74, width: 500, height: 9 }, svg);
    if (plank) plankEl.classList.add("drawn");
    return { svg, posts, plank: plankEl };
  }

  /* one intent line flies from a source chip to a target — the visual verb
     for "the page carries the lesson forward" */
  function flyIntent(fromEl, toEl, onLand) {
    const from = fromEl.getBoundingClientRect();
    const to = toEl.getBoundingClientRect();
    const ghost = fromEl.cloneNode(true);
    ghost.className = "doc-intent mono intent-ghost";
    ghost.style.left = from.left + "px";
    ghost.style.top = from.top + "px";
    document.body.appendChild(ghost);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        ghost.style.transform = `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(0.12)`;
        ghost.style.opacity = "0.2";
      })
    );
    setTimeout(() => {
      ghost.remove();
      if (onLand) onLand();
    }, 560);
  }

  /* the parent epic's one intent line stamps itself onto every ticket */
  function stampTickets(sec) {
    const intent = sec.querySelector(".prism-mid .doc-intent");
    const clips = [...sec.querySelectorAll(".prism-tickets .ticket .badge-clip")];
    clips.forEach((clip, i) => {
      setTimeout(() => flyIntent(intent, clip, () => clip.classList.add("stamped")), 400 + i * 350);
    });
  }

  /* the finale's three intent lines each fly to their own ticket — 1:1 */
  function flyIntentLines(sec) {
    [1, 2, 3].forEach((i) => {
      setTimeout(() => {
        const from = document.getElementById("fin-il-" + i);
        const to = document.getElementById("fin-ti-" + i);
        flyIntent(from, to, () => {
          to.classList.add("stamped");
          to.closest(".ticket").querySelector(".badge-clip").classList.add("stamped");
        });
      }, 300 + (i - 1) * 350);
    });
  }

  function flyArrow(cls, tx, ty, rot, bounce, ms = 550) {
    const a = document.querySelector(`#arrows-svg .arrow.${cls}`);
    a.style.transition = `transform ${ms}ms cubic-bezier(0.3, 0, 0.7, 1)`;
    a.style.transform = `translate(${tx}px, ${ty}px) rotate(${rot}deg)`;
    if (bounce)
      setTimeout(() => {
        a.style.transition = "transform 0.9s ease, opacity 0.9s ease";
        a.style.transform = `translate(${tx - 90}px, ${ty + 70}px) rotate(${rot - 38}deg)`;
        a.style.opacity = "0.3";
      }, ms + 80);
  }

  /* scene 10: one gauge along one clock. x: 0–5.5h → 90–1130; solo lane
     pct → y over baseline 250; trio lanes get their own small baselines. */
  function buildEcon() {
    const svg = document.getElementById("econ-svg");
    svg.innerHTML = "";
    const X = (h) => 90 + h * 189.09;
    const Y = (pct) => 250 - 1.9 * pct;
    const txt = (x, y, s, attrs = {}, parent = svg) => {
      const t = el("text", { x, y, ...attrs }, parent);
      t.textContent = s;
      return t;
    };

    /* frame: axis, zone rules, lane label — visible from beat 0 */
    const frame = el("g", { class: "eg eg-frame on" }, svg);
    const axis = el("g", { class: "eg-axis" }, frame);
    el("line", { x1: 90, y1: 498, x2: 1130, y2: 498 }, axis);
    for (let h = 1; h <= 5; h++) {
      el("line", { x1: X(h), y1: 494, x2: X(h), y2: 502 }, axis);
      txt(X(h), 516, h + "h", { "text-anchor": "middle" }, axis);
    }
    txt(1130, 516, "elapsed", { "text-anchor": "end" }, axis);
    el("line", { class: "eg-rule", x1: 90, y1: Y(50), x2: 1130, y2: Y(50) }, frame);
    el("line", { class: "eg-rule", x1: 90, y1: Y(97), x2: 1130, y2: Y(97) }, frame);
    txt(94, Y(50) - 6, "the door · 50%", { class: "eg-rule-label" }, frame);
    txt(94, Y(97) - 6, "full — auto-compact", { class: "eg-rule-label" }, frame);
    const door = el("g", { class: "eg-door" }, frame);
    el("rect", { x: 1098, y: Y(50) - 17, width: 12, height: 17, rx: 1.5 }, door);
    txt(90, 45, "one window · the whole catch-log epic", { class: "eg-lane-label" }, frame);

    /* the wedge, revealed by a clock-driven clip */
    const clip = el("clipPath", { id: "econ-clip-solo" }, svg);
    el("rect", { class: "eg-clip-solo", x: 90, y: 36, width: 0, height: 230 }, clip);
    const wedge =
      `M ${X(0)} ${Y(8)} L ${X(1.5)} ${Y(95)} L ${X(1.5)} ${Y(5)} L ${X(3.3)} ${Y(96)}` +
      ` L ${X(3.3)} ${Y(5)} L ${X(5.25)} ${Y(88)} L ${X(5.25)} 250 L ${X(0)} 250 Z`;
    el("path", { class: "eg-solo-fill", d: wedge, "clip-path": "url(#econ-clip-solo)" }, svg);

    /* annotations that land as the wedge passes them */
    const cliff1 = el("g", { class: "eg eg-cliff1" }, svg);
    txt(X(1.5) + 10, 58, "auto-compact ×1 — the squeeze, again", {}, cliff1);
    const cliff2 = el("g", { class: "eg eg-cliff2" }, svg);
    txt(X(3.3) + 10, 58, "auto-compact ×2", {}, cliff2);
    const done = el("g", { class: "eg eg-done" }, svg);
    txt(1130, 95, "done · 5h 15m", { "text-anchor": "end" }, done);

    const debt = el("g", { class: "eg eg-debt" }, svg);
    for (const h of [1.3, 3.1, 5.0]) txt(X(h), 120, "✗", { class: "xmark", "text-anchor": "middle" }, debt);
    txt(X(3.1), 145, "written deep in the red — and it ships", { "text-anchor": "middle" }, debt);

    /* the trio as a dependency chain: catch events runs first; its finish
       unblocks the other two, which run in parallel — the shared clip is
       the clock, so the stagger reveals in true time order */
    const trio = el("g", { class: "eg eg-trio" }, svg);
    txt(90, 326, "three fresh windows · planned last scene · one first, then two in parallel", { class: "eg-lane-label" }, trio);
    const tclip = el("clipPath", { id: "econ-clip-trio" }, svg);
    el("rect", { class: "eg-clip-trio", x: 90, y: 330, width: 0, height: 148 }, tclip);
    const UNBLOCK = 0.833; // catch events done · 0h 50m
    const LANES = [
      { base: 360, pct: 14, start: 0, end: UNBLOCK, name: "record catch events" },
      { base: 415, pct: 18, start: UNBLOCK, end: 1.833, name: "flip-through log page" },
      { base: 470, pct: 12, start: UNBLOCK, end: 1.667, name: "empty state" },
    ];
    for (const l of LANES) {
      const top = l.base - 1.9 * l.pct;
      const d =
        `M ${X(l.start)} ${l.base} L ${X(l.start + 0.12)} ${top} L ${X(l.end - 0.06)} ${top}` +
        ` L ${X(l.end)} ${l.base} Z`;
      el("path", { class: "eg-trio-fill", d, "clip-path": "url(#econ-clip-trio)" }, trio);
      txt(X(l.end) + 12, l.base - 8, l.name, {}, trio);
    }
    /* the dependency drop: catch events' finish line unblocks lanes 2–3 —
       its note stacks just under the lane-1 name, clear of lane 2's top */
    const dep = el("g", { class: "eg eg-dep" }, svg);
    el("line", { class: "eg-dep-line", x1: X(UNBLOCK), y1: 362, x2: X(UNBLOCK), y2: 472 }, dep);
    txt(X(UNBLOCK) + 12, 369, "✓ done — unblocks the other two", { class: "eg-dep-label" }, dep);

    /* the two bills + the all-three bracket — they pop together */
    const bills = el("g", { class: "eg eg-bills" }, svg);
    txt(590, 205, "~4M tokens re-read", { class: "bill bill-solo", "text-anchor": "middle" }, bills);
    el("line", { x1: 620, y1: 335, x2: 620, y2: 470 }, bills);
    el("line", { x1: 620, y1: 335, x2: 612, y2: 335 }, bills);
    el("line", { x1: 620, y1: 470, x2: 612, y2: 470 }, bills);
    txt(638, 392, "✓ all three · 1h 50m · peaks ≤18%", { class: "all-three" }, bills);
    txt(638, 424, "~500k tokens re-read", { class: "bill bill-trio" }, bills);
  }

  function buildArrows() {
    const svg = document.getElementById("arrows-svg");
    svg.innerHTML = "";
    /* the spec from the page act, standing like a target */
    const doc = el("g", { transform: "translate(640, 80)" }, svg);
    el("rect", { class: "spec-target", width: 190, height: 240, rx: 8 }, doc);
    const title = el("text", { class: "spec-title", x: 16, y: 30 }, doc);
    title.textContent = "the requirements";
    for (const y of [66, 98, 130, 162, 194]) el("line", { class: "spec-line", x1: 18, x2: 172, y1: y, y2: y }, doc);
    /* the section finding 3 pierces — labeled, so the crack has a referent */
    const sub = el("text", { class: "spec-sub", x: 18, y: 150 }, doc);
    sub.textContent = "§ the size rule";
    el("path", { class: "crack", d: "M 0 168 l 30 -14 l 20 18 l 26 -10" }, doc);
    /* three reviewers, three angles */
    const starts = [
      { cls: "a1", t: "translate(90px, 150px) rotate(14deg)" },
      { cls: "a2", t: "translate(60px, 210px) rotate(-4deg)" },
      { cls: "a3", t: "translate(80px, 320px) rotate(-18deg)" },
    ];
    for (const s of starts) {
      const a = el("g", { class: "arrow " + s.cls }, svg);
      el("line", { x1: 0, y1: 0, x2: 70, y2: 0 }, a);
      el("path", { d: "M 70 0 l -13 -6 M 70 0 l -13 6" }, a);
      a.style.transform = s.t;
      a.style.opacity = "1";
    }
  }

  /* scene 13: the shared tackle box — the object pv-3 names but never draws.
     No bars: your lean skill is a lure; prove it (a fish), and the choice is
     whether it gets stapled onto every rod (forced) or waits in the open box
     for a line that wants it (chosen). Groups toggle .on per beat. */
  function buildTackle() {
    const svg = document.getElementById("tackle-svg");
    svg.innerHTML = "";
    const txt = (x, y, s, attrs = {}, parent = svg) => {
      const t = el("text", { x, y, ...attrs }, parent);
      t.textContent = s;
      return t;
    };
    const fishGlyph = (parent, x, y, scale) => {
      const g = el("g", { transform: `translate(${x}, ${y}) scale(${scale})` }, parent);
      el("path", { class: "tk-fish-body", d: "M6 12 Q 20 4 32 12 Q 20 20 6 12 Z" }, g);
      el("path", { class: "tk-fish-body", d: "M32 12 L 42 6 L 42 18 Z" }, g);
    };
    const rodPole = (parent, bx, tipx, tipy, casts) => {
      el("circle", { class: "tk-reel", cx: bx, cy: 186, r: 6 }, parent);
      el("line", { class: "tk-pole", x1: bx, y1: 192, x2: tipx, y2: tipy }, parent);
      if (casts) el("line", { class: "tk-fline", x1: tipx, y1: tipy, x2: tipx, y2: 250 }, parent);
    };

    /* the dock rail + water */
    const frame = el("g", { class: "tk-frame" }, svg);
    el("line", { class: "tk-water", x1: 40, y1: 278, x2: 880, y2: 278 }, frame);
    el("rect", { class: "tk-rail", x: 40, y: 196, width: 840, height: 9, rx: 2 }, frame);
    for (const x of [110, 690, 840]) el("rect", { class: "tk-post", x, y: 205, width: 8, height: 60 }, frame);

    /* YOU — your rod, the lean skill hanging as its lure */
    const you = el("g", { class: "tk-you" }, svg);
    rodPole(you, 150, 190, 76, true);
    el("ellipse", { class: "tk-ripple", cx: 190, cy: 278, rx: 15, ry: 3.5 }, you);
    el("ellipse", { class: "tk-ripple faint", cx: 190, cy: 278, rx: 27, ry: 6 }, you);
    const yl = el("g", { class: "tk-youlure" }, you);
    el("rect", { class: "tk-lure-card", x: 144, y: 240, width: 92, height: 22, rx: 5 }, yl);
    txt(190, 255, "SKILL.md", { class: "tk-lure-txt", "text-anchor": "middle" }, yl);
    txt(150, 176, "you", { class: "tk-label", "text-anchor": "middle" }, you);

    /* b1: proof — a fish on your line, just under the lure */
    const fish = el("g", { class: "tk tk-fish" }, svg);
    fishGlyph(fish, 166, 262, 1.05);
    txt(250, 266, "it catches", { class: "tk-note" }, fish);

    /* the OPEN tackle box on the rail — an owned object that's naturally shared */
    const box = el("g", { class: "tk-box" }, svg);
    el("polygon", { class: "tk-lid", points: "398,162 522,162 548,134 424,134" }, box);
    el("rect", { class: "tk-box-body", x: 398, y: 162, width: 124, height: 38, rx: 3 }, box);
    for (const x of [438, 482]) el("line", { class: "tk-divider", x1: x, y1: 166, x2: x, y2: 196 }, box);
    el("rect", { class: "tk-lure-card faint", x: 406, y: 172, width: 24, height: 14, rx: 2 }, box);
    txt(460, 124, "the crew’s tackle box", { class: "tk-boxtag", "text-anchor": "middle" }, box);

    /* CREW — three rods on the same rail; one never casts toward the water */
    const crew = el("g", { class: "tk-crew" }, svg);
    const rA = el("g", { class: "tk-rod" }, crew);
    rodPole(rA, 620, 660, 76, true);
    el("ellipse", { class: "tk-ripple faint", cx: 660, cy: 278, rx: 20, ry: 4 }, rA);
    const rB = el("g", { class: "tk-rod" }, crew);
    rodPole(rB, 725, 765, 76, false);
    txt(725, 176, "never casts here", { class: "tk-label", "text-anchor": "middle" }, rB);
    const rC = el("g", { class: "tk-rod" }, crew);
    rodPole(rC, 830, 870, 76, true);
    el("ellipse", { class: "tk-ripple faint", cx: 870, cy: 278, rx: 20, ry: 4 }, rC);

    /* b2: FORCE — the lure stapled onto EVERY rod, even the one that never casts */
    const clamp = el("g", { class: "tk tk-clamp" }, svg);
    for (const tx of [660, 765, 870]) {
      el("rect", { class: "tk-forced-card", x: tx - 34, y: 106, width: 68, height: 18, rx: 4 }, clamp);
      txt(tx, 119, "SKILL.md", { class: "tk-forced-txt", "text-anchor": "middle" }, clamp);
      el("path", { class: "tk-staple", d: `M ${tx - 7} 106 l 0 -6 l 14 0 l 0 6` }, clamp);
    }

    /* b3: the proven lure now waits in the box */
    const inbox = el("g", { class: "tk tk-inbox" }, svg);
    el("rect", { class: "tk-lure-card", x: 448, y: 172, width: 26, height: 14, rx: 2 }, inbox);

    /* b4: CHOOSE — a crewmate lifts it from the box, by choice */
    const take = el("g", { class: "tk tk-take" }, svg);
    el("path", { class: "tk-take-line", d: "M 505 176 Q 585 120 660 114" }, take);
    el("rect", { class: "tk-green-card", x: 626, y: 106, width: 68, height: 18, rx: 4 }, take);
    txt(660, 119, "SKILL.md", { class: "tk-green-txt", "text-anchor": "middle" }, take);
  }

  /* ---------- engine ---------- */

  function maxBeats(sec) {
    return parseInt(sec.dataset.beats || "0", 10);
  }

  function applyBeats(sec) {
    sec.querySelectorAll("[data-beat]").forEach((el) => {
      const n = parseInt(el.dataset.beat, 10);
      el.classList.toggle("on", n <= beat);
    });
  }

  function fireHook(sec) {
    const fn = hooks[sec.id];
    if (fn) fn(sec, beat);
  }

  /* the moon crosses the sky as the deck advances; dawn on the last scene */
  function updateSky() {
    const moon = document.querySelector("#sky .sky-moon");
    if (!moon) return;
    const p = sections.length > 1 ? idx / (sections.length - 1) : 0;
    moon.style.left = 6 + p * 86 + "vw";
    moon.style.top = 16 - Math.sin(p * Math.PI) * 9 + "vh";
    document.body.classList.toggle("dawn", idx === sections.length - 1);
  }

  function show(i) {
    idx = Math.max(0, Math.min(sections.length - 1, i));
    beat = 0;
    sections.forEach((s, j) => s.classList.toggle("active", j === idx));
    const sec = sections[idx];
    applyBeats(sec);
    fireHook(sec);
    updateSky();
    hud.textContent = `${idx + 1} / ${sections.length} · ${sec.dataset.title || ""}`;
    broadcastState();
  }

  function advance() {
    const sec = sections[idx];
    if (beat < maxBeats(sec)) {
      beat++;
      applyBeats(sec);
      fireHook(sec);
      broadcastState();
    } else {
      show(idx + 1);
    }
  }

  function handleKey(key) {
    if (key === "ArrowRight" || key === " " || key === "PageDown") advance();
    else if (key === "ArrowLeft" || key === "PageUp") show(idx - 1);
    else if (key === "Home") show(0);
    else if (key === "End") show(sections.length - 1);
    else if (key === "b" || key === "B") blank.classList.toggle("on");
  }

  document.addEventListener("keydown", (e) => {
    if (["ArrowRight", "ArrowLeft", " ", "PageDown", "PageUp", "Home", "End", "b", "B"].includes(e.key)) {
      e.preventDefault();
      handleKey(e.key);
    }
  });

  /* presenter-view sync: the deck broadcasts its position; a presenter.html
     window (open it beside the deck, keep focus there) shows the talk-track
     cues and remote-controls the deck. Needs http(s) — file:// origins
     can't share a BroadcastChannel. */
  const bc = "BroadcastChannel" in window ? new BroadcastChannel("nightline-deck") : null;

  function broadcastState() {
    if (!bc) return;
    const sec = sections[idx];
    bc.postMessage({
      type: "state",
      idx,
      beat,
      total: sections.length,
      maxBeats: maxBeats(sec),
      title: sec.dataset.title || "",
      id: sec.id,
      nextTitle: sections[idx + 1] ? sections[idx + 1].dataset.title : "",
    });
  }

  if (bc)
    bc.onmessage = (e) => {
      if (!e.data) return;
      if (e.data.type === "key") handleKey(e.data.key);
      if (e.data.type === "hello") broadcastState();
    };

  /* deep-link: #<scene>[.<beat>] (1-based scene) — for rehearsal and QA */
  const m = (location.hash || "").match(/^#(\d+)(?:\.(\d+))?$/);
  if (m) {
    show(parseInt(m[1], 10) - 1);
    const targetBeat = parseInt(m[2] || "0", 10);
    for (let i = 0; i < targetBeat; i++) advance();
  } else {
    show(0);
  }
})();
