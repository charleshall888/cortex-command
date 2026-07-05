---
name: backlog-author
description: >
  Compose structured backlog ticket bodies using the Why/Role/Integration/Edges/Touch-points template.
  Use when user says "ticket authoring", "compose", "write a ticket body", or "author a backlog item".
  Two subcommands: interview (guided prompts) and compose (autonomous, context-driven).
argument-hint: "interview <topic> | compose <context-block>"
---

# backlog-author

Subcommand: $ARGUMENTS (first word = subcommand; remainder = subcommand args)

## Subcommand Dispatch

When invoked without a `{{subcommand}}`, present the available modes via `AskUserQuestion`:

- **interview** — Guided Q&A session; produces a structured body from human answers
- **compose** — Autonomous body composition from a provided context block

### interview

Read `${CLAUDE_SKILL_DIR}/references/body-template.md` before beginning the interview; it governs which questions to ask and how to apply answers.

The interview guides a human author through constructing a structured ticket body. Use `AskUserQuestion` to present each question interactively — not as plain markdown text. Ask one question at a time, letting each answer shape the next; never batch questions into one turn.

**Applying answers**

After all questions are answered, apply the Why-vs-Role disambiguation rule from body-template.md (omit Why when it collapses to Role's lead). Then compose the five-section body and emit it to stdout as a markdown block for `cortex-create-backlog-item --body`.

If the author abandons the session mid-interview, exit cleanly without emitting any partial output.

### compose

Authors a structured ticket body autonomously from a provided context block.

**Input contract**: one piece's context per invocation (a caller with N pieces invokes compose N times). The context block may be structured
(pre-resolved `why:`, `role:`, `integration:`, `edges:`, and optional `touch_points:` fields)
or free-form (natural-language description from which Claude infers the field values).

**Output contract**: one complete five-section markdown body block (`## Why`, `## Role`,
`## Integration`, `## Edges`, `## Touch points`). Frontmatter is owned by
`cortex-create-backlog-item --body`, not by this sub-skill — emit only the body content.

Steps:
1. Read `${CLAUDE_SKILL_DIR}/references/body-template.md` to load section-boundary criteria,
   the Why-vs-Role disambiguation rule, and grounding keywords.
2. Compose the five-section body and emit only that markdown block to stdout.
