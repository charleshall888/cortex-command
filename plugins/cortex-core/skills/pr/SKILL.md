---
name: pr
description: Create GitHub pull requests with well-crafted titles and descriptions. Use when user says "pr", "/cortex-core:pr", "create a pr", "open a pull request", "submit a pr", "make a pull request", or asks to get their changes ready for review.
inputs: []
outputs:
  - "GitHub PR URL — created via gh pr create (printed to stdout)"
preconditions:
  - "Must be on a feature branch with commits ahead of the base branch"
  - "No uncommitted changes in working tree"
  - "GitHub CLI (gh) installed and authenticated"
---

# Pull Request

Create a GitHub pull request from the current branch.

## Workflow

1. Gather context in parallel: current branch (`git branch --show-current`), base branch (`gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'`), and `git log --oneline <base>..HEAD`, `git diff --stat <base>..HEAD`, `git status`.
2. Enforce the preconditions before creating anything: if the working tree has uncommitted changes, warn and stop (the user should `/cortex-core:commit` first); if the branch has no commits ahead of base, warn and stop — nothing to PR.
3. Push the branch if not yet pushed: `git push -u origin HEAD`.
4. Detect a PR template (case-insensitive — GitHub accepts both casings): `.github/pull_request_template.md` / `.github/PULL_REQUEST_TEMPLATE.md`, or a file under `.github/pull_request_template/` / `.github/PULL_REQUEST_TEMPLATE/`.
5. If a template exists, read `${CLAUDE_SKILL_DIR}/references/template-filling.md` and fill the template following that guidance. If no template, use the default format below.
6. Create the PR in two Bash calls — no `$()` in either call (command substitution creates temp files that fail in sandboxed environments):
   a. Write the body to a temp file: `printf '%s\n' "## Summary" "..." "" "## Changes" "- ..." > $TMPDIR/pr-body.md`
   b. Create the PR with `--body-file`: `gh pr create --title "..." --body-file "$TMPDIR/pr-body.md"`
7. Output the PR URL.

Do not output conversational text — only tool calls, except for the final PR URL.

## Default PR Body Format

When no template exists, use this format:

```
## Summary
<1-3 sentences: why this change exists and what reviewers should focus on>

## Changes
- <bullet per logical change — keep high-level, not a changelog>
```

Focus on the *why* and the non-obvious — the diff already shows the what.

## PR Title

- Max 70 characters
- Imperative mood, capitalized ("Add", "Fix", "Update")
- No trailing period

## Constraints

- No `--draft`, `--reviewer`, `--assignee`, or `--label` flags unless the user explicitly requests them
- No `--force` push — ever
- No AI attribution in the PR body
- No command chaining — use separate tool calls
- No `git -C`
