---
schema_version: "1"
id: "071"
uuid: 4f2e8b3c-1a9d-4e7f-bc42-8d5e9f2a0c1b
title: "Auto-launch demo at morning review via lifecycle.config.md demo-command"
type: feature
status: refined
priority: medium
tags: [morning-review, overnight-runner, lifecycle-config, dx]
areas: [skills, overnight-runner]
created: 2026-04-11
updated: 2026-04-11
blocked-by: []
blocks: []
complexity: simple
criticality: medium
discovery_source: research/morning-review-demo-setup/research.md
---

# Auto-launch demo at morning review via lifecycle.config.md demo-command

## Context from discovery

The user wants to reduce morning-review friction: when the overnight runner finishes work on a project, the morning review process should automatically make the result demo-able — launching a server, game, or other runnable artifact on the overnight branch so the user can validate without manual setup.

Key findings from research:
- The integration worktree is **destroyed** by runner.sh at session end (`git worktree remove --force` at lines 1291–1330), before the user opens `/morning-review`. Session-end launch is not viable.
- The overnight **branch** (`overnight/{session_id}`) persists after session end and is the durable reference to the session's code.
- The morning review skill already reads `overnight-state.json` which contains the session ID and branch name — it has everything needed to create a fresh worktree at review time.
- `lifecycle.config.md` in the target repo is not currently read at runtime; the morning review skill can read it directly from the repo root (no runner changes needed).

## What this feature delivers

1. A new `demo-command` field in the `lifecycle.config.md` schema (template at `skills/lifecycle/assets/lifecycle.config.md`).
2. A new Step 2.5 in the morning review skill (`skills/morning-review/SKILL.md`) — runs between Executive Summary and Completed Features:
   - Read `demo-command` from `lifecycle.config.md` in the repo root
   - If absent: skip entirely, no prompt shown
   - If present: create a fresh git worktree from `overnight/{session_id}` at a stable path (e.g., `lifecycle/sessions/{id}/demo-worktree/`)
   - Launch `demo-command` with `cwd=demo_worktree_path`:
     - Server/background type: non-blocking launch (`Popen`-style), surface port/URL to user
     - Interactive/game type: surface command and worktree path as instructions (user runs manually or triggers from terminal)
3. A cleanup hook at Step 6 of the morning review (after PR merge completes): stop any background process started in Step 2.5 and remove the demo worktree.

## Open questions for spec

- Should `demo-command` be per-repo (one launch command for the whole project) or per-feature (individual features may demo at different entry points, e.g., `res://combat.tscn` vs `res://main.tscn` for a Godot game)? This shapes the schema design.
- How is "server vs. interactive" mode determined — via the `type` field in lifecycle.config.md, a separate `demo-mode: background|interactive` field, or by whether the command has a flag/pattern indicating it's long-running?
- What is the cleanup contract for background processes: killed automatically after PR merge, or left running for the user to stop?
- What happens when the overnight branch no longer exists at morning review time (e.g., PR was already merged before the user ran `/morning-review`)?
