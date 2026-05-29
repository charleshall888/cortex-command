---
schema_version: "1"
uuid: b900be81-682f-49bb-aace-aeb16c94d47b
title: "Retire or re-establish the orphaned has_why_n_justification discovery subsystem"
status: complete
priority: low
type: chore
created: 2026-05-28
updated: 2026-05-29
complexity: complex
criticality: high
spec: cortex/lifecycle/retire-or-re-establish-the-orphaned/spec.md
areas: ['skills']
---
## Why

#269 reconciled `skills/discovery/SKILL.md` and `decompose.md` prose to the emitted Architecture vocabulary (`### Pieces` + `### How they connect`), dropping the `### Why N pieces` falsification gate from the operator-facing instruction surfaces. It deliberately scoped out the *code/schema* subsystem that still encodes the now-removed "Why N" concept, because retiring an event field + CLI flag + registry row + live test consumers is a different, schema-touching risk class than prose-vocabulary reconciliation (see #269 spec Non-Requirements). That subsystem is now fully orphaned: no active skill emits the `architecture_section_written` event, yet the field, the flag, the registry row, and four test functions that exercise it all remain.

## Role

Decide whether to **retire** the `has_why_n_justification` / `architecture_section_written` subsystem entirely, or **deliberately re-establish** the Why-N concept (e.g. wire it back into the research template as a real gate). Then make every surface below consistent with that decision so there is no dangling field, no stale producer attribution, and no test exercising a dead path.

## Integration

The emitted research template is the source of truth (ADR 0007 / #268 / #269). If the decision is "retire," all surfaces below are deleted/updated together so `just test` stays green. If "re-establish," the gate is added back to the research template and `SKILL.md`, and the field/flag/tests are kept — but that reverses #269's approved conform-down direction and must be justified explicitly.

## Edges

- The events-registry row for `architecture_section_written` lists `skills/discovery/SKILL.md` in its `producers` column though no active skill emits the event — already false today, more misleading after #269.
- The registry references a consumer test `tests/test_discovery_events.py` that does not exist (dangling reference).
- The real live consumer is `tests/test_discovery_module.py` (4 functions: `test_emit_architecture_written_writes_jsonl`, `test_emit_architecture_written_validation_rejects_negative_piece_count`, the path-routing test, `test_cli_emit_architecture_written_appends_event`) — retiring the subsystem without updating these breaks `just test`.
- The fixtures `tests/fixtures/discovery-brief/{diagnostic,simple,complex}-topic/research.md` still use the old four-heading vocabulary; no current test negatively asserts their heading content, and conforming them risks the `generate-brief` fixture-driven tests.

## Touch points

- `cortex_command/discovery.py` — `emit_architecture_written` function + `--has-why-n-justification` CLI flag + `has_why_n_justification` field.
- `bin/.events-registry.md:115` — `architecture_section_written` row (incl. stale `producers` column + dangling `tests/test_discovery_events.py` reference).
- `tests/test_discovery_module.py` — 4 functions exercising the field.
- `tests/fixtures/discovery-brief/{diagnostic,simple,complex}-topic/research.md` — stale four-heading fixtures.

## References

- Follow-up to #269 (`reconcile-discovery-skillmd-architecture-vocabulary-with`), deferred per its spec Non-Requirements ("file a follow-up ticket").
- Lineage: #268 → #269 → this.