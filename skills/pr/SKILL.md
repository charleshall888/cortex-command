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

1. Gather in parallel: current branch (`git branch --show-current`), base branch (`gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'`), `git log --oneline <base>..HEAD`, `git diff --stat <base>..HEAD`, `git status`.
2. Warn and stop if the working tree has uncommitted changes (`/cortex-core:commit` first) or the branch has no commits ahead of base (nothing to PR); else push if unpushed: `git push -u origin HEAD`.
3. Detect a PR template (`.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, or a file under `.github/pull_request_template/` or `.github/PULL_REQUEST_TEMPLATE/`); if found, read `${CLAUDE_SKILL_DIR}/references/template-filling.md` and follow it, otherwise use the default format below.
4. Create the PR in two Bash calls — no `$()` in either (creates temp files that fail sandboxed): `printf` the body to `$TMPDIR/pr-body.md`, then `gh pr create --title "..." --body-file "$TMPDIR/pr-body.md"`.
5. Output the PR URL — the only conversational text; the rest is tool calls.

## Default PR Body Format

```
## Summary
<1-3 sentences: why it exists, what reviewers should focus on>

## Changes
- <bullet per logical change — high-level, not a changelog>
```

Focus on the *why* and the non-obvious — the diff already shows the what.

## PR Title

Max 70 characters, imperative mood, capitalized ("Add", "Fix", "Update"), no trailing period.

## Constraints

No `--draft`/`--reviewer`/`--assignee`/`--label` unless requested; no `--force` push, ever; no AI attribution in the body; no command chaining (separate tool calls); no `git -C`.
