---
name: pr-review
description: Review a GitHub pull request using a multi-agent pipeline. Use when user says "/pr-review", "/pr-review <number>", "review this PR", "review PR 123", "review my pull request", or asks for a code review of an open pull request.
disable-model-invocation: true
argument-hint: "[number]"
inputs:
  - "number: string (optional) — GitHub PR number; omit to review the PR for the current branch"
outputs:
  - "Review verdict: APPROVE | REQUEST_CHANGES | REJECT with synthesized findings (stdout)"
preconditions:
  - "GitHub CLI (gh) installed and authenticated"
  - "Repository must be a GitHub repo"
  - "If number is omitted, current branch must have an open PR"
---

# PR Review

Run a structured multi-agent review of a GitHub pull request and present a synthesized verdict.

PR: $ARGUMENTS (if non-empty, use as PR number; if empty, auto-detect from current branch).

## Invocation

```
/pr-review           # reviews the PR for the current branch
/pr-review {{number}}  # reviews a specific PR by number
```

Natural language triggers: "review this PR", "review PR 123", "review my pull request".

## What This Skill Does

The pipeline fetches PR metadata and the full diff, then runs a Haiku triage agent to
classify changed files by review priority. Four Sonnet agents run in parallel — each
examining the diff from a different angle: project convention compliance, bug scanning,
git history context, and historical PR feedback on the same files. An Opus agent then
cross-validates their findings and issues a verdict of APPROVE, REQUEST CHANGES, or REJECT.
The main agent presents the synthesis output and keeps all prior agent outputs available
for follow-up questions.

## Protocol

Before doing anything else, read `${CLAUDE_SKILL_DIR}/references/protocol.md` in full. It defines every stage
of the pipeline: exact commands, verbatim prompt templates for each subagent, and failure
handling for every error scenario. Do not proceed without reading it.

## Constraints

- Do not post the review as a GitHub comment unless the user explicitly requests it
- Keep all prior agent outputs in context so the user can ask follow-up questions
- If a stage fails, follow the failure handling rules in `${CLAUDE_SKILL_DIR}/references/protocol.md` exactly
- No conversational text during execution — only tool calls until the final summary
