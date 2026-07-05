---
name: commit
description: Create git commits with consistent, well-formatted messages. Use when user says "commit", "/cortex-core:commit", "make a commit", "commit these changes", or asks to save/checkpoint their work as a git commit.
---

# Commit

Create a single git commit from the current working tree changes.

## Workflow

1. Run `cortex-commit-preflight` for status, working-tree diff, and last 10 commits (one JSON document).
2. Stage relevant files with `git add` (specific files, not `-A`).
3. Compose the message per the format below and commit with `git commit -m`.

Do not push. Do not create branches. Do not output conversational text — only tool calls. A PreToolUse hook validates the message before execution; if it rejects the commit, read the reason and fix the message — do not bypass (e.g. via `git commit -F` or the editor, which the hook cannot see).

## Commit Message Format

Keep the subject imperative-mood and ~72 chars, and summarize the *why*, not the *what*. The hook does not reliably enforce these, so write them yourself: use "Add"/"Fix"/"Remove" — never "Adds"/"Added"/"Fixes". Add a blank-line-separated body only when the change needs motivation; use `- ` bullets for multiple items.

**Release-type marker** — drives the auto-release semver bump; the default is a **patch**. Add a marker only when the change is more than a patch:

- backward-compatible feature → add `[release-type: minor]`
- breaking change → add `[release-type: major]`

The marker must be the entire content of its own line; a column-0 `BREAKING:` also forces major. For the regex, precedence, `--dry-run` check, and examples, read `${CLAUDE_SKILL_DIR}/references/release-type.md`.

## Commit Command

Use `git commit -m "subject"`, adding a second `-m` for a multi-line body. Never use HEREDOC (`<<EOF`) or command substitution (`$(cat ...)`) — these create temp files that fail in sandboxed environments. Never use `dangerouslyDisableSandbox: true` for `git commit`.
