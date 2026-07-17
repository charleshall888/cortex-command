---
name: commit
description: Create git commits with consistent, well-formatted messages. Use when user says "commit", "/cortex-core:commit", "make a commit", "commit these changes", or asks to save/checkpoint their work as a git commit.
---

# Commit

Create a single git commit from the current working tree changes.

## Workflow

Run `cortex-commit-preflight` for status, diff, and recent history (one JSON document); stage relevant files with `git add` (specific files, not `-A`); compose the message per the format below and commit with `git commit --only -m "..." -- <the same paths>`. Concurrent sessions share one git index, and a bare `git commit` sweeps whatever a sibling session staged — `--only` bounds the commit to the named paths. After committing, confirm with `git show --stat HEAD` that only the intended files landed. Do not push, branch, or emit conversational text — only tool calls.

A PreToolUse hook validates the message before execution; if it rejects the commit, fix the message — don't bypass it via `git commit -F` or an editor, which the hook can't see.

## Commit Message Format

Subject: imperative mood, ~72 chars, the *why* over the *what* ("Add"/"Fix"/"Remove", never "Adds"/"Added"/"Fixes" — unenforced by the hook). Add a blank-line body only when the change needs motivation, with `- ` bullets for multiple items.

**Release-type marker** drives the auto-release semver bump (default **patch**), alone on its own line: `[release-type: minor]` for a backward-compatible feature, `[release-type: major]` for a breaking change. Read `${CLAUDE_SKILL_DIR}/references/release-type.md` for the regex, the `BREAKING:` fallback, precedence, and the `--dry-run` check.

## Commit Command

`git commit --only -m "..." [-m "..."] -- <paths>` (a second `-m` for a multi-line body; the trailing pathspec is what makes the commit concurrency-safe); never HEREDOC or command substitution — both create temp files that fail sandboxed; never disable the sandbox.
