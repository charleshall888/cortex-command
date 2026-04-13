# Outline: `docs/overnight-operations.md`

Subsection-level outline for the new operations doc. Every one of the 21 spec req 2 keyword gaps (13 original + 8 research-added) is slotted under a heading below; keywords (or their documented synonyms from spec req 2) appear in heading text so the grep loop passes.

Retros mining (Task 1) found zero "added" disposition findings — no retro-sourced headings are needed.

## Overall H2 structure

Planned top-level H2s (per plan Task 3 + spec edge cases):

1. `## Architecture`
2. `## Code Layout`
3. `## Tuning`
4. `## Observability`
5. `## Security and Trust Boundaries`
6. `## Internal APIs`

Preamble (before H2s): breadcrumb line, audience header, jump-to nav, progressive-disclosure rationale paragraph (spec req 13).

---

## Heading tree

### `## Architecture`

Mental-model scaffolding for the round loop, dispatch, review, and recovery. Reference-first tables preceded by short narrative per subsystem.

#### `### The Round Loop and orchestrator_io`
Purpose: explain the orchestrator-owned round loop; name `orchestrator_io` as the thin re-export surface the prompt consumes. Covers forward-only phase transitions and atomic state writes.

#### `### Post-Merge Review (review_dispatch)`
Purpose: document `review_dispatch.dispatch_review()`, `requires_review()` gating, the CHANGES_REQUESTED rework cycle, HEAD SHA circuit breaker, and deferral-on-reject/cycle-2. (Covers keyword "review_dispatch" / synonym "Post-Merge Review".)

#### `### Per-Task Agent Capabilities (allowed_tools)`
Purpose: reproduce `_ALLOWED_TOOLS` literally with the "source of truth: `claude/pipeline/dispatch.py`; pytest enforces equivalence" comment. Note enforce-by-omission. (Covers "allowed_tools" / synonym "Per-Task Agent Capabilities".)

#### `### brain.py — post-retry triage (SKIP/DEFER/PAUSE)`
Purpose: disambiguation-first lede — `brain.py` is post-retry triage, not a repair agent; `SKIP/DEFER/PAUSE` enum; no RETRY by design. Prompt: `batch-brain.md`. (Covers "brain.py".)

#### `### Conflict Recovery (trivial fast-path and repair fallback)`
Purpose: document the trivial-eligibility rule (≤3 files, none hot), `resolve_trivial_conflict()` fast path, and `dispatch_repair_agent` fallback; per-feature `recovery_depth < 1` budget. (Covers "Conflict Recovery".)

#### `### Cycle-breaking for repeated escalations`
Purpose: document the prompt-implemented cycle break in `orchestrator-round.md` Step 0d — prior `resolution` entry in `escalations.jsonl` plus worker re-ask triggers promotion + deferral + no re-queue. (Covers "Cycle-breaking".)

#### `### Test Gate and integration_health`
Purpose: describe `runner.sh` post-merge test run, `integration_recovery.py` flaky-guard → repair dispatch → SHA circuit breaker → re-test flow, and degraded-mode mutation of `overnight-strategy.json`. (Covers "Test Gate".)

#### `### Startup Recovery (interrupt.py)`
Purpose: document `interrupt.py` startup-recovery semantics — how mid-flight features are reconciled at runner start. (Covers "interrupt.py" / synonym "Startup Recovery".)

#### `### Runner Lock (.runner.lock)`
Purpose: PID mechanics and stale-lock recovery for `.runner.lock`. (Covers ".runner.lock" / synonym "Runner Lock".)

#### `### Scheduled Launch subsystem`
Purpose: document the scheduled-launch flow (how a cron/launchd trigger becomes a runner invocation). (Covers "Scheduled Launch" / synonym "scheduled-launch".)

---

### `## Code Layout`

Disambiguation of the two prompt directories and module-level inventory pointers.

#### `### claude/pipeline/prompts — per-task dispatched prompts`
Purpose: name the contents (`implement.md`, `review.md`) and the dispatch path (worktree-scoped per-task agents). (Covers "pipeline/prompts".)

#### `### claude/overnight/prompts — orchestrator/session-level prompts`
Purpose: name the contents (`orchestrator-round.md`, `batch-brain.md`, `repair-agent.md`) and the load path (`runner.sh` / overnight subsystems). (Covers "overnight/prompts".)

---

### `## Tuning`

Tables-with-reasons for concurrency and per-session knobs.

#### `### --tier concurrency (Concurrency Tuning)`
Purpose: tier → runners/workers table (MAX_5, MAX_100, MAX_200), adaptive rate-limit window, 1-3 hard cap. (Covers "--tier".)

#### `### lifecycle.config.md fields and absence behavior`
Purpose: document the template as source of truth (no centralized Python loader), the fields list, and per-consumer absence behavior (morning-review, lifecycle complete, critical-review). (Covers "lifecycle.config.md".)

#### `### overnight-strategy.json contents and mutators`
Purpose: `OvernightStrategy` dataclass fields; end-of-round write by orchestrator; integration-recovery-failure mutation to `integration_health="degraded"`. (Covers "overnight-strategy.json".)

