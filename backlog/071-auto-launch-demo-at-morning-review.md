---
schema_version: "1"
id: "071"
uuid: 4f2e8b3c-1a9d-4e7f-bc42-8d5e9f2a0c1b
title: "Agent-driven demoability assessment and validation setup at morning review"
type: feature
status: refined
priority: medium
tags: [morning-review, overnight-runner, lifecycle-config, dx]
areas: [skills]
created: 2026-04-11
updated: 2026-04-11
blocked-by: []
blocks: []
complexity: simple
criticality: medium
discovery_source: research/morning-review-demo-setup/research.md
---

# Agent-driven demoability assessment and validation setup at morning review

## Context from discovery

The user wants to reduce morning-review friction for human validation of overnight work. The original research explored static auto-launch (run `demo-command` mechanically), but the right design is smarter: the morning review agent already reads specs and feature descriptions, so it can reason about whether each completed feature is interactively testable by a human — and offer to help set up validation only when it makes sense.

A static `demo-command` can't know whether THIS set of overnight changes actually needs human eyeballs. The agent can. A game mechanic change needs play-testing; a refactor that passed all automated tests probably doesn't. A dashboard UI change needs visual inspection; a cron schedule tweak doesn't.

Key constraints from research:
- The integration worktree is destroyed at session end — any setup must happen at morning review time when the user is present
- The overnight branch (`overnight/{session_id}`) persists and is the durable reference to the session's code
- The user being present eliminates the need for background process management

## What this feature delivers

**1. Optional `demo-command` hint in `lifecycle.config.md`**

A new field in the schema (`skills/lifecycle/assets/lifecycle.config.md`) that tells the agent how to run the project interactively. This is a hint for the agent's reasoning, not a trigger:

```yaml
demo-command: godot --play res://main.tscn   # or: uv run fastapi run src/main.py
```

Absent = project has no interactive demo; agent skips validation setup entirely.

**2. Demoability assessment in the morning review walkthrough**

During the Completed Features section (Step 3), after displaying what was built, the agent reads the **actual diff** (`git diff main...overnight/{session_id}`) alongside each feature's spec. Both contribute equally — diff provides file-path signal (which surfaces were touched), spec provides intent signal (what the feature was meant to do). The agent assesses whether any of the completed work warrants human validation beyond what automated tests cover, considering:
- Which files changed and whether they have a visible/interactive surface (UI scenes, gameplay scripts, user-facing endpoints)
- Whether the automated test gate is likely to cover this class of change fully (unit behavior vs. feel/UX)
- Whether the changes are structural/config/internal with no interactive manifestation

Surfaces conclusion only, not reasoning: "Tonight's changes included UI and gameplay work — want to do a validation session before merging?"

**3. Single interactive offer to set up validation**

After assessing all completed features, the agent makes **one offer** for the session — if any features are judged demoable and `demo-command` is set. The user accepts or skips. No per-feature or per-group prompting.

On acceptance, the agent:
- Creates a worktree from `overnight/{session_id}` at `$TMPDIR/demo-{session_id}/` (avoids disrupting the main repo's branch state; stays within sandbox write paths)
- Runs `demo-command` from that worktree
- Stays present to guide what specifically to look for based on the specs

The user is sitting there. No background process lifecycle, no PID tracking, no Popen management.

**After PR merge (Step 6):** the agent reminds the user to close the demo if it is still running.
