# Specification: Add overnight session observability from within Claude Code sandbox

## Problem Statement

When checking overnight session status from within a sandboxed Claude Code session, the sandbox blocks tmux socket access (`/private/tmp/tmux-503/default` — "Operation not permitted"), making it impossible to check if the runner is alive, view its output, or diagnose crashes. The only current visibility is manually reading state files and event logs. This feature adds structured status reporting via a `bin/overnight-status` script (invocable as `/overnight status`) and optionally restores full tmux access by allowlisting the socket.

## Requirements

### Must-Have

1. **`bin/overnight-status` script**: A standalone bash script that produces a one-shot status report of the active overnight session. When no active session exists but a recent session directory is found, the script shows last-known state for crash diagnosis. Acceptance criteria: `overnight-status` exits 0 and prints a human-readable status report when an active session exists; exits 0 with a "last known" header when showing a recent completed/crashed session; exits 1 with a message only when no session directory can be found at all. Verify: `overnight-status >/dev/null 2>&1; echo $?` returns 0 when a session is running or a recent session exists, 1 only when no session data exists.

2. **Session discovery**: The script reads `~/.local/share/overnight-sessions/active-session.json` to locate the active session's `state_path`. If `active-session.json` is absent or shows `phase: complete`, the script falls back to the most recent directory under `lifecycle/sessions/` (sorted by name, which encodes date). Acceptance criteria: `grep -c 'active-session.json' bin/overnight-status` >= 1 and the script contains fallback logic to scan `lifecycle/sessions/`.

3. **Runner liveness check**: The script reads `.runner.lock` from the session directory, extracts the PID, and checks process liveness via `kill -0 $PID`. Acceptance criteria: status output includes a "Runner: alive (PID NNNN)" or "Runner: dead (stale PID NNNN)" or "Runner: no lock file" line. Verify: `overnight-status | grep -cE 'Runner: (alive|dead|no lock)'` = 1.

4. **Session phase and progress**: The script reads `overnight-state.json` and reports: session phase, current round, feature count by status (pending/running/merged/failed/deferred). Acceptance criteria: `overnight-status | grep -c 'Phase:'` = 1 and `overnight-status | grep -c 'Features:'` = 1.

5. **Recent activity**: The script reads the last 5 events from `overnight-events.log` (tail) and displays them as a timeline. Acceptance criteria: `overnight-status | grep -c 'Recent Events'` = 1.

6. **Error surfacing**: If any features have `status: failed` in `overnight-state.json`, the script lists them with their error messages. Acceptance criteria: when a feature has failed status, `overnight-status | grep -c 'FAILED'` >= 1.

7. **`/overnight status` skill subcommand**: The existing `/overnight` skill's SKILL.md is updated to recognize `status` as a subcommand that invokes `overnight-status`. Acceptance criteria: `grep -c 'overnight-status' skills/overnight/SKILL.md` >= 1.

8. **Deploy-bin integration**: `bin/overnight-status` is added to the `deploy-bin` recipe in the justfile so that `just setup` symlinks it to `~/.local/bin/overnight-status`. Acceptance criteria: `grep -c 'overnight-status' justfile` >= 1.

### Should-Have

9. **tmux socket allowlist**: Add the tmux default socket path to `allowUnixSockets` in `settings.local.json`. This restores `tmux has-session`, `tmux list-sessions`, and `tmux attach` from within sandboxed sessions. Acceptance criteria: Interactive/session-dependent — requires a running tmux session and sandboxed Claude Code session to verify; the socket path is UID-specific (`/private/tmp/tmux-{UID}/default`).

10. **Setup auto-detection for tmux socket**: `just setup` (or a dedicated recipe) auto-detects the tmux socket path using `$(id -u)` and writes it to `settings.local.json`. Because `settings.local.json` arrays replace (not merge with) `settings.json` arrays, the recipe must read the existing `allowUnixSockets` array from `settings.json`, append the tmux socket path, and write the combined array to `settings.local.json`. Acceptance criteria: after running `just setup-tmux-socket`, verify (a) `jq '.sandbox.network.allowUnixSockets' ~/.claude/settings.local.json` contains `/private/tmp/tmux-$(id -u)/default`, and (b) `jq '.sandbox.network.allowUnixSockets' ~/.claude/settings.local.json` also contains `~/.local/share/gnupg/S.gpg-agent.sandbox` (the GPG socket from `settings.json` is preserved).

## Non-Requirements

- **Dashboard localhost access**: Removing `localhost`/`127.0.0.1` from the sandbox deny list is out of scope — too broad a security relaxation for a narrow use case.
- **Runner output logging**: The runner will not tee its output to a log file — tmux socket access (should-have) provides this capability more cleanly without modifying the runner.
- **Real-time streaming**: The status command is a one-shot snapshot, not a watch/polling mode. Users who need live output should use tmux attach (once the socket is allowlisted).
- **Remote status**: The status command operates locally only. Remote access is handled by existing tools (mosh, Tailscale, Cloudflare Tunnel).
- **Cross-file consistency model**: The script reads multiple state files written at different times. File-based state is inherently eventually-consistent; the script reports what it reads without cross-file reconciliation. This is acceptable for a one-shot diagnostic tool.

