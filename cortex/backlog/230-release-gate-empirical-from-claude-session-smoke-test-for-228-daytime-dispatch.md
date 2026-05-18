---
schema_version: "1"
uuid: cb71a336-ce2f-48fb-9ade-33e1e033a7a2
title: "Release-gate empirical from-Claude-session smoke test for #228 daytime dispatch"
status: in_progress
priority: high
type: chore
tags: [daytime-pipeline, mcp, release-gate, manual-verification]
created: 2026-05-16
updated: 2026-05-17
complexity: simple
criticality: high
areas: [overnight-runner]
blocked_by: [228]
spec: cortex/lifecycle/release-gate-empirical-from-claude-session/spec.md
session_id: 73b5157c-f0de-4fe3-a9c8-94c8bec310d6
lifecycle_phase: plan
---

# Release-gate empirical from-Claude-session smoke test for #228 daytime dispatch

## Why this is a separate ticket

#228 builds the daytime CLI + MCP surface. Its 16-task autonomous plan lands the code and ships pytest coverage for everything pytest can reach. But the spec's central claim — that `daytime_start_run` invoked from inside a real Claude session escapes the calling session's Seatbelt sandbox — cannot be verified by pytest. The MCP tool requires a live Claude Code MCP host; an autonomous overnight dispatch agent cannot invoke itself as an MCP tool from a parent Claude session it is not running inside.

The cortex pipeline has no native "interactive complexity tier" that lets a task in `plan.md` defer to manual operator action — the dispatch resolver at `cortex_command/pipeline/dispatch.py:127-235` enforces a closed `trivial|simple|complex` enum and raises `ValueError` on anything else. So this gate cannot live inside #228's plan.md without booby-trapping every autonomous run on it.

This ticket holds the manual procedure and gates the production release tag (not the lifecycle's `feature_complete` event) on the empirical verification being performed.

## Procedure

After #228's lifecycle reaches `feature_complete` and the implementation PR has merged to `main` carrying a `[release-type: skip]` marker (so no version tag fires yet):

1. From inside an interactive Claude Code session, invoke the MCP tool `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run` with `feature="smoke-release-gate"` and `confirm_dangerously_skip_permissions=true`.
2. Wait for the dispatched daytime pipeline to reach at least `feature_dispatched` in `cortex/lifecycle/smoke-release-gate/events.log`.
3. Verify the three assertions against that events.log:
   - `grep -c "EPERM" cortex/lifecycle/smoke-release-gate/events.log` returns `0`
   - `grep -c "Sandbox failed to initialize" cortex/lifecycle/smoke-release-gate/events.log` returns `0`
   - `grep -c "feature_dispatched" cortex/lifecycle/smoke-release-gate/events.log` returns `≥ 1`
4. Record outcomes below in `## Results` (operator initials + UTC date + the verbatim `feature_dispatched` event line pasted from the actual events.log — this is the non-fabricable proof).
5. Clean up: `cortex daytime cancel --feature smoke-release-gate` to terminate the spawned dispatch; `git clean -fd cortex/lifecycle/smoke-release-gate/`.

## Release-tag handshake

After §Results is populated with all three assertions PASS:

1. Set this ticket's status to `merged` via `cortex-update-item 230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch status=merged`.
2. Push a follow-up empty commit on `main` with the message body containing `[release-type: minor]` (or `[release-type: major]` if the spec field changes warrant it) on its own line. The auto-release workflow at `.github/workflows/auto-release.yml` will fire on that commit and cut the version tag including #228.

If ANY assertion FAILS:
- Do NOT mark this ticket merged. Do NOT push the release-cut commit.
- Open a follow-up bug ticket against #228 with the failing events.log excerpt.
- The #228 lifecycle stays merged-to-main-but-unreleased until the bug is resolved and this gate is re-run.

## Acceptance

- This ticket is `merged` only when §Results contains operator initials, UTC date, and a `feature_dispatched` event line that exists verbatim in `cortex/lifecycle/smoke-release-gate/events.log`.
- A release tag covering the #228 implementation commits has been cut on or after this ticket reached `merged`.

## Results

(Populate this section after running §Procedure. Do not pre-fill.)

- **Dispatch ID**:
- **Events.log absolute path**:
- **EPERM count**:
- **Sandbox-init-failure count**:
- **feature_dispatched count**:
- **Pasted feature_dispatched event line** (verbatim from events.log, single JSON object):
  ```
  ```
- **Operator initials**:
- **UTC date** (ISO 8601):

## References

- Parent feature: [[228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment]]
- Spec R16: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` (release-gate requirement)
- Plan reference: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/plan.md` (Task 17 split out into this ticket per Angle-3 critical review finding that `Complexity: interactive` crashes `cortex_command/pipeline/dispatch.py:231-233`'s `ValueError` on unknown tier)
