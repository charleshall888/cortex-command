[← Back to README](../README.md)

# Skills Reference

**For:** All users — quick reference to find the right skill for the job.
**Assumes:** Claude Code is set up and skills are symlinked.

A grouped inventory of the skills in this repo. Each entry shows what the skill does and links to its full SKILL.md for trigger phrases, inputs, outputs, and implementation details.

See also [Optional Plugins](#optional-plugins) below for UI skills and `pr-review`, which now live in the separate `cortex-command-plugins` repo.

---

## Development Workflow

### dev
Route development requests to the right workflow. Analyzes a request and delegates to lifecycle, overnight, discovery, or direct implementation. Also runs backlog triage when invoked without arguments so you always know what to work on next.

[skills/dev/SKILL.md](../skills/dev/SKILL.md)

---

### lifecycle
Structured feature development lifecycle with phases for research, specification, planning, implementation, review, and completion. Enforces research-before-code discipline through a file-based state machine that survives context loss and can be resumed across sessions.

[skills/lifecycle/SKILL.md](../skills/lifecycle/SKILL.md)

---

### refine
Prepare a backlog item for overnight execution by running it through Clarify → Research → Spec. Produces `lifecycle/{slug}/research.md` and `lifecycle/{slug}/spec.md`, then sets `status: refined` on the backlog item so it is eligible for overnight selection.

[skills/refine/SKILL.md](../skills/refine/SKILL.md)

---

### discovery
Ideation research for topics not ready for implementation. Investigates the problem space thoroughly, then decomposes findings into backlog tickets grouped by epic. Stops at backlog tickets rather than proceeding to plan or implement — use lifecycle for that next step.

[skills/discovery/SKILL.md](../skills/discovery/SKILL.md)

---

### research
Parallel research orchestrator for pre-implementation investigation. Dispatches 3–5 agents across independent angles (codebase, web, requirements, tradeoffs, adversarial) and synthesizes findings into a structured `research.md` artifact. Used directly via `/research` or invoked automatically by `/refine` and `/lifecycle`.

[skills/research/SKILL.md](../skills/research/SKILL.md)

---

### backlog
Manage project backlog items as individual markdown files with YAML frontmatter. Supports adding, listing, picking, and archiving items, plus regenerating the index. Invoke with a subcommand (`add`, `list`, `pick`, `ready`, `archive`, `reindex`) or bare to get a menu.

[skills/backlog/SKILL.md](../skills/backlog/SKILL.md)

---

### overnight
Plan and launch autonomous overnight development sessions. Selects eligible features from the backlog, presents a session plan for user approval, and hands off to the bash runner for unattended execution. Requires features to already have research and spec artifacts produced by `/refine` or `/lifecycle`.

[skills/overnight/SKILL.md](../skills/overnight/SKILL.md)

---

### Choosing between `/dev`, `/lifecycle`, and `/overnight`

These three skills overlap and route to each other — here is when to use each:

- **`/dev`** — general entry point when you are not sure what to do next. It analyzes your request, runs backlog triage if invoked bare, and routes automatically to `/lifecycle`, `/overnight`, `/discovery`, or direct implementation. Start here if you do not already know which workflow you need.
- **`/lifecycle`** — invoke directly when you already know the feature and want to work through it phase by phase (research → spec → plan → implement → review → complete). It is a structured, interactive state machine for a single feature. `/dev` routes non-trivial single features here automatically.
- **`/overnight`** — invoke directly when features already have their research and spec artifacts (produced by `/refine` or `/lifecycle`) and you want autonomous unattended execution. It handles plan approval and hands off to the bash runner; no interactive research or spec phases occur. `/dev` recommends this when all backlog children are refined.

---

### morning-review
Guide the user through the morning report after an overnight session. Displays the Executive Summary, walks each report section in order, collects answers to deferred questions, advances completed-feature lifecycles to Complete, and auto-closes backlog tickets at the end.

[skills/morning-review/SKILL.md](../skills/morning-review/SKILL.md)

---

## Code Quality

### commit
Create git commits with consistent, well-formatted messages. Stages relevant files, composes an imperative-mood commit message, runs the GPG signing check, and commits — all without pushing. A pre-tool-use hook validates messages before execution.

[skills/commit/SKILL.md](../skills/commit/SKILL.md)

---

### pr
Create GitHub pull requests with well-crafted titles and descriptions. Detects the base branch, pushes the current branch if needed, fills in a PR template if one exists, and creates the PR via `gh pr create`. Outputs the PR URL when done.

[skills/pr/SKILL.md](../skills/pr/SKILL.md)

---

## Thinking Tools

### critical-review
Derives 3-4 challenge angles from the artifact and project context, then dispatches one reviewer agent per angle in parallel for deep, unanchored criticism. An Opus synthesis agent merges the parallel findings into a single coherent challenge. Also auto-triggers in the lifecycle for Complex + medium/high/critical features after plan approval.

[skills/critical-review/SKILL.md](../skills/critical-review/SKILL.md)

---

### devils-advocate
Stress-tests a direction, plan, or approach by arguing against it. Produces a coherent narrative covering the strongest failure mode, unexamined alternatives, a fragile hidden assumption, and a tradeoff blindspot. Works in any phase — no lifecycle required.

[skills/devils-advocate/SKILL.md](../skills/devils-advocate/SKILL.md)

---

### requirements
Gather and document project-level and feature-area requirements through structured interviews. Creates a `requirements/` directory with a master project doc and area-specific docs. Downstream skills (lifecycle, discovery) consult these automatically during research, spec, and review.

[skills/requirements/SKILL.md](../skills/requirements/SKILL.md)

---

## Session Management

### fresh
Capture the current session state as a resume prompt you can paste into a fresh context window. Reads the conversation, identifies ephemeral context not captured in files, and outputs a ready-to-paste prompt. Also runs `/retro` first for human-initiated sessions.

[skills/fresh/SKILL.md](../skills/fresh/SKILL.md)

---

### retro
Write a dated problem-only log for the current session. Captures user corrections, mistakes made, things missed, and wrong approaches — each with its consequence. Does not capture what worked; that discipline keeps retros actionable rather than celebratory.

[skills/retro/SKILL.md](../skills/retro/SKILL.md)

---

### evolve
Identify recurring problems across retro logs and route each trend to the appropriate skill for investigation or resolution. Clusters problems that appear in two or more retros into trends, classifies each with a proposed route (`/discovery`, `/lifecycle`, `/backlog add`, or direct edit), and dispatches only after explicit user approval.

[skills/evolve/SKILL.md](../skills/evolve/SKILL.md)

---

## Optional Plugins

The UI design enforcement skills (`ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup`) and `pr-review` have been extracted into a separate Claude Code plugin marketplace: [cortex-command-plugins](https://github.com/charleshall888/cortex-command-plugins).

Install via Claude Code's plugin system:

```
claude /plugin marketplace add https://github.com/charleshall888/cortex-command-plugins
```

Then enable the desired plugin (e.g. `cortex-ui-extras` for the UI stack, or the `pr-review` plugin). See the `cortex-command-plugins` repo for the authoritative list of plugins and their install commands.

### Project-local: harness-review

`harness-review` is a project-local skill that lives in `.claude/skills/` inside the cortex-command repo. It is specific to cortex-command's overnight runner inventory and is not published as a plugin or symlinked globally.

---

## Utilities

### diagnose
Systematic 4-phase debugging for skills, hooks, lifecycle, and overnight runner issues. Finds root cause, fixes the underlying problem, and verifies the fix with a structured loop. Use when something is unexpectedly broken or not triggering as expected.

[skills/diagnose/SKILL.md](../skills/diagnose/SKILL.md)

---

### skill-creator
Guide for creating effective skills. Covers the full creation process: understanding the skill with concrete examples, planning reusable resources (scripts, references, assets), initializing via `init_skill.py`, writing the SKILL.md, and packaging for distribution. Also useful for updating existing skills.

[skills/skill-creator/SKILL.md](../skills/skill-creator/SKILL.md)

---

## Keeping This Document Current

When a skill is added, removed, or renamed, update this file. When trigger phrases change significantly, update the description.
