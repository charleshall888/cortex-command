---
name: backlog-author
description: >
  Compose structured backlog ticket bodies using the Why/Role/Integration/Edges/Touch-points template.
  Use when user says "backlog body", "ticket authoring", "interview", "compose", "write a ticket body",
  "author a backlog item", or when a skill needs to produce a structured backlog body for
  cortex-create-backlog-item. Exposes two subcommands: interview (human-facing, guided prompts)
  and compose (autonomous, context-driven).
inputs:
  - "subcommand: string (required) — interview|compose"
  - "topic: string (required with interview) — title or topic of the ticket being authored"
  - "context-block: string (required with compose) — structured context block with pre-resolved or inferable Why/Role/Integration/Edges fields"
outputs:
  - "stdout — structured five-section markdown body (## Why, ## Role, ## Integration, ## Edges, ## Touch points) for passing to cortex-create-backlog-item --body"
preconditions:
  - "Run from project root"
  - "skills/backlog-author/references/body-template.md present for compose mode reference"
argument-hint: "interview <topic> | compose <context-block>"
---

# backlog-author

Author structured backlog ticket bodies using the Why/Role/Integration/Edges/Touch-points template.

Subcommand: $ARGUMENTS (first word = subcommand; remainder = subcommand args)

## Invocation

`/backlog-author interview <topic>` — guided human-facing authoring session that produces a structured body via AskUserQuestion prompts.

`/backlog-author compose <context-block>` — autonomous authoring from a structured context block; produces a body without asking the user any questions.

## Body Template

The canonical five-section body template lives in `skills/backlog-author/references/body-template.md`. Read it before composing a body to apply section-boundary criteria, the Why-vs-Role disambiguation rule, and grounding keywords.

## Subcommand Dispatch

When invoked without a `{{subcommand}}`, present the available modes via `AskUserQuestion`:

- **interview** — Guided Q&A session; produces a structured body from human answers
- **compose** — Autonomous body composition from a provided context block

### interview

<!-- Task 3 will populate this section with the full interview protocol prose. -->

The interview subcommand guides a human author through constructing a structured ticket body.
It uses `AskUserQuestion` to gather the information needed for each section of the body template.

Steps:
1. Read `skills/backlog-author/references/body-template.md` to load section-boundary criteria and the Why-vs-Role disambiguation rule.
2. Present `AskUserQuestion` prompts to gather the information required for each section: Why (symptom-voice description of what is broken or missing), Role (arc42 Responsibility — what the piece does after landing), Integration (interfaces consumed or exposed), Edges (non-goals and boundary constraints), and optionally Touch points (specific file paths or line references).
3. Apply the Why-vs-Role disambiguation rule: if Why collapses to a single sentence restating Role's lead, omit Why.
4. Emit the completed body to stdout as a markdown block suitable for passing to `cortex-create-backlog-item --body`.
5. If the author abandons the session mid-interview, exit cleanly without writing any partial output.

### compose

The compose subcommand authors a structured ticket body autonomously from a provided context block.
It does not ask the user any questions — the caller supplies all necessary context.

**Input contract**: one piece's context per invocation. The context block may be structured
(pre-resolved `why:`, `role:`, `integration:`, `edges:`, and optional `touch_points:` fields)
or free-form (natural-language description from which Claude infers the field values). When a
caller has N pieces to author, it invokes compose N times — one piece per invocation.

**Output contract**: one complete five-section markdown body block (`## Why`, `## Role`,
`## Integration`, `## Edges`, `## Touch points`). Frontmatter is owned by
`cortex-create-backlog-item --body`, not by this sub-skill — emit only the body content.

**Invocation contract**: callers pass the context block as the argument after `compose`. For
body content containing quotes, backticks, or newlines, callers use heredoc-style passing or
a temp-file redirect to avoid shell-escaping issues.

The Edge-vs-Touch-point rebalance rule — "if an edge bullet would name a path or line to
express its constraint, the path:line moves to `## Touch points`" — remains owned by the
calling skill (such as decompose.md), not by this sub-skill.

Steps:
1. Read `skills/backlog-author/references/body-template.md` to load section-boundary criteria,
   the Why-vs-Role disambiguation rule, and grounding keywords.
2. Parse the provided `{{context-block}}` to resolve Why, Role, Integration, Edges, and Touch
   points fields. Infer fields from free-form context when not explicitly labelled.
3. Apply the Why-vs-Role disambiguation rule: if Why collapses to a single sentence restating
   Role's lead, omit Why.
4. Compose the five-section body. Emit it to stdout as a markdown block for the caller to pass
   to `cortex-create-backlog-item --body`.
