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

With no `{{subcommand}}`, present the modes via `AskUserQuestion`:

- **interview** — guided Q&A; produces a structured body from human answers
- **compose** — autonomous body composition from a provided context block

### interview

Read `${CLAUDE_SKILL_DIR}/references/body-template.md` first — it governs the questions and how to apply answers. Present each via `AskUserQuestion`, one at a time, never batched, each answer shaping the next.

Once answered, apply the Why-vs-Role rule from body-template.md (omit Why when it collapses to Role's lead), compose the five-section body, and emit it to stdout as a markdown block for `cortex-create-backlog-item --body`. If the author abandons mid-interview, exit cleanly with no partial output.

### compose

Autonomous ticket-body composition from a provided context block: one piece per invocation (a caller with N pieces invokes compose N times), structured (`why:`, `role:`, `integration:`, `edges:`, optional `touch_points:`) or free-form (fields inferred). Read `${CLAUDE_SKILL_DIR}/references/body-template.md` for section-boundary criteria, the Why-vs-Role rule, and grounding keywords, then emit only the five-section markdown body block (`## Why`, `## Role`, `## Integration`, `## Edges`, `## Touch points`) to stdout — frontmatter belongs to `cortex-create-backlog-item --body`, not this sub-skill.
