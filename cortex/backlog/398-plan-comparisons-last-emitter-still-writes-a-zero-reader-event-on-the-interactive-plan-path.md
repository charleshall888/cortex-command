---
schema_version: "1"
uuid: b3daa28c-5f48-4657-aaee-512cd45e86f2
title: plan_comparison's last emitter still writes a zero-reader event on the interactive plan path
status: backlog
priority: low
type: chore
created: 2026-07-17
updated: 2026-07-17
tags: ['token-efficiency', 'telemetry', 'lifecycle']
areas: ['lifecycle']
---
## Why

`plan_comparison` has **zero production readers**. Its registry row names its only consumers as `cortex_command/pipeline/tests/test_metrics.py:1421,1440,1460 (tests-only)`, and a trace across `cortex_command/{dashboard,overnight,pipeline,common.py}` finds nothing that folds, parses, or reduces it. It is not read by `reduce_lifecycle_state`, not in `_TELEMETRY_ONLY_EVENT_TYPES`, not parsed by `dashboard/poller.py` or `overnight/report.py`.

#391 verified this and deleted the emitter it was scoped to — `cortex_command/overnight/prompts/orchestrator-round.md`, which wrote the event through the `cortex-lifecycle-event log` escape hatch at three sites (auto-select, verdict route, deferred branch). That task named only the overnight emitter, so the interactive one survived.

**One emitter is left**: `skills/lifecycle/references/competing-plans.md` §g — "Log v2 `plan_comparison` event" — a raw JSONL append on the interactive plan-comparison path, followed by routing prose that hands off to the plan reference. It writes a ~10-field row (`variants`, `selected`, `selection_rationale`, `selector_confidence`, `position_swap_check_result`, `disposition`, `operator_choice`, …) into a void on every interactive competing-plans run.

## Proposed direction

Delete §g and the event with it: the emission, the registry row, and the `plan_comparison` exemption in the ADR-0020 hand-written-events list. Keep §g's trailing routing sentence — the "go to plan.md §3a if a variant was selected, §3 if the operator rejected all" handoff is control flow, not telemetry, and must survive the cut.

Then re-check the two round-trip tests that currently pin the row shape (`test_plan_comparison_v2_round_trip`, the mixed-log test) — they are the "tests-only" consumers, and they go with the event.

## Role

The residue of #391. Not a lever: the deletion is worth roughly nothing in tokens (deduplicated, the whole `cortex-lifecycle-event` family is ~118 billed requests). It is here because the evidence is unusually solid — a traced data flow, not an inference — and because leaving one emitter of a dead event is a half-finished deletion that reads as intentional to the next person.

## Integration

- **Unblocks a parked #340 item.** #340's Out of scope defers "the event-migration of the clarify-critic and plan-comparison sites — contested by a dual-producer parity argument". After #391 there is only one producer, so the parity argument no longer has two producers to be about. This ticket settles the plan-comparison half by deletion; the clarify-critic half stays parked.
- Sibling: #391 (zero-reader events) — same audit, same kill-list, same reader-not-cost discipline.
- ADR-0020 lists `plan_comparison` among the hand-written exempt events whose canonical shape places `schema_version` before `feature`; that exemption and its test (`test_subcommand_table_covers_only_non_exempt_events`) shrink with the event.

## Edges

- **This edits an interactive skill flow, which #391 deliberately would not do.** §g sits between the verdict routing (§f) and the plan.md handoff; the cut must not disturb either. That surgery is the actual work — the grep was the easy part.
- **Do not generalise this into removing the event log.** `reduce_lifecycle_state` reduces `events.log` to the canonical lifecycle state and there is no other state store. `plan_comparison` is dead; the log is the cure, not the disease.
- The dashboard/report may want plan-comparison telemetry *later*. Under Deletion bias that is a hypothetical, not named evidence — re-add it with a reader when a reader exists.
- Historical rows survive in archived logs; nothing reads them, so no compat shim is needed (contrast `_DAYTIME_DISPATCH_FIELDS`, which is retained precisely because a reader still parses archived data).

## Touch points

- skills/lifecycle/references/competing-plans.md (§g — the surviving emitter)
- bin/.events-registry.md (the `plan_comparison` row; producers now point only at competing-plans.md)
- cortex_command/lifecycle_event.py (the ADR-0020 exempt-event list at ~695)
- cortex_command/pipeline/tests/test_metrics.py (test_plan_comparison_v2_round_trip and the mixed-log test — the tests-only consumers)
- cortex/backlog/340-core-skill-efficiency-survivors-of-the-post-336-adversarial-audit.md (the parked item this unblocks)