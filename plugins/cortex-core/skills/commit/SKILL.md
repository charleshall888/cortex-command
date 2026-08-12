---
name: commit
description: Create a git commit with a well-formatted message.
---

# Commit

Run `cortex-commit-preflight` for status, diff, and history in one JSON document. Stage the relevant files with `git add` (specific paths, never `-A`), then:

```
git commit --only -m "..." [-m "..."] -- <the same paths>
```

Concurrent sessions share one git index, so a bare `git commit` sweeps whatever a sibling session staged — the trailing pathspec with `--only` is what makes this safe. Confirm with `git show --stat HEAD`. Never HEREDOC or `$(...)`: both create temp files that fail sandboxed, and never disable the sandbox.

Subject: imperative mood, ≤72 chars, the *why* over the *what*. Body only when the change needs motivation.

Do not push or branch. Emit tool calls, not conversational text.
