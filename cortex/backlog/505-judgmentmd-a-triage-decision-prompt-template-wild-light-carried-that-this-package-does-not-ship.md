---
schema_version: "1"
uuid: 1dd3e611-e33d-476f-af1e-746ce27c4f4c
title: 'judgment.md: a triage-decision prompt template wild-light carried that this package does not ship'
status: backlog
priority: low
type: chore
created: 2026-09-01
updated: 2026-09-01
tags: ['overnight', 'prompts', 'filed-from-wild-light']
blocked-by: []
blocks: []
---
Filed from wild-light, 2026-09-01, during a repo-wide spring-cleaning audit.

## Why

wild-light carried a local `claude/overnight/prompts/` directory holding three templates. Two were
copies of ones this package already ships and were **behind** it — `batch-brain.md` was missing the
whole "Final Attempt Diagnostics" section, which is the tell that nobody was loading them, since
`cortex_command.overnight` resolves its prompts through
`importlib.resources.files("cortex_command.overnight.prompts")`. That directory has now been deleted
from wild-light.

The third, `judgment.md`, has **no counterpart in this package**. It is a triage-decision prompt —
retry / skip / defer on a failed overnight task — and it is either (a) a template this package once
had and dropped, (b) a template someone drafted for this package and never landed, or (c) dead. I
cannot tell which from wild-light's side, which is why this is a question rather than a patch.

## What to check

`cortex_command/overnight/prompts/` currently ships `batch-brain.md`, `orchestrator-round.md`,
`plan-synthesizer.md` and `repair-agent.md`. If the runner has a judgment/triage step that builds its
prompt inline rather than from a template file, this may be the missing template. If it has no such
step, this is dead and needs nothing.

## The template, in full

Preserved here because wild-light's copy is now only in git history:

```
You are a Lead Engineer making a triage decision for an overnight autonomous build.

## Feature: {feature}
## Task: {task_description}
## Error: {error_summary}
## Retry Count: {retry_count}

## Learnings from Previous Attempts
{learnings}

## Relevant Spec
{spec_excerpt}

## Your Decision

Decide: retry (try the task again), skip (mark task as done, proceed), or defer (pause feature, ask the human).

Guidelines:
- **retry**: if the error seems transient or learnings suggest a different approach would work
- **skip**: if the task is non-critical and remaining tasks can proceed without it
- **defer**: if the error reveals a spec ambiguity or architectural question only a human can answer

Respond with ONLY a JSON block:
```json
{"action": "retry|skip|defer", "reasoning": "1-2 sentences", "severity": "blocking|non-blocking|informational", "confidence": 0.0-1.0}
```

The `severity` field is only required when action is "defer":
- **blocking**: Feature cannot proceed without human decision
- **non-blocking**: A reasonable default was possible; human should validate
- **informational**: Something unexpected discovered; no action needed
```

## Note on the drift, which is the reusable part

The failure mode is not the missing template — it is that a consuming repo can hold a stale private
copy of a packaged prompt and never learn it is stale, because nothing loads it and nothing compares
it. If the package ever wants to guard that, the cheap check is a startup or CLI assertion that no
`claude/overnight/prompts/*.md` exists in the consuming repo, or that any that does matches the
packaged bytes.
