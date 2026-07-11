---
status: proposed
---

# Cortex-core SessionStart background-install healer

Date: 2026-07-11

Cortex-core ships a SessionStart-async hook — `hooks/cortex-cli-background-install.sh`
(canonical, mirrored into `plugins/cortex-core/hooks/` by `just build-plugin`)
plus a stdlib-only `plugins/cortex-core/install_core.py` — that **initiates** a
detached background reinstall of the cortex-command wheel when the installed
version drifts behind the pin. This reverses the deliberate `#235`/`#263`
decision that scoped the background-**install** pattern to the cortex-overnight
plugin only.

## Context and changed premise

`#235`/`#263` shipped the background-install pattern for cortex-overnight and
deliberately did **not** generalize it: at that time only the overnight runner
had a hard dependency on a specific installed wheel, and interactive sessions
tolerated a stale wheel because nothing they did required a particular verb
generation.

Epic 371 Phase C (the served `next`/`advance` lifecycle loop) changes that
premise. Cortex-core prose now depends on specific wheel verbs, and under
events-as-phase-authority (→ ADR-0001; the exit-gate cutover is ADR-0025) a
consumer whose installed wheel is skewed behind the plugin prose **cannot
advance** — the per-verb protocol check (spec R7/R11) halts the loop with a
remediation message until the wheel matches. Without a self-healing pathway,
that halt persists across every interactive session until the operator
manually reinstalls. The premise that justified overnight-only scope
("interactive sessions don't need a specific wheel") no longer holds, so the
scope decision is reopened on changed-premise grounds — not because
`#235`/`#263` were wrong when made.

## Decision

Port the background-**install** hook pattern (the installer, not the
visibility-only version-sync hook) to cortex-core:

- The canonical hook script `hooks/cortex-cli-background-install.sh` is
  plugin-agnostic — it loads `install_core` from `$CLAUDE_PLUGIN_ROOT` and
  calls `run_install_in_background()`. It is reused verbatim; cortex-core
  supplies its own `plugins/cortex-core/install_core.py` with a leaner
  `run_install_in_background()`.
- The reinstall is spawned detached (`subprocess.Popen(start_new_session=True)`)
  under a shared install flock at
  `${XDG_STATE_HOME}/cortex-command/install.lock`, so Claude Code launch never
  blocks on a network-bound install and concurrent initiators (either plugin)
  serialize.

### Skip predicates

`run_install_in_background()` consults four skip predicates in order; each
silent-skips:

1. **`CORTEX_AUTO_INSTALL=0`** — per-user opt-out.
2. **Probe failure** — `cortex --print-root --format json` is absent, exits
   non-zero, or emits non-JSON; drift cannot be computed, so skip (mirrors the
   loop's warn-only no-install posture).
3. **Recent failure sentinel** — a `session-install-failed.<ts>` file within a
   30-minute window; a persistent failure must not loop on every new session.
4. **Install-in-progress marker** — a fresh
   `${XDG_STATE_HOME}/cortex-command/install.in-progress` marker means a
   concurrent initiate is mid-spawn (markers older than 600s are stale and
   ignored).

## Healing semantics (stated honestly)

SessionStart only *initiates* an async reinstall. It does **not** guarantee the
wheel matches by the time any lifecycle verb runs this session. **The
correctness boundary remains the per-verb detect-and-halt** (spec R7/R11; the
loop-side halt lands with Tasks 13/19), not this healer and not any in-flight
guard. Healing is eventual: the drift closes over one or more sessions as the
reinstall completes; the loop stays halted-with-remediation until the served
payload's protocol falls back in range.

### Mid-session wheel replacement

A reinstall may replace the wheel while an interactive session is live. Both
outcomes are benign:

- **Cross-protocol replacement** — the served protocol integer moves out of the
  prose's compat range. The per-verb payload check halts on the *next* verb
  call with remediation; a mid-flight swap cannot corrupt state because the
  check runs per call, not once per session.
- **Same-protocol replacement** — the served protocol stays in range. By the
  protocol contract's definition (range-based compat, never exact-equality)
  such wheels are interchangeable, so the swap is transparent to the loop.

### In-flight guard deliberately not ported

The cortex-overnight port carries an in-flight-session guard that consults
`~/.local/share/overnight-sessions/active-session.json`. That guard tracks
*runner* sessions only; it has **no** awareness of interactive Claude Code
sessions. Porting it to cortex-core would give false assurance — it could not
detect the interactive sessions cortex-core actually runs in. It is therefore
omitted. Concurrent initiation is instead made benign by the install flock plus
`uv tool install --reinstall` idempotency, and — restating the boundary above —
the correctness guarantee is the per-verb check, explicitly **not** any
in-flight guard.

## Alternatives considered

- **Keep the overnight-only scope; require manual reinstall on skew** (status
  quo). Rejected: under events-authority a skewed interactive consumer is stuck
  halted until a human notices and reinstalls, defeating the served loop's
  goal of predictable, self-maintaining sequencing.
- **Synchronous blocking install at SessionStart.** Rejected: a network-bound
  `uv tool install` would freeze Claude Code launch for the duration; the
  detach property is load-bearing.
- **Make the healer the correctness boundary** (halt only if healing fails).
  Rejected: SessionStart initiate is best-effort and eventual; coupling
  correctness to it would reintroduce a race the per-verb check already closes
  cleanly.

## Consequences

- Reversing this decision means removing the cortex-core hook registration and
  `install_core.py` and reverting the `build-plugin` HOOKS wiring across the
  plugin mirror — a coordinated multi-file change, hence an ADR rather than a
  comment.
- Cortex-core now carries its own version pin (inlined in `install_core.py`,
  mirroring `plugins/cortex-overnight/cli_pin.py`). The two plugin pins are
  bumped together at release; a follow-up could consolidate them if drift
  becomes a maintenance cost.
- `install_core.py` is stdlib-only by the same constraint as the overnight
  copy (the bare-`python3` hook loader resolves no third-party deps), but is
  not covered by the overnight-specific pre-commit parity gate (Phase 1.97),
  which targets `plugins/cortex-overnight/` paths by name.

Back-references: `#235`, `#263` (the reversed scope decision); ADR-0001
(file-based state / events as the durable substrate that makes a skewed
consumer unable to advance); ADR-0025 (events-as-phase-authority, the exit-gate
cutover this healer serves).
