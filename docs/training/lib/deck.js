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

  const hooks = {
    "sc-cold-open": (sec, b) => {
      if (b === 0) {
        sec.classList.remove("staged");
        if (state.termLeft) state.termLeft.clear();
        if (state.termRight) state.termRight.clear();
      }
      if (b === 1) {
        sec.classList.add("staged");
        if (!state.termLeft) {
          state.termLeft = makeTerminal(document.getElementById("term-left"), { title: "fresh session · 9:00 AM" });
          state.termRight = makeTerminal(document.getElementById("term-right"), { title: "same session · 4:00 PM" });
        }
      }
      if (b === 2) state.termLeft.play(LEFT_SCRIPT);
      if (b === 3) state.termRight.play(RIGHT_SCRIPT);
    },

    "sc-scan": (sec, b) => {
      if (b === 0) {
        if (!state.vScan) state.vScan = makeVessel(document.getElementById("vessel-scan"));
        state.vScan.reset();
        setCoins(0);
      }
      if (b === 1)
        chain("scan", () =>
          state.vScan.pour([
            { kind: "system", pct: 8 },
            { kind: "chat", pct: 10 },
            { kind: "tool", pct: 22 },
            { kind: "chat", pct: 6 },
            { kind: "tool", pct: 16 },
          ])
        );
      if (b === 2) chain("scan", () => state.vScan.sweep({ onCoin: setCoins })); // plays silent
      if (b === 3) chain("scan", () => state.vScan.sweep({ cached: true, onCoin: setCoins }));
    },

    "sc-zones": (sec, b) => {
      if (b === 0) {
        if (!state.vZones) state.vZones = makeVessel(document.getElementById("vessel-zones"));
        state.vZones.reset();
        state.vZones.setFill([
          { kind: "system", pct: 8 },
          { kind: "chat", pct: 14 },
          { kind: "tool", pct: 19 },
        ]); // 41% — matches the presenter's own confessed number
      }
      if (b === 1) state.vZones.zones();
    },

    "sc-prism": (sec, b) => {
      const cloud = sec.querySelector(".cloud");
      const bubbles = [...sec.querySelectorAll(".qbubble")];
      if (b === 0) {
        cloud.classList.remove("sharp", "condensed");
        bubbles.forEach((q) => q.classList.remove("on"));
        sec.querySelector(".ticket.callback").classList.remove("lit");
      }
      if (b === 2) {
        bubbles.forEach((q, i) => setTimeout(() => q.classList.add("on"), 300 + i * 900));
        setTimeout(() => cloud.classList.add("sharp"), 1400);
      }
      if (b === 3) {
        cloud.classList.add("condensed");
        if (!state.vFound) state.vFound = makeVessel(document.getElementById("vessel-foundation"), { scale: 0.5 });
        state.vFound.reset();
        state.vFound.pour([
          { kind: "spec", pct: 12 },
          { kind: "spec", pct: 8 },
        ]); // the first 20% — what everything else settles on
      }
      if (b === 5) sec.querySelector(".ticket.callback").classList.add("lit");
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

    "sc-badge": (sec, b) => {
      if (b === 0) sec.classList.remove("decided");
      if (b === 3) sec.classList.add("decided");
    },

    "sc-wish": (sec, b) => {
      if (b === 0) {
        if (state.termWish) state.termWish.clear();
        if (state.termTicket) state.termTicket.clear();
        document.getElementById("meter-wish").style.width = "0";
        document.getElementById("meter-ticket").style.width = "0";
      }
      if (b === 1 && !state.termWish) {
        state.termWish = makeTerminal(document.getElementById("term-wish"), { title: "the wish" });
        state.termTicket = makeTerminal(document.getElementById("term-ticket"), { title: "the ticket" });
      }
      if (b === 2)
        chain("wish", () => {
          const m = document.getElementById("meter-wish");
          m.style.transition = "width 9s linear";
          m.style.width = "68%";
          return state.termWish.play(WISH_SCRIPT);
        });
      if (b === 3)
        chain("wish", () => {
          const m = document.getElementById("meter-ticket");
          m.style.transition = "width 5s linear";
          m.style.width = "18%";
          return state.termTicket.play(TICKET_SCRIPT);
        });
    },

    "sc-tint": (sec, b) => {
      if (b === 0) {
        if (!state.vMurk) state.vMurk = makeVessel(document.getElementById("vessel-murk"), { scale: 0.8 });
        state.vMurk.reset();
        state.vMurk.setFill([
          { kind: "system", pct: 10 },
          { kind: "tool", pct: 20 },
          { kind: "system", pct: 8 },
          { kind: "tool", pct: 14 },
        ]);
        document.getElementById("idea-scrapbook").classList.remove("lit");
      }
      if (b === 3) document.getElementById("idea-scrapbook").classList.add("lit");
    },

    "sc-arrows": (sec, b) => {
      if (b === 0) buildArrows();
      if (b === 1) {
        const fly = (cls, tx, ty, rot, bounce) => {
          const a = document.querySelector(`#arrows-svg .arrow.${cls}`);
          a.style.transition = "transform 0.55s cubic-bezier(0.3, 0, 0.7, 1)";
          a.style.transform = `translate(${tx}px, ${ty}px) rotate(${rot}deg)`;
          if (bounce)
            setTimeout(() => {
              a.style.transition = "transform 0.9s ease, opacity 0.9s ease";
              a.style.transform = `translate(${tx - 90}px, ${ty + 70}px) rotate(${rot - 38}deg)`;
              a.style.opacity = "0.3";
            }, 620);
        };
        setTimeout(() => fly("a1", 575, 160, 14, true), 200);
        setTimeout(() => fly("a2", 572, 205, -4, true), 900);
        setTimeout(() => {
          fly("a3", 585, 270, -18, false);
          setTimeout(() => document.querySelector("#arrows-svg .crack").classList.add("show"), 600);
        }, 1700);
      }
      if (b === 2) document.querySelector("#arrows-svg .crack").classList.add("gold");
      if (b === 3) {
        const card = sec.querySelector(".finding-card");
        card.classList.remove("binned");
        setTimeout(() => card.classList.add("binned"), 3600); // room to read it aloud first
      }
    },

    "sc-assembly": (sec, b) => {
      if (b === 0) buildAssembly();
      if (b === 1) {
        const slots = { vessel: [400, 132], badge: [486, 210], film: [400, 292], arrow: [314, 210] };
        for (const [k, [x, y]] of Object.entries(slots)) {
          const icon = document.querySelector(`#assembly-svg .asm-${k}`);
          icon.style.transform = `translate(${x}px, ${y}px)`;
        }
        document.querySelector("#assembly-svg .shell-path").classList.add("drawn");
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
        svg.querySelector(".gate-dot").setAttribute("fill", getComputedStyle(document.documentElement).getPropertyValue("--zone-green"));
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

    "sc-squeeze": (sec, b) => {
      if (b === 0) {
        if (!state.vSqueeze) state.vSqueeze = makeVessel(document.getElementById("vessel-squeeze"));
        state.vSqueeze.reset();
        state.vSqueeze.setFill([
          { kind: "system", pct: 8 },
          { kind: "chat", pct: 16 },
          { kind: "tool", pct: 26 },
          { kind: "chat", pct: 8 },
          { kind: "tool", pct: 20 },
        ]);
      }
      if (b === 1)
        state.vSqueeze.squeeze({
          chips: [
            "depth is in fathoms, not feet",
            "user prefers tabs",
            "FishManager → CatchService",
            "DON'T touch prod config",
          ],
        });
    },
  };

  function setCoins(n) {
    const el = document.getElementById("coin-count");
    if (el) el.textContent = n;
  }

  /* ---------- scene-specific SVG builders ---------- */

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

  function buildArrows() {
    const svg = document.getElementById("arrows-svg");
    svg.innerHTML = "";
    /* the spec, standing like a target */
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

  function buildAssembly() {
    const svg = document.getElementById("assembly-svg");
    svg.innerHTML = "";
    el("circle", { class: "engine-core", cx: 400, cy: 210, r: 46 }, svg);
    el("rect", { class: "shell-path", x: 268, y: 96, width: 264, height: 228, rx: 26 }, svg);

    const dim = cssVar("--parch-dim");
    const mk = (cls, start) => {
      const icon = el("g", { class: "asm-icon asm-" + cls }, svg);
      icon.style.transform = `translate(${start[0]}px, ${start[1]}px)`;
      return icon;
    };
    const vessel = mk("vessel", [80, 60]);
    el("rect", { x: -13, y: -27, width: 26, height: 54, rx: 4, fill: "none", stroke: dim }, vessel);
    el("rect", { x: -10, y: 10, width: 20, height: 14, fill: "#3a3f4c" }, vessel);
    el("rect", { x: -10, y: 0, width: 20, height: 8, fill: cssVar("--blue-deep") }, vessel);

    const badge = mk("badge", [720, 80]);
    el("rect", { x: -5, y: -15, width: 10, height: 30, rx: 3, fill: cssVar("--ochre-deep") }, badge);

    const film = mk("film", [90, 380]);
    for (const x of [-21, -4, 13]) el("rect", { x, y: -9, width: 12, height: 18, rx: 2, fill: "none", stroke: dim }, film);

    const arrow = mk("arrow", [710, 370]);
    el("line", { x1: -20, y1: 0, x2: 16, y2: 0, stroke: cssVar("--blue") }, arrow);
    el("path", { d: "M 16 0 l -9 -5 M 16 0 l -9 5", stroke: cssVar("--blue"), fill: "none" }, arrow);
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
  }

  function advance() {
    const sec = sections[idx];
    if (beat < maxBeats(sec)) {
      beat++;
      applyBeats(sec);
      fireHook(sec);
    } else {
      show(idx + 1);
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
      e.preventDefault();
      advance();
    } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
      e.preventDefault();
      show(idx - 1);
    } else if (e.key === "Home") {
      show(0);
    } else if (e.key === "End") {
      show(sections.length - 1);
    } else if (e.key === "b" || e.key === "B") {
      blank.classList.toggle("on");
    }
  });

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
