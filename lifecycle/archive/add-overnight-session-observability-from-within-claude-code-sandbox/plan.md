# Plan: Add overnight session observability from within Claude Code sandbox

## Overview

Create a `bin/overnight-status` bash script that reads file-based session state to produce a one-shot status report, add it to the deploy-bin pipeline and `/overnight` skill, and provide a `setup-tmux-socket` recipe that safely allowlists the tmux socket while preserving the GPG socket entry.

## Tasks

### Task 1: Create `bin/overnight-status` script

- **Files**: `bin/overnight-status`
- **What**: Implement the complete status script: session discovery via `active-session.json` with fallback to most recent `lifecycle/sessions/` directory, runner liveness check via `.runner.lock` + `kill -0`, phase/progress from `overnight-state.json`, recent events from `overnight-events.log` tail, and failed-feature error surfacing. Handle all edge cases from the spec (no session data, stale PID, missing lock, corrupt JSON, session directory missing, runner alive but phase complete).
- **Depends on**: none
- **Complexity**: complex
- **Context**:
  - Session pointer: `~/.local/share/overnight-sessions/active-session.json` — JSON with fields `session_id`, `repo_path`, `state_path`, `phase`
  - Fallback: `lifecycle/sessions/` directories sorted by name (date-encoded, e.g., `overnight-2026-04-07-0008`) — use the most recent directory when `active-session.json` is absent or shows `phase: complete`
  - Lock file: `{session_dir}/.runner.lock` — contains a single PID number
  - State file: `{session_dir}/overnight-state.json` — JSON with `phase`, `current_round`, `features` dict (each feature has `status` field: pending/running/merged/failed/deferred, and `error` field for failures)
  - Events file: `{session_dir}/overnight-events.log` — JSONL, one event per line, each with `ts`, `event`, `session_id`, `round`, `details`
  - Uses `jq` for JSON parsing (required dependency)
  - Follow `bin/overnight-start` pattern: `#!/usr/bin/env bash`, `set -euo pipefail`
  - Output format must match spec requirements: "Runner: alive (PID NNNN)" / "Runner: dead (stale PID NNNN)" / "Runner: no lock file", "Phase: {phase}", "Features: N pending, N running, ...", "Recent Events" section header, "FAILED" prefix for failed features
  - Exit 0 when session data found (active or last-known), exit 1 only when no session data exists at all
  - Corrupt JSON fallback: when `overnight-state.json` fails `jq` parsing, the script must still produce useful output from `overnight-events.log` alone — this is a secondary rendering path that reports "State file corrupt or unreadable" and shows recent events without phase/progress data
  - When showing a completed/crashed session (fallback path), print a "Last known session: {session_id}" header to distinguish from active session output
- **Verification**: `test -f bin/overnight-status` — pass if file exists; `grep -c 'active-session.json' bin/overnight-status` >= 1 — pass if session discovery implemented; `grep -c 'kill -0' bin/overnight-status` >= 1 — pass if liveness check implemented; `grep -cE 'Runner: (alive|dead|no lock)' bin/overnight-status` >= 1 — pass if liveness output format matches spec; `grep -c 'Recent Events' bin/overnight-status` >= 1 — pass if events section implemented; `grep -c 'FAILED' bin/overnight-status` >= 1 — pass if error surfacing implemented; `grep -c 'lifecycle/sessions' bin/overnight-status` >= 1 — pass if fallback discovery implemented; `bash -n bin/overnight-status` exits 0 — pass if script has no syntax errors
- **Status**: [x] complete

### Task 2: Add deploy-bin integration

- **Files**: `justfile`
- **What**: Add `bin/overnight-status` to the `deploy-bin` recipe's pairs array so that `just setup` symlinks it to `~/.local/bin/overnight-status`. Make the script executable.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `justfile:130-138` — `deploy-bin` recipe contains a `pairs=()` array of `"source|target"` entries
  - Follow the existing pattern: `"$(pwd)/bin/overnight-status|$HOME/.local/bin/overnight-status"`
  - Existing entries include `overnight-start`, `count-tokens`, `audit-doc`, etc.
  - Script must be `chmod +x` — either in this task or as part of the commit
- **Verification**: `grep -c 'overnight-status' justfile` >= 1 — pass if entry added; `test -x bin/overnight-status` — pass if executable
- **Status**: [x] complete

### Task 3: Add `/overnight status` subcommand to skill

