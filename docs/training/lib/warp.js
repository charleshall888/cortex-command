/* Fast-forward. A deep link, a map jump, and every step back land the same
   way: reload at #N.b and replay beats 0..b. A fresh page is the one landing
   that is always clean, because a scene's beats are async chains that can't
   be cancelled mid-flight. Replayed at talk speed, though, that is seconds of
   animation the room has already watched.

   So the replay runs under the water, SPEED times faster: timers, the clock
   the rAF animations read, and every CSS animation inside the deck. The page
   loads with html.ff (set in the head, before first paint), which keeps the
   deck hidden until the replay settles; then it surfaces on the finished beat.

   Loaded before every other script. The sky is left at real speed, so the
   moon's glide and the stars never jump. */

const warp = (() => {
  const SPEED = 40;
  const realNow = performance.now.bind(performance);
  const realTimeout = window.setTimeout.bind(window);
  const realClear = window.clearTimeout.bind(window);
  const realRaf = window.requestAnimationFrame.bind(window);

  let on = false;
  let base = 0; // real time when fast-forward began
  let offset = 0; // warped time at that moment
  let skew = 0; // warped time runs this far ahead of real once it ends

  const toWarped = (t) => (on ? offset + (t - base) * SPEED : t + skew);
  performance.now = () => toWarped(realNow());
  let frameAsks = 0; // a frame-by-frame animation (the context bars, the vessel) asks once a frame
  window.requestAnimationFrame = (cb) => {
    if (on) frameAsks++;
    return realRaf((t) => cb(toWarped(t)));
  };

  /* timers: shortened while on. Short ones skip the browser's 4ms clamp on
     nested timers via a message tick — the terminals type a character every
     14ms, and 4ms a character would still be seconds of typing. */
  let pending = 0;
  let nextId = -1;
  const live = new Map(); // fake id → run, for message-tick timers
  const tick = new MessageChannel();
  tick.port1.onmessage = (e) => {
    const run = live.get(e.data);
    if (run) run();
  };

  window.setTimeout = (fn, delay = 0, ...args) => {
    if (!on) return realTimeout(fn, delay, ...args);
    pending++;
    let done = false;
    const run = () => {
      if (done) return;
      done = true;
      pending--;
      live.delete(id);
      fn(...args);
    };
    const ms = delay / SPEED;
    let id;
    if (ms < 4) {
      id = nextId--;
      live.set(id, run);
      tick.port2.postMessage(id);
    } else {
      id = realTimeout(run, ms);
      live.set(id, run);
    }
    return id;
  };

  window.clearTimeout = (id) => {
    const run = live.get(id);
    if (run) {
      live.delete(id);
      pending--;
    }
    if (id > 0) realClear(id);
  };

  /* CSS animations and transitions: sped up frame by frame as they appear */
  const inDeck = (a) => {
    const t = a.effect && a.effect.target;
    return !!t && t.id !== "deck" && !t.closest("#sky");
  };
  const finite = (a) => a.effect && Number.isFinite(a.effect.getComputedTiming().endTime);

  function pump() {
    if (!on) return;
    document.getAnimations().forEach((a) => {
      if (a.playbackRate !== SPEED && inDeck(a)) a.playbackRate = SPEED;
    });
    realRaf(pump);
  }

  function start() {
    if (on) return;
    base = realNow();
    offset = base + skew;
    on = true;
    pump();
  }

  /* a window the browser isn't painting gets no frames at all, so every
     wait here also ends on a real timer — the deck must surface regardless */
  const frame = () => new Promise((r) => (realRaf(r), realTimeout(r, 50)));
  const within = (p, ms) => Promise.race([p, new Promise((r) => realTimeout(r, ms))]);

  /* resolves once the replay has nothing left to play: the scene chains
     are done, no shortened timer is waiting, no frame-by-frame animation is
     still asking for frames, no deck CSS animation is running */
  async function settle(chains) {
    const t0 = realNow();
    const CAP = 6000;
    while (realNow() - t0 < CAP) {
      await within(Promise.all(Object.values(chains)), CAP - (realNow() - t0));
      const asks = frameAsks;
      await frame();
      await frame();
      const busy = pending > 0 || frameAsks !== asks || document.getAnimations().some((a) => inDeck(a) && finite(a) && a.playState === "running");
      if (!busy) break;
    }
    document.getAnimations().forEach((a) => {
      if (!inDeck(a)) return;
      if (finite(a) && a.playState === "running") a.finish();
      a.playbackRate = 1;
    });
    skew = toWarped(realNow()) - realNow();
    on = false;
  }

  return { start, settle };
})();
