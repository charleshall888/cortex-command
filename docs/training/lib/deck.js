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
        state.vScan.pour([
          { kind: "system", pct: 8 },
          { kind: "chat", pct: 10 },
          { kind: "tool", pct: 22 },
          { kind: "chat", pct: 6 },
          { kind: "tool", pct: 16 },
        ]);
      if (b === 2) state.vScan.sweep({ onCoin: setCoins }); // plays silent
      if (b === 3) state.vScan.sweep({ cached: true, onCoin: setCoins });
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
