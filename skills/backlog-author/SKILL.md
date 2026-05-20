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

Read `skills/backlog-author/references/body-template.md` before beginning the interview. The template's section-boundary criteria, the Why-vs-Role disambiguation rule, and the Touch-points prose-only constraint all inform which questions to ask and how to apply answers.

The interview guides a human author through constructing a structured ticket body. Use `AskUserQuestion` to present each question interactively — not as plain markdown text. Ask one question at a time, waiting for the user's response before posing the next. The previous answer is the gate to the next question so each question can be shaped by what just landed. Avoid batching multiple questions into a single turn.

**Interview sequence**

1. **Why** — Ask the author to describe the problem the ticket addresses in symptom-voice: what is broken, missing, or degraded in observable terms, as a user or operator would describe the symptom. The answer should not name a solution or mechanism. If the author's answer collapses to a single sentence that would merely restate Role's lead, note the disambiguation rule and flag that Why may be omitted after Role is captured.

2. **Role** — Ask what job this piece fulfills in the system once the ticket lands. The answer should name the arc42 Responsibility — what task exists in the system after this piece is present that could not be done before — without describing how it is built or which files it touches.

3. **Integration** — Ask how this piece connects to neighboring pieces and the existing system. The answer should reference contract surfaces by name (e.g., "the phase-transition contract", "the events-registry schema") without citing file paths or line numbers. Prompt for both inbound and outbound Interface connections.

4. **Edges** — Ask the author to enumerate structural constraints and boundary conditions: what breaks if an upstream contract changes shape, what this piece must not do, and what explicit non-goal decisions keep the scope tight. Each answer item names a contract surface or non-goal by name without citing file paths.

5. **Touch points** (optional) — Ask whether there are known implementation locations: specific file paths with line numbers, section indices, or code excerpts. Inform the author that this section is optional and should be omitted when no implementation locations are known at authoring time.

**Applying answers**

After all questions are answered, apply the Why-vs-Role disambiguation rule: if Why collapses to a single sentence restating Role's lead, omit the Why section from the output. Then compose the body using the five-section template from `skills/backlog-author/references/body-template.md` and emit it to stdout as a markdown block suitable for passing to `cortex-create-backlog-item --body`.

If the author abandons the session mid-interview, exit cleanly without emitting any partial output.

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
