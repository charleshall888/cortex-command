---
type: other
test-command: just test
skip-specify: false
skip-review: false
commit-artifacts: true
# Gate for the overnight critical-tier dual-plan synthesizer dispatch path.
# Default false (fail-closed) until the operator validates the path and flips to true.
synthesizer_overnight_enabled: false
branch-mode: prompt
demo-commands:
  - label: "Dashboard"
    command: "just dashboard"
---

# Lifecycle Configuration

Project-specific overrides for the lifecycle skill.

## Review Criteria

- Settings JSON files must remain valid JSON after any changes
- New hook/notification scripts must be executable (`chmod +x`)
- New config files ship via the relevant plugin tree (cortex-core, cortex-overnight) — never as host-level symlinks
- New skills must have `name` and `description` frontmatter

## Branch Mode

The `branch-mode` frontmatter field configures the default branch-selection behavior of `/cortex-core:lifecycle implement` when invoked on a `main`/`master` checkout. When set to one of the closed-set values below AND the carve-out preflight passes (see below), the three-option branch picker is suppressed and the lifecycle proceeds directly along the chosen path. When unset, absent, or invalid, the picker fires as today.

This project's frontmatter sets `branch-mode: prompt` to preserve the existing pre-feature behavior (picker fires every time). Operators of other repos that adopt cortex-command can flip this to one of the other three values to make a different path the default.

### Values (closed set)

- `worktree-interactive` — skip the picker and proceed directly to the worktree-interactive path (creates a feature branch and a `<repo>/.claude/worktrees/` worktree, hands off to a new Claude Code session in that worktree).
- `trunk` — skip the picker and proceed on the current branch (commits land on `main`/`master`).
- `feature-branch` — skip the picker and proceed to the feature-branch path (creates and checks out `feature/{slug}` in the current working tree).
- `prompt` — picker fires every time (equivalent to leaving the field unset).

### Carve-outs (picker fires regardless of `branch-mode`)

The picker is re-presented — overriding any `branch-mode` short-circuit — when either of these hazardous states is detected:

- **Dirty working tree.** When `git status --porcelain` reports uncommitted changes, the picker fires with a warning prefix so the operator can route the change deliberately rather than mixing uncommitted edits into a `main`-targeted commit.
- **Concurrent live interactive worktree for this feature.** When `cortex/lifecycle/sessions/{slug}.interactive.pid` exists AND its PID is live (per `kill -0`), the picker fires to prevent routing commits onto `main` concurrent with the sibling worktree's diverging history (the shared-index hazard the worktree-interactive flow was built to prevent).

### Normalization rules

- **Case-sensitive.** `trunk` matches; `TRUNK`, `Trunk`, and other case variants do not — they fall through to picker with a stderr warning.
- **Whitespace-stripped.** Leading and trailing whitespace around the value is ignored (`'  trunk  '` matches `trunk`).
- **Last-wins on duplicate keys.** If `branch-mode:` appears twice in the frontmatter, the last value wins (per `yaml.safe_load` default semantics).
- **Commented value → unset.** `branch-mode: # commented out` parses as null and is treated as if the field were absent (picker fires).
- **Invalid value → fall-through to picker.** A value outside the closed set (`worktree-interactive | trunk | feature-branch | prompt`) is treated as unset; a stderr warning names the rejected value and the picker fires. This is the safety direction — operators with a typo see the picker instead of silently routing to an unintended path.

### Edge cases

- **Sandbox preflight failure inside the worktree-interactive path** still halts via the existing `sys.exit(2)` path after `branch-mode: worktree-interactive` short-circuit; operators who want explicit picker context for that failure surface can unset `branch-mode`.
