---
schema_version: "1"
uuid: b16a9e89-dd0c-4516-8691-fbe3bdd06ec3
title: Build loop ends its turn mid-lifecycle after sub-agent reports land; prose cannot reach turn-end
status: backlog
priority: medium
type: bug
created: 2026-08-03
updated: 2026-08-03
rework_of: 423
tags: ['harness', 'lifecycle', 'interactive-loop', 'hooks']
areas: ['build-skill']
---
## Why

**The build loop ends its turn mid-lifecycle after a sub-agent report lands, and prose cannot fix it.**

#423 recorded this on 2026-07-28 (wild-light #409: a run stopped at implement→review to ask whether to proceed) and closed it on 2026-07-29 (`fdc02448`) with a prose-only fix: reword `_SESSION_SPLIT_HINT`, render it above **Next**, and sharpen `skills/build/SKILL.md:65` to "add no stop of your own unless a `<!-- pause: -->` marker…". The operator reported the same stall again on 2026-08-03.

**Why prose is structurally the wrong lever.** By the time the model emits its summary, every instruction it was given has already run and lost. Every prose fix is a bet that the model will not end its turn; `fdc02448` was that bet, and it is the second one to lose. Only a `Stop` hook acts *after* the turn ends. `CLAUDE.md` already states the preference — "prefer structural separation over prose-only enforcement for sequential gates".

**Evidence, stated honestly.** Two operator reports (2026-07-28 and 2026-08-03), spanning a prose fix that was supposed to close the first. That is the whole case, and it is enough: the failure is observed, reproduced after a fix, and the fix class is exhausted.

**Two forensic claims were investigated and must not be revived:**

- *"A 77-minute gap in `orchestrator-review-mandates-a-whole-artifact` between the implement→review transition and its verdict proves a stall."* Unusable — that feature has no `agent-activity.jsonl`, so a long reviewer and an operator round-trip are indistinguishable.
- *"`enrich-dashboard-seed-fixtures-with-board` and `reconcile-dashboard-docs-and-observability-requirements` are stalled on disk at two different points, which falsifies #423's diagnosis."* **False.** Both were being actively worked by a concurrent session at the time of reading; the "missing" `review_verdict` events were simply not written yet, and both features reached `feature_complete` within the hour. An in-flight lifecycle read from outside its owning session is indistinguishable from a stalled one.

That second mistake is load-bearing for the design, not just an erratum: it is exactly the failure mode the hook itself must avoid, and it is why the hook keys on `.session` matching its own `session_id` rather than on any lifecycle that merely looks unfinished. #423's original diagnosis stands unrefuted — this ticket supersedes it on the *fix class*, not on its analysis.

## Role

Resume the loop when it ends a turn mid-lifecycle at a phase the state machine says is non-pausing — enforced by the harness, not by instructions the model has already read and passed.

## Integration

- No `Stop` hook exists in this repo today: `plugins/cortex-core/hooks/hooks.json` carries only `SessionStart`, `SessionEnd`, `PreToolUse`, `WorktreeCreate`, `WorktreeRemove`; `plugins/cortex-overnight/hooks/hooks.json` adds `PostToolUse` and `Notification`.
- `cortex-lifecycle-next --feature <slug>` already serves the authoritative state; the hook consumes it rather than re-deriving a phase.
- `cortex/lifecycle/{feature}/.session` (gitignored, SessionEnd-cleaned, `skills/build/SKILL.md:88`) is the binding that says a lifecycle is live in this session.
- Sanctioned pauses are `<!-- pause: … -->` markers (inventory: `skills/build/references/kept-pauses.md`) and routed outcomes (`escalated`, plan wait-approved). These must keep working.

## Edges

- **`hooks.json` ships into consumer repos.** Every hook there is narrowly matched — `PreToolUse` is `Bash`-only. An unmatched `Stop` hook that spawns `cortex-lifecycle-next` on every turn end taxes every session in every installed repo, nearly all of which have no lifecycle. Guard it with a shell glob test on `cortex/lifecycle/*/.session` and `exit 0` when absent: a stat, not a process spawn.
- **A blocking Stop hook fights the operator.** Deliberately stopping mid-lifecycle to inspect something is normal and must stay possible; being forced onward is worse than the stall. Needs an escape hatch, and the hatch is part of the work, not a follow-up.
- **#401 notes a blocking stop hook can eat the final message.** That was `SubagentStop`, but it is the same class of hazard.
- **Overnight/headless runs have no operator**, so the hook must not assume one is present to answer anything.
- **Do not fix this with another prose instruction.** Two have now been tried and lost.
- **Never infer a stall from another session's lifecycle.** In-flight and stalled look identical from outside the owning session — key on `.session` matching the current `session_id`.

## Touch-points

- `hooks/` (new hook script) + its `plugins/cortex-core/hooks/` mirror — dual-source, rebuilt from staged blobs by the pre-commit hook
- `plugins/cortex-core/hooks/hooks.json`
- `skills/build/SKILL.md` § Phase transitions — reconcile with whatever the hook now enforces, so prose and mechanism do not disagree
- `cortex_command/lifecycle/next_verb.py` — `_SESSION_SPLIT_STATES` / `_SESSION_SPLIT_HINT` survive or go on their own merits, no longer as this bug's cause
- `tests/test_lifecycle_continue_hook.py`
- Attribution gap worth closing separately: `agent-activity.jsonl` is written for some features and not others, so "stalled" and "was slow" are indistinguishable in the log after the fact.
