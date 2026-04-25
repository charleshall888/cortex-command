---
name: discovery
description: Ideation research for topics not ready for implementation. Checks whether the topic is well-aimed, investigates the problem space thoroughly, then decomposes findings into backlog tickets grouped by epic. Use when user says "/cortex-interactive:discovery", "discover this", "research and ticket", "break this down into tickets", "decompose into backlog", "create an epic for", "investigate before building", "what should I discover", "find gaps in requirements", "self-directed discovery", "no topic discovery", or wants to understand a topic deeply before committing to build it. Also use when invoked with no arguments to scan requirements and suggest gap candidates. Different from /cortex-interactive:lifecycle — discovery stops at backlog tickets rather than proceeding to plan/implement.
argument-hint: "[topic]"
inputs:
  - "topic: string (optional) — the topic or feature area to research and decompose into backlog tickets; if omitted, auto-scan mode activates to suggest gap candidates from requirements"
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

- `/cortex-interactive:discovery {{topic}}` — start new or resume existing discovery
- `/cortex-interactive:discovery {{phase}}` — jump to a specific phase (clarify, research, decompose)
- `/cortex-interactive:discovery` — no topic; triggers auto-scan mode to suggest gap candidates from requirements

## Step 1: Identify the Topic

Topic: $ARGUMENTS (if non-empty, use as research topic; if empty, self-directed mode — scan requirements for gap candidates).

Determine the `{{topic}}` from invocation. Use lowercase-kebab-case for directory naming (e.g., `research/plugin-system/`).

**If no topic was provided**: read `${CLAUDE_SKILL_DIR}/references/auto-scan.md` and execute the auto-scan protocol. The scan produces `{{topic}}` from user selection; once selected, continue to Step 2.

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

## Phase Transition

After completing a phase artifact, commit the `research/{{topic}}/` directory, summarize findings, and proceed to the next phase automatically.

## Multiple Discoveries

One active discovery at a time. If multiple incomplete `research/*/` directories exist (those without `decomposed.md`), list them and ask which to resume.

## Relationship to /cortex-interactive:lifecycle

When `/cortex-interactive:discovery` creates backlog tickets, each ticket receives a `discovery_source:` field pointing to the research artifact. When `/cortex-interactive:lifecycle` starts on that ticket, it automatically loads the prior research, presents a summary, and asks whether to skip re-investigation (default: skip). In pipeline or overnight contexts the skip is applied automatically. To re-investigate from scratch, choose N at the prompt.
