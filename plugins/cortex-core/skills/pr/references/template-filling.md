# Filling a PR template

Read the detected template and fill in each section, preserving the template's structure and headings:

- **Replace placeholder tokens** (e.g., `{JIRA_TICKET}`) with actual values derived from context — parse the branch name for ticket IDs, etc. If a value can't be determined, ask the user rather than leaving the placeholder.
- **`{PR_NUMBER}` is special** — it can't be resolved before creation. Leave it as `{PR_NUMBER}` in the body, then after `gh pr create` returns the URL, extract the number and update the PR body with `gh pr edit <number> --body "..."`.
- **Write meaningful testing steps.** If the template has a testing section, write verification steps specific to this change — not generic boilerplate — with concrete commands where applicable.
- **Fill every required section.** Never submit a PR with template default/example content still in place. Every required section should reflect the actual PR or be marked N/A.
- **Strip HTML comments and commented-out optional sections.** Remove `<!-- ... -->` guidance blocks. Also remove entire commented-out optional blocks (e.g., `<!-- Uncomment for UI changes ... -->` with checklists or tables inside) — these are opt-in sections the author chose not to use, not sections to fill in.
