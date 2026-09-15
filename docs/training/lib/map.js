/* The map: NIGHTLINE's pause screen. Press m anywhere in the talk and the
   slide sinks under the water, the dock rises out of it, and every section
   stands in a column over the post it builds. The dock is drawn exactly as
   far as the talk has built it (posts light once their waypoint card has
   been reached, the plank once Friday has run), and anything past the
   furthest point reached stays fogged — the room sees the talk's shape,
   never its later titles.

   Resume never calls show(): the scene underneath kept running, so scene
   and beat are exactly where they were. A jump reloads the page at #N.b
   behind a fade to night — a scene's beats are async chains that can't be
   cancelled mid-flight, so leaving one half-played and coming back leaves
   stale DOM. A fresh page is the one landing that is always clean, and it
   is the same path deep links already take. */

function makeMap({ sections, getPos, maxBeats, moonAt, onChange }) {
  const STORE = "nightline-map";
  const REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.getElementById("map");
  const moon = document.querySelector("#sky .sky-moon");

  let saved = {};
  try {
    saved = JSON.parse(sessionStorage.getItem(STORE) || "{}");
  } catch (e) {}
  /* a cold load of the title card is the start of a talk: the fog comes back.
     Deep links and map jumps carry a hash, so they keep what was reached. */
  let furthest = /^#\d/.test(location.hash || "") ? saved.furthest || 0 : 0;
  if (!furthest) persist();
  let open = false;
  let going = false;
  let sel = 0;
  let selBeat = 0;

  /* ---------- groups: the shore, three posts, the far end ---------- */

  const groups = [];
  sections.forEach((sec, i) => {
    if (sec.dataset.navGroup || !groups.length) groups.push({ label: sec.dataset.navGroup || "", items: [], post: -1 });
    const g = groups[groups.length - 1];
    g.items.push(i);
    if (sec.classList.contains("proverb")) g.post = i;
  });

  /* keep "4:00 PM" on one line */
  const nbsp = (t) => t.replace(/(\d) (AM|PM)/g, "$1\u00a0$2");

  function headline(sec) {
    const h = sec.querySelector(".scene-title, .card.proverb > p.serif, .request, .subtitle");
    if (!h) return "";
    const c = h.cloneNode(true);
    c.querySelectorAll("br").forEach((br) => br.replaceWith(" ")); // proverbs break their line with <br/>
    return nbsp(c.textContent.replace(/\s+/g, " ").trim());
  }

  /* ---------- build ---------- */

  root.innerHTML =
    '<div class="map-head mono"><span class="map-tag">NIGHTLINE · paused</span>' +
    '<span class="map-keys">← → choose · ↑ ↓ beat · enter go · m resume</span>' +
    '<button type="button" class="map-resume mono">resume</button></div>' +
    '<div class="map-body"></div>' +
    '<p class="map-cap serif"></p>' +
    '<div class="map-cursor"></div>';
  const body = root.querySelector(".map-body");
  const cap = root.querySelector(".map-cap");
  const cursor = root.querySelector(".map-cursor");
  root.querySelector(".map-resume").addEventListener("click", () => setOpen(false));
  body.style.setProperty("--cols", groups.length);

  const tiles = [];
  const posts = [];
  const postCols = [];

  groups.forEach((g, c) => {
    const col = document.createElement("div");
    col.className = "map-col";
    col.style.gridColumn = c + 1;
    col.style.setProperty("--c", c);
    body.appendChild(col);
    g.items.forEach((i) => {
      const sec = sections[i];
      const t = document.createElement("button");
      t.type = "button";
      t.tabIndex = -1;
      t.className = "map-tile" + (sec.classList.contains("proverb") ? " proverb" : "");
      t.innerHTML =
        `<span class="mt-num mono">${i + 1}</span>` +
        `<span class="mt-label ${sec.classList.contains("proverb") ? "serif" : ""}">${nbsp(sec.dataset.nav || sec.dataset.title || "")}</span>` +
        `<span class="mt-pips"></span>`;
      const pips = t.querySelector(".mt-pips");
      for (let b = 0; b <= maxBeats(sec); b++) pips.appendChild(document.createElement("i"));
      t.addEventListener("pointermove", (e) => {
        if (e.pointerType === "mouse" && sel !== i) select(i, 0);
      });
      t.addEventListener("click", () => {
        if (sel !== i) select(i, 0);
        go();
      });
      col.appendChild(t);
      tiles[i] = t;
    });

    if (g.post >= 0) {
      const p = document.createElement("div");
      p.className = "map-post";
      p.style.gridColumn = c + 1;
      p.style.setProperty("--k", posts.length);
      body.appendChild(p);
      posts.push({ el: p, at: g.post });
      postCols.push(c);
    }
    const lab = document.createElement("p");
    lab.className = "map-group mono";
    lab.style.gridColumn = c + 1;
    lab.style.setProperty("--c", c);
    /* shore and far-end labels keep an empty badge slot so every name sits on one line */
    lab.innerHTML = `<span class="habit-num mono"${g.post >= 0 ? "" : ' style="visibility:hidden"'}>${g.post >= 0 ? posts.length : ""}</span><span>${g.label}</span>`;
    if (g.post >= 0) lab.dataset.post = g.post;
    body.appendChild(lab);
  });

  const plank = document.createElement("div");
  plank.className = "map-plank";
  if (postCols.length) plank.style.gridColumn = `${postCols[0] + 1} / ${postCols[postCols.length - 1] + 2}`;
  body.appendChild(plank);
  const water = document.createElement("div");
  water.className = "map-water";
  body.appendChild(water);
  const finale = sections.findIndex((s) => s.id === "sc-finale");

  /* ---------- state ---------- */

  function persist(extra) {
    try {
      sessionStorage.setItem(STORE, JSON.stringify({ furthest, ...extra }));
    } catch (e) {}
  }

  function noteShown(idx) {
    if (idx > furthest) {
      furthest = idx;
      persist();
    }
  }

  function paint() {
    const { idx, beat } = getPos();
    tiles.forEach((t, i) => {
      t.classList.toggle("here", i === idx);
      t.classList.toggle("seen", i <= furthest);
      t.classList.toggle("fog", i > furthest);
      t.classList.toggle("sel", i === sel);
      const lit = i === sel ? selBeat : i === idx ? beat : -1;
      t.querySelectorAll(".mt-pips i").forEach((p, b) => {
        p.className = b < lit ? "done" : b === lit ? "now" : "";
      });
    });
    posts.forEach((p) => p.el.classList.toggle("lit", furthest >= p.at));
    body.querySelectorAll(".map-group[data-post]").forEach((l) => l.classList.toggle("lit", furthest >= +l.dataset.post));
    plank.classList.toggle("drawn", finale >= 0 && furthest > finale);
  }

  /* layout offsets, not bounding rects: the tiles are mid-entrance
     (translated) when the map opens, and the ring must land where they settle */
  function place(snap) {
    const t = tiles[sel];
    let x = 0;
    let y = 0;
    for (let n = t; n && n !== root; n = n.offsetParent) {
      x += n.offsetLeft;
      y += n.offsetTop;
    }
    if (snap) cursor.style.transition = "none";
    cursor.style.width = t.offsetWidth + 12 + "px";
    cursor.style.height = t.offsetHeight + 8 + "px";
    cursor.style.transform = `translate(${x - 6}px, ${y - 4}px)`;
    if (snap) {
      void cursor.offsetWidth;
      cursor.style.transition = "";
    }
  }

  function moonTo(i) {
    if (!moon) return;
    const p = moonAt(i);
    moon.style.left = p.left;
    moon.style.top = p.top;
  }

  function select(i, b) {
    sel = Math.max(0, Math.min(sections.length - 1, i));
    selBeat = Math.max(0, Math.min(maxBeats(sections[sel]), b));
    const sec = sections[sel];
    /* a fogged section shows its own label once the presenter chooses it,
       but its headline stays unsaid — the scene gets to land it */
    cap.textContent = sel <= furthest ? headline(sec) : "";
    cap.classList.toggle("empty", !cap.textContent);
    paint();
    place();
    if (root.scrollHeight > root.clientHeight) tiles[sel].scrollIntoView({ block: "nearest" });
    moonTo(sel);
    onChange();
  }

  /* ---------- open · resume · go ---------- */

  function setOpen(v) {
    if (going || open === v) return;
    open = v;
    const { idx, beat } = getPos();
    if (v) {
      sel = idx;
      selBeat = beat;
      tiles.forEach((t, i) => t.style.setProperty("--d", Math.min(Math.abs(i - idx), 10)));
      document.body.classList.add("map-open");
      select(idx, beat);
      place(true);
    } else {
      document.body.classList.remove("map-open");
      moonTo(idx);
      onChange();
    }
  }

  function go() {
    if (!open || going) return;
    const { idx, beat } = getPos();
    if (sel === idx && selBeat === beat) return setOpen(false);
    going = true;
    tiles.forEach((t, i) => t.style.setProperty("--d", Math.min(Math.abs(i - sel), 10)));
    document.body.classList.add("map-going");
    onChange();
    const r = moon ? moon.getBoundingClientRect() : null;
    persist({ jump: true, moon: moon ? { left: moonAt(sel).left, top: moonAt(sel).top } : null, from: r ? { x: r.left, y: r.top } : null });
    setTimeout(() => {
      history.replaceState(null, "", `#${sel + 1}.${selBeat}`);
      location.reload();
    }, REDUCED ? 0 : 900);
  }

  /* on arrival after a jump: the moon starts where it was left, then glides */
  function arrive() {
    if (!saved.jump) return false;
    persist();
    if (moon && saved.from) {
      moon.style.transition = "none";
      moon.style.left = saved.from.x + "px";
      moon.style.top = saved.from.y + "px";
      void moon.offsetWidth;
      moon.style.transition = "";
    }
    return true;
  }

  function handleKey(key) {
    if (key === "m" || key === "M") {
      setOpen(!open);
      return true;
    }
    if (!open) return false;
    if (going) return true;
    const { idx } = getPos();
    if (key === "Escape") setOpen(false);
    else if (key === "ArrowRight" || key === "PageDown") select(sel + 1, 0);
    else if (key === "ArrowLeft" || key === "PageUp") select(sel - 1, 0);
    else if (key === "ArrowDown") select(sel, selBeat + 1);
    else if (key === "ArrowUp") select(sel, selBeat - 1);
    else if (key === "Home") select(0, 0);
    else if (key === "End") select(sections.length - 1, 0);
    else if (key === "Enter" || key === " ") go();
    else if (key === "b" || key === "B") return false; // blanking still works over the map
    return true;
  }

  window.addEventListener("resize", () => open && place(true));

  return {
    handleKey,
    noteShown,
    arrive,
    setOpen,
    get open() {
      return open;
    },
    get furthest() {
      return furthest;
    },
    groups,
    state: () => (open ? { sel, beat: selBeat, title: sections[sel].dataset.nav || sections[sel].dataset.title, going } : null),
  };
}
