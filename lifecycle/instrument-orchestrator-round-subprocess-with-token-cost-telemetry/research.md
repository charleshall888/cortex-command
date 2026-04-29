# Research: Instrument orchestrator-round subprocess with token-cost telemetry

## Codebase Analysis

### Files that will change

- **`cortex_command/overnight/runner.py`** — `_spawn_orchestrator` (line 682) is the spawn site. Currently `subprocess.Popen([...], stdout=PIPE, stderr=PIPE, ...)` with **no consumer of either pipe**: `_poll_subprocess` (line 1631) and `WatchdogThread` (`runner_primitives.py:115-133`) track liveness via `proc.poll()` only. There is no inline NOTIFY: stdout consumer (the only `NOTIFY:` reference in runner.py is line 235, which is the runner's own stderr fallback when `~/.claude/notify.sh` is absent). Two changes land here:
  1. Replace `stdout=PIPE` with a session-scoped file redirect (`stdout=open(session_dir/"orchestrator-round-N.stdout.json", "wb")`) to eliminate pipe-buffer deadlock — see Adversarial #2.
  2. Add `--output-format=json` to the argv. Read the file post-`proc.wait()`, parse `usage` + `total_cost_usd`, emit `dispatch_start`/`dispatch_complete` records via `pipeline.state.log_event` (not via `pipeline/dispatch.py` — see Adversarial #5).
  3. Stall branch (line 1636-1653) currently emits no `events.log` record of the failure — emit `dispatch_error` (or reuse `ORCHESTRATOR_FAILED` with `details.reason="stall_timeout"`) so orphan-start records do not silently accumulate in `pair_dispatch_events`'s FIFO queue.

- **`cortex_command/pipeline/dispatch.py`** — `Skill` Literal (line 156): add `"orchestrator-round"`. The runtime guard at line 432 (`if skill not in get_args(Skill): raise ValueError(...)`) is internal to `dispatch.py` and does not fire when records are emitted via `pipeline.state.log_event` from runner.py — but extending the Literal still keeps the canonical vocabulary in one place for static type-checking and documentation. No `dispatch_task` callsite passes `"orchestrator-round"`.

- **`cortex_command/pipeline/metrics.py`** — `compute_skill_tier_dispatch_aggregates` (line 624) requires no change. Bucket key `f"{skill},{tier}"` already produces an `"orchestrator-round,<tier>"` bucket from any record with that `skill` value. `discover_pipeline_event_logs` (line 270) already aggregates root `lifecycle/pipeline-events.log` plus all `lifecycle/sessions/*/pipeline-events.log`; session-scoped writes are auto-picked-up. **However** `pair_dispatch_events` (line 312) keys its FIFO queue by `feature` (line 377), so the orchestrator-round record must carry a stable feature value (see Adversarial #4 for sentinel choice).

- **Created** — `cortex_command/overnight/tests/test_orchestrator_round_telemetry.py` (or extension to existing test file): contract test that `_spawn_orchestrator` emits a `dispatch_start`/`dispatch_complete` pair into `<session_dir>/pipeline-events.log`, and that the aggregator surfaces an `orchestrator-round,<tier>` bucket end-to-end. Stall-branch test for the new failure event.

### Existing patterns to follow

1. **Pipeline-events emission from runner.py** — runner.py:1301-1318 already imports `from cortex_command.pipeline.state import log_event as pipeline_log_event` and writes a `pr_ready_failed` event into the pipeline events log. This is the precedent for the new dispatch-event emission. Bypasses the dispatch.py module entirely; no closed-Literal guard friction.
2. **Atomic JSONL writes** — `pipeline/state.py:288 log_event` is the canonical writer (auto-prepends `"ts"`, ensures parent dirs exist). Use this rather than ad-hoc `open(...)`.
3. **Per-session paths** — `feature_executor.py:595, 605, 636` uses `config.pipeline_events_path` for per-session pipeline writes. Match the convention: write to `<session_dir>/pipeline-events.log`, not the repo-root `lifecycle/pipeline-events.log`.
4. **Dispatch event field shape** (`dispatch.py:486-503` for `dispatch_start`; `561-567` for `dispatch_complete`):
   - `dispatch_start`: `event, feature, skill, attempt, escalated, escalation_event, complexity, criticality, model, effort, max_turns, max_budget_usd` (+ optional `cycle`).
   - `dispatch_complete`: `event, feature, cost_usd, duration_ms, num_turns`.
   - For orchestrator-round: omit `escalated`, `escalation_event`, `cycle` (n/a); set `complexity` from the round's tier; `criticality` defaults to `"medium"` per the criticality matrix at session scope.
5. **Cost capture from `--output-format=json`** — JSON envelope's `usage` exposes `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` separately, plus `total_cost_usd`, `duration_ms`, `num_turns` (Adversarial #7 confirmed empirically). Persist all four token fields plus `total_cost_usd` in the raw event so R11/R12-style prompt-cache comparisons can read them.
6. **Fire-and-forget telemetry contract** — per `docs/overnight-operations.md` `_write_activity_event` doc, "writes are fire-and-forget and swallow exceptions — activity logging never blocks or interrupts the agent." Match this contract: any json-parse / file-write exception in the new path must be swallowed with a stderr breadcrumb, not raised.

### Integration points and dependencies

- **`metrics.py` aggregator surface (no change required)**: `compute_skill_tier_dispatch_aggregates` consumes records from any of the auto-discovered `pipeline-events.log` files; emitting to `<session_dir>/pipeline-events.log` lands the new bucket with no metric-side code change.
- **`pair_dispatch_events` FIFO pairing**: keyed by `feature`. Within a single session, orchestrator rounds are sequential (`_spawn_orchestrator` is followed by `_poll_subprocess` to exit), so a single FIFO key works — but a stable sentinel (`feature="<orchestrator-round>"`) is safer than `None`, both for FIFO isolation and for downstream filters (Adversarial #3).
- **Dashboard cost source is `agent-activity.jsonl`** (`requirements/observability.md` Dashboard acceptance, line 34) — separate from `pipeline-events.log`. New session-scope records do not affect dashboard cost accumulation. `dashboard/data.py:1107-1115` reads only the *root* `lifecycle/pipeline-events.log` and skips records with empty `feature` — the new sentinel-feature records are silently ignored by the dashboard, which is acceptable (no double-count, no crash).
- **Watchdog vs subprocess stdout**: replacing `stdout=PIPE` with `stdout=open(...)` (file redirect) avoids both the pipe-buffer-fill deadlock and any reader-thread machinery. The watchdog's `proc.poll()` semantics are unchanged.
- **Ticket 111 R11/R12 closure** — `lifecycle/extract-overnight-orchestrator-round-state-read-into-bin-orchestrator-context/verification.md`: ticket 111 is `status: complete` (commits `ec55340` and `296e451`). R12 is documented as informational, not a close gate (per spec.md/plan.md). The inline-read prompt is **already retired** in main, so a live re-baseline of R11 against the original prompt is no longer obtainable. Comparison is method-divergent: 7,063 estimated tokens (4-char/token char-count estimate) vs. live `usage.input_tokens` from the new instrumentation — a separate ticket should frame this divergence explicitly rather than quietly substituting the new measurement (Adversarial #6).

## Web Research

### `claude -p` output formats (https://code.claude.com/docs/en/headless)

- `--output-format=text` (default): plain text.
- `--output-format=json`: end-of-run blob; envelope contains `result`, `session_id`, `usage{input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens}`, `total_cost_usd`, `duration_ms`, `num_turns`. Single object emitted at process exit.
- `--output-format=stream-json`: NDJSON; **requires `--verbose`**. Event types: `system/init`, `system/api_retry`, `system/plugin_install`, `assistant`, `user`, `stream_event` (only with `--include-partial-messages`), `result`. Per-message `usage` lives on assistant messages (`message.usage`); a final `result` event carries the cumulative envelope.

### Known issue — Claude Code CLI #1920

Final `{"type":"result",...}` event can be missing in stream-json mode after successful tool execution, causing hangs. **Load-bearing for design choice**: any stream-json implementation needs a fallback aggregating from per-message `usage` deltas. `--output-format=json` does not have this issue — it emits one envelope at exit.

### Subprocess teeing patterns (Python)

Canonical pattern for line-by-line stdout capture: `Popen(stdout=PIPE, bufsize=1, text=True)` + `for line in proc.stdout`. **Anti-pattern**: `proc.communicate()` blocks until EOF, incompatible with real-time consumption. ccusage demonstrates the established pattern of opportunistic `try: json.loads(line)` with malformed-line skip.

For ticket 153 specifically, **neither pattern is needed** because the runner does not consume orchestrator stdout in real time (Codebase analysis confirms). The simplest safe approach is **not PIPE at all** — redirect stdout to a session-scoped file via `stdout=open(...)`.

### Anthropic top-level-vs-sub-task telemetry pattern

`CLAUDE_CODE_ENABLE_TELEMETRY=1` + standard `OTEL_*` env vars emit per-session token consumption via OpenTelemetry; `TRACEPARENT`/`TRACESTATE` propagation links subagent spans to the orchestrator. **Implication**: Anthropic's documented model treats orchestrator-as-top-level-span and dispatched-tasks-as-child-spans — distributed tracing, not a parallel event channel. This is informational; cortex-command does not currently use OTel and ticket 153 stays inside the existing JSONL convention.

### Sources consulted

- [Run Claude Code programmatically (headless docs)](https://code.claude.com/docs/en/headless)
- [Stream responses in real-time (Agent SDK)](https://code.claude.com/docs/en/agent-sdk/streaming-output)
- [Issue #1920: Missing Final Result Event](https://github.com/anthropics/claude-code/issues/1920)
- [Issue #24594: --input-format stream-json undocumented](https://github.com/anthropics/claude-code/issues/24594)
- [ccusage (ryoppippi)](https://github.com/ryoppippi/ccusage)
- [claude_telemetry (TechNickAI)](https://github.com/TechNickAI/claude_telemetry)
- [Streaming Messages (Claude API)](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Claude Code Monitor: OpenTelemetry Setup](https://www.ai.cc/blogs/claude-code-monitor-2026-opentelemetry-tutorial-setup-guide/)

## Requirements & Constraints

### `requirements/project.md`

- **File-based state** (line 25): telemetry storage stays as plain-file JSONL.
- **Complexity must earn its place** (line 19): favors emitting via existing `pipeline.state.log_event` precedent over a new dispatch.py wrapper or a parallel session-scope channel.
- **Iterative improvement / Maintainability through simplicity** (lines 32-33): favor not adding parallel aggregation pipelines.

### `requirements/pipeline.md`

- **Session Orchestration acceptance criterion line 28**: "When `~/.claude/notify.sh` is absent, notifications fall back to stderr with a `NOTIFY:` prefix so stdout remains clean as the orchestrator agent's input channel." Interpretively load-bearing — see Open Questions for resolution. Adversarial concluded the phrasing most plausibly refers to the **runner's** stdout (snapshot-tested at `tests/fixtures/dry_run_reference.txt`), not the orchestrator subprocess's stdout. The recommended approach (file-redirect of the orchestrator subprocess's stdout) does not violate the requirement *as actually implemented*.
- **Atomic state writes** (line 21, line 126): JSONL writes use tempfile + `os.replace()` — `pipeline/state.py:288 log_event` already applies this pattern.
- **Audit trail convention** (line 129): `lifecycle/pipeline-events.log` is the append-only JSONL record of dispatch and merge events — the canonical surface for the new records.
- **Metrics and Cost Tracking** (lines 97-108, should-have): metrics computed from `lifecycle/*/events.log` JSONL streams. Frames metrics as **per-feature** — adding session-scope records is a data-model extension (not a conflict).

### `requirements/observability.md`

- **Notifications subsystem** (lines 42-51): NOTIFY: parsing is a runner-stderr concern; orchestrator subprocess stdout is unrelated to this subsystem.
- **Dashboard cost source is `agent-activity.jsonl`** (line 34): per-feature accumulation; new session-scope records do not double-count or conflict (dashboard's `parse_pipeline_dispatch` filters records with empty feature, so the sentinel-feature records are silently skipped).
- **Read-only consumers** (line 93): the runner is the writer; dashboard/statusline/notifications stay read-only.

### `requirements/multi-agent.md`

- **Cost accumulation is part of agent-spawn output contract** (line 17).
- **Resource constraints** (line 71): stderr capped at 100 lines, learnings truncated to 2000 chars — precedent for capping volumes (relevant if `--include-partial-messages` were chosen, which it is not).
- **Parallelism is orchestrator-owned** (line 74): orchestrator-round is structurally a session-scope agent, not a per-feature dispatch.

### `docs/overnight-operations.md` (authoritative per CLAUDE.md)

- **Round Loop** (lines 17-33): each round spawns a fresh `claude -p`; orchestrator is ephemeral per round; telemetry must capture per-round (not per-session-cumulative) usage.
- **`agent-activity.jsonl`** (lines 417-439): "writes are fire-and-forget and swallow exceptions — activity logging never blocks or interrupts the agent." **Telemetry contract precedent**: never block, swallow exceptions.
- **State File Locations** (lines 315-333): `lifecycle/sessions/{id}/pipeline-events.log` is per-session "Append-only JSONL of per-task dispatch/merge/test events." Session-scope orchestrator records co-exist with per-task records here.

### `docs/sdk.md`

- Orchestrator-round goes via `claude -p` subprocess (not via `claude_agent_sdk.query()`). Cannot use `ResultMessage.total_cost_usd` directly — must come from CLI output formats. Subscription billing fallback may report zero/missing cost values; aggregator must tolerate.

### Architectural constraints summary

- File-based state, atomic writes, fire-and-forget contract, JSONL append-only, per-session paths.
- Pipeline scope (`cortex_command/pipeline/`) is per-feature; overnight scope (`cortex_command/overnight/`) is session-level. Orchestrator-round is overnight-scope; emit via `pipeline.state.log_event` is the existing cross-boundary pattern (precedent at runner.py:1301-1318) and does not introduce a new coupling.
- Out of scope per the topic: orchestrator-round optimization, batch-runner instrumentation, historical backfill.

## Tradeoffs & Alternatives

### Q1 — Schema mapping (per-skill record vs. parallel session-scope channel)

- **Alt A — Synthetic `Skill` value `"orchestrator-round"` on existing per-skill schema; sentinel `feature="<orchestrator-round>"`.** Reuses `compute_skill_tier_dispatch_aggregates` untouched; minimal new code. Sentinel form (`<orchestrator-round>` with angle brackets) is invalid as a real feature name and distinguishable from legacy untagged records — protects pair-walker FIFO semantics from any future emitter that omits feature, and dashboards' `if not feature: continue` filter drops these records cleanly without crashing.
- **Alt B — Parallel session-scope event channel + sibling aggregator.** ~2× implementation surface (new event names, pair helper, aggregator, test file, morning-report renderer entry). Cleaner separation but ticket framing implies a single rollup.
- **Alt C — Hybrid `scope: "feature"|"session"` discriminator.** Largest blast radius; touches every existing reader.
- **Recommended: Alt A with sentinel `<orchestrator-round>`.**

### Q2 — Output-format choice + stdout handling

- **Alt A — `--output-format=stream-json --include-partial-messages` + inline streaming parser.** Per-turn granularity. Inherits issue #1920 hang risk if the final `result` event is missing (must add fallback aggregation from per-message deltas). Requires reader thread or asyncio loop alongside `_poll_subprocess`. Real-time NOTIFY: not actually a concern (no consumer in runner).
- **Alt B — `--output-format=json` end-of-run blob, stdout=PIPE, communicate().** Simplest parser. **Pipe-buffer-fill deadlock risk**: 30-turn orchestrator session's envelope can exceed Linux/macOS ~64 KB pipe buffer; once full, claude blocks writing to stdout, watchdog timer keeps resetting on `events.log` activity until it doesn't, eventually SIGKILL — full envelope discarded, no telemetry. Adversarial #2 establishes this as a real failure mode, not theoretical.
- **Alt B' — `--output-format=json` end-of-run blob, stdout redirected to a session-scoped file (`stdout=open(<session_dir>/orchestrator-round-{round_n}.stdout.json, "wb")`)**. Eliminates pipe-buffer-fill (file write doesn't block the way pipe-write does). Runner reads the file post-`proc.wait()`. Watchdog kill path unchanged (file is closed by OS on subprocess death). Layered complexity is minimal — one open() call and one file read.
- **Alt C — Text output + sidecar usage report file written by orchestrator agent itself.** Burns turns and tokens to instrument the thing whose tokens we are measuring; self-reported numbers; perverse.
- **Recommended: Alt B'** — file-redirect + `--output-format=json`.

### Q3 — Emission point

- **Alt A — Emit from inside `_spawn_orchestrator` via `pipeline.state.log_event` directly.** Matches the existing precedent at runner.py:1301-1318 (`pr_ready_failed` emission). One function owns spawn lifecycle and telemetry. No closed-Literal guard friction (the guard at dispatch.py:432 is internal to dispatch.py functions). No circular-import concerns. **Recommended.**
- **Alt B — Thin wrapper in `dispatch.py` that runner calls; `_spawn_orchestrator` returns usage to wrapper.** Centralizes dispatch event emission in dispatch.py. But: requires extending the closed `Skill` Literal to be matched by every static type-check site; adds a new function to dispatch.py whose body would just call `pipeline.state.log_event` (which runner.py can call directly); introduces a potential import-cycle risk (dispatch.py importing from runner.py). **Heavier than necessary.**

### Q4 — R11/R12 closure

- **Alt A — Wire 111's verification.md update into 153's acceptance criteria.** Couples 153's ship gate to a live overnight session run. 111 is already `complete`; reopening it re-litigates a closed lifecycle. The inline-read prompt is **already retired** (commits ec55340 / 296e451), so a live re-baseline of the *original* prompt is no longer obtainable.
- **Alt B — File a separate follow-up ticket; ship 153 independently.** Cleaner ship gate. **But Adversarial #6 flag**: the comparison between the static 7,063-token estimate (R11) and live measured tokens (R12 via 153 instrumentation) is **method-divergent**. Don't quietly defer the ratio — the follow-up ticket must explicitly frame the divergence (estimate vs measurement) so the comparison's meaning is preserved. Otherwise verification.md silently substitutes a different measurement method.
- **Recommended: Alt B with explicit method-divergence framing in the follow-up ticket body.**

## Adversarial Review

### Failure modes confirmed

1. **Pipe-buffer-fill deadlock with `--output-format=json` + `stdout=PIPE`**: empirically the JSON envelope is small (~700 bytes for one-turn no-op), but a 30-turn orchestrator session's `result` text + `iterations` array + `modelUsage` can exceed the typical 64 KB OS pipe buffer. Once the pipe fills, claude blocks writing to its stdout indefinitely. Runner never reads. Watchdog timer resets mid-write because `events.log` is still seeing activity. Eventual SIGKILL discards the full envelope — no telemetry. **Mitigation: redirect stdout to a session-scoped file (`stdout=open(...)`), not PIPE.**

2. **Watchdog stall path emits no `events.log` record of the failure mode** (`runner.py:1636-1653`): the stall branch prints a warning, calls `_transition_paused` and `_notify`, and `break`s. **No `events.log_event(events.ORCHESTRATOR_FAILED, ...)` call.** ORCHESTRATOR_FAILED is only emitted on non-zero clean exit (line 1659). Stalled rounds emit zero events about their failure mode, and consequently orphan-`dispatch_start` records sit silently in `pair_dispatch_events`'s unmatched queue. **Mitigation: emit a `dispatch_error` (or `ORCHESTRATOR_FAILED` with `details.reason="stall_timeout"`) in the stall branch as part of 153.**

3. **`pair_dispatch_events` feature=None pairing is fragile across rounds.** `metrics.py:377` keys by `feature = evt.get("feature", "")` — None or empty maps all orchestrator-round events across all rounds in a session into a single FIFO queue. Within one session this works because rounds are sequential. **But**: clock skew or re-emitted events during paused-resume could interleave starts/completes from different rounds; if any other emitter (a baseline-capture script, a future test fixture) lands on the same shared key, mispair becomes possible. **Mitigation: use sentinel `feature="<orchestrator-round>"` (with angle brackets — invalid as a real feature name).**

4. **Closed-Literal `Skill` guard makes Alt B (dispatch.py wrapper) heavier than it looks**: dispatch.py:432 raises if `skill not in get_args(Skill)`. To use any dispatch.py emission helper, the new value must be added to the Literal, which propagates to every callsite's static type-check. **Mitigation: emit via `pipeline.state.log_event` directly from runner.py (precedent at runner.py:1301-1318); extend the `Skill` Literal anyway for canonical-vocabulary documentation, but do not depend on dispatch.py for emission.**

5. **R11/R12 method-divergence**: verification.md's R11 baseline is a static character-count estimate (28,254 chars / 4 chars/token = 7,063 tokens) — explicitly because no live measurement existed. After 153 ships, R12's measurement is `usage.input_tokens` from `--output-format=json` (real BPE tokens). Comparing 7,063 estimated to N measured is method-divergent. The 4-char/token assumption can be off by 15-30% on code-heavy prompts. **Mitigation: the R11/R12 follow-up ticket must explicitly frame the divergence; do not silently substitute live measurements into a slot the verification.md described as an estimate.**

6. **`--output-format=json` envelope confirmed empirically**: `usage.input_tokens`, `usage.output_tokens`, `usage.cache_read_input_tokens`, `usage.cache_creation_input_tokens` are all separately exposed alongside `total_cost_usd`, `duration_ms`, `num_turns`. **Persist all four token fields plus cost in the raw `dispatch_complete` event** so prompt-cache comparisons can read them. `pair_dispatch_events`'s output dict (metrics.py:340-356) currently surfaces only `cost_usd` and `num_turns` — the cache fields stay in the raw event, and any future prompt-cache analysis reads raw events directly (or extends `pair_dispatch_events`).

### Assumptions to retire

- "Watchdog records the kill via ORCHESTRATOR_FAILED" — false. Stall branch emits nothing. Fix opportunistically as part of 153.
- "feature=None gives one queue per non-overlapping round, correct semantically" — only correct under fragile invariants. Use sentinel.
- "Stream-json is the safer choice because it preserves real-time stdout" — moot in this codebase (no consumer); stream-json's pipe-fill profile is *worse* than json because more bytes flow through the same pipe more often.
- "`requirements/pipeline.md:27` reserves orchestrator subprocess stdout" — interpretively ambiguous. The phrase "orchestrator agent's input channel" most plausibly means the runner's stdout (which is also tested by the dry-run snapshot fixture), not the orchestrator subprocess's stdout. Recommended approach (file-redirect of subprocess stdout) does not violate the requirement as implemented.

### Recommended mitigations (consolidated)

1. **Redirect orchestrator subprocess stdout to a session-scoped file**, not PIPE. Eliminates pipe-buffer-fill deadlock entirely.
2. **Emit `dispatch_start` before spawn, `dispatch_complete` after `proc.wait()` returns 0, `dispatch_error` (or stall-flagged ORCHESTRATOR_FAILED) on the stall-flag-set branch and the non-zero-exit branch.** Use `pipeline.state.log_event` directly. Fixes orphan-start accumulation as a side-effect.
3. **Use sentinel `feature="<orchestrator-round>"` with angle brackets** — protects FIFO semantics and downstream filters.
4. **Extend `Skill` Literal at dispatch.py:156 to include `"orchestrator-round"`** for canonical-vocabulary completeness, but do not route emission through dispatch.py.
5. **Persist all four token fields** (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`) plus `total_cost_usd` in the `dispatch_complete` raw event.
6. **R11/R12 closure**: file a separate follow-up ticket framing the static-estimate-vs-live-measurement divergence explicitly. Do not couple 153's ship gate to a verification.md amendment.
7. **Emit a stall-failure event in `runner.py:1636-1653`** — pre-existing observability gap that 153 should opportunistically close while editing the path.

## Open Questions

All resolved during research before transitioning to Spec.

1. **Stdout file path & retention** — **Resolved**: `<session_dir>/orchestrator-round-{round_number}.stdout.json`. No zero-padding (round numbers are small integers). No compression. Retain with the session directory (matches the existing per-session artifact convention). Cleanup, if it ever becomes desirable, follows session-directory retention policy as a whole — not 153's concern.

2. **Stall-event scope** — **Resolved by refinement of Q7**: per-round-unique feature names (Q7 below) make stalled rounds produce a single orphan `dispatch_start` that does not poison subsequent rounds' pairing. The "stall path emits no events.log record" issue is a pre-existing observability gap; file a separate ticket if it bites in practice. Out of scope for 153.

3. **`Skill` Literal extension** — **Resolved**: yes, add `"orchestrator-round"` to the closed Literal at `dispatch.py:156`. Keeps canonical vocabulary in one place; emission still goes through `pipeline.state.log_event`, not dispatch.py's runtime guard.

4. **Cache-token field surfacing in pair-walker output** — **Resolved**: persist `cache_read_input_tokens`, `cache_creation_input_tokens`, `input_tokens`, `output_tokens` in the raw `dispatch_complete` event only. Do **not** extend `pair_dispatch_events`'s output dict — its current shape (`cost_usd`, `num_turns`) is uniform across skills, and special-casing one skill or threading cache fields through for all skills both exceed 153's scope. Future cache-aware analyses read raw events.

5. **Requirements doc clarification** — **Resolved**: no edit. Re-read in context, `requirements/pipeline.md:27` ("stdout remains clean as the orchestrator agent's input channel") is part of the runner's Session Orchestration acceptance criteria — it describes the runner's own stdout when the runner is invoked by an orchestrator agent (e.g., `claude -p cortex overnight start`). It does not constrain the orchestrator subprocess that the runner spawns. The file-redirect of the subprocess's stdout is orthogonal.

6. **R11/R12 follow-up framing** — **Deferred to a separate backlog item**: 153's spec will note that R11/R12 closure is out of scope. A separate low-priority follow-up ticket should be filed after 153 ships, with body framing the static-estimate-vs-live-measurement divergence explicitly so verification.md does not silently substitute a different measurement method. Filing the follow-up is a tracking task, not a 153 deliverable.

7. **Sentinel feature value** — **Resolved with refinement**: per-round-unique `<orchestrator-round-{round_number}>` (with angle brackets — invalid as a real feature name; distinguishable from legacy untagged records). Aggregator buckets by `(skill, tier)` only, so unique feature names do not fragment the `orchestrator-round,<tier>` bucket. Per-round uniqueness makes `pair_dispatch_events` FIFO matching robust by construction to stalled rounds — a stalled round produces one orphan `dispatch_start` keyed to its own unique feature name, leaving subsequent rounds' starts/completes to pair correctly. This eliminates the need for stall-event emission (Q2) entirely.
