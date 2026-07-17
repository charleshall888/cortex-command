---
schema_version: "1"
uuid: c6f9873c-ad45-4bca-afa4-4354f3e2a5fa
title: Delete zero-reader lifecycle events and audit the untyped log escape hatch
status: complete
priority: low
type: chore
created: 2026-07-16
updated: 2026-07-16
tags: ['token-efficiency', 'telemetry', 'lifecycle']
areas: ['lifecycle']
---
## Why

> **UPDATED 2026-07-16 after independent verification.** (1) The `log` open question below is answered: the escape hatch demonstrably writes orphaned events in production — `cortex_command/overnight/prompts/orchestrator-round.md` emits `plan_comparison`, which has zero readers outside a comment at `lifecycle_event.py:685`. Add it to the delete list alongside the two events below. (2) The counts in this ticket are raw JSONL line counts, not billed requests — deduplicated by `message.id`, `cortex-lifecycle-event` is ~118 requests total (the subcommand split below is proportionally indicative only). The deletions stay free hygiene either way; the token sizing just shrinks. (3) The "instrument claim/commit before judging" item in Edges is withdrawn per the requirements Deletion-bias bar — existing-tool verification beats building instrumentation: grep the corpus's `events.log`/claim files once for an actual in-flight-refusal row; if none has ever fired, ticket the deletion of the ~450-line protocol instead.

`cortex-lifecycle-event` is the highest-turn verb in the harness — **477 full-context requests** across the measured corpus, 2.7x the next verb. Most of it is load-bearing state and must stay. Some of it is a write into a void.

Decomposed by subcommand:

| subcommand | turns | verdict |
|---|---|---|
| `batch-dispatch` | 135 | overnight/script-driven — not interactive cost |
| **`log`** | **126** | **untyped escape hatch — reader unverified** |
| `phase-transition` | 89 | **load-bearing state** |
| `review-verdict` / `plan-approved` / `spec-approved` / `feature-complete` / `lifecycle-start` | 109 | **load-bearing state** |
| `--help` / `help` | 17 | pure waste (model reading CLI usage) |

**Two subcommands have zero readers.** Verified during the 2026-07-16 audit by tracing every non-test consumer in `cortex_command/{dashboard,overnight,lifecycle}`:

- `interactive-worktree-entered` (written from `skills/lifecycle/references/worktree-entry.md:46`)
- `critical-review-skipped` (written from `skills/lifecycle/references/critical-review-gate.md:16`)

Neither is in `_TELEMETRY_ONLY_EVENT_TYPES`, neither is folded by `reduce_lifecycle_events`, neither is parsed by `dashboard/poller.py` or `report.py`. They are telemetry nobody telemeters.

**`log` (126 turns) is the open question.** `cortex_command/lifecycle_event.py:822` — `sub.add_parser("log", help="Append one event row to events.log")`. It is the generic escape hatch: it appends an arbitrary row rather than using a typed subcommand from `_EVENT_SUBCOMMANDS`. Whether `reduce_lifecycle_state` reads anything it writes is **unverified**. It is the only high-volume subcommand where the reader is unknown.

## Proposed direction

Audit **by reader, not by cost**:

- **Delete** `interactive-worktree-entered` and `critical-review-skipped` — write with no reader. Remove the emission sites and the subcommands.
- **Audit `log`'s 126 turns.** Sample the rows it actually writes. For each event name: does `reduce_lifecycle_state` fold it? Does the dashboard/report parse it? Rows with a reader → promote to a typed subcommand. Rows with no reader → delete the call site. If the escape hatch itself has no legitimate remaining use, remove it.
- **Fix the `--help` turns.** 17 requests were the model discovering invocation syntax at full accumulated-context price. Whatever contract is missing from the skill prose, state it.

## Role

Cheap hygiene with a verified kill-list. Not a lever — the whole item is worth low single digits. It is here because the evidence is unusually solid (traced data flow, not inference) and the deletions are free.

## Integration

- Sibling: #390 (skills consume the served envelope) — same verb family, same investigation.
- Independent of #389 (subagent turn caps).

## Edges

- **The event log is NOT the problem. Do not generalise this ticket into removing it.** `common.py:942` — `reduce_lifecycle_state` reduces `events.log` to *the canonical lifecycle state*, consumed by `next_verb.py`, `advance.py`, `state_cli.py`, `complete_route.py`, `implement_transition.py`, `refine.py`, `review_dispatch.py`. There is no other state store. Remove events → no served state → no `resume` → no starting a fresh session mid-lifecycle → loss of the 37–61% session-splitting lever. **The event log is what makes the session disposable; it is the cure, not the disease.**
- `lifecycle_start` / `*_override` / `phase_transition` / `review_verdict` / `feature_wontfix` / `pr_opened` / `batch_dispatch` all gate real state. Keep every one.
- **`READ_OK` is NOT vestigial** — an earlier guess that it was decorative was wrong. `verification-gates.md`'s `check-synth-stable` consumes the sentinel and routes to `EXCLUDED sha_mismatch|read_failed`. It is real drift defense against a reviewer reading stale content. Worth instrumenting for fire-rate, not cutting.
- The claim/commit two-phase protocol in `lifecycle_event.py` (~450 of 883 lines: flock-hold-read-validate-append, in-flight refusal, idempotent resume) is an **experiment-candidate**, not a kill-target: its docstring cites a *hypothetical* race ("adversarial finding 1"), and the audit could not establish it has ever refused a real collision. Instrument before judging. ADR-0020 owns the design.
- `--help` at 17 turns is a symptom of prose that doesn't state the invocation, not of the verb.

## Touch points

- cortex_command/lifecycle_event.py (`_EVENT_SUBCOMMANDS` at 700; the `log` parser at 822)
- skills/lifecycle/references/worktree-entry.md (46 — `interactive-worktree-entered` emission)
- skills/lifecycle/references/critical-review-gate.md (16 — `critical-review-skipped` emission)
- cortex_command/common.py (942 — `reduce_lifecycle_state`, the reader that decides what is load-bearing)
- cortex_command/dashboard/poller.py, cortex_command/overnight/report.py (the other candidate readers)