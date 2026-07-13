/* Context vessel: the deck's workhorse component.
   A tank that fills with layers (system prompt sediment, chat, tool
   results, spec), sweeps a scan line over everything each turn, tints
   zones, and compacts with visible loss. */

const VESSEL = { W: 320, H: 460, TX: 50, TY: 20, TW: 160, TH: 420 };

function makeVessel(container, opts = {}) {
  const box = document.createElement("div");
  box.className = "vessel-box";
  box.style.position = "relative";
  container.appendChild(box);

  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const scale = opts.scale || 1;
  svg.setAttribute("viewBox", `0 0 ${VESSEL.W} ${VESSEL.H}`);
  svg.setAttribute("width", VESSEL.W * scale);
  box.appendChild(svg);

  const tank = document.createElementNS(ns, "rect");
  tank.setAttribute("class", "vessel-tank");
  tank.setAttribute("x", VESSEL.TX);
  tank.setAttribute("y", VESSEL.TY);
  tank.setAttribute("width", VESSEL.TW);
  tank.setAttribute("height", VESSEL.TH);
  tank.setAttribute("rx", 10);
  svg.appendChild(tank);

  const layerGroup = document.createElementNS(ns, "g");
  svg.appendChild(layerGroup);
  const overlay = document.createElementNS(ns, "g");
  svg.appendChild(overlay);

  let layers = []; // {kind, pct, rect}

  const bottomY = () => VESSEL.TY + VESSEL.TH;
  const fillPct = () => layers.reduce((s, l) => s + l.pct, 0);
  const fillTopY = () => bottomY() - (fillPct() / 100) * VESSEL.TH;

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  function addLayerRect(kind, pct, animate) {
    const startY = fillTopY();
    const h = (pct / 100) * VESSEL.TH;
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("class", "layer-" + kind);
    rect.setAttribute("x", VESSEL.TX + 3);
    rect.setAttribute("width", VESSEL.TW - 6);
    rect.setAttribute("y", startY - h);
    rect.setAttribute("height", h);
    if (animate) {
      rect.setAttribute("y", startY);
      rect.setAttribute("height", 0);
      rect.style.transition = "y 0.8s ease, height 0.8s ease";
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          rect.setAttribute("y", startY - h);
          rect.setAttribute("height", h);
        })
      );
    }
    layerGroup.appendChild(rect);
    layers.push({ kind, pct, rect });
  }

  async function pour(list) {
    for (const l of list) {
      addLayerRect(l.kind, l.pct, true);
      await sleep(900);
    }
  }

  function setFill(list) {
    layerGroup.innerHTML = "";
    layers = [];
    for (const l of list) addLayerRect(l.kind, l.pct, false);
  }

  /* one full-height scan: bottom → top of tank, coins tick per fill passed */
  function sweep({ cached = false, onCoin = null, duration = 4000 } = {}) {
    return new Promise((resolve) => {
      if (cached) {
        for (const l of layers) {
          const y = parseFloat(l.rect.getAttribute("y"));
          const h = parseFloat(l.rect.getAttribute("height"));
          for (let hy = y + 6; hy < y + h; hy += 12) {
            const hl = document.createElementNS(ns, "line");
            hl.setAttribute("class", "hatch");
            hl.setAttribute("x1", VESSEL.TX + 6);
            hl.setAttribute("x2", VESSEL.TX + VESSEL.TW - 6);
            hl.setAttribute("y1", hy);
            hl.setAttribute("y2", hy - 6);
            overlay.appendChild(hl);
          }
        }
      }
      const line = document.createElementNS(ns, "line");
      line.setAttribute("class", "scanline");
      line.setAttribute("x1", VESSEL.TX + 2);
      line.setAttribute("x2", VESSEL.TX + VESSEL.TW - 2);
      overlay.appendChild(line);

      const yFrom = bottomY() - 2;
      const yTo = VESSEL.TY + 4;
      const start = performance.now();
      const filled = fillPct();
      const rate = cached ? 0.1 : 1; // cache reads at a deep discount
      function frame(now) {
        const t = Math.min(1, (now - start) / duration);
        const y = yFrom + (yTo - yFrom) * t;
        line.setAttribute("y1", y);
        line.setAttribute("y2", y);
        if (onCoin) {
          const pctPassed = Math.min(t * 100, filled);
          onCoin(Math.round(pctPassed * rate * 3));
        }
        if (t < 1) requestAnimationFrame(frame);
        else {
          setTimeout(() => line.remove(), 500);
          resolve();
        }
      }
      requestAnimationFrame(frame);
    });
  }

  /* zone bands measured from the bottom: green <30, amber 30–50, red >50 */
  function zones() {
    const bands = [
      { from: 0, to: 30, cls: "zone-green", label: "9AM", pct: "" },
      { from: 30, to: 50, cls: "zone-amber", label: "2PM", pct: "30%" },
      { from: 50, to: 100, cls: "zone-red", label: "4PM", pct: "50%" },
    ];
    const els = [];
    for (const b of bands) {
      const y = bottomY() - (b.to / 100) * VESSEL.TH;
      const h = ((b.to - b.from) / 100) * VESSEL.TH;
      const band = document.createElementNS(ns, "rect");
      band.setAttribute("class", "zone-band");
      band.setAttribute("x", VESSEL.TX + 2);
      band.setAttribute("width", VESSEL.TW - 4);
      band.setAttribute("y", y);
      band.setAttribute("height", h);
      band.setAttribute("fill", getComputedStyle(document.documentElement).getPropertyValue("--" + b.cls));
      overlay.appendChild(band);
      els.push(band);

      if (b.from > 0) {
        const rule = document.createElementNS(ns, "line");
        rule.setAttribute("class", "zone-rule");
        rule.setAttribute("x1", VESSEL.TX - 6);
        rule.setAttribute("x2", VESSEL.TX + VESSEL.TW + 6);
        rule.setAttribute("y1", bottomY() - (b.from / 100) * VESSEL.TH);
        rule.setAttribute("y2", bottomY() - (b.from / 100) * VESSEL.TH);
        overlay.appendChild(rule);
        els.push(rule);
      }

      const lbl = document.createElementNS(ns, "text");
      lbl.setAttribute("class", "zone-label");
      lbl.setAttribute("x", VESSEL.TX + VESSEL.TW + 12);
      lbl.setAttribute("y", bottomY() - (b.from / 100) * VESSEL.TH - 8);
      lbl.textContent = b.label;
      overlay.appendChild(lbl);
      els.push(lbl);

      if (b.pct) {
        const pct = document.createElementNS(ns, "text");
        pct.setAttribute("class", "zone-label zone-pct");
        pct.setAttribute("x", VESSEL.TX - 42);
        pct.setAttribute("y", bottomY() - (b.from / 100) * VESSEL.TH + 5);
        pct.textContent = b.pct;
        overlay.appendChild(pct);
        els.push(pct);
      }
    }
    /* exit door at the 50% line */
    const door = document.createElementNS(ns, "g");
    door.setAttribute("class", "exit-door");
    const dy = bottomY() - 0.5 * VESSEL.TH - 30;
    const dr = document.createElementNS(ns, "rect");
    dr.setAttribute("x", VESSEL.TX + VESSEL.TW + 44);
    dr.setAttribute("y", dy);
    dr.setAttribute("width", 22);
    dr.setAttribute("height", 34);
    dr.setAttribute("rx", 3);
    const knob = document.createElementNS(ns, "circle");
    knob.setAttribute("cx", VESSEL.TX + VESSEL.TW + 62);
    knob.setAttribute("cy", dy + 18);
    knob.setAttribute("r", 2.5);
    door.appendChild(dr);
    door.appendChild(knob);
    overlay.appendChild(door);
    els.push(door);

    requestAnimationFrame(() =>
      requestAnimationFrame(() => els.forEach((e) => e.classList.add("on")))
    );
  }

  /* compaction: piston descends, everything collapses to one amber stripe,
     and the specific things you cared about fall out the sides */
  async function squeeze({ chips = [] } = {}) {
    const piston = document.createElementNS(ns, "rect");
    piston.setAttribute("class", "piston");
    piston.setAttribute("x", VESSEL.TX + 3);
    piston.setAttribute("width", VESSEL.TW - 6);
    piston.setAttribute("y", VESSEL.TY - 16);
    piston.setAttribute("height", 20);
    piston.style.transition = "y 2.6s cubic-bezier(0.5, 0, 0.8, 0.4)";
    svg.appendChild(piston);

    const stripeH = 20;
    const pistonEndY = bottomY() - stripeH - 20;

    requestAnimationFrame(() =>
      requestAnimationFrame(() => piston.setAttribute("y", pistonEndY))
    );

    /* layers collapse */
    for (const l of layers) {
      l.rect.style.transition = "y 2.6s ease, height 2.6s ease, opacity 2.6s ease";
      l.rect.setAttribute("y", bottomY() - stripeH);
      l.rect.setAttribute("height", 0);
      l.rect.style.opacity = "0";
    }
    const stripe = document.createElementNS(ns, "rect");
    stripe.setAttribute("class", "layer-amber");
    stripe.setAttribute("x", VESSEL.TX + 3);
    stripe.setAttribute("width", VESSEL.TW - 6);
    stripe.setAttribute("y", bottomY() - 2);
    stripe.setAttribute("height", 0);
    stripe.style.transition = "y 2.6s ease, height 2.6s ease";
    layerGroup.appendChild(stripe);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        stripe.setAttribute("y", bottomY() - stripeH);
        stripe.setAttribute("height", stripeH);
      })
    );

    /* chips escape in a deterministic fan (left and up, away from the
       ghost-question side), stay readable, then dissolve */
    const FAN = [
      { dx: -185, dy: -40, rot: -5 },
      { dx: -285, dy: -140, rot: -8 },
      { dx: -165, dy: -235, rot: -4 },
      { dx: -270, dy: -330, rot: -9 },
    ];
    const rect = box.getBoundingClientRect();
    chips.forEach((text, i) => {
      setTimeout(() => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = text;
        chip.style.left = rect.width / 2 + "px";
        chip.style.top = rect.height * 0.6 + "px";
        box.appendChild(chip);
        const f = FAN[i % FAN.length];
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            chip.style.opacity = "1";
            chip.classList.add("fly");
            chip.style.transform = `translate(${f.dx}px, ${f.dy}px) rotate(${f.rot}deg)`;
            setTimeout(() => (chip.style.opacity = "0"), 2200);
          })
        );
      }, 400 + i * 420);
    });

    /* the piston did its job; get it out of the shot */
    setTimeout(() => {
      piston.style.transition = "y 1.2s ease, opacity 1.2s ease";
      piston.setAttribute("y", VESSEL.TY - 24);
      piston.style.opacity = "0";
      setTimeout(() => piston.remove(), 1300);
    }, 3100);

    await sleep(3000);
    layers = [{ kind: "amber", pct: (stripeH / VESSEL.TH) * 100, rect: stripe }];
  }

  function reset() {
    layerGroup.innerHTML = "";
    overlay.innerHTML = "";
    box.querySelectorAll(".chip").forEach((c) => c.remove());
    svg.querySelectorAll(".piston").forEach((p) => p.remove());
    layers = [];
  }

  return { box, svg, pour, setFill, sweep, zones, squeeze, reset, fillPct };
}
