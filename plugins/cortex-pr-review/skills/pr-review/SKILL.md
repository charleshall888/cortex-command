---
name: pr-review
description: Review a GitHub pull request using a multi-agent pipeline. Use when user says "/pr-review", "/pr-review <number>", "review this PR", "review PR 123", "review my pull request", or asks for a code review of an open pull request.
disable-model-invocation: true
argument-hint: "[number]"
inputs:
  - "number: string (optional) — GitHub PR number; omit to review the PR for the current branch"
outputs:
  - "Review verdict (APPROVE | REQUEST_CHANGES), Conventional Comments-labeled findings list, observability footer with dropped-finding details (stdout)"
preconditions:
  - "GitHub CLI (gh) installed and authenticated"
  - "Repository must be a GitHub repo"
  - "If number is omitted, current branch must have an open PR"
  - "jq available on PATH (macOS: brew install jq)"
  - "python3 available on PATH (macOS base install sufficient)"
  - "writable cache directory at ${CLAUDE_SKILL_DIR:-$TMPDIR}/.cache"
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
cross-validates their findings and issues a verdict of APPROVE or REQUEST CHANGES.
The main agent presents the synthesis output and keeps all prior agent outputs available
for follow-up questions.

## Protocol

The skill directory is `${CLAUDE_SKILL_DIR}` — an absolute path that resolves only here, in
this SKILL.md body. Every script and reference path in this pipeline is anchored at that
directory; reference files and composed subagent prompts cannot resolve the token themselves,
so this body resolves it and propagates the absolute value (or inlined content) to whatever
needs it.

Before doing anything else, read `${CLAUDE_SKILL_DIR}/references/protocol.md` in full. It defines every stage
of the pipeline: exact commands, verbatim prompt templates for each subagent, and failure
handling for every error scenario. Do not proceed without reading it.

Two propagation steps the body owns, because their consumers run in contexts where
`${CLAUDE_SKILL_DIR}` is unset:

- **Stage 4 dispatch — inline the rubric and output-format content.** Before composing the
  Stage-4 synthesizer prompt, Read `${CLAUDE_SKILL_DIR}/references/rubric.md` and
  `${CLAUDE_SKILL_DIR}/references/output-format.md` in full, and inline their content into the
  composed subagent prompt at dispatch time. The fresh Stage-4 subagent cannot resolve the
  token or follow a bare `rubric.md` / `output-format.md` consult-pointer, so it must receive
  the actual content inlined — never a path it would have to resolve. (Do not paste that
  content into this standing body; it belongs only in the dispatched prompt.)
- **Stage 3.5 shell invocation — propagate the absolute skill-dir path.** The evidence-grounding
  pre-step runs in a shell where `${CLAUDE_SKILL_DIR}` is unset. Resolve the absolute skill-dir
  path here and substitute it into protocol.md's Stage 3.5 shell command in place of the
  unresolvable token before running it.

## Constraints

- Do not post the review as a GitHub comment unless the user explicitly requests it
- Keep all prior agent outputs in context so the user can ask follow-up questions
- If a stage fails, follow the failure handling rules in `${CLAUDE_SKILL_DIR}/references/protocol.md` exactly
- No conversational text during execution — only tool calls until the final summary
