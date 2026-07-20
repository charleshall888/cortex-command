/* Context bar: the deck's recurring literacy object. A zone-banded gauge
   that sits under a mock terminal (h≈14) or stands alone (big). Fill color
   crosses green → amber → red live as the value animates, so "six hours"
   can be compressed into a three-second sweep the audience watches. */

function makeContextBar(container, opts = {}) {
  const h = opts.h || 14;
  const marker = "marker" in opts ? opts.marker : 50;

  const root = document.createElement("div");
  root.className = "cbar" + (opts.big ? " big" : "");
  root.innerHTML =
    (opts.label !== "" ? `<span class="cbar-label">${opts.label || "context"}</span>` : "") +
    `<span class="cbar-track" style="height:${h}px"><span class="cbar-fill"></span>` +
    (marker != null ? `<span class="cbar-marker" style="left:${marker}%"></span>` : "") +
    `</span>` +
    (opts.readout === false ? "" : `<span class="cbar-pct">0%</span>`);
  container.appendChild(root);

  const fill = root.querySelector(".cbar-fill");
  const pctEl = root.querySelector(".cbar-pct");
  let value = 0;
  let painted = 0; // where the fill visibly IS — a canceled animation resumes from here, never from the stale target
  let raf = null;

  function paint(v) {
    v = Math.max(0, Math.min(100, v));
    painted = v;
    fill.style.width = v + "%";
    fill.classList.toggle("cb-green", v < 30);
    fill.classList.toggle("cb-amber", v >= 30 && v < 50);
    fill.classList.toggle("cb-red", v >= 50);
    if (pctEl) pctEl.textContent = Math.round(v) + "%";
  }

  function set(pct, { ms = 1200 } = {}) {
    if (raf) cancelAnimationFrame(raf);
    const from = painted;
    value = pct;
    if (ms <= 0) return paint(pct);
    const start = performance.now();
    function frame(now) {
      const t = Math.min(1, Math.max(0, (now - start) / ms));
      const eased = t * (2 - t); // ease-out
      paint(from + (pct - from) * eased);
      if (t < 1) raf = requestAnimationFrame(frame);
    }
    raf = requestAnimationFrame(frame);
  }

  function flash() {
    root.classList.remove("cbar-flash");
    requestAnimationFrame(() => root.classList.add("cbar-flash"));
  }

  paint(0);
  if (opts.pct) set(opts.pct, { ms: 0 });

  return { el: root, set, flash, get: () => value };
}
