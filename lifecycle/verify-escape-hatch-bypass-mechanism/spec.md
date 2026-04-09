# Specification: Verify escape hatch bypass mechanism

## Problem Statement

The permissions-audit epic research (DR-2) claims that `Bash(bash *)`, `Bash(sh *)`, and similar allow-list entries let interpreter-wrapped commands bypass deny-list patterns — e.g., `bash -c "git push --force origin main"` might match `Bash(bash *)` allow instead of `Bash(git push --force *)` deny. This hypothesis is the sole blocker for ticket 057 (removing escape hatch commands) and affects the security posture of the global `claude/settings.json` template deployed to all projects via `just setup`. Without empirical verification, the permissions-audit epic cannot proceed on its highest-impact recommendation.

## Requirements

1. **Test case 1 — bash wrapper around denied git command**: Execute `bash -c "git push --force --dry-run origin main"` in a live Claude Code session. Record which of three outcomes occurs based on the tool call response: (a) permission error returned without execution (deny), (b) user prompted for approval (ask), or (c) command executes (allow). The `--dry-run` flag exercises the identical permission path as the non-dry-run command — `Bash(git push --force *)` matches both — while preventing actual destructive writes if the permission system allows execution. The permission audit log at `$TMPDIR/claude-permissions-*.log` is checked as supplementary evidence to confirm whether a prompt fired. Acceptance criteria: Interactive/session-dependent — the test runs within this Claude Code session and the three-tier outcome is recorded from the tool call response.

2. **Test case 1 control — bash wrapper around non-denied command**: Execute `bash -c "echo hello"` in the same session. This control case has NO matching deny rule — `echo` is not denied. If this is also blocked or prompted, the mechanism is the `f65` dangerous-shell-prefix classifier catching all `bash -c` commands regardless of arguments. If this passes silently, deny rules are being evaluated through the wrapper. Acceptance criteria: Interactive/session-dependent — the outcome (block/prompt/allow) is compared against R1's result to determine the blocking mechanism.

3. **Test case 2 — python3 wrapper around denied git command**: Execute `python3 -c "import os; os.system('git push --force --dry-run origin main')"` in a live Claude Code session. Record the three-tier outcome using the same methodology as R1. Acceptance criteria: Interactive/session-dependent — same observation methodology as R1.

4. **Test case 3 — sh wrapper around denied rm command**: Execute `sh -c "rm -rf /tmp/test"` in a live Claude Code session. Record the three-tier outcome. Note: unlike R1 and R3, the sandbox may independently block this command since `rm` is not in `excludedCommands`. If the tool call returns a sandbox error rather than a permission error, the permission-layer outcome is indeterminate. Check the permission audit log to determine whether the permission layer evaluated the command before the sandbox blocked it. Acceptance criteria: Interactive/session-dependent — tool call response and permission audit log checked to isolate permission-layer behavior from sandbox enforcement.

5. **Test report artifact**: Write findings to `lifecycle/verify-escape-hatch-bypass-mechanism/test-report.md` with a per-case results table (command, expected deny pattern, actual outcome, mechanism determination, whether sandbox was involved, conclusion). Include a "Mechanism Analysis" section comparing R1 and R2 (control) results to determine whether protection comes from deny-rule composition or the dangerous-shell-prefix classifier. Acceptance criteria: `test -f lifecycle/verify-escape-hatch-bypass-mechanism/test-report.md` exits 0, and the file contains a results row for each of the four test cases plus the mechanism analysis section.

