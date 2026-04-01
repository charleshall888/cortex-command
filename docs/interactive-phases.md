[← Back to Agentic Layer](agentic-layer.md)

# Interactive Phases Guide

**For:** Users running their first `/lifecycle` or `/refine` — or anyone wanting to understand how interactive phases work.  **Assumes:** Basic familiarity with Claude Code skills.

When you invoke `/lifecycle`, `/refine`, `/discovery`, or `/interview`, the agent pauses to ask questions and produce artifacts. This guide explains what each interactive phase produces, what questions to expect, and how the artifacts flow between skills. Read this before your first `/refine` or `/lifecycle` run to avoid surprises.

---

## Artifact Flow Overview

The skills form a pipeline. Each skill produces artifacts that the next skill consumes:

```
/discovery
    |
    v
backlog tickets (backlog/NNN-slug.md)
    |
    v  (/refine or /lifecycle picks up discovery artifacts automatically)
/refine  (Clarify → Research → Spec)
         -->  lifecycle/{slug}/research.md
         -->  lifecycle/{slug}/spec.md
    |
    v
/lifecycle (plan phase)
    |
    v
lifecycle/{slug}/plan.md
    |
    v
Implement (commits to git)
    |
    v
lifecycle/{slug}/review.md  (complex tier / high / critical criticality only)
```

You do not need to run all four skills — `/lifecycle` on a fresh feature covers the full journey. The other skills exist for partial workflows: `/discovery` when you have a vague idea, `/refine` when you want to prepare a backlog item before overnight execution, and `/interview` when you have a plan but want gap analysis before building.

---

## /lifecycle — Full Feature Lifecycle

`/lifecycle <feature>` drives a feature from idea to merged code. The early phases (Clarify, Research, Specify) are delegated to `/refine` internally; the later phases (Plan, Implement, Review, Complete) run directly in the lifecycle context.

### Phase Sequence

| Phase | What happens | Artifact produced | Interactive? |
|-------|-------------|-------------------|-------------|
| Clarify | Agent asks intent, complexity, and criticality | none (output captured internally) | Yes — up to 5 questions |
| Research | Agent reads codebase, dependencies, and requirements | `lifecycle/{feature}/research.md` | Minimal — complexity escalation prompt only |
| Specify | Structured requirements interview covering problem statement, requirements, non-requirements, edge cases, technical constraints | `lifecycle/{feature}/spec.md` | Yes — spec approval required |
| Plan | Agent produces a task breakdown; orchestrator reviews before approval | `lifecycle/{feature}/plan.md` | Yes — plan approval required |
| Implement | Agent executes tasks as commits | Source code + commits | Optional — user can monitor or leave it running |
| Review | Multi-agent verdict (complex tier or forced by criticality) | `lifecycle/{feature}/review.md` | No — automated; results presented for acceptance |
| Complete | events.log closure, backlog item closed | events.log update | No |

### What to Expect in Each Phase

**Clarify** — The agent asks focused questions: What problem does this solve? Who benefits? Any specific requirements? What is the scope? Expect at most 5 questions. Answer these directly; this is not the deep requirements interview — that happens in Specify.

**Research** — Mostly automated. The agent reads relevant files and may surface an escalation prompt: "This looks more complex than anticipated — escalate to Complex tier?" Answer yes or no. If it looks straightforward, say no. Complexity can also be escalated manually at any time.

**Specify** — The agent conducts a structured requirements interview covering:
- Problem statement (one paragraph)
- Requirements with acceptance criteria
- Non-requirements (explicit exclusions)
- Edge cases and expected behavior
- Technical constraints from research

The agent presents a draft spec and asks for approval. Review it carefully — once approved, the spec drives planning. Request changes if anything is wrong or missing; the agent will revise and re-present.

**Plan** — Automated task breakdown followed by an orchestrator review. The plan is presented for your approval before implementation begins. This is your last chance to adjust scope before code is written.

