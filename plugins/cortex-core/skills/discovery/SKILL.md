---
name: discovery
description: Ideation research for topics not ready for implementation — checks aim, investigates the problem space, then decomposes findings into backlog tickets grouped by epic. Use when user says "/cortex-core:discovery", "discover this", "break this down into tickets", "decompose into backlog", or wants to understand a topic before committing to build. Requires a topic argument; for "what should I work on" or "next task" routing without a specific topic, use /cortex-core:dev instead.
when_to_use: "Use when investigating a topic deeply before committing to build it. Different from /cortex-core:research — research produces a research.md and stops; discovery wraps clarify→research→decompose and ends with backlog tickets. Different from /cortex-core:lifecycle — discovery stops at backlog tickets rather than proceeding to plan/implement."
argument-hint: "<topic>"
inputs:
  - "topic: string (required) — the topic or feature area to research and decompose into backlog tickets"
  - "phase: string (optional) — explicit phase to enter: clarify|research|decompose"
outputs:
  - "cortex/backlog/NNN-{{topic}}.md — decomposed backlog tickets grouped by epic"
  - "cortex/research/{{topic}}/ — durable research artifact"
preconditions:
  - "Run from project root"
  - "cortex/backlog/ directory exists"
---

# Discovery

## Step 1: Identify the Topic

Topic: $ARGUMENTS (required — non-empty topic).

Determine the `{{topic}}` from invocation. Use lowercase-kebab-case for directory naming (e.g., `cortex/research/plugin-system/`).

**If `$ARGUMENTS` is empty**: halt with the message "discovery requires a topic argument; for 'what should I work on' or 'next task' routing, use `/cortex-core:dev` instead."

## Step 2: Check for Existing State

Scan for `cortex/research/{{topic}}/` at the project root:

```
if no cortex/research/{{topic}}/ directory exists:
    phase = clarify
elif research.md exists and no decomposed.md:
    phase = decompose
elif decomposed.md exists:
    phase = complete (offer to re-run or update)
```

If resuming, report the detected phase and offer to continue or restart from an earlier phase.

### Re-run slug-collision semantics (spec R13)

On a re-run-from-scratch (not resume or update in place) of an existing `cortex/research/{{topic}}/`, read and follow `${CLAUDE_SKILL_DIR}/references/rerun-semantics.md` before writing anything — it governs slugging, frontmatter, and reconciliation.

## Step 3: Execute Current Phase

| Phase | Reference | Artifact |
|-------|-----------|----------|
| Clarify | [clarify.md](${CLAUDE_SKILL_DIR}/references/clarify.md) | none (conversation output only) |
| Research | [research.md](${CLAUDE_SKILL_DIR}/references/research.md) | `cortex/research/{{topic}}/research.md` |
| Decompose | [decompose.md](${CLAUDE_SKILL_DIR}/references/decompose.md) | Epic + backlog tickets |

Read **only** the reference for the current phase.

**Sibling-path propagation (load-bearing).** `clarify.md` and `research.md` load files that live in sibling skills, not in discovery's own `references/`. Resolve these in the body (where `${CLAUDE_SKILL_DIR}/../…` resolves) and substitute the absolute paths wherever the current-phase reference points at a sibling:

- **load-requirements** → `${CLAUDE_SKILL_DIR}/../lifecycle/references/load-requirements.md`
- **fanout** (research-sizing matrix) → `${CLAUDE_SKILL_DIR}/../research/references/fanout.md`
- **orchestrator-review** (canonical protocol) → `${CLAUDE_SKILL_DIR}/../lifecycle/references/orchestrator-review.md`
- **fix-agent-prompt-template** → `${CLAUDE_SKILL_DIR}/../lifecycle/references/fix-agent-prompt-template.md`

### Research → Decompose approval gate (spec R4)

Between Research and Decompose a single-question user-blocking gate fires — no decompose work begins until the user answers it. Whether reached by completing Research in this session or by resuming directly into Decompose, read and follow `${CLAUDE_SKILL_DIR}/references/decompose-gate.md`.

### Decompose-commit batch-review gate

In the Decompose phase, a user-blocking post-decompose batch-review gate (`checkpoint: decompose-commit`) fires after all ticket bodies are authored and the prescriptive-prose scanner has passed, before any commit to `cortex/backlog/`. See decompose.md §5 for the five response options and full gate semantics.

## Phase Transition

After completing a phase artifact, commit the `cortex/research/{{topic}}/` directory, summarize findings, and proceed to the next phase automatically.

## Multiple Discoveries

One active discovery at a time. If multiple incomplete `cortex/research/*/` directories exist (those without `decomposed.md`), list them and ask which to resume.

## Relationship to /cortex-core:lifecycle

When `/cortex-core:discovery` creates backlog tickets, each receives a `discovery_source:` field pointing to the research artifact. When `/cortex-core:lifecycle` starts on that ticket, it auto-loads the prior research, presents a summary, and asks whether to skip re-investigation (default: skip; pipeline/overnight contexts apply the skip automatically). Choose N at the prompt to re-investigate from scratch.
