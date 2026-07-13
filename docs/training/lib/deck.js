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

  /* the No-loop: both design calls live in the tank, so the agent oscillates
     between them — and the third suggestion is verbatim the first */
  const NOLOOP_A = [
    { t: "user", text: "dawn spawns still feel wrong — fix them" },
    { t: "agent", text: "Rare fish hide at dawn — lowering the multiplier.", pause: 250 },
    { t: "tool", text: "Edit spawn_table.js" },
    { t: "del", lines: ["- DAWN_RARE_MULT = 1.0"] },
    { t: "add", lines: ["+ DAWN_RARE_MULT = 0.4"] },
    { t: "user", text: "NO!" },
  ];
  const NOLOOP_B = [
    { t: "agent", text: "Right — dawn is the rare-fish window. Raising it.", pause: 250 },
    { t: "tool", text: "Edit spawn_table.js" },
    { t: "del", lines: ["- DAWN_RARE_MULT = 0.4"] },
    { t: "add", lines: ["+ DAWN_RARE_MULT = 2.5"] },
    { t: "user", text: "Still no." },
  ];
  const NOLOOP_C = [
    { t: "agent", text: "Reconsidering — rare fish hide at dawn. Lowering.", pause: 250 },
    { t: "del", lines: ["- DAWN_RARE_MULT = 2.5"], snap: true },
    { t: "add", lines: ["+ DAWN_RARE_MULT = 0.4"], snap: true },
    { t: "warn", text: "✗ turn 74 · 40 minutes · same diff as turn 71", snap: true },
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
    { t: "user", text: "interview me — scope Monday's playtest" },
    { t: "ask", text: "what should a player wake up to?", pause: 250 },
    { t: "user", text: "a catch in the log — and fish actually biting" },
    { t: "ask", text: "biting's been off since 4:00 — fix first?", pause: 250 },
    { t: "user", text: "fix it first" },
    { t: "tool", text: "Write first-night-epic.md" },
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

  const SCROLL_START = [
    { n: "#1", text: "Review the spec from an adversarial angle." },
    { n: "#7", text: "Return findings with evidence quotes." },
    { n: "#12", text: "Keep skills short and focused.", gag: true },
  ];
  const SCROLL_GAGS = [
    { n: "#212", text: "Always begin findings with a severity emoji." },
    { n: "#1,003", text: "NEVER use the word “delve”." },
    { n: "#1,486", text: "If unsure, re-read lines 1–1,485.", gag: true },
    { n: "#2,041", text: "Do not add more instructions to this file.", gag: true },
  ];

  function skillLine(l) {
    return `<div><span class="lnum">${l.n}</span><span class="${l.gag ? "gag" : ""}">${l.text}</span></div>`;
  }

  const GAUGE_BASE = [
    { kind: "system", pct: 6, label: "system prompt" },
    { kind: "chat", pct: 8, label: "your messages" },
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
        if (state.termLeft) state.termLeft.clear();
        if (state.termRight) state.termRight.clear();
        if (state.cbLeft) state.cbLeft.set(0, { ms: 0 });
        if (state.cbRight) state.cbRight.set(0, { ms: 0 });
      }
      if (b === 1) {
        sec.classList.add("staged");
        if (!state.termLeft) {
          state.termLeft = makeTerminal(document.getElementById("term-left"), { title: "fresh session · 9:00 AM" });
          state.termRight = makeTerminal(document.getElementById("term-right"), { title: "same session · 4:00 PM" });
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
          state.cbSqueeze.set(30, { ms: 2600 }); // the number improves; the mind got worse
          await state.vSqueeze.squeeze({ stripeLabel: 'kept: "building a fishing game"' });
        });
      if (b === 2)
        chain("squeeze", async () => {
          await sleep(2200); // the mini-term lines land first
          const chip = state.vSqueeze.box.querySelector(".chip");
          if (chip) chip.classList.add("needed");
        });
    },

    "sc-noloop": (sec, b) => {
      if (b === 0) {
        sec.classList.remove("spotlight");
        if (!state.termLoop) {
          state.termLoop = makeTerminal(document.getElementById("term-noloop"), { title: "same session · turn 71" });
          state.cbLoop = makeContextBar(document.getElementById("cbar-noloop"), { h: 12 });
        }
        if (!state.vLoop) state.vLoop = makeVessel(document.getElementById("vessel-noloop"), { scale: 0.8 });
        state.termLoop.clear();
        state.vLoop.reset();
        state.vLoop.setFill([
          { kind: "system", pct: 8 },
          { kind: "chat", pct: 6 },
          { kind: "tool", pct: 16, label: "the morning's design chat" },
          { kind: "chat", pct: 6 },
          { kind: "tool", pct: 16 },
        ]); // 52% — deep in the afternoon
        state.vLoop.pinChips(
          ['turn 14: “rare fish hide at dawn”', 'turn 62: “dawn is the rare-fish window”'],
          { fracs: [0.66, 0.34] }
        );
        state.cbLoop.set(58, { ms: 600 });
      }
      if (b === 1)
        chain("noloop", async () => {
          await state.termLoop.play(NOLOOP_A);
          state.vLoop.pinChips(['turn 72: “NO!”'], { fracs: [0.5] });
          state.cbLoop.set(63, { ms: 800 });
        });
      if (b === 2)
        chain("noloop", async () => {
          await state.termLoop.play(NOLOOP_B, { append: true });
          state.vLoop.pinChips(['turn 73: “Still no.”'], { fracs: [0.18] });
          state.cbLoop.set(70, { ms: 800 });
          await state.termLoop.play(NOLOOP_C, { append: true }); // the relapse snaps in — no crawl
          state.vLoop.box.querySelectorAll(".chip").forEach((c, i) => {
            if (i < 2) c.classList.add("conflict"); // the two design calls, both still live
          });
        });
      if (b === 3) sec.classList.add("spotlight");
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
      if (b === 1) state.wp2.posts.page.classList.add("lit");
    },
    "pv-3": (sec, b) => {
      if (b === 0) state.wp3 = buildDock(document.getElementById("wp-dock-3"), { sketch: true, lit: ["window", "page"] });
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
        if (state.cbHandoff) state.cbHandoff.set(0, { ms: 0 });
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
        if (!state.cbHandoff) state.cbHandoff = makeContextBar(document.getElementById("cbar-handoff"), { h: 10 });
        state.cbHandoff.set(8, { ms: 0 });
        state.cbHandoff.set(14, { ms: 2600 });
      }
    },

    "sc-lines": (sec, b) => {
      if (b === 0) {
        if (!state.vMurk) state.vMurk = makeVessel(document.getElementById("vessel-murk"), { scale: 0.8 });
        state.vMurk.reset();
        state.vMurk.setFill([
          { kind: "system", pct: 10 },
          { kind: "tool", pct: 20 },
          { kind: "system", pct: 8 },
          { kind: "tool", pct: 14 },
        ]);
        if (!state.vFresh) {
          state.vFresh = [1, 2, 3].map((i) => makeVessel(document.getElementById("vessel-fresh-" + i), { scale: 0.28 }));
          state.cbFresh = [1, 2, 3].map((i) =>
            makeContextBar(document.getElementById("cbar-fresh-" + i), { h: 8, label: "", readout: false, marker: null })
          );
        }
        state.vFresh.forEach((v) => {
          v.reset();
          v.setFill([{ kind: "spec", pct: 9 }]); // fresh, carrying only the page
        });
        state.cbFresh.forEach((cb) => cb.set(8, { ms: 0 }));
        document.getElementById("lines-clock").textContent = "4:00 PM";
        document.getElementById("idea-scrapbook").classList.remove("lit");
        sec.classList.remove("picked", "working");
      }
      if (b === 3) {
        sec.classList.add("working");
        state.cbFresh[0].set(26, { ms: 5200 });
        state.cbFresh[1].set(24, { ms: 5600 });
        state.cbFresh[2].set(27, { ms: 6000 });
        setTimeout(() => (document.getElementById("lines-clock").textContent = "4:20 PM"), 3000);
      }
      if (b === 4) {
        sec.classList.add("picked");
        const chip = document.getElementById("lines-intent");
        const target = document.getElementById("idea-scrapbook");
        setTimeout(() => flyIntent(chip, target, () => target.classList.add("lit")), 600);
      }
    },

    "sc-arrows": (sec, b) => {
      const card = (id, delay) => setTimeout(() => document.getElementById(id).classList.add("on"), delay);
      if (b === 0) {
        buildArrows();
        sec.classList.remove("spec-docked");
        ["fcard-1", "fcard-2", "fcard-3"].forEach((id) => document.getElementById(id).classList.remove("on"));
        sec.querySelector(".finding-card").classList.remove("binned");
      }
      if (b === 1) setTimeout(() => sec.classList.add("spec-docked"), 1400); // the doc takes its place on the range
      if (b === 2) {
        setTimeout(() => flyArrow("a1", 575, 160, 14, true), 200);
        card("fcard-1", 900);
        setTimeout(() => flyArrow("a2", 572, 205, -4, true), 1400);
        card("fcard-2", 2100);
      }
      if (b === 3) {
        flyArrow("a3", 585, 270, -18, false);
        setTimeout(() => document.querySelector("#arrows-svg .crack").classList.add("show"), 600);
        card("fcard-3", 800);
      }
      if (b === 4) document.querySelector("#arrows-svg .crack").classList.add("gold");
      if (b === 5) {
        const fc = sec.querySelector(".finding-card");
        fc.classList.remove("binned");
        setTimeout(() => fc.classList.add("binned"), 3600); // room to read it aloud first
      }
    },

    "sc-scroll": (sec, b) => {
      const body = document.getElementById("skill-body");
      const count = document.getElementById("line-count");
      const thumb = document.getElementById("scroll-thumb");
      const file = document.getElementById("skill-file");
      if (b === 0) {
        body.innerHTML = SCROLL_START.map(skillLine).join("");
        count.textContent = "20 lines";
        thumb.style.height = "82%";
        file.classList.remove("shoved");
        document.getElementById("tune-col").innerHTML = "";
        sec.querySelector(".drawers-block").classList.remove("on");
      }
      if (b === 2)
        chain("scroll", async () => {
          const tunes = ["tune it", "be stricter about evidence", "add the edge cases", "catch auth issues too"];
          tunes.forEach((t, i) =>
            setTimeout(() => {
              const el = document.createElement("span");
              el.className = "tune-bubble";
              el.textContent = t;
              document.getElementById("tune-col").appendChild(el);
              requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("on")));
            }, i * 800)
          );
          thumb.style.height = "4%";
          const STEPS = 68;
          const D = 3400;
          let gagIdx = 0;
          for (let step = 1; step <= STEPS; step++) {
            await sleep(D / STEPS);
            const p = step / STEPS;
            const n = Math.round(20 + (2041 - 20) * p * p);
            count.textContent = n.toLocaleString() + " lines";
            const due = Math.min(SCROLL_GAGS.length, Math.floor(p * (SCROLL_GAGS.length + 0.99)));
            while (gagIdx < due) {
              body.innerHTML += skillLine(SCROLL_GAGS[gagIdx]);
              while (body.children.length > 5) body.firstChild.remove();
              gagIdx++;
            }
          }
        });
      if (b === 3)
        chain("scroll", async () => {
          if (!state.vSkill) state.vSkill = makeVessel(document.getElementById("vessel-skill"), { scale: 0.8 });
          state.vSkill.reset();
          file.classList.add("shoved");
          await sleep(900);
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

    "sc-turnstile": (sec, b) => {
      const svg = document.getElementById("gate-svg");
      if (b === 0) {
        buildGate();
        document.getElementById("gate-linecount").textContent = "adversarial-review · SKILL.md — 2,041 lines";
        if (state.gateRecoil) clearTimeout(state.gateRecoil);
      }
      if (b === 1) {
        const w = svg.querySelector(".walker");
        w.style.transform = "translateX(470px)";
        setTimeout(() => svg.querySelector(".sign-cap").classList.add("on"), 1100); // as the walker clears the sign
        state.gateRecoil = setTimeout(
          () => ((w.style.transition = "transform 0.3s ease"), (w.style.transform = "translateX(455px)")),
          1900
        );
      }
      if (b === 2)
        chain("gate", async () => {
          if (state.gateRecoil) clearTimeout(state.gateRecoil);
          const w = svg.querySelector(".walker");
          w.style.transition = "transform 0.6s ease";
          w.style.transform = "translateX(430px)"; // step back from the arms
          await sleep(700);
          const fix = el("g", { class: "gate-fix" }, svg);
          el("rect", { x: 428, y: 128, width: 240, height: 30, rx: 6 }, fix);
          const ft = el("text", { x: 442, y: 148 }, fix);
          ft.textContent = "⏺ run tests → ✓ 14 passing";
          await sleep(1700);
          svg.querySelector(".gate-dot").setAttribute("fill", cssVar("--zone-green"));
          svg.querySelector(".gate-label").textContent = "tests ✓";
          const arms = svg.querySelector(".turnstile-arms");
          arms.style.transformOrigin = "690px 218px";
          arms.style.transform = "rotate(-120deg)";
          w.style.transition = "transform 1.6s ease 0.5s";
          w.style.transform = "translateX(760px)";
        });
      if (b === 3) {
        svg.classList.add("sign-faded");
        const lc = document.getElementById("gate-linecount");
        lc.textContent = "adversarial-review · SKILL.md — 1,988 lines";
        lc.classList.add("ticked"); // § 1,847 came out of the file
      }
    },

    "sc-finale": (sec, b) => {
      if (b === 0) {
        sec.classList.remove("f1", "f2", "f3", "f4", "f5");
        if (!state.finRed) {
          state.finRed = makeTerminal(document.getElementById("term-fin-red"), { title: "same session · 4:00 PM" });
          state.finInt = makeTerminal(document.getElementById("term-fin-int"), { title: "fresh session · 4:05 PM · the interview" });
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
          lit: ["window", "page", "clean"],
          plank: true,
        });
      }
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

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  /* write finished terminal lines instantly — a freeze-frame */
  function prefill(term, lines) {
    const body = term.el.querySelector(".term-body");
    body.innerHTML = lines.map((s) => `<div class="term-line ${s.t}">${s.text}</div>`).join("");
  }

  /* the dock diagram: three posts = the three pillars (left → right:
     window · page · clean — teaching order IS retell order now), the
     plank = the pipeline, drawn only when Friday runs end-to-end. */
  function buildDock(container, { sketch = false, lit = [], plank = false } = {}) {
    container.innerHTML = "";
    const svg = el("svg", { viewBox: "0 0 640 210", class: "dock-diagram" });
    container.appendChild(svg);
    el("line", { class: "bp-water", x1: 0, y1: 158, x2: 640, y2: 158 }, svg);
    const posts = {};
    const XS = { window: 101, page: 315, clean: 529 };
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

  function flyArrow(cls, tx, ty, rot, bounce) {
    const a = document.querySelector(`#arrows-svg .arrow.${cls}`);
    a.style.transition = "transform 0.55s cubic-bezier(0.3, 0, 0.7, 1)";
    a.style.transform = `translate(${tx}px, ${ty}px) rotate(${rot}deg)`;
    if (bounce)
      setTimeout(() => {
        a.style.transition = "transform 0.9s ease, opacity 0.9s ease";
        a.style.transform = `translate(${tx - 90}px, ${ty + 70}px) rotate(${rot - 38}deg)`;
        a.style.opacity = "0.3";
      }, 620);
  }

  function buildArrows() {
    const svg = document.getElementById("arrows-svg");
    svg.innerHTML = "";
    /* the spec from the page act, standing like a target */
    const doc = el("g", { transform: "translate(640, 80)" }, svg);
    el("rect", { class: "spec-target", width: 190, height: 240, rx: 8 }, doc);
    const title = el("text", { class: "spec-title", x: 16, y: 30 }, doc);
    title.textContent = "throw small fish back";
    for (const y of [66, 98, 130, 162, 194]) el("line", { class: "spec-line", x1: 18, x2: 172, y1: y, y2: y }, doc);
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

  function buildGate() {
    const svg = document.getElementById("gate-svg");
    svg.innerHTML = "";
    el("line", { class: "ground", x1: 40, y1: 262, x2: 960, y2: 262 }, svg);

    /* the sign: prose, politely ignored */
    el("line", { class: "sign-post", x1: 300, y1: 262, x2: 300, y2: 156 }, svg);
    el("rect", { class: "sign-board", x: 196, y: 106, width: 226, height: 52, rx: 4 }, svg);
    const t1 = el("text", { class: "sign-text", x: 206, y: 126 }, svg);
    t1.textContent = "§ 1,847";
    const t2 = el("text", { class: "sign-text", x: 206, y: 146 }, svg);
    t2.textContent = "please always run the tests";
    const cap = el("text", { class: "sign-cap", x: 196, y: 186 }, svg);
    cap.textContent = "in the window every turn — obeyed sometimes";

    /* the turnstile: structure */
    el("line", { class: "turnstile-frame", x1: 662, y1: 170, x2: 662, y2: 262 }, svg);
    el("line", { class: "turnstile-frame", x1: 718, y1: 170, x2: 718, y2: 262 }, svg);
    const arms = el("g", { class: "turnstile-arms" }, svg);
    el("line", { x1: 690, y1: 218, x2: 690, y2: 184 }, arms);
    el("line", { x1: 690, y1: 218, x2: 719.4, y2: 235 }, arms);
    el("line", { x1: 690, y1: 218, x2: 660.6, y2: 235 }, arms);
    el("circle", { class: "gate-dot", cx: 690, cy: 150, r: 5, fill: cssVar("--zone-red") }, svg);
    const lbl = el("text", { class: "gate-label", x: 706, y: 155 }, svg);
    lbl.textContent = "tests ✗";

    /* the agent, out for a walk */
    const w = el("g", { class: "walker" }, svg);
    el("circle", { cx: 110, cy: 205, r: 11 }, w);
    el("path", { d: "M 110 216 L 110 240 M 110 222 L 98 232 M 110 222 L 122 232 M 110 240 L 100 262 M 110 240 L 120 262" }, w);
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