**Implement** — The agent works through the plan tasks. Each task produces one or more commits. You can monitor progress or leave the session running. If the feature is complex or high-criticality, a review phase follows.

**Review** — For complex tier features or high/critical criticality, a multi-agent review runs automatically after implementation. The verdict (APPROVE, CHANGES_REQUESTED, or REJECTED) is presented. CHANGES_REQUESTED sends the feature back to implement for rework.

### Resuming a Lifecycle

`/lifecycle <feature>` can be run at any time. The skill detects the current phase by checking which artifacts exist in `lifecycle/{feature}/`:

- No directory → starts at Clarify
- `research.md` exists, no `spec.md` → resumes at Specify
- `spec.md` exists, no `plan.md` → starts at Plan
- `plan.md` exists with unchecked tasks → resumes at Implement
- All tasks checked, no `review.md` → starts Review (if applicable) or Complete

### Complexity and Criticality

Two parameters govern the lifecycle:

- **Complexity tier** (`simple` | `complex`) — set during Clarify, affects whether Review runs and how planning proceeds. Simple features skip the Review phase. Complex features include it and may use the critical-review skill on the spec.
- **Criticality** (`low` | `medium` | `high` | `critical`) — set during Clarify, affects model selection and forces Review for high/critical regardless of tier.

Both can be overridden at any point by asking the agent to change them.

---

## /refine — Clarify → Research → Spec in One Invocation

`/refine <item>` prepares a single backlog item for overnight autonomous execution. It runs exactly the same Clarify, Research, and Specify phases as `/lifecycle`, but stops before planning. When `/refine` completes, the backlog item has `status: refined` and a linked spec — the overnight runner can plan and execute it without further human input.

### When to Use /refine

Use `/refine` when:
- You want to prepare a backlog item for the overnight runner
- You want to review and approve the spec before the agent plans autonomously
- You want to run Clarify and Research interactively on your schedule (morning) and defer planning to overnight

### Phase Sequence

| Phase | What happens | Artifact produced | Interactive? |
|-------|-------------|-------------------|-------------|
| Clarify | Same as lifecycle Clarify | Complexity + criticality written to backlog item | Yes — up to 5 questions |
| Research | Same as lifecycle Research | `lifecycle/{slug}/research.md` | Minimal |
| Spec | Same as lifecycle Specify | `lifecycle/{slug}/spec.md` | Yes — spec approval required |

After spec approval, `/refine` writes `status: refined` and `spec:` to the backlog item's YAML frontmatter. The next `/overnight` or `/lifecycle` run picks up these artifacts automatically and skips to planning.

### State Resumption

`/refine` resumes at the appropriate point:
- If `spec.md` already exists: offers to re-run (re-running resets `status` to `in_progress` until the new spec is approved)
- If `research.md` exists but not `spec.md`: resumes at Spec (applies a sufficiency check to verify the existing research covers the clarified intent)
- Otherwise: starts at Clarify

---

## /discovery — Research → Backlog Tickets → Epic Grouping

`/discovery <topic>` is for topics that are not yet concrete enough for `/lifecycle`. It researches the problem space broadly, then decomposes findings into backlog tickets grouped by epic. Unlike `/lifecycle`, discovery does not produce a plan or write code.

### Phase Sequence

| Phase | What happens | Artifact produced | Interactive? |
|-------|-------------|-------------------|-------------|
| Clarify | Agent asks about scope and research focus | none (conversation output) | Yes — scoping questions |
| Research | Deep codebase and requirements exploration | `research/{topic}/research.md` | Minimal |
| Decompose | Findings broken into epics and backlog tickets | `backlog/NNN-slug.md` files per ticket | Yes — epic grouping review |

### What to Expect

**Clarify** — The agent asks what you want to understand, what's in scope, and how deep to go. If you run `/discovery` with no argument, it enters auto-scan mode and reads `requirements/` to suggest gap candidates.

