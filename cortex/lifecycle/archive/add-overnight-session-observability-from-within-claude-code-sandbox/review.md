# Review: Add overnight session observability from within Claude Code sandbox

## Stage 1: Spec Compliance

### Must-Have Requirements

**Requirement 1: `bin/overnight-status` script**
- Script exists at `bin/overnight-status`, is executable (`chmod +x`), and passes `bash -n` syntax check.
- Exits 0 when session data found (active or last-known). Exits 1 with "No overnight session data found." when no session directory can be found.
- Produces a human-readable status report with session header, runner liveness, phase/progress, features summary, and recent events.
- **Rating: PASS**

**Requirement 2: Session discovery**
- Reads `~/.local/share/overnight-sessions/active-session.json` to locate the active session's `state_path` (line 15, lines 27-55).
- Falls back to most recent `lifecycle/sessions/` directory sorted by name when `active-session.json` is absent or shows `phase: complete` (lines 57-74).
- Handles edge cases: missing file, complete phase, non-existent `state_path` directory.
- **Rating: PASS**

**Requirement 3: Runner liveness check**
- Reads `.runner.lock`, extracts PID, checks via `kill -0 $PID` (lines 97-112).
- Output matches spec format: "Runner: alive (PID NNNN)", "Runner: dead (stale PID NNNN)", "Runner: no lock file".
- Handles empty lock file content as "no lock file" (reasonable degradation).
- **Rating: PASS**

**Requirement 4: Session phase and progress**
- Reads `overnight-state.json` and reports phase, current round, and feature counts by status (lines 118-153).
- Output includes "Phase: {phase} (round {current_round})" and "Features: N pending, N running, N merged, N failed, N deferred".
- `grep -c 'Phase:'` = 1 and `grep -c 'Features:'` = 1 confirmed.
- **Rating: PASS**

**Requirement 5: Recent activity**
- Reads last 5 events from `overnight-events.log` via `tail -5` and displays as a timeline (lines 159-188).
- Output includes "Recent Events:" header.
- Parses JSONL events and formats timestamp, event, round, and details.
- **Rating: PASS**

**Requirement 6: Error surfacing**
- When features have `status: failed`, lists them with "FAILED:" prefix and error messages (lines 139-147).
- Uses jq to extract failed features and their error fields.
- **Rating: PASS**

**Requirement 7: `/overnight status` skill subcommand**
- SKILL.md updated: description includes "/overnight status" trigger phrase, Invocation section lists `/overnight status`, command variant validation includes `status`, and a `## Status Flow` section delegates to `overnight-status`.
- `grep -c 'overnight-status' skills/overnight/SKILL.md` = 1 (the script reference in the Status Flow section).
- **Rating: PASS**

**Requirement 8: Deploy-bin integration**
- `bin/overnight-status` added to the `deploy-bin` recipe's pairs array at justfile line 138.
- Follows the existing `"$(pwd)/bin/overnight-status|$HOME/.local/bin/overnight-status"` pattern.
- `just setup` invokes `deploy-bin`, so the symlink is created automatically.
- **Rating: PASS**

### Should-Have Requirements

**Requirement 9: tmux socket allowlist**
- The `setup-tmux-socket` recipe constructs the tmux socket path as `/private/tmp/tmux-$(id -u)/default` (line 560).
- Writes it to `settings.local.json` under `sandbox.network.allowUnixSockets`.
- Interactive verification (requires running tmux + sandbox) is noted as session-dependent per the spec.
- **Rating: PASS**

**Requirement 10: Setup auto-detection for tmux socket**
- Recipe reads existing `allowUnixSockets` from `settings.json` (line 575), appends tmux socket, deduplicates with `jq ... unique` (line 577), and writes the combined array to `settings.local.json`.
- Preserves existing `settings.local.json` content (uses jq to set just the target key, preserving sibling keys like `sandbox.filesystem.allowWrite`).
- Creates `settings.local.json` from scratch if it doesn't exist (lines 583-584).
- Includes idempotency check (skips if tmux socket already present, lines 570-573).
- Prints clear warning about what access is being granted (line 586).
- **Rating: PASS**

