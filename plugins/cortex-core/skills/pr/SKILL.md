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

1. Run `git branch --show-current` to get the current branch
2. Detect the base branch:
   ```bash
   gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'
   ```
3. Run `git log --oneline <base>..HEAD`, `git diff --stat <base>..HEAD`, and `git status` in parallel to gather context
4. If there are uncommitted changes, warn the user and stop — they should `/cortex-core:commit` first
5. If the branch has no commits ahead of base, warn and stop — nothing to PR
6. Push the branch if not yet pushed: `git push -u origin HEAD`
7. Check for a PR template (case-insensitive — GitHub accepts both casings):
   - `.github/pull_request_template.md` or `.github/PULL_REQUEST_TEMPLATE.md`
   - Files in `.github/pull_request_template/` or `.github/PULL_REQUEST_TEMPLATE/`
8. If a template exists, read it and fill in each section thoughtfully (preserve the template's structure and headings):
   - **Replace placeholder tokens** (e.g., `{JIRA_TICKET}`) with actual values derived from context — parse the branch name for ticket IDs, etc. If a value can't be determined, ask the user rather than leaving the placeholder.
   - **`{PR_NUMBER}` is special** — it can't be resolved before creation. Leave it as `{PR_NUMBER}` in the body, then after `gh pr create` returns the URL, extract the number and update the PR body with `gh pr edit <number> --body "..."`.
   - **Write meaningful testing steps.** If the template has a testing section, write verification steps specific to this change — not generic boilerplate. Consider the type of change (app feature, bugfix, tooling/scripts, CI, docs) and what a reviewer would actually need to do. Include specific commands where applicable.
   - **Fill every required section.** Never submit a PR with template default/example content still in place. Every required section should reflect the actual PR or be marked N/A.
   - **Strip HTML comments and commented-out optional sections.** Remove `<!-- ... -->` guidance blocks. Also remove entire commented-out optional blocks (e.g., `<!-- Uncomment for UI changes ... -->` with checklists or tables inside) — these are opt-in sections the author chose not to use, not sections to fill in.
9. If no template, use the default format below
10. Create the PR in two Bash calls (no `$()` in either call):
    a. Write the PR body to a temp file:
       ```bash
       printf '%s\n' "## Summary" "..." "" "## Changes" "- ..." > $TMPDIR/pr-body.md
       ```
    b. Create the PR using `--body-file`:
       ```bash
       gh pr create --title "..." --body-file "$TMPDIR/pr-body.md"
       ```
11. Output the PR URL

Do not output conversational text — only tool calls, except for the final PR URL.

## Default PR Body Format

When no template exists, use this format:

```
## Summary
<1-3 sentences: why this change exists and what reviewers should focus on>

## Changes
- <bullet per logical change — keep high-level, not a changelog>
```

Focus on the *why* and anything non-obvious, not a detailed inventory of what was touched. Reviewers can see the diff — the description should add context the diff doesn't show.

## PR Title

- Max 70 characters
- Imperative mood, capitalized ("Add", "Fix", "Update")
- No trailing period
- Summarize the *why*, not the *what*

## PR Body Format

Always use two separate Bash calls — no `$()` in either call:

1. Write the body to a temp file:
```bash
printf '%s\n' "## Summary" "Description here" "" "## Changes" "- Change one" "- Change two" > $TMPDIR/pr-body.md
```

2. Create the PR with `--body-file`:
```bash
gh pr create --title "Title here" --body-file "$TMPDIR/pr-body.md"
```

## Constraints

- No `--draft`, `--reviewer`, `--assignee`, or `--label` flags unless the user explicitly requests them
- No `--force` push — ever
- No AI attribution in the PR body
- No command chaining — use separate tool calls
- No `git -C`
