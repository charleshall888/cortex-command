---
schema_version: "1"
uuid: e8440910-a53b-4964-9652-dac35478cdb0
title: "Agent-reasoned demo selection from configured command list at morning review"
status: complete
priority: medium
type: feature
created: 2026-04-12
updated: 2026-04-13
parent: "071"
tags: [morning-review, overnight-runner, lifecycle-config, dx]
areas: [skills]
blocked-by: []
blocks: []
session_id: null
lifecycle_phase: research
lifecycle_slug: agent-reasoned-demo-selection-from-configured-command-list-at-morning-review
complexity: simple
criticality: high
spec: lifecycle/agent-reasoned-demo-selection-from-configured-command-list-at-morning-review/spec.md
---

Follow-up to #071, which added a single `demo-command` string that always
offers when guards pass (demo-command set + local session + branch exists).

The user wants the agent to reason about what changed overnight and pick the
most relevant demo from a configured list — or skip the offer entirely if
nothing relevant landed.

One approach might be: `lifecycle.config.md` gains a `demo-commands:` list,
where each entry has a label and a command string. In Section 2a, the agent
diffs the overnight integration branch, reads the list, and selects the entry
most relevant to the changes (or none). Agent judgment is explicitly accepted
as the filter — no `demo-paths:` config to maintain.

The untestable part is the selection logic. The testable part is the structure:
one offer or none, from a finite configured list, always auto-advancing after.