## Edge Cases

- **No active session, recent session exists**: `active-session.json` does not exist or `phase` is `complete`. Script falls back to the most recent `lifecycle/sessions/` directory, prints a "Last known session" header, and reports state from that directory. Exits 0.
- **No session data at all**: Neither `active-session.json` nor any `lifecycle/sessions/` directories exist. Script exits 1 with "No overnight session data found."
- **Stale PID in `.runner.lock`**: The runner process died but the lock file wasn't cleaned up. `kill -0` returns non-zero. Script reports "Runner: dead (stale PID NNNN)" rather than "alive."
- **Missing `.runner.lock`**: No lock file exists (runner was never started, or was cleaned up). Script reports "Runner: no lock file" and continues with state-file-based status.
- **Malformed `overnight-state.json`**: File exists but is not valid JSON (e.g., truncated write). Script reports "State file corrupt or unreadable" and falls back to events.log if available.
- **Session directory missing**: `active-session.json` points to a `state_path` that doesn't exist on disk. Script falls back to most recent `lifecycle/sessions/` directory (same as "no active session" path).
- **Runner alive but phase complete**: Runner process responds to `kill -0` but `overnight-state.json` shows `phase: complete` with all features in terminal states. This is a normal end-of-session state (runner doing cleanup). Script reports both accurately: "Runner: alive (PID NNNN)" and "Phase: complete" — the user can infer the runner is shutting down.
- **Sandbox blocks `kill -0`**: If a future sandbox change restricts signal checks, `kill -0` would return non-zero for alive processes. The script would misreport "dead." Mitigated by the fact that `kill -0 $$` has been verified to work in the current sandbox (2026-04-08). If this regresses, the script degrades to state-file-only status (still useful) — it does not crash.
- **tmux socket path varies by UID**: The setup recipe uses `$(id -u)` to construct the path dynamically. This is machine-specific and belongs in `settings.local.json`, not the committed `settings.json`.
- **tmux socket allowlist grants broad access**: Adding the default tmux socket to `allowUnixSockets` grants sandboxed agents access to ALL tmux sessions, not just the overnight runner. This is acceptable for personal tooling on a single-user machine where the user explicitly opts in. The setup recipe should print a clear message explaining what access is being granted.

## Changes to Existing Behavior

- ADDED: `bin/overnight-status` — new script providing overnight session status from within sandboxed sessions
- MODIFIED: `skills/overnight/SKILL.md` — adds `status` as a recognized subcommand that delegates to `overnight-status`
- MODIFIED: `justfile` — adds `overnight-status` to `deploy-bin` pairs array
- ADDED: `justfile` recipe `setup-tmux-socket` — auto-detects and writes tmux socket path to `settings.local.json` (should-have)
- MODIFIED: `~/.claude/settings.local.json` — gains `allowUnixSockets` entry combining GPG socket (from settings.json) and tmux socket (should-have, machine-specific)

## Technical Constraints

- **Sandbox read access**: `~/.local/share/overnight-sessions/` is readable (not in the sandbox deny list). Session state under `lifecycle/sessions/` is in the repo working directory and also readable.
- **`kill -0` in sandbox**: Verified empirically (2026-04-08): `kill -0 $$` returns exit code 0 within a sandboxed Claude Code bash session. Process signal checks are not restricted by the current sandbox profile. The script should handle non-zero exit gracefully regardless (edge case: sandbox blocks `kill -0`).
- **`settings.local.json` array replacement**: Claude Code deep-merges `settings.local.json` over `settings.json` at the object level, but arrays at leaf positions are **replaced**, not concatenated. Verified empirically: `settings.json` defines `sandbox.filesystem.allowWrite: ["~/cortex-command/lifecycle/sessions/", "~/.cache/uv"]`, `settings.local.json` defines `sandbox.filesystem.allowWrite: ["/Users/charlie.hall/Workspaces/cortex-command/lifecycle/sessions/"]`, and at runtime `~/.cache/uv` is not writable (Operation not permitted). Therefore, any `settings.local.json` array must be self-contained — it must include all entries from `settings.json` that need to survive, plus its own additions.
- **deploy-bin pattern**: New scripts follow the established convention: logic in `bin/`, symlinked to `~/.local/bin/` via `just deploy-bin`. The skill invokes the binary by name, not a relative path.
- **jq dependency**: The status script should use `jq` for JSON parsing (already a project dependency per requirements/observability.md). Pure-bash fallback is not required for a CLI utility.

## Open Decisions

- None — all decisions resolved during the structured interview and critical review.
