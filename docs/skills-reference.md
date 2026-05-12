[← Back to README](../README.md)

# Skills Reference

**For:** All users — quick reference to find the right skill for the job.
**Assumes:** Claude Code is set up and the cortex-core plugin is installed.

A grouped inventory of the skills in this repo. Each entry shows what the skill does and links to its full SKILL.md for trigger phrases, inputs, outputs, and implementation details.

See also [Optional Plugins](#optional-plugins) below for UI skills and `pr-review`, which ship as separate plugins in the `cortex-command` marketplace.

> **Note on `pipeline`:** `pipeline` is not a user-facing skill and has no entry in `skills/`. It is an internal Python orchestration module (`cortex_command/pipeline/`, `cortex_command/overnight/`) invoked automatically by `/overnight` to manage multi-feature batch execution. Use `/overnight` to trigger pipeline behavior; do not invoke `pipeline` directly. For internals, see [docs/internals/pipeline.md](internals/pipeline.md).

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
Prepare a backlog item for overnight execution by running it through Clarify → Research → Spec. Produces `cortex/lifecycle/{slug}/research.md` and `cortex/lifecycle/{slug}/spec.md`, then sets `status: refined` on the backlog item so it is eligible for overnight selection.

[skills/refine/SKILL.md](../skills/refine/SKILL.md)

---

### discovery
Ideation research for topics not ready for implementation. Investigates the problem space thoroughly, then decomposes findings into backlog tickets grouped by epic. Stops at backlog tickets rather than proceeding to plan or implement — use lifecycle for that next step.

[skills/discovery/SKILL.md](../skills/discovery/SKILL.md)

---

### research
Parallel research orchestrator for pre-implementation investigation. Dispatches 3–5 agents across independent angles (codebase, web, requirements, tradeoffs, adversarial) and synthesizes findings into a structured `research.md` artifact. Used directly via `/cortex-core:research` or invoked automatically by `/cortex-core:refine` and `/cortex-core:lifecycle`.

[skills/research/SKILL.md](../skills/research/SKILL.md)

---

### backlog
Manage project backlog items as individual markdown files with YAML frontmatter. Supports adding, listing, picking, and archiving items, plus regenerating the index. Invoke with a subcommand (`add`, `list`, `pick`, `ready`, `archive`, `reindex`) or bare to get a menu.

[skills/backlog/SKILL.md](../skills/backlog/SKILL.md)

---

### overnight
Plan and launch autonomous overnight development sessions. Selects eligible features from the backlog, presents a session plan for user approval, and hands off to the runner for unattended execution. Requires features to already have research and spec artifacts produced by `/cortex-core:refine` or `/cortex-core:lifecycle`.

[skills/overnight/SKILL.md](../skills/overnight/SKILL.md)

---

### Choosing between `/cortex-core:dev`, `/cortex-core:lifecycle`, and `/overnight`

These three skills overlap and route to each other — here is when to use each:

- **`/cortex-core:dev`** — general entry point when you are not sure what to do next. It analyzes your request, runs backlog triage if invoked bare, and routes automatically to `/cortex-core:lifecycle`, `/overnight`, `/cortex-core:discovery`, or direct implementation. Start here if you do not already know which workflow you need.
- **`/cortex-core:lifecycle`** — invoke directly when you already know the feature and want to work through it phase by phase (research → spec → plan → implement → review → complete). It is a structured, interactive state machine for a single feature. `/cortex-core:dev` routes non-trivial single features here automatically.
- **`/overnight`** — invoke directly when features already have their research and spec artifacts (produced by `/cortex-core:refine` or `/cortex-core:lifecycle`) and you want autonomous unattended execution. It handles plan approval and hands off to the runner; no interactive research or spec phases occur. `/cortex-core:dev` recommends this when all backlog children are refined.

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

### requirements
Gather and document project-level and feature-area requirements through structured interviews. Creates a `requirements/` directory with a master project doc and area-specific docs. Downstream skills (lifecycle, discovery) consult these automatically during research, spec, and review.

[skills/requirements/SKILL.md](../skills/requirements/SKILL.md)

---

## Optional Plugins

Several skills ship as optional plugins in the `cortex-command` marketplace:

| Plugin | Skills |
|--------|--------|
| `cortex-ui-extras` | `ui-a11y`, `ui-brief`, `ui-check`, `ui-judge`, `ui-lint`, `ui-setup` |
| `cortex-pr-review` | `pr-review` |

Install via Claude Code's plugin system (see [docs/setup.md](setup.md) for the full walkthrough):

```
/plugin install cortex-ui-extras@cortex-command
/plugin install cortex-pr-review@cortex-command
```

Then enable the desired plugin per project in `.claude/settings.json`.

### Project-local: harness-review

`harness-review` is a project-local skill that lives in `.claude/skills/` inside the cortex-command repo. It is specific to cortex-command's overnight runner inventory and is not distributed as a plugin.

---

## Utilities

### diagnose
Systematic 4-phase debugging for skills, hooks, lifecycle, and overnight runner issues. Finds root cause, fixes the underlying problem, and verifies the fix with a structured loop. Use when something is unexpectedly broken or not triggering as expected.

[skills/diagnose/SKILL.md](../skills/diagnose/SKILL.md)

---

## Keeping This Document Current

When a skill is added, removed, or renamed, update this file. When trigger phrases change significantly, update the description.
