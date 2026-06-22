# Phase-2 De-risk: stream-json incremental flush to a redirected file

VERDICT: PASS

**Implementation rider (operator decision at the gate):** PASS is conditioned on adding
`--include-partial-messages` to the orchestrator invocation alongside
`--output-format=stream-json --verbose`. Without that flag the signal is *event-granular*
(safe, but with a multi-second-to-minutes silence window during a single long message);
with it the signal is *chunk-granular* (continuous growth during generation). The robust
form is bundled into this lifecycle rather than deferred — see Decision below.

## Question (spec Req 12)

Does `--output-format=stream-json` written to a *redirected file* (the runner uses
`open(stdout_path, "wb")`, runner.py:1481 — a regular, non-TTY file) advance `mtime`/`size`
**mid-stream**, or does Claude Code Issue #25670 (block-buffering ~4–8 KB to a non-TTY
stdout) make it inert until process exit?

## Method

Spawned a real `claude -p` exactly as the runner does — regular-file stdout, `stdin=DEVNULL`,
`start_new_session=True`, `--max-turns 1`, `--dangerously-skip-permissions` — but with
`--output-format=stream-json --verbose`, and polled the redirected file's `os.path.getsize`
every 0.5 s while the process was still alive (`proc.poll() is None`). The prompt forced a
long single-turn text generation (a 200-item trivia list ⇒ tens of KB) so the test spans
many buffer windows and represents real orchestrator output volume, not a sub-buffer toy.
Two runs: (A) plain stream-json; (B) stream-json + `--include-partial-messages`.

## Findings

**Run A — plain `--output-format=stream-json` (event-granular):**
The file is NOT block-buffered-until-exit (#25670's worst case is refuted): it flushed the
system/init/thinking events early — `0 → 7216 B (≈4.5 s) → 9628 B (≈9.5 s)`. But it then sat
**static at 9628 B for ~100 s** while the model generated the 29 KB assistant message, and
flushed the remainder (→ 69153 B) only at turn completion. NDJSON inspection explains why:
`claude -p --output-format=stream-json` emits each event when it *completes* — the assistant
text arrives as **one atomic event** (one 29179-byte NDJSON line), so its entire ~100 s
generation produced zero file activity. The growth signal tracks **event boundaries**
(system events, thinking blocks, tool_use/tool_result, the terminal result), not tokens.

**Run B — `--output-format=stream-json --verbose --include-partial-messages` (chunk-granular):**
The same long message now grows the file **continuously** during generation — directly
observed at a steady ~465 B every 2 s (~232 B/s) across the whole assistant-text phase,
with no plateau. Final tally: 209 distinct file-growth events over the run, and a
**maximum silence gap of 9.05 s** (the longest the file went without advancing at any point,
including pre-generation setup) — versus the 1800 s STALL_TIMEOUT, a ~200× margin.
`--include-partial-messages` emits partial message chunks as they arrive, converting the
signal from event-granular to chunk-granular.

## Interpretation for the watchdog (STALL_TIMEOUT = 1800 s, ceiling = 14400 s)

- Plain stream-json (Run A) is *adequate but not robust*: a real agentic orchestrator emits
  tool_use/tool_result/turn events constantly, so file growth normally recurs every few
  seconds-to-minutes — comfortably under 1800 s. The residual risk is a pathological single
  long message / extended-thinking block with no intervening events; the observed ~100 s
  worst case is ~18× under the timeout, but a maximal single message is a (narrow, bounded)
  exposure.
- `--include-partial-messages` (Run B) **removes that exposure**: the file advances during
  the message itself, so the watchdog resets continuously through any long single generation.
  This is strictly the right signal for a watchdog whose whole purpose is "don't kill
  productive work."

## Decision

PASS **with `--include-partial-messages`**. Operator delegated the gate call and preferred
bundling the robust fix into this lifecycle rather than filing a follow-up. The flag is
parser-compatible — the terminal `type:"result"` object is still present and shape-identical,
so Task 5's "select the last `type == result` NDJSON line" approach is unaffected; the parser
simply skips the additional `stream_event`/partial-message lines.

### Rider for Tasks 5 & 6 (de-risk PASS branch)

- **Task 6** (orchestrator flag flip, runner.py ~1492): change `--output-format=json` →
  `--output-format=stream-json` **and add `--verbose` and `--include-partial-messages`**
  (stream-json in `-p` mode requires `--verbose`). Wire the orchestrator watchdog's
  `activity_probe` over `stdout_path`.
- **Task 5** (orchestrator telemetry parser, runner.py:1546 + call-site read at 2736): select
  the **last** NDJSON line whose `type == "result"`; ignore `stream_event`/partial-message
  and other non-result lines. Multi-line fixture must include partial-message lines plus a
  decoy non-terminal `result`-shaped line so the test discriminates "last terminal result".

## Mechanism note (why not PTY)

The ~100 s Run-A silence is Claude Code emitting the assistant message as one application-level
event, **not** libc stdout buffering — so a PTY / `unbuffer` wrapper would not have fixed it
(it changes buffer flushing, not when claude writes the event). `--include-partial-messages`
is the correct lever because it changes *what* claude emits (incremental chunks), not how the
bytes are buffered on the way to the file.
