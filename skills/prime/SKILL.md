---
name: prime
description: Seed Claude's context with a full project orientation. Run at the start of a session to understand project structure, conventions, current state, and open work.
disable-model-invocation: true
---

# Prime

Gather project context, then report what you found.

## Execute

Run these to understand the current state:

```bash
git ls-files
```

```bash
git log --oneline -5
```

## Read

Load what exists — skip what doesn't:

1. `CLAUDE.md` or `Agents.md` — conventions and instructions
2. `README.md` — project overview
3. `requirements/project.md` — goals, scope, constraints
4. `backlog/index.md` — backlog state
5. Any `lifecycle/` subdirectories — note in-progress features by name

## Report

Summarize in four sections:

**Project**: What is this? What does it do?

**Conventions**: Key rules and patterns Claude should follow while working here.

**Current state**: In-progress lifecycle features and notable backlog items. If no backlog/index.md, scan `backlog/*.md` frontmatter for `status: in_progress` items.

**Ready to help with**: Based on context, what kinds of tasks are likely next?

Keep it concise — this is a briefing, not a document.
