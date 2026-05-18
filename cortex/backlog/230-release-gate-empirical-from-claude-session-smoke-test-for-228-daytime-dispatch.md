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

### Step 0: Pin local CLI + plugin to the merged #228 SHA

Defends against running the smoke against a stale local install that predates #228.

1. Capture the #228 squash-merge commit SHA on `main`:
   ```
   git log --grep='#228' --format='%H %s' main | head -3
   ```
   Operator selects the squash-merge SHA from the output and pastes it into §Results under **#228 merge commit SHA on main**.
2. Re-install the CLI from that exact SHA:
   ```
   uv tool install --reinstall --no-cache git+https://github.com/charleshall888/cortex-command.git@<#228-merge-sha>
   ```
3. Re-install the cortex-daytime plugin from the same SHA, or confirm via `/plugin list` in the Claude session that the installed plugin is at or after the #228 merge commit.
4. Capture `cortex --version` output and paste it into §Results under **CLI version captured before Step 1**. Capture the `/plugin list` excerpt for cortex-daytime and paste it under **Plugin version captured before Step 1**.

The §Acceptance gate (below) declares FAIL if either the SHA field or the CLI version field is empty when §Acceptance is evaluated, or if the captured version cannot be reconciled with the #228 merge SHA.

### Step 1: Invoke the MCP tool from inside a Claude Code session

From inside an interactive Claude Code session (confirm `cortex-daytime` is `connected` via `/mcp` first), invoke the MCP tool `mcp__plugin_cortex-daytime_cortex-daytime__daytime_start_run` with `feature="smoke-release-gate"` and `confirm_dangerously_skip_permissions=true`.

### Step 2: Wait for the dispatch to complete (5-minute wall-clock timeout)

Wait for the dispatched daytime pipeline to emit `dispatch_complete` in `cortex/lifecycle/smoke-release-gate/pipeline-events.log`. The wall-clock timeout covering steps 2 and 3 together is 5 minutes from the MCP-tool invocation. On timeout, capture the MCP-tool stdout/stderr and the contents of `cortex/lifecycle/smoke-release-gate/` (if any) for the failure ticket and transition to the FAIL path under §Release-tag handshake.

### Step 3: Run the four assertions against `pipeline-events.log`

All four assertions run against `cortex/lifecycle/smoke-release-gate/pipeline-events.log` (NOT `events.log`):

- `grep -c '"event": "dispatch_start"' cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `≥ 1` and the matched line's payload has `feature` equal to `smoke-release-gate`.
- `grep -c '"event": "dispatch_complete"' cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `≥ 1` with the same `feature` field AND a `ts` strictly greater than the matched `dispatch_start` line's `ts`.
- `grep -c "EPERM" cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `0`.
- `grep -c "Sandbox failed to initialize" cortex/lifecycle/smoke-release-gate/pipeline-events.log` returns `0`.

### Step 4: Record the proof in §Results

Paste into §Results: operator initials, UTC date (ISO 8601), the two paired event lines verbatim (the `dispatch_start` line and the `dispatch_complete` line, single JSON object each), and the captured `git rev-parse HEAD` from the same shell that ran the greps.

### Step 4.5: Archive the pipeline-events.log before cleanup

The archive lives outside the cleanup target so the non-fabricable proof survives Step 5. Run:

```
mkdir -p cortex/lifecycle/release-gate-empirical-from-claude-session/archive/
cp cortex/lifecycle/smoke-release-gate/pipeline-events.log \
   cortex/lifecycle/release-gate-empirical-from-claude-session/archive/smoke-pipeline-events-<UTC-date>.log
