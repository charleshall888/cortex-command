---
schema_version: "1"
uuid: 434baf9a-0746-4bdd-8f06-263ed0c0423e
title: Move the orchestrator round's embedded Python into round-prep and round-finish verbs
status: backlog
priority: medium
type: chore
created: 2026-09-14
updated: 2026-09-14
tags: ['overnight', 'prompts']
blocked-by: []
blocks: []
---
## Why

`cortex_command/overnight/prompts/orchestrator-round.md` is 480 lines, of which 173 lines in 13 fenced blocks are Python the model pastes into Bash: reading state and session strategy, aggregating round context, the intra-session dependency gate, the criticality partition, plan-generation dispatch bookkeeping, and batch master-plan generation. Every block already calls an existing library function (`aggregate_round_context`, `generate_batch_plan`, `save_state`, `update_feature_status`, `read_synthesizer_gate`, `log_event`, `reduce_lifecycle_state`). Only the escalation-answering step and the plan-generation delegation need judgment.

Measured cost and observed failure (2026-09-14 prompt audit): the 30 KB prompt (~7.5k tokens) is re-sent on every round of every overnight session, and code that lives in prose has no test — the prompt called `write_escalation(dict, path)` against a function whose signature is `(EscalationEntry, session_dir)` and that only ever wrote `type: "escalation"`, so no orchestrator resolution could ever register with `orchestrator_context`. That bug shipped unnoticed until the audit; it is fixed in f51ad66b by an interim typed helper, but the same class of drift remains possible for the other twelve blocks.

## Role

Two verbs, `cortex overnight round-prep` and `cortex overnight round-finish`, own the deterministic halves. `round-prep` reads state, strategy and the session plan, applies the dependency gate and the criticality partition, and emits one JSON brief (eligible features, unresolved escalations with context, the critical subset, warnings). `round-finish` takes the model's decisions (escalation answers, plan-generation outcomes) and writes the batch master plan and state. The prompt keeps only the judgment steps and the two verb calls. Expected net effect: the prompt drops by roughly 60% and every deterministic step gains a unit test.

## Integration

`runner.py` spawns the round agent with the filled prompt (`fill_prompt.py`); the verb pair sits beside the existing `cortex overnight` subcommands in `cli.py` and reuses the library functions the blocks already import. `tests/test_orchestrator_prompt_render.py` and `tests/test_fill_prompt.py` pin the rendered prompt's contract and must be updated with it.

## Edges

- The criticality partition's single-agent-not-defer rule must keep its stated reason (currently a comment the render test pins on one line).
- `round-finish` must be idempotent per round so a crashed agent can be re-spawned.
- Escalation outcomes keep writing through `write_escalation_outcome` (deferral.py) so `orchestrator_context` can close them.

## Touch-points

`cortex_command/overnight/prompts/orchestrator-round.md`, `cortex_command/overnight/cli.py`, `cortex_command/overnight/orchestrator_io.py`, `cortex_command/overnight/deferral.py`, `cortex_command/overnight/fill_prompt.py`, `tests/test_orchestrator_prompt_render.py`, `tests/test_fill_prompt.py`, `docs/overnight-operations.md`.
