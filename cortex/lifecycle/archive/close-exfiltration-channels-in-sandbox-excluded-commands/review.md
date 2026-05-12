# Review: Close exfiltration channels in sandbox-excluded commands

## Stage 1: Spec Compliance

### Requirement 1: Remove WebFetch from global allow list
`WebFetch` is no longer present in `permissions.allow`. It remains in `sandbox.excludedCommands` as expected.
**Rating**: PASS

### Requirement 2: Replace `Bash(gh *)` with read-only subcommand patterns
The catch-all `Bash(gh *)` is removed. All 7 specified read-only patterns are present in `permissions.allow`: `gh pr view`, `gh pr list`, `gh pr diff`, `gh pr checks`, `gh repo view`, `gh run list`, `gh run view`.
**Rating**: PASS

### Requirement 3: Deny gh gist commands
Both `Bash(gh gist create *)` and `Bash(gh gist edit *)` are present in `permissions.deny`.
**Rating**: PASS

### Requirement 4: Narrow `git remote` to read-only
`Bash(git remote *)` is removed from `permissions.allow`. Replaced with `Bash(git remote -v)` and `Bash(git remote get-url *)`. The no-args `Bash(git remote)` is preserved.
**Rating**: PASS

### Requirement 5: Deny git remote mutation commands
All three deny rules present: `Bash(git remote add *)`, `Bash(git remote set-url *)`, `Bash(git remote remove *)`.
**Rating**: PASS

### Requirement 6: Deny inline URL git pushes
All four patterns present in `permissions.deny`: `Bash(git push https://*)`, `Bash(git push http://*)`, `Bash(git push * https://*)`, `Bash(git push * http://*)`.
**Rating**: PASS

### Requirement 7: Settings JSON remains valid
`python3 -c "import json; json.load(open('claude/settings.json'))"` exits 0.
**Rating**: PASS

## Stage 2: Code Quality

### Naming conventions
New entries follow the exact naming patterns established by existing allow/deny rules: `Bash(command subcommand *)` format, consistent quoting, no trailing commas. The deny rules are logically grouped (gh gist, git remote, git push URL) matching the existing grouping convention.

### Error handling
Not applicable -- this is a static configuration change with no runtime error paths. The deny-before-allow evaluation order ensures the new deny rules take precedence over the broad `Bash(git push *)` allow rule.

### Test coverage
All 7 acceptance criteria from the spec were executed and returned the expected results. The diff was reviewed for unintended changes -- none found. Only the specified entries were added, removed, or replaced.

### Pattern consistency
The flag-position variant convention for git push URL deny rules mirrors the existing force-push deny patterns (`--force` in three positions). New deny entries are appended at the end of the deny array, grouped logically. The allow list replacements maintain the existing ordering (git remote patterns near other git patterns, gh patterns near the end of the list).

## Requirements Drift
**State**: detected
**Findings**:
- The implementation introduces security hardening for the permission allow/deny list (exfiltration channel closure). The project requirements (`requirements/project.md`) describe the project scope ("Global agent configuration (settings, hooks, reference docs)") but contain no mention of security posture, permission management, or sandbox hardening as a quality attribute or architectural concern. This is a new behavioral domain not yet reflected in requirements.
**Update needed**: requirements/project.md

## Suggested Requirements Update

**Target**: `requirements/project.md`

**Proposed addition** (new "Security posture" subsection or quality attribute):

> **Security posture**: The agentic layer maintains a least-privilege permission set in `claude/settings.json`. Read-only operations (`gh pr view`, `gh repo view`, `git remote -v`, etc.) are allowlisted by exact subcommand pattern; mutating operations that could exfiltrate data or escape sandbox controls (`gh gist create`, `git remote add/set-url/remove`, inline-URL `git push`, `WebFetch` at global scope) are explicitly denied. Deny rules take precedence over allow rules. Any expansion of the allow list must be reviewed against this principle; new exfiltration vectors (network egress, credential exposure, write paths outside the project tree) require an explicit deny rule before any broader allow rule is added.

**Evidence trail**:
- `claude/settings.json` deny array: `Bash(gh gist create *)`, `Bash(gh gist edit *)`, `Bash(git remote add *)`, `Bash(git remote set-url *)`, `Bash(git remote remove *)`, `Bash(git push https://*)`, `Bash(git push http://*)`, `Bash(git push * https://*)`, `Bash(git push * http://*)` (this review, Requirements 3, 5, 6).
- `claude/settings.json` allow array: replaced `Bash(gh *)` and `Bash(git remote *)` with read-only subcommand patterns (this review, Requirements 2, 4).
- `WebFetch` removed from global `permissions.allow` (this review, Requirement 1).

## Verdict

```json
{
  "verdict": "APPROVED",
  "cycle": 1,
  "issues": [],
  "requirements_drift": "detected"
}
```
