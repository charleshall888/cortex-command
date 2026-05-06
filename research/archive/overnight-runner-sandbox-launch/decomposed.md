# Decomposition: overnight-runner-sandbox-launch

The research produced three work items. Per user direction, T1 and T3 were implemented inline in the decomposition session rather than routed through backlog tickets. Only T2 (LaunchAgent migration for scheduling) was created as a backlog ticket.

## Work Items

| # | Title | Priority | Size | Status |
|---|-------|----------|------|--------|
| T1 | Revert `tmux:*` from `excludedCommands`; switch run-now launch to per-call `dangerouslyDisableSandbox: true` | high | S | Done inline |
| T2 | Migrate `overnight-schedule` to a LaunchAgent-based scheduler | high | M | Ticket #112 |
| T3 | Document the `excludedCommands` contract in `claude/rules/sandbox-behaviors.md` | medium | S | Done inline |

## T1 — Done Inline

**Files changed:**
- `claude/settings.json` — removed `"tmux:*"` from `sandbox.excludedCommands`
- `skills/overnight/SKILL.md` — both run-now and scheduled branches of Step 7, and the resume-flow launch call, now instruct the agent to use the Bash tool with `dangerouslyDisableSandbox: true`

**Effect:** Daytime tmux usage is now sandboxed again. Overnight launches surface a per-call permission prompt, logged in the session transcript as an audit record. `overnight-schedule`'s internal `tmux` invocation still works via the per-call bypass until T2 lands.

## T2 — Backlog Ticket

- **ID:** 112
- **Title:** Migrate overnight-schedule to a LaunchAgent-based scheduler
- **Depends on:** none (T1 done inline)
- **Status:** backlog

T2 is the medium-sized work item deferred to a full `/lifecycle` run. It has its own planning surface (plist template, `launchctl bootstrap` semantics, `~/Library/LaunchAgents/` write path, self-unload wrapper, wake-coalesce testing) and closes the present-tense lid-close / low-battery / reboot brittleness of the current `caffeinate -i sleep + tmux` scheduling mechanism.

## T3 — Done Inline

**Files changed:**
- `claude/rules/sandbox-behaviors.md` — new `## `excludedCommands` Contract: What Belongs` section articulating the short-lived/transactional rule, ruling out long-lived-subtree tools, and pointing at the two sanctioned escape paths (`dangerouslyDisableSandbox: true` per call, and LaunchAgent handoff).

**Effect:** Future edits to `sandbox.excludedCommands` have an explicit rule to evaluate against. Blesses `launchctl:*` as a reasonable addition if T2 chooses that escape path. Rules out future `tmux:*`-style additions.

## Key Design Decisions

- **F+E adopted over F-alone.** The user chose to close the present-tense lid-close defect in the same epic rather than accept it as an open gap. This makes T2 a high-priority follow-up, not a deferred nice-to-have.
- **No epic created.** With T1 and T3 done inline and only T2 as a ticket, there is no multi-ticket structure to parent. T2 stands on its own with `discovery_source` pointing back to the research artifact.
- **D ruled out, not just deprioritized.** The review-phase verification that `!` prefix inherits the sandbox turned D from "acceptable with UX cost" into "concretely broken" — the feasibility table and rejection list reflect this.

## Created Files

- `backlog/112-migrate-overnight-schedule-to-launchagent-based-scheduler.md`