**Research** — Automated. The agent reads codebase, requirements, and (if needed) external documentation. The resulting `research/{topic}/research.md` is a durable artifact — it is referenced by the backlog tickets created in Decompose.

**Decompose** — The agent groups findings into epics and creates one backlog ticket per concrete work item. Each ticket gets YAML frontmatter including a `discovery_source:` field pointing to the research artifact. The agent may ask for confirmation on epic groupings before writing tickets.

### Connecting Discovery to Lifecycle

When `/lifecycle` starts on a ticket created by `/discovery`:

1. It detects the `discovery_source:` field in the backlog item frontmatter.
2. It copies the referenced research into `lifecycle/{feature}/research.md`.
3. If a `spec:` field also exists, it copies that too and skips directly to Plan.
4. It announces what was bootstrapped and which phases were skipped.

This means a well-run `/discovery` session can eliminate hours of repeated research for every downstream feature.

---

## /interview — Surface Gaps in Plans

`/interview` interviews you about an existing plan to surface gaps, unstated assumptions, and missing requirements before implementation begins. It is different from the Specify phase inside `/lifecycle` — it works against a plan you have already written rather than producing a new spec from scratch.

### When to Use /interview

Use `/interview` when:
- You have written or imported a plan and want validation before building
- You are about to implement a complex feature and want gap analysis
- You want a structured challenge of your assumptions before committing to the approach

### What to Expect

The agent reads your plan file (from `.claude/plans/` or a path you provide) and asks probing questions across:
- Technical implementation details and approach
- UI/UX decisions (if applicable)
- Edge cases and error handling
- Trade-offs and alternatives considered
- Security and performance implications

Questions are non-obvious — the agent challenges assumptions rather than confirming stated details. Expect "why" and "what if" questions. The session continues until ambiguities are resolved, then the agent writes a refined spec incorporating your answers.

### Output

`/interview` produces a refined spec as conversational output. If you want it persisted, ask the agent to write it to a file. Unlike the other skills, `/interview` does not automatically write artifacts to `lifecycle/` — it is a thinking tool rather than a pipeline stage.

---

## Artifact Flow Diagram

```
/discovery <topic>
    |
    +-- research/{topic}/research.md   (durable research artifact)
    +-- backlog/NNN-slug.md            (one per ticket, discovery_source: field set)
         |
         v  (when /lifecycle or /refine picks up the backlog item)
/refine <item>  -- OR --  /lifecycle <feature>  [early phases]
    |
    +-- lifecycle/{slug}/research.md   (implementation-level research)
    +-- lifecycle/{slug}/spec.md       (approved requirements spec)
         |
         v  (/lifecycle plan phase, or overnight runner)
/lifecycle <feature>  [plan phase]
    |
    +-- lifecycle/{slug}/plan.md       (task breakdown, orchestrator-reviewed)
         |
         v  (/lifecycle implement phase)
Implement
    |
    +-- Source code changes
    +-- Git commits (one per task)
         |
         v  (complex tier or high/critical criticality)
Review
    |
    +-- lifecycle/{slug}/review.md     (multi-agent verdict)
         |
         v
Complete
    |
    +-- events.log closure
    +-- Backlog item closed
    +-- PR created
```

---

## Keeping This Document Current

This document describes the interactive phases as implemented in the skill files under `skills/`. The canonical source of truth for each skill's behavior is its `SKILL.md`:

- `/lifecycle`: `skills/lifecycle/SKILL.md` and `skills/lifecycle/references/`
- `/refine`: `skills/refine/SKILL.md`
- `/discovery`: `skills/discovery/SKILL.md`
- `/interview`: `skills/interview/SKILL.md`

When a skill's phase sequence or artifact output changes, update this guide to match. The artifact flow diagram is the most likely section to drift — verify it against the skill files whenever a skill is substantially revised.
