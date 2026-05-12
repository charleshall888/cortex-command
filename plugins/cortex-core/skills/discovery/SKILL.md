---
name: discovery
description: Ideation research for topics not ready for implementation — checks aim, investigates the problem space, then decomposes findings into backlog tickets grouped by epic. Use when user says "/cortex-core:discovery", "discover this", "research and ticket", "break this down into tickets", "decompose into backlog", "create an epic for", "investigate before building", "what should I discover", or wants to understand a topic before committing to build. Requires a topic argument; for "what should I work on" or "next task" routing without a specific topic, use /cortex-core:dev instead.
when_to_use: "Use when investigating a topic deeply before committing to build it. Different from /cortex-core:research — research produces a research.md and stops; discovery wraps clarify→research→decompose and ends with backlog tickets. Different from /cortex-core:lifecycle — discovery stops at backlog tickets rather than proceeding to plan/implement."
argument-hint: "<topic>"
inputs:
  - "topic: string (required) — the topic or feature area to research and decompose into backlog tickets"
  - "phase: string (optional) — explicit phase to enter: clarify|research|decompose"
outputs:
  - "backlog/NNN-{{topic}}.md — decomposed backlog tickets grouped by epic"
  - "research/{{topic}}/ — durable research artifact"
preconditions:
  - "Run from project root"
  - "backlog/ directory exists"
---

# Discovery

## Invocation

- `/cortex-core:discovery {{topic}}` — start new or resume existing discovery
- `/cortex-core:discovery {{phase}}` — jump to a specific phase (clarify, research, decompose)

## Step 1: Identify the Topic

Topic: $ARGUMENTS (required — non-empty topic).

Determine the `{{topic}}` from invocation. Use lowercase-kebab-case for directory naming (e.g., `research/plugin-system/`).

**If `$ARGUMENTS` is empty**: halt with the message "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead." Do not proceed to Step 2.

**If a topic was provided**: proceed to Step 2 directly.

## Step 2: Check for Existing State

Scan for `research/{{topic}}/` at the project root:

```
if no research/{{topic}}/ directory exists:
    phase = clarify
elif research.md exists and no decomposed.md:
    phase = decompose
elif decomposed.md exists:
    phase = complete (offer to re-run or update)
```

Backward compat: existing discoveries that have `spec.md` but no `decomposed.md` will also have `research.md` present and correctly resume at `phase = decompose`.

If resuming, report the detected phase and offer to continue or restart from an earlier phase.

## Step 3: Execute Current Phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation output only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the reference for the current phase.

Within the Decompose phase, a user-blocking post-decompose batch-review gate (`checkpoint: decompose-commit`) fires after all ticket bodies are authored and the prescriptive-prose scanner has passed, BEFORE any tickets commit to `backlog/`. The gate offers `approve-all`, `revise-piece <N>`, and `drop-piece <N>` options and emits an `approval_checkpoint_responded` event per response. See decompose.md §5 for the gate semantics.

## Phase Transition

After completing a phase artifact, commit the `research/{{topic}}/` directory, summarize findings, and proceed to the next phase automatically.

## Multiple Discoveries

One active discovery at a time. If multiple incomplete `research/*/` directories exist (those without `decomposed.md`), list them and ask which to resume.

## Relationship to /cortex-core:lifecycle

When `/cortex-core:discovery` creates backlog tickets, each ticket receives a `discovery_source:` field pointing to the research artifact. When `/cortex-core:lifecycle` starts on that ticket, it automatically loads the prior research, presents a summary, and asks whether to skip re-investigation (default: skip). In pipeline or overnight contexts the skip is applied automatically. To re-investigate from scratch, choose N at the prompt.
