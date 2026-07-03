---
name: backlog-author
description: >
  Compose structured backlog ticket bodies using the Why/Role/Integration/Edges/Touch-points template.
  Use when user says "ticket authoring", "compose", "write a ticket body", or "author a backlog item".
  Two subcommands: interview (guided prompts) and compose (autonomous, context-driven).
argument-hint: "interview <topic> | compose <context-block>"
---

# backlog-author

Author structured backlog ticket bodies using the Why/Role/Integration/Edges/Touch-points template.

Subcommand: $ARGUMENTS (first word = subcommand; remainder = subcommand args)

## Subcommand Dispatch

When invoked without a `{{subcommand}}`, present the available modes via `AskUserQuestion`:

- **interview** — Guided Q&A session; produces a structured body from human answers
- **compose** — Autonomous body composition from a provided context block

### interview

Read `${CLAUDE_SKILL_DIR}/references/body-template.md` before beginning the interview. The template's section-boundary criteria, the Why-vs-Role disambiguation rule, and the Touch-points prose-only constraint all inform which questions to ask and how to apply answers.

The interview guides a human author through constructing a structured ticket body. Use `AskUserQuestion` to present each question interactively — not as plain markdown text. Ask one question at a time, waiting for the user's response before posing the next. The previous answer is the gate to the next question so each question can be shaped by what just landed. Avoid batching multiple questions into a single turn.

**Applying answers**

After all questions are answered, apply the Why-vs-Role disambiguation rule: if Why collapses to a single sentence restating Role's lead, omit the Why section from the output. Then compose the body using the five-section template from `skills/backlog-author/references/body-template.md` and emit it to stdout as a markdown block suitable for passing to `cortex-create-backlog-item --body`.

If the author abandons the session mid-interview, exit cleanly without emitting any partial output.

### compose

The compose subcommand authors a structured ticket body autonomously from a provided context block.

**Input contract**: one piece's context per invocation. The context block may be structured
(pre-resolved `why:`, `role:`, `integration:`, `edges:`, and optional `touch_points:` fields)
or free-form (natural-language description from which Claude infers the field values). When a
caller has N pieces to author, it invokes compose N times — one piece per invocation.

**Output contract**: one complete five-section markdown body block (`## Why`, `## Role`,
`## Integration`, `## Edges`, `## Touch points`). Frontmatter is owned by
`cortex-create-backlog-item --body`, not by this sub-skill — emit only the body content.

Steps:
1. Read `${CLAUDE_SKILL_DIR}/references/body-template.md` to load section-boundary criteria,
   the Why-vs-Role disambiguation rule, and grounding keywords.
4. Compose the five-section body. Emit it to stdout as a markdown block for the caller to pass
   to `cortex-create-backlog-item --body`.