6. **Ticket 057 priority adjustment with rationale**: Update `backlog/057-remove-interpreter-escape-hatch-commands.md` priority field based on results using three-tier logic: (a) if any test case shows `allow` (silent execution): set priority to `high` — deny rules do not compose through wrappers, removing escape hatches is urgent; (b) if any test case shows `ask` but none show `allow`: set priority to `medium` — Claude Code inspects interpreter arguments (consistent with ticket 057's own "lower priority" conditional), but removing escape hatches is still worthwhile as defense-in-depth; (c) if all test cases show `deny`: set priority to `low` — deny rules already compose through wrappers. Append a brief rationale note to the body referencing the test results and the mechanism analysis. Acceptance criteria: `grep -c 'priority:' backlog/057-remove-interpreter-escape-hatch-commands.md` = 1 (field exists with updated value), and body contains a "## Verification results" section.

7. **Research open questions resolved**: Update the `## Open Questions` section of `lifecycle/verify-escape-hatch-bypass-mechanism/research.md` with resolution annotations based on empirical findings, including the mechanism determination from the control test. Acceptance criteria: the two existing open question bullets in research.md contain inline resolution text (e.g., "RESOLVED: ...") or are replaced with resolved versions.

## Non-Requirements

- **No settings.json changes**: This spike verifies behavior; it does not modify the allow/deny list. Changes are ticket 057's scope.
- **No encoding variations or indirect interpreter paths**: Testing `$'...'` quoting, `/usr/bin/env bash -c`, `command bash -c`, or other exotic vectors is deferred. If baseline results warrant deeper investigation, a follow-up ticket will be created.
- **No overnight runner testing**: The overnight runner bypasses permissions entirely via `--dangerously-skip-permissions`. Permission-layer verification is only relevant to interactive sessions.
- **No sandbox-layer testing**: The spike tests whether the permission layer catches interpreter-wrapped commands. Sandbox behavior is observed as a side effect but is not the primary test target.
- **No differential testing via settings modification**: Temporarily removing deny rules to isolate mechanisms is out of scope (requires session restart). The control test case (R2) provides mechanism disambiguation without settings changes.

## Edge Cases

- **Ask outcome**: If a test command triggers a permission prompt (ask) rather than a silent allow or deny, this is a meaningful partial protection. The test report must distinguish ask from allow — ask provides user-in-the-loop mitigation that allow does not, and the two map to different 057 priority levels (medium vs. high).
- **Sandbox pre-emption on test case 4**: The `sh -c "rm -rf /tmp/test"` command may be blocked by the sandbox before the permission layer evaluates it. If the tool call returns a sandbox error, the permission-layer outcome is indeterminate. Check the permission audit log: if a `permission_prompt` entry exists, the permission layer evaluated before sandbox. If no log entry and sandbox blocked, document as "inconclusive — sandbox blocked before permission evaluation."
- **Control case interpretation**: If R2 (`bash -c "echo hello"`) is blocked/prompted AND R1 is also blocked/prompted, both results reflect the f65 classifier, not deny-rule composition. If R2 passes but R1 is blocked, the deny rule is being evaluated through the wrapper. If both pass, the escape hatch is confirmed open. Document the mechanism determination in the test report.
- **Session-specific settings**: The active session's merged permissions may differ from the template due to `settings.local.json` overrides. Before running tests, verify that the relevant allow/deny entries match the template by reading the active settings.
- **Tool call response ambiguity**: If a command is blocked, distinguish the response type: permission denial (explicit rejection message from Claude Code's permission system), sandbox violation (OS-level operation-not-permitted error), or agent self-censorship (agent declines to issue the tool call). Only permission denial and sandbox violation are empirical results; self-censorship must be overcome by explicit instruction.

## Changes to Existing Behavior

- [ADDED: `test-report.md`] New artifact in the lifecycle directory documenting empirical test results and mechanism analysis
- [MODIFIED: `backlog/057-remove-interpreter-escape-hatch-commands.md`] Priority field updated and verification results section appended based on findings
- [MODIFIED: `lifecycle/verify-escape-hatch-bypass-mechanism/research.md`] Open questions section updated with resolution annotations

## Technical Constraints

- **Git is sandbox-excluded**: `excludedCommands: ["git:*"]` means git commands bypass sandbox enforcement. Test case 1 (`bash -c "git push --force --dry-run"`) is the cleanest test because the permission system is the sole gatekeeper — no sandbox interference to disentangle. The `--dry-run` flag prevents actual push if the permission system allows execution.
- **Observation methodology**: The primary instrument is the tool call response — whether the command executes (allow), returns a permission error (deny), or triggers a user prompt (ask). The permission audit log at `$TMPDIR/claude-permissions-{session_key}.log` is supplementary evidence: it confirms whether a `permission_prompt` event fired, but cannot confirm silent denials (which produce no log entry).
- **autoAllowBashIfSandboxed**: Set to `true` in the active config. This auto-approves non-denied commands within sandbox constraints but does NOT bypass deny rules. If a deny rule fires, `autoAllowBashIfSandboxed` does not override it.
- **Settings verification**: Before running tests, verify the active session has `Bash(bash *)` in allow and `Bash(git push --force *)` in deny by reading `~/.claude/settings.json` (or the merged active config). If the entries don't match, results don't apply to the template.
- **f65 dangerous-shell-prefix classifier**: Binary analysis identified an internal classifier that flags `bash`, `sh`, and other interpreters as dangerous prefixes. This classifier operates independently of glob-matching deny rules. The control test case (R2) disambiguates classifier-based blocking from deny-rule composition.

## Open Decisions

- None. All decisions resolved during the interview and critical review.