- **Files**: `skills/overnight/SKILL.md`
- **What**: Update the overnight skill to recognize `status` as a third subcommand alongside the existing `overnight` and `overnight resume`. Add it to the Invocation section, update the input validation to accept `status` as a valid variant, and add a Status Flow section that instructs Claude to run `overnight-status` and present the output.
- **Depends on**: [1]
- **Complexity**: simple
- **Context**:
  - `skills/overnight/SKILL.md:24-27` — Invocation section currently lists `/overnight` and `/overnight resume`
  - `skills/overnight/SKILL.md:41` — Command variant validation: "Only `overnight` and `overnight resume` are valid. Unknown variants should report error → stop."
  - Add `- '/overnight status' -- check the status of a running or recent overnight session` to the Invocation section
  - Update the validation line to include `status` as a valid variant
  - Add a `## Status Flow ('/overnight status')` section that instructs: "Run `overnight-status` (the deployed script) and present its output to the user. If the command is not found, instruct the user to run `just deploy-bin` first."
- **Verification**: `grep -c 'overnight-status' skills/overnight/SKILL.md` >= 1 — pass if script reference present; `grep -c '/overnight status' skills/overnight/SKILL.md` >= 1 — pass if subcommand documented
- **Status**: [x] complete

### Task 4: Create `setup-tmux-socket` justfile recipe

- **Files**: `justfile`
- **What**: Add a `setup-tmux-socket` recipe that auto-detects the tmux socket path via `$(id -u)`, reads the existing `allowUnixSockets` array from `~/.claude/settings.json` (to preserve the GPG socket), appends the tmux socket path, and deep-merges the result into `~/.claude/settings.local.json` without clobbering sibling keys. Print a clear message explaining what access is being granted. Skip if the tmux socket is already present.
- **Depends on**: [2]
- **Complexity**: simple
- **Context**:
  - tmux socket path: `/private/tmp/tmux-$(id -u)/default`
  - Existing GPG socket in `settings.json`: `~/.local/share/gnupg/S.gpg-agent.sandbox` (under `sandbox.network.allowUnixSockets`)
  - `settings.local.json` arrays REPLACE (not merge with) `settings.json` arrays — the recipe must write a self-contained array with both sockets
  - Current `~/.claude/settings.local.json` has `sandbox.filesystem.allowWrite` only, no `sandbox.network` section
  - **Critical: read `settings.local.json` as the base file**, then deep-merge the new `sandbox.network.allowUnixSockets` array into it. The jq approach: read `settings.json` to extract existing `allowUnixSockets`, append the tmux socket, then use `jq` with `--slurpfile` or `--argjson` to set `.sandbox.network.allowUnixSockets` on the existing `settings.local.json` content. This preserves `sandbox.filesystem.allowWrite` and any other existing keys.
  - Example pattern: `jq --argjson sockets "$combined_array" '.sandbox.network.allowUnixSockets = $sockets' ~/.claude/settings.local.json > tmp && mv tmp ~/.claude/settings.local.json`
  - Print warning: "Adding tmux socket access to sandbox allowlist. This grants sandboxed sessions access to ALL tmux sessions on this machine."
- **Verification**: Run `just setup-tmux-socket` then: `jq '.sandbox.network.allowUnixSockets | length' ~/.claude/settings.local.json` >= 2 — pass if both sockets present; `jq '.sandbox.network.allowUnixSockets[] | select(contains("tmux"))' ~/.claude/settings.local.json` produces output — pass if tmux socket present; `jq '.sandbox.network.allowUnixSockets[] | select(contains("gnupg"))' ~/.claude/settings.local.json` produces output — pass if GPG socket preserved; `jq '.sandbox.filesystem.allowWrite | length' ~/.claude/settings.local.json` >= 1 — pass if existing filesystem allowWrite not clobbered
- **Status**: [x] complete

## Verification Strategy

After all tasks complete:

1. Run `just deploy-bin` to create the symlink
2. Run `overnight-status` — verify it exits 0 (if a recent session exists) or exits 1 with "No overnight session data found" (if no sessions exist), and output includes "Runner:", "Phase:", "Features:", "Recent Events", and "FAILED" sections (where applicable)
3. Run `just setup-tmux-socket` — verify `~/.claude/settings.local.json` contains both the tmux socket and GPG socket in `allowUnixSockets`, AND that `sandbox.filesystem.allowWrite` is preserved
4. Verify `/overnight status` in a Claude Code session invokes the script (Interactive/session-dependent: requires an active Claude Code session to test skill dispatch)
