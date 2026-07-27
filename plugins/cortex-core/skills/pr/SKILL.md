---
name: pr
description: Create GitHub pull requests with well-crafted titles and descriptions. Use when user says "pr", "/cortex-core:pr", "create a pr", "open a pull request", "submit a pr", "make a pull request", or asks to get their changes ready for review.
---

# Pull Request

1. Gather in parallel: current branch, base branch (`gh repo view --json defaultBranchRef`), `git log --oneline <base>..HEAD`, `git diff --stat <base>..HEAD`, `git status`.
2. Stop if the tree is dirty (`/cortex-core:commit` first) or there are no commits ahead of base. Otherwise `git push -u origin HEAD` if unpushed.
3. Create the PR in two Bash calls — no `$()` in either (temp files fail sandboxed): `printf` the body to `$TMPDIR/pr-body.md`, then `gh pr create --title "..." --body-file "$TMPDIR/pr-body.md"`.
4. Output the PR URL — the only conversational text.

Title: ≤70 chars, imperative, capitalized, no trailing period.

Body: a `## Summary` (why it exists, where reviewers should look) and `## Changes` bullets per logical change. Focus on the *why* and the non-obvious — the diff shows the what.

If `.github/pull_request_template*` exists, fill its sections instead: substitute placeholders from context, strip commented-out opt-in blocks, mark inapplicable sections N/A. `{PR_NUMBER}` can't resolve before creation — leave it, then `gh pr edit <number> --body` afterward.

No `--draft`/`--reviewer`/`--assignee`/`--label` unless asked; never `--force`; no AI attribution; no `git -C`.