---

### `## Observability`

Symptom-first Emmer procedures plus log-file disambiguation.

#### `### Log Disambiguation (events.log, pipeline-events.log, agent-activity.jsonl)`
Purpose: table naming each log, who writes it, what schema, and which symptom to grep which log for. Covers `agent-activity.jsonl` schema specifically. (Covers "agent-activity.jsonl" and synonym "Log Disambiguation" — satisfies the 21st gap.)

#### `### Escalation System (escalations.jsonl)`
Purpose: `EscalationEntry` schema, `type ∈ {escalation, resolution, promoted}`, writers (`write_escalation`, inline from prompt Step 0d), readers (orchestrator Steps 0a-0d, `_next_escalation_n`), acknowledged TOCTOU. (Covers "escalations.jsonl".)

#### `### Morning Report Generation (report.py)`
Purpose: describe `report.py` (1555 lines) entrypoint, commit-to-local-main behavior (the only runner commit that stays on local main). (Covers "report.py" / synonym "Morning Report Generation".)

#### `### Dashboard Polling and dashboard state`
Purpose: document dashboard's state-file poll cadence and the poll-vs-atomic-replace interaction; read-only; bind address covered under Security. (Covers "Dashboard Polling".)

#### `### Session Hooks (SessionStart, SessionEnd, notification hooks)`
Purpose: hook points, silent-failure mode (acknowledge-gap), pointers to hook scripts. (Covers "Session Hooks" / synonym "SessionStart" / "notification hooks".)

---

### `## Security and Trust Boundaries`

Each boundary enumerated once with a single-sentence threat model.

#### `### --dangerously-skip-permissions and sandbox surface`
Purpose: state the boundary; name the sandbox config as the critical security surface for autonomous execution.

#### `### Tool bound at the SDK level (_ALLOWED_TOOLS)`
Purpose: reiterate that allowlist is orthogonal to `--dangerously-skip-permissions`; pointer to Per-Task Agent Capabilities section.

#### `### Dashboard binds 0.0.0.0, unauthenticated`
Purpose: "Do not expose"; "local network ≠ home network"; read-only by design.

#### `### Keychain prompt as session-blocking failure mode`
Purpose: macOS keychain prompt mid-session breaks the "runs while you sleep" premise; document as a named failure mode.

#### `### Auth Resolution (apiKeyHelper and env-var fallback order)`
Purpose: document `runner.sh` 4-step fallback order — `ANTHROPIC_API_KEY` → `apiKeyHelper` → `~/.claude/personal-oauth-token` → keychain; propagation into SDK subprocesses. (Covers "apiKeyHelper" / synonym "Auth Resolution".)

---

### `## Internal APIs`

#### `### orchestrator_io re-export surface`
Purpose: pointer + invariant (what's re-exported today; convention that new orchestrator-callable I/O primitives are added here). Do NOT enumerate symbols — point to `__all__` or module source. (Covers "orchestrator_io" — reinforced; primary slot above under Architecture.)

---

## Keyword → heading assignment table (self-check)

| # | Keyword (spec req 2) | Heading |
|---|----------------------|---------|
| 1 | review_dispatch | `### Post-Merge Review (review_dispatch)` |
| 2 | allowed_tools | `### Per-Task Agent Capabilities (allowed_tools)` |
| 3 | pipeline/prompts | `### claude/pipeline/prompts — per-task dispatched prompts` |
| 4 | overnight/prompts | `### claude/overnight/prompts — orchestrator/session-level prompts` |
| 5 | escalations.jsonl | `### Escalation System (escalations.jsonl)` |
| 6 | overnight-strategy.json | `### overnight-strategy.json contents and mutators` |
| 7 | Conflict Recovery | `### Conflict Recovery (trivial fast-path and repair fallback)` |
| 8 | Cycle-breaking | `### Cycle-breaking for repeated escalations` |
| 9 | Test Gate | `### Test Gate and integration_health` |
| 10 | --tier | `### --tier concurrency (Concurrency Tuning)` |
| 11 | brain.py | `### brain.py — post-retry triage (SKIP/DEFER/PAUSE)` |
| 12 | lifecycle.config.md | `### lifecycle.config.md fields and absence behavior` |
| 13 | apiKeyHelper | `### Auth Resolution (apiKeyHelper and env-var fallback order)` |
| 14 | orchestrator_io | `### The Round Loop and orchestrator_io` (and `### orchestrator_io re-export surface`) |
| 15 | .runner.lock | `### Runner Lock (.runner.lock)` |
| 16 | report.py | `### Morning Report Generation (report.py)` |
| 17 | agent-activity.jsonl | `### Log Disambiguation (events.log, pipeline-events.log, agent-activity.jsonl)` |
| 18 | Dashboard Polling | `### Dashboard Polling and dashboard state` |
| 19 | Session Hooks | `### Session Hooks (SessionStart, SessionEnd, notification hooks)` |
| 20 | Scheduled Launch | `### Scheduled Launch subsystem` |
| 21 | interrupt.py | `### Startup Recovery (interrupt.py)` |
