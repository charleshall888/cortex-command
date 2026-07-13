/* Mock terminal: plays scripted session beats. Content is stylized but
   technically real (real prompt shapes, real diff hunks) — the sessions
   are scripted so they're clean and nobody's real code gets dunked on. */

function makeTerminal(container, opts = {}) {
  const term = document.createElement("div");
  term.className = "term";
  term.innerHTML =
    '<div class="term-bar"><span class="dot"></span><span class="dot"></span><span class="dot"></span>' +
    "<span>" + (opts.title || "claude") + "</span></div>" +
    '<div class="term-body"></div>';
  container.appendChild(term);
  const body = term.querySelector(".term-body");

  const CHAR_MS = 14; // typing speed
  const LINE_GAP = 260;

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  async function typeLine(cls, text) {
    const line = document.createElement("div");
    line.className = "term-line " + cls;
    body.appendChild(line);
    line.classList.add("caret");
    for (let i = 0; i < text.length; i++) {
      line.textContent = text.slice(0, i + 1);
      await sleep(CHAR_MS);
    }
    line.classList.remove("caret");
  }

  async function play(script) {
    body.innerHTML = "";
    for (const step of script) {
      if (step.pause) await sleep(step.pause);
      if (step.lines) {
        for (const l of step.lines) await typeLine(step.t, l);
      } else {
        await typeLine(step.t, step.text);
      }
      await sleep(step.gap ?? LINE_GAP);
    }
  }

  function clear() {
    body.innerHTML = "";
  }

  return { el: term, play, clear };
}
