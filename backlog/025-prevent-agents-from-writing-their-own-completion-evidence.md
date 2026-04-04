---
schema_version: "1"
uuid: c8d9e0f1-a2b3-4567-cdef-789012345678
id: "025"
title: "Prevent agents from writing their own completion evidence"
type: chore
status: complete
priority: medium
parent: "018"
blocked-by: []
tags: [overnight, reliability, verification, lifecycle]
created: 2026-04-03
updated: 2026-04-04
discovery_source: research/harness-design-long-running-apps/research.md
session_id: null
lifecycle_phase: implement
lifecycle_slug: prevent-agents-from-writing-their-own-completion-evidence
complexity: complex
criticality: high
spec: lifecycle/prevent-agents-from-writing-their-own-completion-evidence/spec.md
areas: [lifecycle,overnight-runner]
---

# Prevent agents from writing their own completion evidence

## Context from discovery

The failure historian found a confirmed instance of self-sealing completion evidence (retro 2026-04-02-1629): a plan task used `ls ~/.claude/rules/` as its own completion evidence and wrote a `req1_verified` log entry itself. A self-written log entry is a false positive by construction — the agent checks for the artifact it just created, which always passes.

This is distinct from the spec compliance failures addressed by ticket 019. Tighter verification requirements in plan.md do nothing if the agent can manufacture the artifact that satisfies those requirements. The root problem is provenance: the agent both writes and reads its own completion signal.

The fix required human intervention to catch: the plan had to be rewritten to prohibit the agent from writing the `req1_verified` event, requiring instead that it be written by a human in a prior session. That was a one-off patch to one plan. The general pattern — an agent writing an artifact and then using that artifact as evidence it completed a task — has no systemic guard.

## What to investigate

1. **Where else does this pattern appear?** Scan lifecycle plan files and overnight prompts for verification steps that instruct agents to write a log entry, create a file, or set a status that they then immediately check as proof of completion.

2. **What is the general principle?** Completion evidence is only valid if it was written by a different agent, a different session, or a human — not by the agent currently executing the task being verified.

3. **What is the right enforcement mechanism?** Options include:
   - A lint/validation step in the lifecycle plan phase that flags verification steps where the agent both writes and reads the same artifact
   - A convention in the plan template that explicitly prohibits self-written completion evidence (e.g., a "Verification must not be self-sealing" requirement in the plan authoring guide)
   - A review checklist item in the lifecycle review phase
   - Runtime enforcement (the plan parser rejects certain patterns before overnight dispatch)

4. **Is the `req1_verified` pattern a one-off or a recurring risk?** Check whether any current lifecycle plans or overnight plan files contain similar self-sealing verification steps.

## Why this matters

A verification step that the executing agent can satisfy by writing its own evidence provides no actual verification — it is theater that passes with 100% reliability regardless of whether the underlying task was completed correctly. This is a different failure mode than weak tests (ticket 019) or incomplete spec criteria: the signal is not just weak, it is fabricated.
