---
schema_version: "1"
uuid: 88aa1935-073e-434b-8ffb-a179174b20ce
title: "Add sandbox-violation tracker hook for PostToolUse(Bash)"
status: in_progress
priority: medium
type: feature
parent: 162
tags: [overnight-runner, sandbox, observability, hook]
areas: [overnight-runner,observability]
created: 2026-05-04
updated: 2026-05-05
lifecycle_slug: add-sandbox-violation-tracker-hook-for-posttoolusebash
lifecycle_phase: implement
session_id: 0876e18a-ebc1-4924-b941-e7673bef36a5
blocks: []
blocked-by: []
discovery_source: research/sandbox-overnight-child-agents/research.md
complexity: complex
criticality: high
spec: lifecycle/add-sandbox-violation-tracker-hook-for-posttoolusebash/spec.md
---

# Add sandbox-violation tracker hook for PostToolUse(Bash)

## Context from discovery

After #163 lands, sandbox-blocked writes from spawned overnight agents will surface as generic Bash failures — exit code non-zero with `Operation not permitted` in stderr. Per discovery RQ6, this surface is identical to chmod-denied writes and other filesystem permission errors; the agent cannot distinguish sandbox denial from a normal permissions error, and the runner sees no specific signal.

The existing `claude/hooks/cortex-tool-failure-tracker.sh` fires on any non-zero Bash exit and emits `additionalContext` warnings + per-session `/tmp` logs at the 3rd failure. It catches sandbox denials but does not classify them — they appear as generic Bash failures with no morning-report visibility.

## Findings from discovery

- PostToolUse(Bash) hook payload includes `tool_name`, `tool_input.command`, `tool_response.{exit_code,stdout,stderr}`, `session_id` (per https://code.claude.com/docs/en/hooks).
- Distinguishability of sandbox vs other EPERM is imperfect via stderr alone. High-precision: parse the command for write targets, check membership against the spawn's `--settings` denyWrite list. Low-precision: regex on stderr (`Operation not permitted` + path matching `\.git/refs/heads/main` or other deny patterns).
- This is **observability, not enforcement** — sandbox already blocked the write; the hook records that an attempt happened.
- `~50 lines of shell`, modeled on `cortex-tool-failure-tracker.sh`.

## Value

Today, sandbox denials surface as generic Bash failures with no classification (no signal in morning report). After #163 ships, we need to know whether agents are attempting denied writes — useful for catching agents whose prompts are leading them somewhere wrong, even when prompt deviation didn't successfully escape. Citation: `claude/hooks/cortex-tool-failure-tracker.sh` (model hook with the existing classification gap).

## Acceptance criteria (high-level)

- A new shell hook (e.g., `claude/hooks/cortex-sandbox-violation-tracker.sh`) fires on PostToolUse(Bash) and emits a typed `sandbox_denial` event into `lifecycle/<feature>/events.log` (or the active overnight session's events stream) when stderr matches sandbox-denial patterns.
- The hook is registered in the cortex-overnight-integration plugin's hooks.json.
- Morning report aggregator surfaces a count line for `sandbox_denial` events.
- Hook is gated on `CORTEX_RUNNER_CHILD=1` to limit scope to overnight-spawned children.
- `docs/overnight-operations.md` is updated with a brief subsection on sandbox-violation telemetry and how it appears in morning reports.

## Research context

Full research at `research/sandbox-overnight-child-agents/research.md`. Particularly relevant: RQ6, RQ8, DR-5.
