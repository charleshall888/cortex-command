# Filling a PR template

Fill each section of the detected template, preserving its structure and headings:

- **Replace placeholders** (e.g., `{JIRA_TICKET}`) with real values from context (e.g., parse the branch name for ticket IDs); ask the user if a value can't be determined.
- **`{PR_NUMBER}`** can't resolve before creation — leave it as-is, then after `gh pr create` returns the URL, update the body via `gh pr edit <number> --body "..."`.
- **Testing steps**: specific to this change, concrete commands, not boilerplate.
- **Fill every required section** — no leftover default/example content; mark inapplicable ones N/A.
- **Strip HTML comments and commented-out optional blocks** (e.g., `<!-- Uncomment for UI changes ... -->`) — opt-in sections the author didn't use, not blanks to fill.
