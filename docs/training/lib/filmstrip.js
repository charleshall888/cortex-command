/* The filmstrip: a conversation as a timeline you can fork and rewind.
   This component is the seed of the wave-2 Cockpit engine.
   The rewind is the deck's wonder bet: one unbroken take — stillness,
   then scrub, shear, gravity, the track thins, the agent straightens. */

function makeFilmstrip(container) {
  const ns = "http://www.w3.org/2000/svg";
  const W = 1180;
  const H = 420;
  const TRACK_Y = 190;
  const SEG_W = 24;
  const SEG_H = 42;
  const GAP = 7;
  const X0 = 70;

  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", "100%");
  container.appendChild(svg);

  const g = {
    ghosts: document.createElementNS(ns, "g"),
    segs: document.createElementNS(ns, "g"),
    fx: document.createElementNS(ns, "g"),
  };
  svg.appendChild(g.ghosts);
  svg.appendChild(g.segs);
  svg.appendChild(g.fx);

  const segs = []; // {rect, cls}
  const FORK_AT = 6; // fork departs after this many base segments

  function segX(i) {
    return X0 + i * (SEG_W + GAP);
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function addSeg(cls, animate = true) {
    const i = segs.length;
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("class", "seg " + cls);
    rect.setAttribute("x", segX(i));
    rect.setAttribute("y", TRACK_Y - SEG_H / 2);
    rect.setAttribute("width", SEG_W);
    rect.setAttribute("height", SEG_H);
    rect.setAttribute("rx", 4);
    if (animate) {
      rect.style.opacity = "0";
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          rect.style.transition = "opacity 0.35s ease";
          rect.style.opacity = "1";
        })
      );
    }
    g.segs.appendChild(rect);
    segs.push({ rect, cls });
    return rect;
  }

  /* load bar: the track's thickness — how much the next turn re-reads */
  const loadBar = document.createElementNS(ns, "rect");
  loadBar.setAttribute("class", "load-bar");
  loadBar.setAttribute("x", X0);
  loadBar.setAttribute("y", TRACK_Y + SEG_H / 2 + 26);
  loadBar.setAttribute("height", 6);
  loadBar.setAttribute("width", 0);
  loadBar.setAttribute("rx", 3);
  svg.appendChild(loadBar);

  function setLoad() {
    loadBar.style.transition = "width 0.5s ease";
    loadBar.setAttribute("width", Math.max(0, segX(segs.length) - X0 - GAP));
  }

  /* the load bar names itself — it is the context gauge, lying on its side */
  const loadLabel = document.createElementNS(ns, "text");
  loadLabel.setAttribute("class", "load-label");
  loadLabel.setAttribute("x", X0);
  loadLabel.setAttribute("y", TRACK_Y + SEG_H / 2 + 52);
  loadLabel.textContent = "next turn re-reads this much";
  loadLabel.style.opacity = "0";
  svg.appendChild(loadLabel);

  /* playhead */
  const playhead = document.createElementNS(ns, "g");
  playhead.setAttribute("class", "playhead");
  const phLine = document.createElementNS(ns, "line");
  phLine.setAttribute("y1", TRACK_Y - SEG_H / 2 - 18);
  phLine.setAttribute("y2", TRACK_Y + SEG_H / 2 + 14);
  const phGrip = document.createElementNS(ns, "path");
  playhead.appendChild(phLine);
  playhead.appendChild(phGrip);
  svg.appendChild(playhead);

  function setPlayhead(x, transitionMs = 0) {
    playhead.style.transition = transitionMs ? `transform ${transitionMs}ms cubic-bezier(0.5, 0, 0.4, 1)` : "none";
    playhead.style.transform = `translateX(${x}px)`;
    phLine.setAttribute("x1", 0);
    phLine.setAttribute("x2", 0);
    phGrip.setAttribute("d", `M -7 ${TRACK_Y - SEG_H / 2 - 30} L 7 ${TRACK_Y - SEG_H / 2 - 30} L 0 ${TRACK_Y - SEG_H / 2 - 16} Z`);
  }

  /* ---------- beats ---------- */

  async function populate() {
    for (let i = 0; i < FORK_AT + 1; i++) {
      addSeg("seg-base");
      await sleep(140);
    }
    setLoad();
    setPlayhead(segX(segs.length) - GAP / 2, 0);
    loadLabel.style.transition = "opacity 0.8s ease";
    loadLabel.style.opacity = "0.7";
  }

  async function fork() {
    /* a ghost lane branches up-right, explores, and hands one answer back */
    const fx = segX(FORK_AT) + SEG_W / 2;
    for (let i = 1; i <= 4; i++) {
      const gr = document.createElementNS(ns, "rect");
      gr.setAttribute("class", "seg seg-ghost");
      gr.setAttribute("x", fx + i * 30);
      gr.setAttribute("y", TRACK_Y - SEG_H / 2 - i * 34);
      gr.setAttribute("width", SEG_W);
      gr.setAttribute("height", SEG_H);
      gr.setAttribute("rx", 4);
      gr.style.opacity = "0";
      g.ghosts.appendChild(gr);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          gr.style.transition = "opacity 0.4s ease";
          gr.style.opacity = "0.28";
        })
      );
      await sleep(220);
    }
    /* the answer comes home; the main lane never carried the exploration */
    const token = document.createElementNS(ns, "circle");
    token.setAttribute("class", "fork-token");
    token.setAttribute("r", 6);
    token.setAttribute("cx", fx + 4 * 30 + SEG_W / 2);
    token.setAttribute("cy", TRACK_Y - SEG_H / 2 - 4 * 34 + SEG_H / 2);
    g.fx.appendChild(token);
    await sleep(300);
    token.style.transition = "cx 1.1s ease, cy 1.1s ease";
    token.setAttribute("cx", fx);
    token.setAttribute("cy", TRACK_Y);
    setTimeout(() => token.remove(), 1600);
  }

  async function badRun() {
    for (let i = 0; i < 9; i++) {
      addSeg("seg-red");
      setLoad();
      setPlayhead(segX(segs.length) - GAP / 2, 200);
      await sleep(170);
    }
  }

  /* THE unbroken take. Full stillness first; then everything in one motion. */
  async function rewind() {
    await sleep(900); // stillness — let the room settle before the shot

    const reds = segs.filter((s) => s.cls === "seg-red");
    const forkX = segX(FORK_AT + 1) - GAP / 2;
    const totalMs = 2400;

    /* the label taught its lesson back at populate; clear the note's landing strip */
    loadLabel.style.transition = "opacity 0.8s ease";
    loadLabel.style.opacity = "0";

    setPlayhead(forkX, totalMs);

    reds.reverse().forEach((s, i) => {
      setTimeout(() => {
        const x = parseFloat(s.rect.getAttribute("x"));
        s.rect.style.transition = "transform 1.4s cubic-bezier(0.4, 0, 0.7, 1), opacity 1.4s ease";
        s.rect.style.transformOrigin = `${x + SEG_W / 2}px ${TRACK_Y}px`;
        s.rect.style.transform = `translateY(${130 + (i % 3) * 24}px) rotate(${i % 2 ? 14 : -11}deg)`;
        s.rect.style.opacity = "0";

        /* rent you would have kept paying */
        const cent = document.createElementNS(ns, "text");
        cent.setAttribute("class", "cent");
        cent.setAttribute("x", x + SEG_W / 2);
        cent.setAttribute("y", TRACK_Y - SEG_H / 2 - 10);
        cent.textContent = "¢";
        g.fx.appendChild(cent);
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            cent.style.transition = "transform 1.2s ease, opacity 1.2s ease";
            cent.style.transform = "translateY(-26px)";
            cent.style.opacity = "0";
          })
        );
        setTimeout(() => cent.remove(), 1400);
      }, (totalMs / reds.length) * i * 0.7);
    });

    /* the track thins as the wreckage falls */
    setTimeout(() => {
      loadBar.style.transition = `width ${totalMs * 0.7}ms ease`;
      loadBar.setAttribute("width", forkX - X0);
    }, 300);

    /* carry the lesson, not the tokens */
    setTimeout(() => {
      const midRedX = segX(FORK_AT + 5);
      const note = document.createElementNS(ns, "g");
      note.setAttribute("class", "note");
      note.innerHTML =
        `<rect x="-16" y="-11" width="32" height="22" rx="3"></rect>` +
        `<path d="M 8 -11 L 16 -3" ></path>` +
        `<line x1="-10" y1="-3" x2="8" y2="-3"></line><line x1="-10" y1="3" x2="4" y2="3"></line>`;
      note.style.transform = `translate(${midRedX}px, ${TRACK_Y}px)`;
      g.fx.appendChild(note);
      note.style.transition = "transform 0.7s cubic-bezier(0.3, -0.4, 0.6, 1)";
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          note.style.transform = `translate(${(midRedX + forkX) / 2}px, ${TRACK_Y - 90}px) rotate(-6deg)`;
          setTimeout(() => {
            note.style.transition = "transform 0.7s cubic-bezier(0.4, 0, 0.7, 1.4)";
            note.style.transform = `translate(${forkX + 12}px, ${TRACK_Y + 88}px) rotate(0deg)`;
          }, 700);
        })
      );
      /* the lesson the note carries, in words — intent line #2 is born here */
      setTimeout(() => {
        const nt = document.createElementNS(ns, "text");
        nt.setAttribute("class", "note-text");
        nt.setAttribute("x", forkX + 34);
        nt.setAttribute("y", TRACK_Y + 93);
        nt.textContent = "single-player — cheating's allowed";
        nt.style.opacity = "0";
        nt.style.transition = "opacity 0.8s ease";
        g.fx.appendChild(nt);
        requestAnimationFrame(() => requestAnimationFrame(() => (nt.style.opacity = "1")));
      }, 1500);
    }, totalMs);

    /* drop the dead segments from the model's world entirely */
    setTimeout(() => {
      reds.forEach((s) => s.rect.remove());
      for (let i = segs.length - 1; i >= 0; i--) if (segs[i].cls === "seg-red") segs.splice(i, 1);
    }, totalMs + 1600);

    /* hold until the whole take (shear, note hop, cleanup) has landed,
       so a queued next beat can't start mid-shot */
    await sleep(totalMs + 2000);
  }

  async function cleanBranch() {
    for (let i = 0; i < 3; i++) {
      addSeg("seg-clean");
      setLoad();
      setPlayhead(segX(segs.length) - GAP / 2, 220);
      await sleep(240);
    }
  }

  function reset() {
    g.ghosts.innerHTML = "";
    g.segs.innerHTML = "";
    g.fx.innerHTML = "";
    segs.length = 0;
    loadBar.setAttribute("width", 0);
    loadLabel.style.opacity = "0";
    setPlayhead(X0, 0);
  }

  return { populate, fork, badRun, rewind, cleanBranch, reset };
}
