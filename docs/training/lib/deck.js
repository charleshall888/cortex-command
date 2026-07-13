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

  const WISH_SCRIPT = [
    { t: "user", text: "make the catch log better" },
    { t: "agent", text: "Adding filters, sorting, and a stats view…", pause: 200 },
    { t: "tool", text: "Edit catch_log_view.js" },
    { t: "add", lines: ["+ <FilterBar/>  <SortDropdown/>"] },
    { t: "tool", text: "Write catch_stats.js" },
    { t: "add", lines: ["+ renderCatchRateChart(entries)"] },
    { t: "agent", text: "Also wiring up CSV export…" },
    { t: "warn", text: "✗ 6 files changed · filters, stats, export" },
  ];

  const TICKET_SCRIPT = [
    { t: "user", text: "ticket: empty-state for the catch log" },
    { t: "user", text: "constraints: keepsake voice, no data-UI chrome" },
    { t: "user", text: "done when: a first-night player feels invited to cast" },
    { t: "tool", text: "Read catch_log_view.js" },
    { t: "add", lines: ['+ EmptyState("No catches yet.", "The night is young.")'] },
    { t: "done", text: "✓ 1 file changed · tests pass" },
  ];

  /* the full circle: the cold open's Friday, replayed with the habits */
  const REPLAY_A = [
    { t: "user", text: "add flip-through paging to the catch log" },
    { t: "agent", text: "Working — pulling the whole day back in…", pause: 300 },
    { t: "user", text: "stop — you're at 91%. write the handoff ticket first." },
    { t: "tool", text: "Write handoff-flip-through.md" },
    { t: "done", text: "✓ ticket written · constraints + done-when · session closed" },
  ];

  const REPLAY_B = [
    { t: "user", text: "ticket: flip-through paging for the catch log" },
    { t: "user", text: "constraints: keepsake voice · one page per catch" },
    { t: "tool", text: "Read handoff-flip-through.md" },
    { t: "add", lines: ["+ page.flip(direction)", "+ renderPage(entry)"] },
    { t: "done", text: "✓ tests pass · 2 files changed" },
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

  /* the gauge scene's pour: layers name themselves inside the tank */
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
      if (b === 3) {
        state.termRight.play(RIGHT_SCRIPT);
        state.cbRight.set(96, { ms: 13000 });
      }
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
          await new Promise((r) => setTimeout(r, 2200)); // the mini-term lines land first
          const chip = state.vSqueeze.box.querySelector(".chip");
          if (chip) chip.classList.add("needed");
        });
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
      if (b === 1) state.wp1.posts.exit.classList.add("lit");
    },
    "pv-2": (sec, b) => {
      if (b === 0) state.wp2 = buildDock(document.getElementById("wp-dock-2"), { sketch: true, lit: ["exit"] });
      if (b === 1) state.wp2.posts.page.classList.add("lit");
    },
    "pv-3": (sec, b) => {
      if (b === 0) state.wp3 = buildDock(document.getElementById("wp-dock-3"), { sketch: true, lit: ["exit", "page"] });
      if (b === 1) {
        state.wp3.plank.classList.add("drawn");
        state.wp3.posts.instructions.classList.add("pulse");
      }
    },

    "sc-prism": (sec, b) => {
      const cloud = sec.querySelector(".cloud");
      const bubbles = [...sec.querySelectorAll(".qbubble")];
      const tickets = [...sec.querySelectorAll(".prism-tickets .ticket")];
      if (b === 0) {
        cloud.classList.remove("sharp", "condensed");
        bubbles.forEach((q) => q.classList.remove("on"));
        tickets.forEach((t) => t.classList.remove("on"));
        sec.querySelectorAll(".badge-clip").forEach((c) => c.classList.remove("stamped"));
        sec.querySelector(".ticket.callback").classList.remove("lit");
        sec.querySelector(".doc").classList.remove("on");
        sec.classList.remove("past-top", "past-mid", "fork-mode", "decided");
      }
      if (b === 2) {
        bubbles.forEach((q, i) => setTimeout(() => q.classList.add("on"), 300 + i * 900));
        setTimeout(() => cloud.classList.add("sharp"), 1400);
      }
      if (b === 3) {
        cloud.classList.add("condensed");
        sec.classList.add("past-top");
        sec.querySelector(".doc").classList.add("on");
      }
      if (b === 4) {
        sec.classList.add("past-mid");
        tickets.forEach((t) => t.classList.add("on"));
        stampTickets(sec);
        setTimeout(() => sec.querySelector(".ticket.callback").classList.add("lit"), 2200);
      }
      if (b === 5) {
        sec.classList.add("fork-mode");
        setTimeout(() => sec.classList.add("decided"), 2600);
      }
    },

    "sc-wish": (sec, b) => {
      if (b === 0) {
        if (state.termWish) state.termWish.clear();
        if (state.termTicket) state.termTicket.clear();
        if (state.cbWish) state.cbWish.set(0, { ms: 0 });
        if (state.cbTicket) state.cbTicket.set(0, { ms: 0 });
      }
      if (b === 1 && !state.termWish) {
        state.termWish = makeTerminal(document.getElementById("term-wish"), { title: "fresh session A" });
        state.termTicket = makeTerminal(document.getElementById("term-ticket"), { title: "fresh session B" });
        state.cbWish = makeContextBar(document.getElementById("cbar-wish"), { h: 12 });
        state.cbTicket = makeContextBar(document.getElementById("cbar-ticket"), { h: 12 });
      }
      if (b === 1) {
        state.cbWish.set(8, { ms: 700 });
        state.cbTicket.set(8, { ms: 700 }); // identical starts — the controls of the experiment
      }
      if (b === 2)
        chain("wish", () => {
          state.cbWish.set(68, { ms: 12000 });
          return state.termWish.play(WISH_SCRIPT);
        });
      if (b === 3)
        chain("wish", () => {
          state.cbTicket.set(18, { ms: 6000 });
          return state.termTicket.play(TICKET_SCRIPT);
        });
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
        }
        state.vFresh.forEach((v) => {
          v.reset();
          v.setFill([{ kind: "spec", pct: 9 }]); // fresh, carrying only the page
        });
        document.getElementById("idea-scrapbook").classList.remove("lit");
        sec.classList.remove("picked");
      }
      if (b === 3) {
        document.getElementById("idea-scrapbook").classList.add("lit");
        sec.classList.add("picked");
      }
    },

    "sc-arrows": (sec, b) => {
      const card = (id, delay) => setTimeout(() => document.getElementById(id).classList.add("on"), delay);
      if (b === 0) {
        buildArrows();
        ["fcard-1", "fcard-2", "fcard-3"].forEach((id) => document.getElementById(id).classList.remove("on"));
        sec.querySelector(".finding-card").classList.remove("binned");
      }
      if (b === 1) {
        setTimeout(() => flyArrow("a1", 575, 160, 14, true), 200);
        card("fcard-1", 900);
        setTimeout(() => flyArrow("a2", 572, 205, -4, true), 1400);
        card("fcard-2", 2100);
      }
      if (b === 2) {
        flyArrow("a3", 585, 270, -18, false);
        setTimeout(() => document.querySelector("#arrows-svg .crack").classList.add("show"), 600);
        card("fcard-3", 800);
      }
      if (b === 3) document.querySelector("#arrows-svg .crack").classList.add("gold");
      if (b === 4) {
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
            await new Promise((r) => setTimeout(r, D / STEPS));
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
          await new Promise((r) => setTimeout(r, 900));
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
      if (b === 0) buildGate();
      const svg = document.getElementById("gate-svg");
      if (b === 0 && state.gateRecoil) clearTimeout(state.gateRecoil);
      if (b === 1) {
        const w = svg.querySelector(".walker");
        w.style.transform = "translateX(470px)";
        state.gateRecoil = setTimeout(
          () => ((w.style.transition = "transform 0.3s ease"), (w.style.transform = "translateX(455px)")),
          1900
        );
      }
      if (b === 2) {
        if (state.gateRecoil) clearTimeout(state.gateRecoil);
        svg.querySelector(".gate-dot").setAttribute("fill", cssVar("--zone-green"));
        svg.querySelector(".gate-label").textContent = "tests ✓";
        const arms = svg.querySelector(".turnstile-arms");
        arms.style.transformOrigin = "690px 218px";
        arms.style.transform = "rotate(-120deg)";
        const w = svg.querySelector(".walker");
        w.style.transition = "transform 1.6s ease 0.6s";
        w.style.transform = "translateX(760px)";
      }
      if (b === 3) svg.classList.add("sign-faded");
    },

    "sc-byhand": (sec, b) => {
      const wall = sec.querySelector(".wall");
      if (b === 0) wall.classList.remove("automated");
      if (b === 2) wall.classList.add("automated");
    },

    "sc-replay": (sec, b) => {
      const chips = [1, 2, 3].map((i) => document.getElementById("rchip-" + i));
      if (b === 0) {
        if (state.termReplay) state.termReplay.clear();
        if (state.cbReplay) state.cbReplay.set(0, { ms: 0 });
        chips.forEach((c) => c.classList.remove("on"));
        setTermTitle(state.termReplay, "same session · 4:00 PM");
      }
      if (b === 1) {
        if (!state.termReplay) {
          state.termReplay = makeTerminal(document.getElementById("term-replay"), { title: "same session · 4:00 PM" });
          state.cbReplay = makeContextBar(document.getElementById("cbar-replay"), { h: 12 });
        }
        state.cbReplay.set(91, { ms: 1800 }); // exactly where the cold open left it
      }
      if (b === 2)
        chain("replay", async () => {
          await state.termReplay.play(REPLAY_A);
          chips[0].classList.add("on"); // the handoff ticket IS direction on the page
        });
      if (b === 3)
        chain("replay", async () => {
          state.termReplay.clear();
          setTermTitle(state.termReplay, "fresh session · 4:04 PM");
          state.cbReplay.set(8, { ms: 1600 }); // the single most legible image in the deck
          state.cbReplay.flash();
          chips[1].classList.add("on");
          await new Promise((r) => setTimeout(r, 1700));
          await state.termReplay.play(REPLAY_B);
          state.cbReplay.set(16, { ms: 1200 });
          chips[2].classList.add("on");
        });
      if (b === 4) {
        state.wpFinal = buildDock(document.getElementById("wp-dock-final"), { lit: ["page", "exit", "instructions"], plank: true });
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

  function setTermTitle(term, title) {
    if (!term) return;
    const spans = term.el.querySelectorAll(".term-bar span");
    spans[spans.length - 1].textContent = title;
  }

  /* the dock diagram: three posts = the three habits (left → right:
     page · exit · instructions), the plank = the techniques laid across
     them. Sketch = blueprint dashes; lit = built. */
  function buildDock(container, { sketch = false, lit = [], plank = false } = {}) {
    container.innerHTML = "";
    const svg = el("svg", { viewBox: "0 0 640 210", class: "dock-diagram" });
    container.appendChild(svg);
    el("line", { class: "bp-water", x1: 0, y1: 158, x2: 640, y2: 158 }, svg);
    const posts = {};
    const XS = { page: 101, exit: 315, instructions: 529 };
    for (const [key, x] of Object.entries(XS)) {
      posts[key] = el("rect", { class: "bp-post" + (sketch ? " sketch" : ""), x, y: 84, width: 10, height: 74 }, svg);
      if (lit.includes(key)) posts[key].classList.add("lit");
    }
    const plankEl = el("rect", { class: "bp-plank" + (sketch ? " sketch" : ""), x: 70, y: 74, width: 500, height: 9 }, svg);
    if (plank) plankEl.classList.add("drawn");
    return { svg, posts, plank: plankEl };
  }

  /* the parent epic's intent line stamps itself onto each ticket —
     the stripe on a ticket is literally a copy of that one line */
  function stampTickets(sec) {
    const intent = sec.querySelector(".doc-intent");
    const clips = [...sec.querySelectorAll(".prism-tickets .ticket .badge-clip")];
    const from = intent.getBoundingClientRect();
    clips.forEach((clip, i) => {
      setTimeout(() => {
        const to = clip.getBoundingClientRect();
        const ghost = intent.cloneNode(true);
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
          clip.classList.add("stamped");
        }, 560);
      }, 400 + i * 350);
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
    /* the spec from the prism scene, standing like a target */
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
