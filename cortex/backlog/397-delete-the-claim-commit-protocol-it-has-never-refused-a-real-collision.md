---
schema_version: "1"
uuid: 33779683-4c39-4b3a-8b6b-357a0e6ff6cb
title: 'Delete the claim/commit protocol: it has never refused a real collision'
status: backlog
priority: low
type: chore
created: 2026-07-17
updated: 2026-07-17
tags: ['token-efficiency', 'telemetry', 'lifecycle', 'deletion-bias']
areas: ['lifecycle']
---
## Why

> **Evidence gathered 2026-07-17 under the #391 task that replaced the "instrument it first" idea.** `cortex/requirements/project.md` (Deletion bias) puts the burden of proof on keeping and prefers existing-tool verification over building instrumentation. The one-off grep has now run. This ticket is the disposition it was meant to produce.

The claim/commit two-phase protocol in `cortex_command/lifecycle_event.py` is **~450 of the file's ~883 lines**: flock-hold-read-validate-append, in-flight refusal, idempotent resume. Its docstring justifies itself with a *hypothetical* race ("adversarial finding 1"). #391's Edges called it an **experiment-candidate, not a kill-target**, and asked for a fire-rate before judging.

**The fire rate is zero.** Measured across every `cortex/lifecycle/*/events.log` and `cortex/lifecycle/archive/*/events.log` in this repo — **332 files, 10,694 event rows**:

| fact | value |
|---|---|
| `advance_started` rows | 11 |
| `advance_committed` rows | 11 |
| orphaned claims (started, never committed) | **0** |
| in-flight collisions (a claim opened while another was unresolved) | **0** |
| refusals of a real collision | **0** |

Every claim the protocol has ever opened committed cleanly. In its entire recorded history it has never once done the thing it exists to do.

## Proposed direction

Delete the protocol and the machinery that exists only to serve it, keeping the plain locked append that every typed subcommand actually uses.

- The `advance_started` / `advance_committed` machine-row pair and the `invocation_id` derivation that keys it.
- The in-flight refusal branch and its `conflicting_row` reporting.
- The idempotent-resume path (`derive_invocation_id` → claim resumes an orphaned `advance_started`).

**Sequence this against the reader, not the writer.** `advance` is the only consumer; ADR-0020 owns the design and must be superseded, not silently contradicted.

## Role

The deletion half of the #391 audit. #391 shipped the zero-reader *event* deletions and deliberately left this alone — the task that produced the evidence said explicitly: do NOT delete the protocol in that session, report the count, and ticket it if zero. It was zero.

## Integration

- **ADR-0020 owns this design.** Deleting the protocol requires superseding that ADR, not just cutting the code (`cortex/adr/README.md` three-criteria gate).
- `cortex_command/lifecycle/advance.py` is the sole reader: `_SANCTIONED_OVERRIDE`, the in-flight refusal, and the claim-time gate all key off it.
- Sibling: #391 (zero-reader events) — same audit, same "burden of proof sits on keeping" bar.
- Independent of #393; that bug is about phase resolution at the claim gate, not the claim primitive itself.

## Edges

- **Zero fires is not zero value — state the counter-argument honestly.** A concurrency guard that never fired may mean the race is impossible, OR that it has been silently preventing collisions by serializing writers, OR that the corpus never ran two writers at once. The measured 11 claims over the protocol's whole life points hard at the third: the interactive loop is single-writer by construction. Confirm that before cutting.
- **The `log` escape hatch is NOT part of this.** #391 audited it and kept it: `advance` refusals point operators at `cortex-lifecycle-event log` as the sanctioned out-of-band override across 5 refusal paths (operator req 7). It survives this deletion.
- The plain flock'd append (`log_event`) is load-bearing and used by every typed subcommand — do not delete it with the claim wrapper.
- Overnight is the one plausible multi-writer surface. Check whether a concurrent overnight run could ever open two claims on one feature before concluding the race is impossible.

## Touch points

- cortex_command/lifecycle_event.py (~450 of 883 lines: the claim/commit primitive)
- cortex_command/lifecycle/advance.py (sole reader: claim gate, in-flight refusal, idempotent resume)
- cortex/adr/0020-*.md (owns the design; must be superseded)
- cortex/backlog/391-delete-zero-reader-lifecycle-events-and-audit-the-untyped-log-escape-hatch.md (the audit that produced the count)