## Stage 2: Code Quality

### Naming Conventions
- `bin/overnight-status` follows the `bin/overnight-start` naming pattern. Consistent.
- `setup-tmux-socket` follows the `setup-*` recipe naming convention. Consistent.
- Internal variables use `UPPER_CASE` for globals, `lower_case` for locals. Consistent with `bin/overnight-start`.

### Error Handling
- Script uses `set -euo pipefail` — appropriate for a diagnostic tool.
- Corrupt JSON handled gracefully: `jq empty` validation before parsing, falls back to "State file corrupt or unreadable" message.
- Missing files handled at each level: active-session.json, session directory, lock file, state file, events file.
- `kill -0` errors suppressed with `2>/dev/null` — correct for sandbox compatibility.

### Test Coverage
- All plan verification steps pass: file exists, executable, references `active-session.json`, `kill -0`, correct output format strings, `lifecycle/sessions` fallback, no syntax errors.
- The `setup-tmux-socket` recipe includes idempotency and GPG socket preservation logic — verifiable via the plan's `jq` commands.
- Integration testing (running against a live session) is session-dependent and acknowledged as such in both the spec and plan.

### Pattern Consistency
- Follows deploy-bin pattern: logic in `bin/`, symlinked to `~/.local/bin/`, skill invokes by name.
- Uses `jq` for JSON parsing (consistent with project dependency).
- Script header follows the `bin/overnight-start` template (shebang, description comment, usage, exit codes).
- `setup-tmux-socket` recipe uses the same `jq` + temp file + `mv` pattern seen elsewhere in the justfile.

### Minor Observations (non-blocking)
- The `REPO_ROOT` computation via `realpath` + `dirname` on `BASH_SOURCE[0]` correctly follows the deploy symlink back to the repo root. Robust.
- The events display truncates fractional seconds and timezone suffixes for readability — a nice touch.
- When the lock file exists but is empty, the script reports "Runner: no lock file" rather than something more specific like "Runner: lock file empty". Functionally correct and matches the spec's three-state output model.

## Requirements Drift

**State**: detected
**Findings**:
- The `bin/overnight-status` script and `/overnight status` subcommand add a new observability tool for overnight sessions (file-based status reporting from within the sandbox). This capability is not reflected in `requirements/observability.md`, which covers the statusline, dashboard, and notification subsystems but does not mention a CLI-based session status tool.
- The `setup-tmux-socket` recipe adds tmux socket allowlisting to enable sandboxed sessions to access tmux. This sandbox configuration capability is not captured in any requirements document.
**Update needed**: requirements/observability.md

## Suggested Requirements Update

**Target**: `requirements/observability.md`

**Proposed addition** (new subsection in the observability surfaces list):

> **CLI session status**: A `bin/overnight-status` script (also reachable via `/overnight status`) reports active or last-known session phase, runner liveness (PID + `kill -0` check), per-feature status counts, recent events, and surfaced failures by reading `~/.local/share/overnight-sessions/active-session.json`, `.runner.lock`, `overnight-state.json`, and `overnight-events.log` directly from disk. This is the sandbox-compatible counterpart to the dashboard and is the canonical liveness probe when the dashboard is unavailable.

**Proposed addition** (sandbox prerequisites or a new "Sandbox integration" subsection):

> **Tmux socket allowlist**: The `setup-tmux-socket` justfile recipe writes the active tmux socket path (`/private/tmp/tmux-$(id -u)/default`) into `settings.local.json` under `sandbox.network.allowUnixSockets`, allowing sandboxed sessions to reach the tmux server. The recipe is idempotent and preserves sibling settings.

**Evidence trail**:
- `bin/overnight-status` lines 15, 27-74, 97-153, 159-188 (this review, Requirements 1-6).
- `skills/overnight/SKILL.md` `## Status Flow` (this review, Requirement 7).
- `justfile` line 138 (deploy-bin pair) and lines 560-586 (`setup-tmux-socket` recipe) (this review, Requirements 8-10).

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