git add cortex/lifecycle/release-gate-empirical-from-claude-session/archive/smoke-pipeline-events-<UTC-date>.log
```

Paste the archive path into §Results under **Archive path**.

### Step 5: Terminate, poll for shutdown, then clean

Order matters — cancel before clean, and poll between them so the cleanup cannot race the still-running child:

1. `cortex daytime cancel --feature smoke-release-gate`
2. Poll `cortex daytime status --feature smoke-release-gate` at 5-second intervals until it reports no active dispatch, or until 30 seconds have elapsed (whichever comes first). If `cortex daytime status` reports "no PID file" within 30 seconds of the original MCP-tool invocation, treat it as a silent dispatch failure and transition to the FAIL path.
3. Only after the poll loop exits clean, run `git clean -fd cortex/lifecycle/smoke-release-gate/`.

## Release-tag handshake

After §Results is populated with all 12 fields and all four Step 3 assertions PASS:

1. Pre-push check: confirm no concurrent `[release-type:]` marker is pending from another ticket within the current auto-release cycle:
   ```
   git log <latest-tag>..HEAD --grep='\[release-type:' --oneline
   ```
   If any unresolved markers from other tickets appear, coordinate with the other operator before pushing (the `auto-release.yml` concurrency group collapses concurrent pushes and resolves marker precedence as `skip > major > minor > patch`).
2. Set this ticket's status to `merged` via `cortex-update-item 230-release-gate-empirical-from-claude-session-smoke-test-for-228-daytime-dispatch status=merged`.
3. Push a follow-up empty commit on `main` whose message body contains `[release-type: minor]` (or `[release-type: major]` if the spec field changes warrant it) on its own line. The auto-release workflow at `.github/workflows/auto-release.yml` will fire on that commit and cut the version tag including #228.

If ANY Step 3 assertion FAILS, the §Acceptance gate is unmet, or the §Results SHA field cannot be reconciled with the installed CLI version:
- Do NOT mark this ticket merged. Do NOT push the release-cut commit.
- Open a follow-up bug ticket against #228 with the captured `pipeline-events.log` excerpt (or MCP-tool stdout/stderr on the timeout path).
- The #228 lifecycle stays merged-to-main-but-unreleased until the bug is resolved and this gate is re-run.

## Acceptance

- This ticket is `merged` only when §Results contains all 12 fields below populated (no blanks):
  - **#228 merge commit SHA on main**, **CLI version captured before Step 1**, **Plugin version captured before Step 1**, **Dispatch ID**, **Pipeline-events.log absolute path**, **EPERM count** (must be `0`), **Sandbox-init-failure count** (must be `0`), **Paired dispatch event lines** (both `dispatch_start` and `dispatch_complete` JSON objects pasted verbatim, with `dispatch_complete.ts > dispatch_start.ts`), **git rev-parse HEAD**, **Archive path**, **Operator initials**, **UTC date** (ISO 8601).
  - The captured `cortex --version` field must reconcile against the captured **#228 merge commit SHA on main** (the installed CLI build corresponds to a ref at or after that SHA).
  - The **Archive path** must point to a committed file under `cortex/lifecycle/release-gate-empirical-from-claude-session/archive/`.
- A release tag covering the #228 implementation commits has been cut on or after this ticket reached `merged`.

## Results

(Populate this section after running §Procedure. Do not pre-fill.)

- **#228 merge commit SHA on main**:
- **CLI version captured before Step 1** (`cortex --version`):
- **Plugin version captured before Step 1** (`/plugin list` excerpt):
- **Dispatch ID**:
- **Pipeline-events.log absolute path**:
- **EPERM count**:
- **Sandbox-init-failure count**:
- **Paired dispatch event lines** (verbatim from pipeline-events.log, single JSON object each; the `dispatch_complete` `ts` must be strictly greater than the `dispatch_start` `ts`):
  ```
  dispatch_start:
  dispatch_complete:
  ```
- **git rev-parse HEAD** (captured in the same shell that ran the greps):
- **Archive path** (committed before cleanup):
- **Operator initials**:
- **UTC date** (ISO 8601):

## References

- Parent feature: [[228-wire-daytime-dispatch-through-cli-and-mcp-with-launchd-detachment]]
- Spec R16: `cortex/lifecycle/wire-daytime-dispatch-through-cortex-cli/spec.md` (release-gate requirement)
- Plan reference: `cortex/lifecycle/release-gate-empirical-from-claude-session/plan.md` (this ticket's Task 1 carries the §Procedure + §Results rewrite landing the paired-events proof shape; see plan.md for the full task breakdown)
